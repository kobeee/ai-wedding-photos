"""Prompt 组装器 — 把结构化上下文渲染成稳定 prompt。

组装顺序（工程落地版 §七）：
1. System Identity
2. Identity Anchor
3. Creative Brief 主体
4. Dynamic Slots
5. Variant Intent
6. Weak Controls
7. Avoid Global + Avoid Local

V5 改进（实验验证回灌）：
- 全局 anti-diptych 硬约束
- R2 修复 prompt 铁律：绝不改构图
- 生成语义身份融合模板（R3 专用）
- 性别枚举式身份锁定
"""

from __future__ import annotations

from context.briefs import CreativeBrief, PromptVariant
from context.slot_renderer import SlotPayload


# ---------------------------------------------------------------------------
# 全局硬约束（实验验证，所有生成必带）
# ---------------------------------------------------------------------------

_GLOBAL_HARD_AVOIDS = [
    "diptych", "collage", "split-screen", "multi-panel layout",
    "airbrushed skin", "face slimming or jawline reshaping",
]

# Solo 场景专用硬约束（禁止幻生第二个人）
_SOLO_HARD_AVOIDS = [
    "second person", "partner", "companion figure",
    "opposite-gender wardrobe", "couple interaction",
    "hand-holding with another person",
]

_SOLO_HARD_RULE = (
    "ABSOLUTE RULE: This is a SOLO portrait — exactly ONE person in the frame. "
    "Do NOT introduce a partner, companion, or second figure of any kind."
)

# Solo variant action 中需要清理的双人互动短语
import re as _re

_COUPLE_ACTION_PATTERNS = _re.compile(
    r"(?i)\b("
    r"his arms around her|her arms around him|"
    r"laughing together|standing together|walking together|"
    r"foreheads (gently )?touching|eyes closed together|"
    r"his lips near her|her lips near his|"
    r"they |them |their |together\b"
    r")",
)


def _sanitize_variant_for_solo(text: str, gender: str) -> str:
    """清理 variant action/intent 中的双人互动描述，替换为 solo 对应表达。
    仅作为没有专用 solo_* 字段时的兜底方案。
    """
    role = "bride" if gender == "female" else "groom"
    # 先做具体短语替换（保持语义）
    cleaned = _re.sub(r"(?i)his arms around her from behind", f"the {role} looking over one shoulder", text)
    cleaned = _re.sub(r"(?i)laughing together", f"the {role} laughing naturally", cleaned)
    cleaned = _re.sub(r"(?i)standing together", f"the {role} standing alone", cleaned)
    cleaned = _re.sub(r"(?i)walking together", f"the {role} walking alone", cleaned)
    cleaned = _re.sub(r"(?i)foreheads (gently )?touching", f"a quiet moment of reflection", cleaned)
    cleaned = _re.sub(r"(?i)eyes closed together", f"eyes gently closed", cleaned)
    cleaned = _re.sub(r"(?i)his lips near her temple", f"a serene, contemplative expression", cleaned)
    # 通用清理：移除残留的 they/them/their/together
    cleaned = _COUPLE_ACTION_PATTERNS.sub("", cleaned)
    # 压缩多余空格和标点
    cleaned = _re.sub(r"\s{2,}", " ", cleaned).strip(" ,;")
    if not cleaned or len(cleaned) < 10:
        cleaned = f"A compelling solo portrait of the {role}, natural and emotionally present"
    return cleaned


def _resolve_variant_for_gender(
    variant: "PromptVariant", gender: str,
) -> tuple[str, str, str]:
    """根据 gender 返回 (intent, action, emotion_focus)。
    优先使用专用 solo_* 字段，无专用字段时走 sanitize 兜底。
    """
    if gender == "female":
        intent = variant.solo_bride_intent or _sanitize_variant_for_solo(variant.intent, gender)
        action = variant.solo_bride_action or _sanitize_variant_for_solo(variant.action, gender)
        emotion = variant.solo_bride_emotion or (
            _sanitize_variant_for_solo(variant.emotion_focus, gender) if variant.emotion_focus else ""
        )
        return intent, action, emotion
    if gender == "male":
        intent = variant.solo_groom_intent or _sanitize_variant_for_solo(variant.intent, gender)
        action = variant.solo_groom_action or _sanitize_variant_for_solo(variant.action, gender)
        emotion = variant.solo_groom_emotion or (
            _sanitize_variant_for_solo(variant.emotion_focus, gender) if variant.emotion_focus else ""
        )
        return intent, action, emotion
    # couple — 原样返回
    return variant.intent, variant.action, variant.emotion_focus


def _solo_story_adapt(story: str, visual_essence: str, gender: str) -> tuple[str, str]:
    """将 couple 叙事自然适配为 solo 叙事。处理代词替换和动词一致性。"""
    role = "bride" if gender == "female" else "groom"
    pronoun = "she" if gender == "female" else "he"
    pronoun_cap = pronoun.capitalize()
    obj = "her" if gender == "female" else "him"

    def _adapt(text: str) -> str:
        if not text:
            return text
        t = text
        # 短语级替换（避免碎片化语法问题）
        t = _re.sub(r"(?i)\bThe last two people\b", f"The {role}, alone", t)
        t = _re.sub(r"(?i)\btwo people\b", f"the {role}", t)
        t = _re.sub(r"(?i)\btwo lives\b", "a life", t)
        t = _re.sub(r"(?i)\btwo souls\b", "a soul", t)
        # 短语级替换（常见 couple 叙事转 solo）
        t = _re.sub(r"(?i)\bthey are not tourists\b", f"{pronoun} is not a tourist", t)
        t = _re.sub(r"(?i)\bthey are the reason\b", f"{pronoun} is the reason", t)
        # 所有格：their own → her/his own
        t = _re.sub(r"(?i)\btheir own\b", f"{'her' if gender == 'female' else 'his'} own", t)
        t = _re.sub(r"(?i)\btheir\b", f"{'her' if gender == 'female' else 'his'}", t)
        # 动词一致性：they + verb → pronoun + verb+s
        t = _re.sub(r"(?i)\bthey remain\b", f"{pronoun} remains", t)
        t = _re.sub(r"(?i)\bthey are\b", f"{pronoun} is", t)
        t = _re.sub(r"(?i)\bthey don't\b", f"{pronoun} doesn't", t)
        t = _re.sub(r"(?i)\bthey do not\b", f"{pronoun} does not", t)
        t = _re.sub(r"(?i)\bthey have\b", f"{pronoun} has", t)
        t = _re.sub(r"(?i)\bthey were\b", f"{pronoun} was", t)
        # 通用代词替换（放在动词替换之后）
        t = _re.sub(r"\bThey\b", pronoun_cap, t)
        t = _re.sub(r"\bthey\b", pronoun, t)
        t = _re.sub(r"\bthem\b", obj, t)
        # couple → solo
        t = _re.sub(r"(?i)\bA couple\b", f"The {role}", t)
        t = _re.sub(r"(?i)\bThe couple\b", f"The {role}", t)
        t = _re.sub(r"(?i)\bthe couple\b", f"the {role}", t)
        # gender-specific
        if gender == "male":
            t = _re.sub(r"(?i)\bShe is the only warmth\b", "He is the only warmth", t)
        return t

    def _fix_caps(text: str) -> str:
        """修复句首代词大写。"""
        return _re.sub(r'(?<=\.\s)(he|she)\b', lambda m: m.group().capitalize(), text)

    return _fix_caps(_adapt(story)), _fix_caps(_adapt(visual_essence))

# ---------------------------------------------------------------------------
# R2 铁律（绝不改构图，实验 V3→V4 血泪教训）
# ---------------------------------------------------------------------------

R2_COMPOSITION_LOCK = (
    "ABSOLUTE RULE: Do NOT recompose, reframe, zoom in, zoom out, crop tighter, "
    "or change the camera angle, lens feel, or framing in any way. "
    "This is a detail refinement pass — composition is locked."
)

# ---------------------------------------------------------------------------
# 生成语义身份融合模板（R3 专用，实验 V4 验证最优）
# ---------------------------------------------------------------------------

R3_IDENTITY_FUSION_TEMPLATE = """You are a world-class wedding photographer creating the final editorial image.

Generate a new image that combines the SCENE COMPOSITION from the first reference image and the FACIAL IDENTITY from the remaining reference images.

The first reference image provides the exact scene composition, camera angle, lighting, wardrobe, pose, and background. Reproduce this scene faithfully.

The remaining reference images show the real {subject_type}. Their facial identity MUST appear in the final image:
- Identical eye shape, nose bridge contour, jawline angle, lip proportions, skin tone
- Natural hair texture and style consistent with the references
- Body proportions and build faithful to the reference photos

{brief_context}

{variant_context}

{identity_locks}

CRITICAL RULES:
- The scene comes from image 1. The faces come from the remaining images.
- Do NOT average or blend faces. Each person must look exactly like their reference.
- Preserve the exact lighting, color grade, and photographic quality of the scene.
- This must look like a real high-end editorial wedding photograph, not AI-generated.
- OUTPUT FORMAT: Generate exactly ONE single photograph.

{avoid_context}"""

# ---------------------------------------------------------------------------
# Layer 1: System Identity（静态，不含业务实例信息）
# ---------------------------------------------------------------------------

SYSTEM_IDENTITY_PHOTOGRAPHER = (
    "You are a world-class wedding photographer creating images that feel "
    "real, emotional, and timeless. When reference photos are provided, "
    "preserve their exact facial identity, body proportions, and "
    "natural skin texture in every shot. Your images should be "
    "indistinguishable from high-end editorial wedding photography."
)

_SYSTEM_IDENTITY_RETOUCHER_COUPLE = (
    "You are an elite wedding photo retoucher improving an already-generated "
    "editorial wedding image. Make the smallest necessary change to solve the "
    "detected problems while preserving the couple's exact identity, the "
    "composition, wardrobe, scene design, lighting, and premium photographic realism."
)

_SYSTEM_IDENTITY_RETOUCHER_SOLO = (
    "You are an elite wedding photo retoucher improving an already-generated "
    "editorial wedding portrait. Make the smallest necessary change to solve the "
    "detected problems while preserving the person's exact identity, the "
    "composition, wardrobe, scene design, lighting, and premium photographic realism."
)


def _retoucher_identity(gender: str) -> str:
    if gender == "couple":
        return _SYSTEM_IDENTITY_RETOUCHER_COUPLE
    return _SYSTEM_IDENTITY_RETOUCHER_SOLO

COUPLE_BODY_PROPORTION_ANCHOR = (
    "The first reference image is a full-body couple photo. When both people are "
    "visible, preserve the relative height difference and overall build shown there, "
    "while keeping the final composition natural and photographic."
)

# ---------------------------------------------------------------------------
# 性别枚举式身份锁定（实验���证："preserve identity" 无效，必须具体枚举）
# ---------------------------------------------------------------------------

def _identity_lock_by_gender(gender: str) -> str:
    """根据性别生成具体的面部特征锁定描述。

    经验：泛泛说"preserve identity"对模型无效，
    必须按性别枚举具体面部特征维度，模型才能真正锁定。
    """
    if gender == "couple":
        return (
            "IDENTITY LOCKS (non-negotiable):\n"
            "BRIDE: Preserve exact face shape (round/oval/heart), eye shape and lid structure, "
            "nose bridge width and tip shape, lip fullness and bow shape, cheekbone placement, "
            "natural skin tone (no lightening), hair length and texture as shown in references.\n"
            "GROOM: Preserve exact jawline angle and definition, facial hair pattern and density, "
            "eye depth and brow bone structure, nose profile, forehead proportion, "
            "natural skin tone, hair style and length as shown in references.\n"
            "Both: Skin must show real texture — pores, subtle warmth variation, not airbrushed."
        )
    if gender == "female":
        return (
            "IDENTITY LOCKS (non-negotiable):\n"
            "Preserve exact face shape, eye shape and lid structure, "
            "nose bridge width and tip shape, lip fullness and bow shape, "
            "cheekbone placement, natural skin tone (no lightening), "
            "hair length and texture as shown in references.\n"
            "Skin must show real texture — pores, subtle warmth variation, not airbrushed."
        )
    # male
    return (
        "IDENTITY LOCKS (non-negotiable):\n"
        "Preserve exact jawline angle and definition, facial hair pattern and density, "
        "eye depth and brow bone structure, nose profile, forehead proportion, "
        "natural skin tone, hair style and length as shown in references.\n"
        "Skin must show real texture — pores, subtle warmth variation, not airbrushed."
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

    # 无参考图 — 风格样片模式，但仍需面部真实性锚点
    _FACE_REALISM_BRIDE = (
        "Generate natural, photorealistic facial features: "
        "visible skin pores, subtle under-eye texture, natural lip contour, "
        "soft cheekbone highlight, real eyelash weight, unretouched skin warmth."
    )
    _FACE_REALISM_GROOM = (
        "Generate natural, photorealistic facial features: "
        "visible skin pores, natural jawline definition, real brow bone structure, "
        "subtle stubble or clean-shaven texture, unretouched skin warmth."
    )
    if pairing == "a bride and groom":
        return (
            "No reference photos provided — this is a style sample, not a personalized result. "
            "Generate a beautiful editorial wedding portrait of a bride and groom with "
            "believable, distinct faces. "
            f"Her: {_FACE_REALISM_BRIDE} Him: {_FACE_REALISM_GROOM}"
        )
    if pairing == "a bride":
        return (
            "No reference photos provided — this is a style sample. "
            "Generate a beautiful editorial wedding portrait with a "
            f"believable, natural face. {_FACE_REALISM_BRIDE}"
        )
    return (
        "No reference photos provided — this is a style sample. "
        "Generate a beautiful editorial wedding portrait with a "
        f"believable, natural face. {_FACE_REALISM_GROOM}"
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
    gender: str = "couple",
) -> str:
    """组装最终传给 Nano Banana Pro 的生图 prompt。

    每个 token 都要有信号价值。先身份、再创意、再差异化、最后约束。
    gender 参数控制 wardrobe/subject/variant 的渲染范围。
    """
    is_solo = gender in ("female", "male")
    sections: list[str] = []

    # Layer 1: System Identity
    sections.append(SYSTEM_IDENTITY_PHOTOGRAPHER)

    # Solo 硬约束（越早越好，优先级最高）
    if is_solo:
        sections.append(_SOLO_HARD_RULE)

    # Layer 2: Identity Anchor
    sections.append(_identity_anchor(has_refs, slots.pairing, has_couple_refs))

    if has_couple_anchor and not is_solo:
        sections.append(COUPLE_BODY_PROPORTION_ANCHOR)

    # Layer 3: Creative Brief — 叙事+视觉+情绪+风格，连贯融合为一段
    story = brief.story
    visual_essence = brief.visual_essence
    if is_solo:
        story, visual_essence = _solo_story_adapt(story, visual_essence, gender)

    role_label = {"couple": "a bride and groom", "female": "the bride", "male": "the groom"}.get(gender, "a bride and groom")
    brief_narrative = (
        f"{story} {visual_essence} "
        f"The subject{'s are' if gender == 'couple' else ' is'} {role_label}. "
        f"The feeling: {brief.emotion}. Visual style: {brief.aesthetic}."
    )
    sections.append(brief_narrative)

    # Layer 4: Styling — wardrobe + makeup 合为一段，减少碎片感
    styling_parts: list[str] = []
    if gender == "couple":
        if brief.wardrobe_bride:
            styling_parts.append(f"Her look: {brief.wardrobe_bride}")
        if brief.wardrobe_groom:
            styling_parts.append(f"His look: {brief.wardrobe_groom}")
    elif gender == "female":
        if brief.wardrobe_bride:
            styling_parts.append(f"Her look: {brief.wardrobe_bride}")
    elif gender == "male":
        if brief.wardrobe_groom:
            styling_parts.append(f"His look: {brief.wardrobe_groom}")

    makeup = slots.makeup or brief.makeup_default
    if makeup:
        styling_parts.append(f"Makeup: {makeup}")

    if slots.user_preference:
        styling_parts.append(slots.user_preference)

    if styling_parts:
        sections.append(". ".join(styling_parts) + ".")

    # Layer 5: Variant — 用专用 solo 字段（优先）或 sanitize 兜底
    v_intent, v_action, v_emotion = _resolve_variant_for_gender(variant, gender)
    variant_text = (
        f"This shot: {v_intent}. "
        f"Framing: {variant.framing}. "
        f"{v_action}."
    )
    if v_emotion:
        variant_text += f" {v_emotion}."
    sections.append(variant_text)

    # Layer 6: Weak Controls — 只在非默认值时渲染
    controls: list[str] = []
    if brief.lighting_bias:
        controls.append(f"Lighting tendency: {brief.lighting_bias.replace('_', ' ')}.")
    if brief.pose_energy:
        controls.append(f"Energy: {brief.pose_energy}.")
    if controls:
        sections.append(" ".join(controls))

    # Layer 7: Avoid（含全局硬约束 + solo 专用约束）
    all_avoids = list(brief.avoid_global) + list(variant.avoid_local) + _GLOBAL_HARD_AVOIDS
    if is_solo:
        all_avoids += _SOLO_HARD_AVOIDS
    seen: set[str] = set()
    deduped: list[str] = []
    for a in all_avoids:
        lower = a.lower()
        if lower not in seen:
            seen.add(lower)
            deduped.append(a)
    sections.append("Avoid: " + ", ".join(deduped) + ".")

    return "\n\n".join(sections)


def assemble_nano_repair_prompt(
    render_prompt: str,
    repair_hints: list[str],
    *,
    has_identity_refs: bool,
    focus: str = "general",
    gender: str = "couple",
) -> str:
    """组装交给 Nano Banana 的修复 prompt。"""
    is_solo = gender in ("female", "male")
    sections: list[str] = [_retoucher_identity(gender)]

    if is_solo:
        sections.append(_SOLO_HARD_RULE)

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

    # R2 铁律：绝不改构图（V3→V4 实验验证，改构图必崩）
    sections.append(R2_COMPOSITION_LOCK)

    # 全局硬约束 + solo 约束
    r2_avoids = list(_GLOBAL_HARD_AVOIDS)
    if is_solo:
        r2_avoids += _SOLO_HARD_AVOIDS
    sections.append(
        "OUTPUT FORMAT: Generate exactly ONE single photograph. "
        "Avoid: " + ", ".join(r2_avoids) + "."
    )

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# R3 身份融合 prompt 组装（生成语义，实验 V4 验证最优路径）
# ---------------------------------------------------------------------------

def assemble_identity_fusion_prompt(
    brief: CreativeBrief,
    variant: PromptVariant,
    gender: str = "couple",
) -> str:
    """组装 R3 身份融合 prompt。

    核心原则（V4 实验验证）：
    - 用"生成语义"（Generate a new image combining...），不用"修复语义"
    - 第一张参考图 = 构图锚定，后续 = 身份源
    - 按性别枚举面部特征，不用泛泛的 "preserve identity"
    - 强制单图输出，禁止 diptych/collage
    """
    subject_map = {
        "couple": "bride and groom",
        "female": "bride",
        "male": "groom",
    }
    subject_type = subject_map.get(gender, "couple")

    is_solo = gender in ("female", "male")

    story = brief.story
    if is_solo:
        story, _ = _solo_story_adapt(story, "", gender)

    brief_context = (
        f"Scene story: {story}\n"
        f"Visual style: {brief.aesthetic}\n"
        f"Emotion: {brief.emotion}"
    )
    if gender in ("couple", "female") and brief.wardrobe_bride:
        brief_context += f"\nWardrobe — Her: {brief.wardrobe_bride}"
    if gender in ("couple", "male") and brief.wardrobe_groom:
        brief_context += f"\nWardrobe — Him: {brief.wardrobe_groom}"

    v_intent, v_action, v_emotion = _resolve_variant_for_gender(variant, gender)
    variant_context = (
        f"This shot: {v_intent}. Framing: {variant.framing}. "
        f"{v_action}."
    )
    if v_emotion:
        variant_context += f" {v_emotion}."

    identity_locks = _identity_lock_by_gender(gender)
    all_avoids = list(brief.avoid_global) + list(variant.avoid_local) + _GLOBAL_HARD_AVOIDS
    if is_solo:
        all_avoids += _SOLO_HARD_AVOIDS
    seen: set[str] = set()
    deduped: list[str] = []
    for a in all_avoids:
        lower = a.lower()
        if lower not in seen:
            seen.add(lower)
            deduped.append(a)
    avoid_context = "Avoid: " + ", ".join(deduped) + "." if deduped else ""

    # Solo 额外身份硬约束
    solo_extra = ""
    if is_solo:
        solo_extra = (
            "\n\n" + _SOLO_HARD_RULE + "\n"
            "Use only the referenced person's identity; do not synthesize a second face or body."
        )

    return R3_IDENTITY_FUSION_TEMPLATE.format(
        subject_type=subject_type,
        brief_context=brief_context,
        variant_context=variant_context,
        identity_locks=identity_locks + solo_extra,
        avoid_context=avoid_context,
    )
