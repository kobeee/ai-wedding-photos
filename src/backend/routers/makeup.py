from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from config import settings
from models.schemas import MakeupRequest, MakeupResponse, Gender, MakeupStyle
from services.nano_banana import nano_banana_service
from utils.storage import (
    read_upload_metadata,
    read_file_bytes,
    save_generated_image,
    user_output_dir,
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


def _reference_signature(ref_image_path: Path | None) -> str:
    if ref_image_path is None or not ref_image_path.exists():
        return "no-reference"

    stat = ref_image_path.stat()
    return f"{ref_image_path.name}:{stat.st_mtime_ns}:{stat.st_size}"


def _makeup_cache_manifest_path(user_id: str, gender: Gender) -> Path:
    return user_output_dir(user_id) / f"makeup-{gender.value}-cache.json"


def _output_url(user_id: str, path: Path) -> str:
    version = 0
    try:
        version = path.stat().st_mtime_ns
    except OSError:
        logger.warning("Failed to read output file timestamp for cache key: %s", path)

    return f"/api/files/outputs/{user_id}/{path.name}?v={version}"


def _load_cached_makeup(
    user_id: str,
    gender: Gender,
    reference_signature: str,
) -> list[str] | None:
    manifest_path = _makeup_cache_manifest_path(user_id, gender)
    if not manifest_path.exists():
        return None

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read makeup cache manifest: %s", manifest_path)
        return None

    if payload.get("reference_signature") != reference_signature:
        return None

    filenames = payload.get("filenames")
    if not isinstance(filenames, list) or len(filenames) != len(ALL_STYLES):
        return None

    base_dir = user_output_dir(user_id).resolve()
    cached_urls: list[str] = []
    for filename in filenames:
        file_path = (base_dir / str(filename)).resolve()
        try:
            file_path.relative_to(base_dir)
        except ValueError:
            return None

        if not file_path.exists() or not file_path.is_file():
            return None

        cached_urls.append(_output_url(user_id, file_path))

    return cached_urls


def _save_cached_makeup(
    user_id: str,
    gender: Gender,
    reference_signature: str,
    image_paths: list[Path],
) -> None:
    manifest_path = _makeup_cache_manifest_path(user_id, gender)
    payload = {
        "reference_signature": reference_signature,
        "filenames": [path.name for path in image_paths],
    }
    try:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("Failed to persist makeup cache manifest: %s", manifest_path)


def _find_user_reference_image(user_id: str, gender: Gender) -> Path | None:
    """优先按性别角色选择参考图，避免误用双人照或另一方照片。"""
    upload_dir = user_upload_dir(user_id)
    preferred_role = "groom" if gender == Gender.male else "bride"
    preferred_slot = "groom_portrait" if gender == Gender.male else "bride_portrait"
    role_candidates: list[tuple[int, Path]] = []
    fallbacks: list[Path] = []

    for ext in ("*.jpg", "*.jpeg", "*.png"):
        files = sorted(upload_dir.glob(ext))
        for image_path in files:
            metadata = read_upload_metadata(image_path)
            validation = metadata.get("validation")
            if isinstance(validation, dict) and validation.get("accepted") is False:
                continue

            role = str(metadata.get("role", "")).strip().lower()
            slot = str(metadata.get("slot", "")).strip().lower()
            fallbacks.append(image_path)
            if role == preferred_role:
                score = 2 if slot == preferred_slot else 1
                role_candidates.append((score, image_path))

    if role_candidates:
        role_candidates.sort(key=lambda item: item[0], reverse=True)
        return role_candidates[0][1]

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

    reference_signature = _reference_signature(ref_image_path)
    cached_urls = _load_cached_makeup(req.user_id, req.gender, reference_signature)
    if cached_urls:
        logger.info("Using cached makeup previews for user=%s gender=%s", req.user_id, req.gender.value)
        return MakeupResponse(user_id=req.user_id, images=cached_urls)

    async def _render_style(style: MakeupStyle) -> Path | None:
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
            return path

        except RuntimeError as exc:
            # API key 未配置
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except Exception:
            logger.exception("Makeup generation failed for style=%s", style.value)
            return None

    result_paths = list(await asyncio.gather(*(_render_style(s) for s in ALL_STYLES)))

    valid_paths = [path for path in result_paths if path is not None]
    if len(valid_paths) != len(ALL_STYLES):
        raise HTTPException(
            status_code=502,
            detail="Makeup preview generation incomplete",
        )

    _save_cached_makeup(req.user_id, req.gender, reference_signature, valid_paths)
    valid_urls = [_output_url(req.user_id, path) for path in valid_paths]
    return MakeupResponse(user_id=req.user_id, images=valid_urls)
