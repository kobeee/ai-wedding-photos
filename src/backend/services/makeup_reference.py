from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from models.schemas import Gender, MakeupStyle
from services.nano_banana import nano_banana_service
from utils.storage import (
    read_file_bytes,
    read_upload_metadata,
    save_generated_image,
    user_output_dir,
    user_upload_dir,
)

logger = logging.getLogger(__name__)

_MAKEUP_PROMPTS: dict[tuple[str, str], str] = {
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
_STYLE_INDEX = {style.value: index for index, style in enumerate(ALL_STYLES)}


@dataclass
class MakeupReference:
    gender: str
    style: str
    path: Path
    url: str

    async def as_inline_ref(self) -> tuple[bytes, str]:
        data = await read_file_bytes(self.path)
        mime = "image/png" if self.path.suffix.lower() == ".png" else "image/jpeg"
        return data, mime


def _normalize_gender(gender: Gender | str) -> Gender:
    if isinstance(gender, Gender):
        return gender
    return Gender(gender)


def _normalize_style(style: MakeupStyle | str | None, *, default: MakeupStyle) -> MakeupStyle:
    if style is None:
        return default
    if isinstance(style, MakeupStyle):
        return style
    return MakeupStyle(style)


def _get_prompt(gender: Gender, style: MakeupStyle) -> str:
    key = (gender.value, style.value)
    fallback_key = ("male", "natural") if gender == Gender.male else ("female", "natural")
    return _MAKEUP_PROMPTS.get(key, _MAKEUP_PROMPTS[fallback_key])


def _mime_type_for_path(path: Path) -> str:
    return "image/png" if path.suffix.lower() == ".png" else "image/jpeg"


def _reference_signature(ref_image_path: Path | None) -> str:
    if ref_image_path is None or not ref_image_path.exists():
        return "no-reference"

    stat = ref_image_path.stat()
    return f"{ref_image_path.name}:{stat.st_mtime_ns}:{stat.st_size}"


def _makeup_cache_manifest_path(user_id: str, gender: Gender) -> Path:
    return user_output_dir(user_id) / f"makeup-{gender.value}-cache.json"


def _single_makeup_manifest_path(user_id: str, gender: Gender, style: MakeupStyle) -> Path:
    return user_output_dir(user_id) / f"makeup-{gender.value}-{style.value}-single.json"


def output_url(user_id: str, path: Path) -> str:
    version = 0
    try:
        version = path.stat().st_mtime_ns
    except OSError:
        logger.warning("Failed to read output file timestamp for cache key: %s", path)

    return f"/api/files/outputs/{user_id}/{path.name}?v={version}"


def resolve_output_reference_path(user_id: str, url: str | None) -> Path | None:
    if not url:
        return None

    parsed = urlparse(url)
    prefix = f"/api/files/outputs/{user_id}/"
    if not parsed.path.startswith(prefix):
        return None

    filename = parsed.path.removeprefix(prefix)
    if not filename:
        return None

    base_dir = user_output_dir(user_id).resolve()
    candidate = (base_dir / filename).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError:
        return None
    return candidate if candidate.exists() and candidate.is_file() else None


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

        cached_urls.append(output_url(user_id, file_path))

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


def _load_single_makeup(
    user_id: str,
    gender: Gender,
    style: MakeupStyle,
    reference_signature: str,
) -> MakeupReference | None:
    manifest_path = _single_makeup_manifest_path(user_id, gender, style)
    if not manifest_path.exists():
        return None

    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Failed to read single makeup manifest: %s", manifest_path)
        return None

    if payload.get("reference_signature") != reference_signature:
        return None

    filename = str(payload.get("filename", "")).strip()
    if not filename:
        return None

    base_dir = user_output_dir(user_id).resolve()
    candidate = (base_dir / filename).resolve()
    try:
        candidate.relative_to(base_dir)
    except ValueError:
        return None

    if not candidate.exists() or not candidate.is_file():
        return None

    return MakeupReference(
        gender=gender.value,
        style=style.value,
        path=candidate,
        url=output_url(user_id, candidate),
    )


def _save_single_makeup(
    user_id: str,
    gender: Gender,
    style: MakeupStyle,
    reference_signature: str,
    path: Path,
) -> None:
    manifest_path = _single_makeup_manifest_path(user_id, gender, style)
    payload = {
        "reference_signature": reference_signature,
        "filename": path.name,
    }
    try:
        manifest_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    except OSError:
        logger.warning("Failed to persist single makeup manifest: %s", manifest_path)


def find_user_reference_image(user_id: str, gender: Gender) -> Path | None:
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


async def generate_makeup_previews(
    user_id: str,
    gender: Gender | str,
) -> list[str]:
    normalized_gender = _normalize_gender(gender)
    ref_image_path = find_user_reference_image(user_id, normalized_gender)
    ref_image_data: bytes | None = None
    ref_mime_type = "image/jpeg"
    if ref_image_path and ref_image_path.exists():
        ref_image_data = await read_file_bytes(ref_image_path)
        ref_mime_type = _mime_type_for_path(ref_image_path)
        logger.info("Using makeup reference image: %s", ref_image_path)

    reference_signature = _reference_signature(ref_image_path)
    cached_urls = _load_cached_makeup(user_id, normalized_gender, reference_signature)
    if cached_urls:
        return cached_urls

    result_paths: list[Path] = []
    for style in ALL_STYLES:
        prompt = _get_prompt(normalized_gender, style)
        if ref_image_data is not None:
            img_bytes = await nano_banana_service.image_to_image(
                prompt=prompt,
                image_data=ref_image_data,
                mime_type=ref_mime_type,
            )
        else:
            img_bytes = await nano_banana_service.text_to_image(prompt=prompt)

        _, path = await save_generated_image(user_id, img_bytes)
        result_paths.append(path)

    _save_cached_makeup(user_id, normalized_gender, reference_signature, result_paths)
    return [output_url(user_id, path) for path in result_paths]


async def generate_single_makeup_reference(
    user_id: str,
    gender: Gender | str,
    style: MakeupStyle | str | None,
) -> MakeupReference | None:
    normalized_gender = _normalize_gender(gender)
    default_style = MakeupStyle.natural if normalized_gender == Gender.male else MakeupStyle.refined
    normalized_style = _normalize_style(style, default=default_style)

    ref_image_path = find_user_reference_image(user_id, normalized_gender)
    ref_image_data: bytes | None = None
    ref_mime_type = "image/jpeg"
    if ref_image_path and ref_image_path.exists():
        ref_image_data = await read_file_bytes(ref_image_path)
        ref_mime_type = _mime_type_for_path(ref_image_path)
        logger.info("Using makeup reference image: %s", ref_image_path)

    reference_signature = _reference_signature(ref_image_path)

    preview_urls = _load_cached_makeup(user_id, normalized_gender, reference_signature)
    if preview_urls:
        style_index = _STYLE_INDEX[normalized_style.value]
        if style_index < len(preview_urls):
            cached_path = resolve_output_reference_path(user_id, preview_urls[style_index])
            if cached_path is not None:
                return MakeupReference(
                    gender=normalized_gender.value,
                    style=normalized_style.value,
                    path=cached_path,
                    url=output_url(user_id, cached_path),
                )

    cached_single = _load_single_makeup(
        user_id,
        normalized_gender,
        normalized_style,
        reference_signature,
    )
    if cached_single is not None:
        return cached_single

    prompt = _get_prompt(normalized_gender, normalized_style)
    if ref_image_data is not None:
        img_bytes = await nano_banana_service.image_to_image(
            prompt=prompt,
            image_data=ref_image_data,
            mime_type=ref_mime_type,
        )
    else:
        img_bytes = await nano_banana_service.text_to_image(prompt=prompt)

    _, path = await save_generated_image(user_id, img_bytes)
    _save_single_makeup(
        user_id,
        normalized_gender,
        normalized_style,
        reference_signature,
        path,
    )
    return MakeupReference(
        gender=normalized_gender.value,
        style=normalized_style.value,
        path=path,
        url=output_url(user_id, path),
    )


async def resolve_selected_makeup_reference(
    user_id: str,
    gender: Gender | str,
    style: MakeupStyle | str | None,
    preferred_url: str | None,
) -> MakeupReference | None:
    normalized_gender = _normalize_gender(gender)
    default_style = MakeupStyle.natural if normalized_gender == Gender.male else MakeupStyle.refined
    normalized_style = _normalize_style(style, default=default_style)

    preferred_path = resolve_output_reference_path(user_id, preferred_url)
    if preferred_path is not None:
        return MakeupReference(
            gender=normalized_gender.value,
            style=normalized_style.value,
            path=preferred_path,
            url=output_url(user_id, preferred_path),
        )

    return await generate_single_makeup_reference(
        user_id,
        normalized_gender,
        normalized_style,
    )
