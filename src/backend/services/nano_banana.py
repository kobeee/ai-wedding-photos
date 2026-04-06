from __future__ import annotations

import asyncio
import base64
import logging
from io import BytesIO

import httpx
from PIL import Image, ImageOps

from config import settings

logger = logging.getLogger(__name__)


class NanoRequestTooLargeError(RuntimeError):
    """上游拒绝请求体积过大的专用错误。"""


class NanoBananaService:
    """
    封装 Nano Banana Pro (Gemini 3 Pro Image) API。
    通过 laozhang.ai 代理调用，支持文生图、图生图、多图参考生成。
    """

    def __init__(self) -> None:
        self.api_url = (
            f"{settings.laozhang_base_url}/v1beta/models/"
            f"{settings.nano_banana_model}:generateContent"
        )

    def _headers(self) -> dict[str, str]:
        return {
            "x-goog-api-key": settings.nano_banana_api_key,
            "Content-Type": "application/json",
        }

    def _check_api_key(self) -> None:
        if not settings.nano_banana_api_key:
            raise RuntimeError(
                "nano banana api key is not configured. "
                "Set LAOZHANG_NANO_API_KEY or LAOZHANG_API_KEY."
            )

    @staticmethod
    def _normalize_size(size: str) -> str:
        raw = str(size or "").strip()
        normalized = raw.upper()

        aliases = {
            "256": "1K",
            "512": "1K",
            "1024": "1K",
            "1K": "1K",
            "2048": "2K",
            "2K": "2K",
            "4096": "4K",
            "4K": "4K",
        }

        resolved = aliases.get(normalized)
        if resolved:
            if normalized != resolved:
                logger.info("Normalized Nano Banana image size '%s' -> '%s'", raw, resolved)
            return resolved

        logger.warning("Unsupported Nano Banana image size '%s', falling back to 1K", raw)
        return "1K"

    def _extract_image_bytes(self, data: dict) -> bytes:
        """从 API 响应中提取图片 bytes。"""
        try:
            parts = data["candidates"][0]["content"]["parts"]
            for part in parts:
                if "inlineData" in part:
                    return base64.b64decode(part["inlineData"]["data"])
                if "inline_data" in part:
                    return base64.b64decode(part["inline_data"]["data"])
        except (KeyError, IndexError) as exc:
            logger.error("Failed to extract image from response: %s", data)
            raise ValueError("API response does not contain image data") from exc
        raise ValueError("No image data found in API response")

    @staticmethod
    def _inline_image_part(image_data: bytes, mime_type: str) -> dict:
        return {
            "inline_data": {
                "mime_type": mime_type,
                "data": base64.b64encode(image_data).decode(),
            }
        }

    @staticmethod
    def _prepare_reference_image(image_data: bytes, mime_type: str) -> tuple[bytes, str]:
        """压缩参考图，避免多图请求过大。"""
        try:
            with Image.open(BytesIO(image_data)) as image:
                image = ImageOps.exif_transpose(image)
                image.load()

                if image.mode in ("RGBA", "LA") or (
                    image.mode == "P" and "transparency" in image.info
                ):
                    base = Image.new("RGB", image.size, (255, 255, 255))
                    alpha = image.convert("RGBA")
                    base.paste(alpha, mask=alpha.getchannel("A"))
                    image = base
                elif image.mode != "RGB":
                    image = image.convert("RGB")

                max_dim = max(settings.nano_reference_max_image_dimension, 768)
                if image.width > max_dim or image.height > max_dim:
                    image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                quality = settings.nano_reference_jpeg_quality
                min_quality = max(
                    min(settings.nano_reference_min_jpeg_quality, quality),
                    35,
                )

                while True:
                    buffer = BytesIO()
                    image.save(
                        buffer,
                        format="JPEG",
                        quality=quality,
                        optimize=True,
                    )
                    prepared = buffer.getvalue()
                    if len(prepared) <= settings.nano_reference_max_bytes:
                        return prepared, "image/jpeg"

                    if quality > min_quality:
                        quality -= 6
                        continue

                    long_edge = max(image.size)
                    if long_edge <= 768:
                        return prepared, "image/jpeg"

                    scaled_long_edge = max(768, int(round(long_edge * 0.85)))
                    scale = scaled_long_edge / max(long_edge, 1)
                    resized_width = max(1, int(round(image.width * scale)))
                    resized_height = max(1, int(round(image.height * scale)))
                    image = image.resize((resized_width, resized_height), Image.Resampling.LANCZOS)
        except Exception:
            logger.warning("Failed to preprocess Nano reference image", exc_info=True)

        return image_data, mime_type

    @staticmethod
    def _prepare_reference_bundle(
        reference_images: list[tuple[bytes, str]],
        *,
        max_images: int,
    ) -> list[tuple[bytes, str]]:
        budget = max(settings.nano_reference_total_max_bytes, settings.nano_reference_max_bytes)
        limit = max(max_images, 0)
        prepared_bundle: list[tuple[bytes, str]] = []
        total_bytes = 0

        for index, (img_data, mime) in enumerate(reference_images):
            if len(prepared_bundle) >= limit:
                logger.info(
                    "Dropped Nano reference #%d because max image count %d was reached",
                    index + 1,
                    limit,
                )
                break

            prepared_image, prepared_mime = NanoBananaService._prepare_reference_image(img_data, mime)
            projected_total = total_bytes + len(prepared_image)
            if prepared_bundle and projected_total > budget:
                logger.info(
                    "Dropped Nano reference #%d to keep payload within budget (%dKB > %dKB)",
                    index + 1,
                    projected_total // 1024,
                    budget // 1024,
                )
                continue

            prepared_bundle.append((prepared_image, prepared_mime))
            total_bytes = projected_total

        logger.info(
            "Prepared %d Nano reference image(s), total=%dKB",
            len(prepared_bundle),
            total_bytes // 1024,
        )
        return prepared_bundle

    @staticmethod
    def _is_request_too_large(status_code: int, response_text: str) -> bool:
        text = (response_text or "").lower()
        keywords = (
            "请求体积过大",
            "request body too large",
            "payload too large",
            "content too large",
        )
        return status_code == 413 or any(keyword in text for keyword in keywords)

    async def _generate_from_parts(
        self,
        parts: list[dict],
        *,
        aspect_ratio: str,
        size: str,
        timeout: int | None = None,
    ) -> bytes:
        resolved_size = self._normalize_size(size or settings.nano_image_size)
        resolved_timeout = timeout or settings.nano_timeout_seconds
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                    "imageSize": resolved_size,
                },
            },
        }

        max_attempts = 3
        async with httpx.AsyncClient(timeout=resolved_timeout) as client:
            for attempt in range(1, max_attempts + 1):
                resp = await client.post(
                    self.api_url, headers=self._headers(), json=payload
                )
                if resp.status_code >= 400:
                    logger.warning(
                        "Nano Banana request failed: status=%s size=%s timeout=%ss parts=%d attempt=%d body=%s",
                        resp.status_code,
                        resolved_size,
                        resolved_timeout,
                        len(parts),
                        attempt,
                        resp.text[:500],
                    )
                if self._is_request_too_large(resp.status_code, resp.text):
                    raise NanoRequestTooLargeError("请求体积过大，请减少参考图或压缩后重试")
                if resp.status_code not in {429, 503} or attempt == max_attempts:
                    resp.raise_for_status()
                    return self._extract_image_bytes(resp.json())

                await asyncio.sleep(min(2 ** (attempt - 1), 4))

        raise RuntimeError("Nano Banana request exhausted retries")

    async def text_to_image(
        self,
        prompt: str,
        aspect_ratio: str = "3:4",
        size: str = settings.nano_image_size,
    ) -> bytes:
        """文生图 - 仅靠文字 prompt 生成图片，返回图片 bytes。"""
        self._check_api_key()
        return await self._generate_from_parts(
            [{"text": prompt}],
            aspect_ratio=aspect_ratio,
            size=size,
        )

    async def image_to_image(
        self,
        prompt: str,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        aspect_ratio: str = "3:4",
        size: str = settings.nano_image_size,
    ) -> bytes:
        """图生图 - 传入原图 bytes 和 prompt，返回生成图片 bytes。"""
        self._check_api_key()
        prepared_bundle = self._prepare_reference_bundle(
            [(image_data, mime_type)],
            max_images=1,
        )
        prepared_image, prepared_mime = prepared_bundle[0]
        return await self._generate_from_parts(
            [self._inline_image_part(prepared_image, prepared_mime), {"text": prompt}],
            aspect_ratio=aspect_ratio,
            size=size,
            timeout=settings.nano_timeout_seconds,
        )

    async def multi_reference_generate(
        self,
        prompt: str,
        reference_images: list[tuple[bytes, str]],
        aspect_ratio: str = "3:4",
        size: str = settings.nano_image_size,
    ) -> bytes:
        """
        多图参考生成 - 最多 14 张参考图。
        reference_images: [(image_bytes, mime_type), ...]
        """
        self._check_api_key()

        if len(reference_images) > 14:
            raise ValueError("Maximum 14 reference images allowed")

        parts: list[dict] = [{"text": prompt}]
        prepared_bundle = self._prepare_reference_bundle(
            reference_images,
            max_images=max(settings.nano_reference_max_images, 1),
        )
        for prepared_image, prepared_mime in prepared_bundle:
            parts.append(self._inline_image_part(prepared_image, prepared_mime))

        return await self._generate_from_parts(
            parts,
            aspect_ratio=aspect_ratio,
            size=size,
            timeout=settings.nano_timeout_seconds,
        )

    async def repair_with_references(
        self,
        prompt: str,
        image_data: bytes,
        reference_images: list[tuple[bytes, str]] | None = None,
        mime_type: str = "image/jpeg",
        aspect_ratio: str = "3:4",
        size: str = settings.nano_image_size,
    ) -> bytes:
        """修复当前成片，并附带额外身份参考图提升稳定性。"""
        self._check_api_key()

        refs = reference_images or []
        if len(refs) > 13:
            raise ValueError("Maximum 13 extra reference images allowed for repair")

        prepared_current_bundle = self._prepare_reference_bundle(
            [(image_data, mime_type)],
            max_images=1,
        )
        parts: list[dict] = [
            self._inline_image_part(*prepared_current_bundle[0]),
            {"text": prompt},
        ]
        prepared_refs = self._prepare_reference_bundle(
            refs,
            max_images=max(settings.nano_reference_max_images - 1, 0),
        )
        for prepared_image, prepared_mime in prepared_refs:
            parts.append(self._inline_image_part(prepared_image, prepared_mime))

        return await self._generate_from_parts(
            parts,
            aspect_ratio=aspect_ratio,
            size=size,
            timeout=settings.nano_timeout_seconds,
        )


nano_banana_service = NanoBananaService()
