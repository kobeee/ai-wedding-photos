from __future__ import annotations

from dataclasses import dataclass, field

from config import settings
from context.briefs import CreativeBrief, PromptVariant
from context.prompt_assembler import (
    assemble_generation_prompt,
    assemble_nano_repair_prompt,
)
from context.reference_selector import ReferenceSet
from context.slot_renderer import SlotPayload
from services.makeup_reference import MakeupReference
from services.nano_banana import nano_banana_service


@dataclass
class PipelineRound:
    key: str
    prompt: str
    image_data: bytes
    reference_count: int
    mode: str


@dataclass
class PipelineResult:
    rounds: list[PipelineRound] = field(default_factory=list)

    @property
    def prompts(self) -> dict[str, str]:
        return {round_result.key: round_result.prompt for round_result in self.rounds}

    @property
    def final_image(self) -> bytes:
        return self.rounds[-1].image_data

    @property
    def review_prompt(self) -> str:
        if not self.rounds:
            return ""
        return self.rounds[-1].prompt


def build_r2_prompt(
    brief: CreativeBrief,
    slots: SlotPayload,
    *,
    gender: str = "couple",
    has_identity_refs: bool = False,
) -> str:
    """V14 标准 R2 收口，只做商业完成度提升，不重做构图。"""
    is_solo = gender in ("female", "male")

    wardrobe_parts: list[str] = []
    if gender in ("couple", "female") and brief.wardrobe_bride:
        wardrobe_parts.append(brief.wardrobe_bride)
    if gender in ("couple", "male") and brief.wardrobe_groom:
        wardrobe_parts.append(brief.wardrobe_groom)

    repair_hints = [
        "Refine ONLY within the existing frame — do NOT change the crop, zoom, or composition",
        "Keep the same people, facial identity, pose relationship, and scene design from the current render",
        "Polish wedding wardrobe realism: fabric weave, draping, seam finish, and premium material detail",
        "Fix hand anatomy and finger separation with natural joints and believable gestures",
        "Improve skin realism, eye clarity, and premium editorial finishing without plastic retouching",
        "Remove visible artifacts or broken edges while keeping the image photographic and commercially deliverable",
    ]
    if wardrobe_parts:
        repair_hints.append(f"Preserve the requested wardrobe direction: {' / '.join(wardrobe_parts)}")
    if is_solo:
        repair_hints.append(
            "Enhance the subject's expression, eye contact, and emotional presence without turning the face into a hard profile"
        )
    else:
        repair_hints.append(
            "Enhance couple interaction and eye-lines — keep the emotional connection readable, with visible eyes and no hard side profiles"
        )
    if gender in ("couple", "female") and slots.bride_makeup:
        repair_hints.append(f"Finalize the bride's beauty styling to match: {slots.bride_makeup}")
    if gender in ("couple", "male") and slots.groom_makeup:
        repair_hints.append(f"Finalize the groom's grooming to match: {slots.groom_makeup}")

    return assemble_nano_repair_prompt(
        render_prompt=(
            f"{brief.story} {brief.visual_essence} "
            f"Wardrobe: {' / '.join(wardrobe_parts)}. "
            f"Makeup: {slots.makeup or brief.makeup_default}."
        ),
        repair_hints=repair_hints,
        has_identity_refs=has_identity_refs,
        focus="physical",
        gender=gender,
    )


def _append_unique_refs(
    target: list[tuple[bytes, str]],
    refs: list[tuple[bytes, str]],
    *,
    limit: int,
) -> None:
    for item in refs:
        if len(target) >= limit:
            return
        if item not in target:
            target.append(item)


def _build_r1_reference_images(
    ref_set: ReferenceSet | None,
    *,
    gender: str,
) -> list[tuple[bytes, str]]:
    if ref_set is None:
        return []

    refs: list[tuple[bytes, str]] = []
    if gender == "couple":
        _append_unique_refs(refs, ref_set.structure_refs, limit=max(settings.nano_reference_max_images, 1))
    _append_unique_refs(
        refs,
        ref_set.identity_refs,
        limit=max(settings.nano_reference_max_images, 1),
    )
    return refs


async def _build_r2_reference_images(
    *,
    ref_set: ReferenceSet | None,
    bride_makeup_ref: MakeupReference | None,
    groom_makeup_ref: MakeupReference | None,
    gender: str,
) -> list[tuple[bytes, str]]:
    refs: list[tuple[bytes, str]] = []
    max_extra_refs = max(settings.nano_reference_max_images - 1, 0)

    if gender in {"couple", "female"} and bride_makeup_ref is not None:
        _append_unique_refs(refs, [await bride_makeup_ref.as_inline_ref()], limit=max_extra_refs)
    if gender in {"couple", "male"} and groom_makeup_ref is not None:
        _append_unique_refs(refs, [await groom_makeup_ref.as_inline_ref()], limit=max_extra_refs)
    if ref_set is not None:
        _append_unique_refs(refs, ref_set.identity_refs, limit=max_extra_refs)
    return refs


async def run_editorial_pipeline(
    *,
    brief: CreativeBrief,
    variant: PromptVariant,
    slots: SlotPayload,
    gender: str,
    ref_set: ReferenceSet | None,
    bride_makeup_ref: MakeupReference | None = None,
    groom_makeup_ref: MakeupReference | None = None,
    track: str = "hero",
) -> PipelineResult:
    result = PipelineResult()
    r1_reference_images = _build_r1_reference_images(ref_set, gender=gender)
    identity_refs = ref_set.identity_refs if ref_set is not None else []

    r1_prompt = assemble_generation_prompt(
        brief=brief,
        variant=variant,
        slots=slots,
        has_refs=bool(r1_reference_images),
        has_couple_refs=bool(identity_refs),
        has_couple_anchor=bool(ref_set and ref_set.structure_refs) and gender == "couple",
        gender=gender,
        identity_priority=bool(identity_refs),
        track="validation" if track == "validation" else "final",
    )
    if r1_reference_images:
        r1_image = await nano_banana_service.multi_reference_generate(
            prompt=r1_prompt,
            reference_images=r1_reference_images,
        )
    else:
        r1_image = await nano_banana_service.text_to_image(prompt=r1_prompt)
    result.rounds.append(
        PipelineRound(
            key="r1",
            prompt=r1_prompt,
            image_data=r1_image,
            reference_count=len(r1_reference_images),
            mode="final_candidate",
        )
    )

    r2_reference_images = await _build_r2_reference_images(
        ref_set=ref_set,
        bride_makeup_ref=bride_makeup_ref,
        groom_makeup_ref=groom_makeup_ref,
        gender=gender,
    )
    r2_prompt = build_r2_prompt(
        brief,
        slots,
        gender=gender,
        has_identity_refs=bool(r2_reference_images),
    )
    if r2_reference_images:
        r2_image = await nano_banana_service.repair_with_references(
            prompt=r2_prompt,
            image_data=r1_image,
            mime_type="image/png",
            reference_images=r2_reference_images,
        )
        r2_reference_count = 1 + len(r2_reference_images)
    else:
        r2_image = await nano_banana_service.image_to_image(
            prompt=r2_prompt,
            image_data=r1_image,
            mime_type="image/png",
        )
        r2_reference_count = 1
    result.rounds.append(
        PipelineRound(
            key="r2",
            prompt=r2_prompt,
            image_data=r2_image,
            reference_count=r2_reference_count,
            mode="final_polish",
        )
    )
    return result
