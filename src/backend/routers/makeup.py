from __future__ import annotations

import asyncio
import logging
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from config import settings
from models.schemas import MakeupRequest, MakeupResponse, Gender, MakeupStyle
from services.nano_banana import nano_banana_service
from utils.storage import (
    save_generated_image,
    read_file_bytes,
    upload_metadata_path,
    user_upload_dir,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["makeup"])

# 妆造 prompt 模板
_MAKEUP_PROMPTS: dict[tuple[str, str], str] = {
    # (gender, style) -> prompt
    ("female", "natural"): (
        "Professional wedding portrait photo of a beautiful bride with natural, elegant makeup. "
        "Light foundation, subtle blush, soft pink lips, natural eye makeup with minimal eyeshadow. "
        "Hair styled in loose waves. Soft, warm studio lighting. Ultra-realistic, 8K quality."
    ),
    ("female", "refined"): (
        "Professional wedding portrait photo of a stunning bride with refined, sophisticated makeup. "
        "Flawless skin with medium coverage foundation, defined brows, smokey eye with champagne shimmer, "
        "mauve lips, contoured cheekbones. Elegant updo hairstyle with jeweled hairpin. "
        "Studio lighting with soft bokeh. Ultra-realistic, 8K quality."
    ),
    ("female", "sculpt"): (
        "Professional wedding portrait photo of a glamorous bride with sculpted, high-fashion makeup. "
        "Full coverage flawless base, dramatic winged eyeliner, false lashes, bold red lips, "
        "highlighted cheekbones, strong contour. Hair in a sleek chignon with veil. "
        "Dramatic studio lighting. Ultra-realistic, 8K quality."
    ),
    ("male", "natural"): (
        "Professional wedding portrait photo of a handsome groom with natural, clean grooming. "
        "Well-groomed skin, natural brows, clean-shaven or neat stubble. "
        "Classic hairstyle, well-fitted suit. Warm studio lighting. Ultra-realistic, 8K quality."
    ),
    ("male", "refined"): (
        "Professional wedding portrait photo of a refined groom with polished grooming. "
        "Matte foundation, well-shaped brows, styled hair with pomade. "
        "Tailored three-piece suit with boutonniere. Elegant studio lighting. Ultra-realistic, 8K quality."
    ),
    ("male", "sculpt"): (
        "Professional wedding portrait photo of a dashing groom with sculpted, editorial grooming. "
        "Contoured jawline, defined brows, textured modern hairstyle. "
        "Designer suit with bold accessories. Dramatic studio lighting. Ultra-realistic, 8K quality."
    ),
}

ALL_STYLES = [MakeupStyle.natural, MakeupStyle.refined, MakeupStyle.sculpt]


def _get_prompt(gender: Gender, style: MakeupStyle) -> str:
    key = (gender.value, style.value)
    return _MAKEUP_PROMPTS.get(key, _MAKEUP_PROMPTS[("female", "natural")])


def _mime_type_for_path(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


def _find_user_reference_image(user_id: str, gender: Gender) -> Path | None:
    """优先按性别角色选择参考图，避免误用双人照或另一方照片。"""
    upload_dir = user_upload_dir(user_id)
    preferred_role = "groom" if gender == Gender.male else "bride"
    fallbacks: list[Path] = []

    for ext in ("*.jpg", "*.jpeg", "*.png"):
        files = sorted(upload_dir.glob(ext))
        for image_path in files:
            meta_path = upload_metadata_path(image_path)
            role = ""
            if meta_path.exists():
                try:
                    payload = json.loads(meta_path.read_text(encoding="utf-8"))
                    role = str(payload.get("role", "")).strip().lower()
                except (OSError, json.JSONDecodeError):
                    logger.warning("Failed to read upload metadata for %s", image_path)
            if role == preferred_role:
                return image_path
            fallbacks.append(image_path)

    return fallbacks[0] if fallbacks else None


@router.post("/api/makeup/generate", response_model=MakeupResponse)
async def generate_makeup(req: MakeupRequest, request: Request):
    """
    AI 试妆 - 生成 3 种不同风格的妆造效果图。
    如果用户已上传照片，会基于上传照片进行图生图；
    否则直接文生图。
    """
    if request.state.user_id != req.user_id:
        raise HTTPException(status_code=403, detail="Session token does not match user_id")

    if not settings.nano_banana_api_key:
        raise HTTPException(
            status_code=503,
            detail="Nano Banana service not configured. Set LAOZHANG_NANO_API_KEY or LAOZHANG_API_KEY.",
        )

    ref_image_path = _find_user_reference_image(req.user_id, req.gender)
    ref_image_data: bytes | None = None
    ref_mime_type = "image/jpeg"
    if ref_image_path and ref_image_path.exists():
        ref_image_data = await read_file_bytes(ref_image_path)
        ref_mime_type = _mime_type_for_path(ref_image_path)
        logger.info("Using reference image: %s", ref_image_path)

    async def _render_style(style: MakeupStyle) -> str:
        prompt = _get_prompt(req.gender, style)

        try:
            if ref_image_data is not None:
                # 图生图：基于用户照片
                img_bytes = await nano_banana_service.image_to_image(
                    prompt=prompt,
                    image_data=ref_image_data,
                    mime_type=ref_mime_type,
                )
            else:
                # 文生图：纯生成
                img_bytes = await nano_banana_service.text_to_image(prompt=prompt)

            _, path = await save_generated_image(req.user_id, img_bytes)
            return f"/api/files/outputs/{req.user_id}/{path.name}"

        except RuntimeError as exc:
            # API key 未配置
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception:
            logger.exception("Makeup generation failed for style=%s", style.value)
            return ""

    result_urls = list(await asyncio.gather(*(_render_style(style) for style in ALL_STYLES)))

    valid_urls = [u for u in result_urls if u]
    if len(valid_urls) != len(ALL_STYLES):
        raise HTTPException(
            status_code=502,
            detail="Makeup preview generation incomplete",
        )

    return MakeupResponse(user_id=req.user_id, images=valid_urls)
