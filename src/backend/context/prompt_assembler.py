"""Prompt 组装器 — 把结构化上下文渲染成稳定 prompt。

组装顺序（工程落地版 §七）：
1. System Identity
2. Identity Anchor
3. Creative Brief 主体
4. Dynamic Slots
5. Variant Intent
6. Weak Controls
7. Avoid Global + Avoid Local
"""

from __future__ import annotations

from context.briefs import CreativeBrief, PromptVariant
from context.slot_renderer import SlotPayload

# ---------------------------------------------------------------------------
# Layer 1: System Identity（静态，不含业务实例信息）
# ---------------------------------------------------------------------------

SYSTEM_IDENTITY_PHOTOGRAPHER = (
    "You are a world-class wedding photographer creating images that feel "
    "real, emotional, and timeless. You receive reference photos of real "
    "people — preserve their exact facial identity, body proportions, and "
    "natural skin texture in every shot. Your images should be "
    "indistinguishable from high-end editorial wedding photography."
)

SYSTEM_IDENTITY_RETOUCHER = (
    "You are an elite wedding photo retoucher improving an already-generated "
    "editorial wedding image. Make the smallest necessary change to solve the "
    "detected problems while preserving the couple's exact identity, the "
    "composition, wardrobe, scene design, lighting, and premium photographic realism."
)

COUPLE_BODY_PROPORTION_ANCHOR = (
    "The first reference image is a full-body couple photo. When both people are "
    "visible, preserve the relative height difference and overall build shown there, "
    "while keeping the final composition natural and photographic."
)

# ---------------------------------------------------------------------------
# Layer 3: Identity Anchor（参考图定位文本）
# ---------------------------------------------------------------------------

def _identity_anchor(has_refs: bool, pairing: str, has_couple_refs: bool) -> str:
    if has_refs:
        if pairing == "a bride and groom" and has_couple_refs:
            return (
                "The reference photos show the real bride and groom. "
                "Preserve both partners as recognizable individuals — their "
                "facial features, skin tone, body shape, and overall likeness "
                "must remain faithful. These are identity references, not style references."
            )
        if pairing == "a bride and groom":
            return (
                "The reference photos provide identity guidance for this wedding portrait. "
                "Preserve the visible identity cues as faithfully as possible and keep the "
                "couple believable as two distinct individuals. These are identity references, "
                "not style references."
            )
        return (
            "The reference photos show the real person. Preserve their exact "
            "facial features, skin tone, body shape, and overall likeness. "
            "These are identity references, not style references."
        )

    if pairing == "a bride and groom":
        return (
            "No reference photos provided. Generate a beautiful editorial wedding "
            "portrait of a bride and groom with natural, believable faces. "
            "This is a style sample, not a personalized result."
        )
    return (
        "No reference photos provided. Generate a beautiful editorial wedding "
        "portrait with natural, believable faces. This is a style sample, "
        "not a personalized result."
    )


# ---------------------------------------------------------------------------
# 组装函数
# ---------------------------------------------------------------------------

def assemble_generation_prompt(
    brief: CreativeBrief,
    variant: PromptVariant,
    slots: SlotPayload,
    has_refs: bool = True,
    has_couple_refs: bool = False,
    has_couple_anchor: bool = False,
) -> str:
    """组装最终传给 Nano Banana Pro 的生图 prompt。

    每个 token 都要有信号价值。先身份、再创意、再差异化、最后约束。
    """
    sections: list[str] = []

    # Layer 1: System Identity
    sections.append(SYSTEM_IDENTITY_PHOTOGRAPHER)

    # Layer 3: Identity Anchor
    sections.append(_identity_anchor(has_refs, slots.pairing, has_couple_refs))

    if has_couple_anchor and slots.pairing == "a bride and groom":
        sections.append(COUPLE_BODY_PROPORTION_ANCHOR)

    # Layer 2: Creative Brief 主体
    sections.append(
        f"{brief.story} {brief.visual_essence} "
        f"The feeling: {brief.emotion}. "
        f"Visual style: {brief.aesthetic}."
    )

    if slots.pairing:
        sections.append(f"The subjects are {slots.pairing}.")

    # Layer 4: Dynamic Slots — 空值不渲染
    styling_parts: list[str] = []
    if brief.wardrobe_bride or brief.wardrobe_groom:
        if brief.wardrobe_bride:
            styling_parts.append(f"Her look: {brief.wardrobe_bride}.")
        if brief.wardrobe_groom:
            styling_parts.append(f"His look: {brief.wardrobe_groom}.")

    # 妆造：slots 覆盖 brief 默认值
    makeup = slots.makeup or brief.makeup_default
    if makeup:
        styling_parts.append(f"Makeup: {makeup}.")

    if slots.user_preference:
        styling_parts.append(slots.user_preference + ".")

    if styling_parts:
        sections.append(" ".join(styling_parts))

    # Layer 5: Variant Intent
    variant_text = (
        f"This shot: {variant.intent}. "
        f"Framing: {variant.framing}. "
        f"{variant.action}."
    )
    if variant.emotion_focus:
        variant_text += f" {variant.emotion_focus}."
    sections.append(variant_text)

    # Layer 6: Weak Controls — 只在非默认值时渲染
    controls: list[str] = []
    if brief.lighting_bias:
        controls.append(f"Lighting tendency: {brief.lighting_bias.replace('_', ' ')}.")
    if brief.pose_energy and brief.pose_energy != "natural":
        controls.append(f"Energy: {brief.pose_energy}.")
    if controls:
        sections.append(" ".join(controls))

    # Layer 7: Avoid
    all_avoids = list(brief.avoid_global) + list(variant.avoid_local)
    if all_avoids:
        sections.append("Avoid: " + ", ".join(all_avoids) + ".")

    return "\n\n".join(sections)


def assemble_nano_repair_prompt(
    render_prompt: str,
    repair_hints: list[str],
    *,
    has_identity_refs: bool,
    focus: str = "general",
) -> str:
    """组装交给 Nano Banana 的修复 prompt。"""
    sections: list[str] = [SYSTEM_IDENTITY_RETOUCHER]

    if has_identity_refs:
        sections.append(
            "The first image is the current render that needs repair. Any additional "
            "images are identity anchors only. Keep the people recognizable and treat "
            "the current render as the composition and styling source of truth."
        )
    else:
        sections.append(
            "The input image is the current render that needs repair. Preserve its "
            "composition, styling, lighting, and overall photographic intent."
        )

    if render_prompt:
        sections.append(f"Original creative intent to preserve:\n{render_prompt}")

    focus_instructions = {
        "physical": (
            "Repair anatomy, facial structure, garment edges, object boundaries, and "
            "lighting continuity. Remove artifacts without redesigning the shot."
        ),
        "emotional": (
            "Improve facial expressions, gaze, and emotional warmth. Keep the change "
            "subtle, believable, and premium editorial rather than exaggerated."
        ),
        "general": (
            "Repair the detected flaws while preserving the original photographic look."
        ),
    }
    sections.append(f"Repair focus: {focus_instructions.get(focus, focus_instructions['general'])}")

    if repair_hints:
        sections.append("Required fixes:\n- " + "\n- ".join(repair_hints))

    sections.append(
        "Preserve exactly: facial identity, pose intent, framing, lens feel, wardrobe, "
        "background design, skin texture, and color grade. Do not add new props, do not "
        "change the outfit, and do not turn this into a different photo."
    )

    return "\n\n".join(sections)
