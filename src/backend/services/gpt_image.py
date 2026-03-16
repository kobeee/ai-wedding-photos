from __future__ import annotations

import base64
import logging
from pathlib import Path

import httpx

from config import settings

logger = logging.getLogger(__name__)


class GPTImageService:
    """
    封装 GPT Image 1 API（通过 laozhang.ai 代理）。
    支持文生图和遮罩式局部重绘。
    """

    def __init__(self) -> None:
        self.api_url = f"{settings.laozhang_base_url}/v1/images/generations"
        self.edit_url = f"{settings.laozhang_base_url}/v1/images/edits"
        self.headers = {
            "Authorization": f"Bearer {settings.laozhang_api_key}",
        }

    def _check_api_key(self) -> None:
        if not settings.laozhang_api_key:
            raise RuntimeError(
                "laozhang_api_key is not configured. "
                "Set LAOZHANG_API_KEY in .env or environment variables."
            )

    async def generate(
        self,
        prompt: str,
        size: str = "auto",
        quality: str = "auto",
        n: int = 1,
        output_format: str = "png",
    ) -> list[str]:
        """
        文生图，返回图片 URL 列表。
        size: "auto" | "1024x1024" | "1024x1536" | "1536x1024"
        quality: "auto" | "low" | "medium" | "high"
        """
        self._check_api_key()

        payload = {
            "model": settings.gpt_image_model,
            "prompt": prompt,
            "n": n,
            "size": size,
            "quality": quality,
            "output_format": output_format,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.api_url,
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["url"] for item in data.get("data", [])]

    async def generate_b64(
        self,
        prompt: str,
        size: str = "auto",
        quality: str = "auto",
    ) -> bytes:
        """文生图，直接返回图片 bytes（通过 b64_json 格式）。"""
        self._check_api_key()

        payload = {
            "model": settings.gpt_image_model,
            "prompt": prompt,
            "n": 1,
            "size": size,
            "quality": quality,
            "response_format": "b64_json",
        }

        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(
                self.api_url,
                headers={**self.headers, "Content-Type": "application/json"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            b64_str = data["data"][0]["b64_json"]
            return base64.b64decode(b64_str)

    async def edit(
        self,
        image_path: str | Path,
        prompt: str,
        mask_path: str | Path | None = None,
        size: str = "auto",
    ) -> str:
        """
        图片编辑 / 局部重绘。
        image_path: 原图文件路径
        mask_path: 遮罩图文件路径（可选，透明区域表示需要重绘的部分）
        返回编辑后图片 URL。
        """
        self._check_api_key()

        image_path = Path(image_path)
        files: dict = {
            "image": (image_path.name, open(image_path, "rb"), "image/png"),
            "prompt": (None, prompt),
            "model": (None, settings.gpt_image_model),
            "size": (None, size),
        }

        if mask_path is not None:
            mask_path = Path(mask_path)
            files["mask"] = (
                mask_path.name,
                open(mask_path, "rb"),
                "image/png",
            )

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(
                    self.edit_url,
                    headers=self.headers,
                    files=files,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["url"]
        finally:
            # 确保文件句柄被关闭
            for key, val in files.items():
                if isinstance(val, tuple) and len(val) >= 2 and hasattr(val[1], "close"):
                    val[1].close()


gpt_image_service = GPTImageService()
