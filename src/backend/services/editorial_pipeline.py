from __future__ import annotations

from dataclasses import dataclass, field

from context.briefs import CreativeBrief, PromptVariant
from context.prompt_assembler import (
    assemble_generation_prompt,
    assemble_identity_fusion_prompt,
    assemble_makeup_finish_prompt,
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
        if "r3" in self.prompts:
            return self.prompts["r3"]
        return self.rounds[-1].prompt


def build_r2_prompt(brief: CreativeBrief, slots: SlotPayload, *, gender: str = "couple") -> str:
    """标准 R2 细修，固定职责：服饰/手部/皮肤/眼神，不改构图。"""
    is_solo = gender in ("female", "male")

    wardrobe_parts: list[str] = []
    if gender in ("couple", "female") and brief.wardrobe_bride:
        wardrobe_parts.append(brief.wardrobe_bride)
    if gender in ("couple", "male") and brief.wardrobe_groom:
        wardrobe_parts.append(brief.wardrobe_groom)

    repair_hints = [
        "Refine ONLY within the existing frame — do NOT change the crop, zoom, or composition",
        "Improve wardrobe texture: fabric weave, draping, stitching detail",
        "Fix hand anatomy — all fingers clearly defined with natural joints",
        "Add realistic skin texture: visible pores, natural imperfections",
    ]
    if is_solo:
        repair_hints.append(
            "Enhance the subject's expression, eye contact, and emotional presence without turning the face into a hard profile"
        )
    else:
        repair_hints.append(
            "Enhance couple interaction and eye-lines — keep the emotional connection readable, with visible eyes and no hard side profiles"
        )

    return assemble_nano_repair_prompt(
        render_prompt=(
            f"{brief.story} {brief.visual_essence} "
            f"Wardrobe: {' / '.join(wardrobe_parts)}. "
            f"Makeup: {slots.makeup or brief.makeup_default}."
        ),
        repair_hints=repair_hints,
        has_identity_refs=False,
        focus="physical",
        gender=gender,
    )


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
    structure_refs = ref_set.structure_refs if ref_set is not None else []
    identity_refs = ref_set.identity_refs if ref_set is not None else []

    r1_prompt = assemble_generation_prompt(
        brief=brief,
        variant=variant,
        slots=slots,
        has_refs=False,
        has_couple_refs=False,
        has_couple_anchor=bool(structure_refs) and gender == "couple",
        gender=gender,
        identity_priority=bool(identity_refs),
        track=track,
    )
    if structure_refs:
        r1_image = await nano_banana_service.multi_reference_generate(
            prompt=r1_prompt,
            reference_images=structure_refs,
        )
    else:
        r1_image = await nano_banana_service.text_to_image(prompt=r1_prompt)
    result.rounds.append(
        PipelineRound(
            key="r1",
            prompt=r1_prompt,
            image_data=r1_image,
            reference_count=len(structure_refs),
            mode="scene_generation",
        )
    )

    r2_prompt = build_r2_prompt(brief, slots, gender=gender)
    r2_image = await nano_banana_service.image_to_image(
        prompt=r2_prompt,
        image_data=r1_image,
        mime_type="image/png",
    )
    result.rounds.append(
        PipelineRound(
            key="r2",
            prompt=r2_prompt,
            image_data=r2_image,
            reference_count=1,
            mode="detail_refine",
        )
    )

    if identity_refs:
        r3_prompt = assemble_identity_fusion_prompt(
            brief=brief,
            variant=variant,
            gender=gender,
            identity_priority=True,
        )
        r3_refs = [(r2_image, "image/png")] + identity_refs
        r3_image = await nano_banana_service.multi_reference_generate(
            prompt=r3_prompt,
            reference_images=r3_refs,
        )
        result.rounds.append(
            PipelineRound(
                key="r3",
                prompt=r3_prompt,
                image_data=r3_image,
                reference_count=len(r3_refs),
                mode="identity_fusion",
            )
        )
    else:
        r3_image = r2_image

    r4_reference_images: list[tuple[bytes, str]] = []
    has_bride_reference = False
    has_groom_reference = False
    if bride_makeup_ref is not None:
        r4_reference_images.append(await bride_makeup_ref.as_inline_ref())
        has_bride_reference = True
    if groom_makeup_ref is not None:
        r4_reference_images.append(await groom_makeup_ref.as_inline_ref())
        has_groom_reference = True
    r4_reference_images.extend(identity_refs[:2])

    r4_prompt = assemble_makeup_finish_prompt(
        render_prompt=result.review_prompt or r2_prompt,
        gender=gender,
        bride_makeup=slots.bride_makeup,
        groom_makeup=slots.groom_makeup,
        has_bride_reference=has_bride_reference,
        has_groom_reference=has_groom_reference,
        has_identity_refs=bool(identity_refs),
    )

    if r4_reference_images:
        r4_image = await nano_banana_service.repair_with_references(
            prompt=r4_prompt,
            image_data=r3_image,
            mime_type="image/png",
            reference_images=r4_reference_images,
        )
        r4_ref_count = 1 + len(r4_reference_images)
    else:
        r4_image = await nano_banana_service.image_to_image(
            prompt=r4_prompt,
            image_data=r3_image,
            mime_type="image/png",
        )
        r4_ref_count = 1

    result.rounds.append(
        PipelineRound(
            key="r4",
            prompt=r4_prompt,
            image_data=r4_image,
            reference_count=r4_ref_count,
            mode="makeup_finish",
        )
    )
    return result
