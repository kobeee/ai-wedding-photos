from __future__ import annotations

import base64
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)


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

    async def text_to_image(
        self,
        prompt: str,
        aspect_ratio: str = "3:4",
        size: str = "4K",
    ) -> bytes:
        """文生图 - 仅靠文字 prompt 生成图片，返回图片 bytes。"""
        self._check_api_key()

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                    "imageSize": size,
                },
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.api_url, headers=self._headers(), json=payload
            )
            resp.raise_for_status()
            return self._extract_image_bytes(resp.json())

    async def image_to_image(
        self,
        prompt: str,
        image_data: bytes,
        mime_type: str = "image/jpeg",
        aspect_ratio: str = "3:4",
        size: str = "4K",
    ) -> bytes:
        """图生图 - 传入原图 bytes 和 prompt，返回生成图片 bytes。"""
        self._check_api_key()

        b64_image = base64.b64encode(image_data).decode()
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": b64_image,
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                    "imageSize": size,
                },
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.api_url, headers=self._headers(), json=payload
            )
            resp.raise_for_status()
            return self._extract_image_bytes(resp.json())

    async def multi_reference_generate(
        self,
        prompt: str,
        reference_images: list[tuple[bytes, str]],
        aspect_ratio: str = "3:4",
        size: str = "4K",
    ) -> bytes:
        """
        多图参考生成 - 最多 14 张参考图。
        reference_images: [(image_bytes, mime_type), ...]
        """
        self._check_api_key()

        if len(reference_images) > 14:
            raise ValueError("Maximum 14 reference images allowed")

        parts: list[dict] = [{"text": prompt}]
        for img_data, mime in reference_images:
            parts.append(
                {
                    "inline_data": {
                        "mime_type": mime,
                        "data": base64.b64encode(img_data).decode(),
                    }
                }
            )

        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {
                "responseModalities": ["IMAGE"],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                    "imageSize": size,
                },
            },
        }

        async with httpx.AsyncClient(timeout=180) as client:
            resp = await client.post(
                self.api_url, headers=self._headers(), json=payload
            )
            resp.raise_for_status()
            return self._extract_image_bytes(resp.json())


nano_banana_service = NanoBananaService()
