from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException

from config import settings
from models.schemas import MakeupRequest, MakeupResponse, Gender, MakeupStyle
from services.nano_banana import nano_banana_service
from utils.storage import save_generated_image, read_file_bytes, user_upload_dir

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


def _find_user_reference_image(user_id: str) -> Path | None:
    """查找用户上传的第一张照片作为参考图。"""
    upload_dir = user_upload_dir(user_id)
    for ext in ("*.jpg", "*.jpeg", "*.png"):
        files = sorted(upload_dir.glob(ext))
        if files:
            return files[0]
    return None


@router.post("/api/makeup/generate", response_model=MakeupResponse)
async def generate_makeup(req: MakeupRequest):
    """
    AI 试妆 - 生成 3 种不同风格的妆造效果图。
    如果用户已上传照片，会基于上传照片进行图生图；
    否则直接文生图。
    """
    if not settings.laozhang_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set LAOZHANG_API_KEY.",
        )

    ref_image_path = _find_user_reference_image(req.user_id)
    ref_image_data: bytes | None = None
    if ref_image_path and ref_image_path.exists():
        ref_image_data = await read_file_bytes(ref_image_path)
        logger.info("Using reference image: %s", ref_image_path)

    result_urls: list[str] = []

    for style in ALL_STYLES:
        prompt = _get_prompt(req.gender, style)

        try:
            if ref_image_data is not None:
                # 图生图：基于用户照片
                img_bytes = await nano_banana_service.image_to_image(
                    prompt=prompt,
                    image_data=ref_image_data,
                    mime_type="image/jpeg",
                )
            else:
                # 文生图：纯生成
                img_bytes = await nano_banana_service.text_to_image(prompt=prompt)

            file_id, path = await save_generated_image(req.user_id, img_bytes)
            url = f"/api/files/outputs/{req.user_id}/{path.name}"
            result_urls.append(url)

        except RuntimeError as exc:
            # API key 未配置
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception:
            logger.exception("Makeup generation failed for style=%s", style.value)
            result_urls.append("")  # 占位，表示该风格生成失败

    # 过滤掉空 URL
    valid_urls = [u for u in result_urls if u]
    if not valid_urls:
        raise HTTPException(status_code=500, detail="All makeup styles generation failed")

    return MakeupResponse(user_id=req.user_id, images=result_urls)
