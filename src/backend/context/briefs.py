"""CreativeBrief schema + 套餐基础 Brief 模板库。

每个套餐一份人工精调的基础 brief。Director 只做编辑，不从零生成。
基础版本永远可用，Director 不可用时直接 fallback。
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PromptVariant(BaseModel):
    """单张照片的差异化意图。"""

    id: str
    intent: str = Field(..., description="这张照片要讲什么")
    framing: str = Field(..., description="镜头意图：close/medium/wide/overhead")
    action: str = Field(..., description="人物状态与画面关系")
    emotion_focus: str = ""
    avoid_local: list[str] = Field(default_factory=list)


class CreativeBrief(BaseModel):
    """套餐创意简报 — 替代旧 CameraSchema。

    叙事字段定义"拍什么故事"，弱控制字段稳住输出分布。
    """

    package_id: str
    story: str = Field(..., description="一句话叙事定位")
    visual_essence: str = Field(..., description="核心画面描述")
    emotion: str = Field(..., description="要唤起的感受")
    aesthetic: str = Field(..., description="视觉风格：色调/氛围/质感")
    wardrobe_bride: str = ""
    wardrobe_groom: str = ""
    makeup_default: str = ""
    avoid_global: list[str] = Field(default_factory=list)

    # 弱控制字段 — 不是技术参数，是创意约束的工程化表达
    shot_scale: str = Field("mixed", description="close/medium/wide/mixed")
    subject_arrangement: str = Field("couple", description="couple/solo_bride/solo_groom")
    lighting_bias: str = Field("", description="soft_warm/cool_diffused/high_contrast/neon_reflective")
    pose_energy: str = Field("natural", description="still/tender/playful/dramatic")

    variants: list[PromptVariant] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 套餐基础 Brief 模板库（人工精调，核心资产）
# ---------------------------------------------------------------------------

_BRIEF_ICELAND = CreativeBrief(
    package_id="iceland",
    story="The last two people at the edge of the world.",
    visual_essence=(
        "A couple on Iceland's black sand beach, aurora borealis overhead. "
        "Vast and raw, yet impossibly intimate. She is the only warmth "
        "in a monochrome landscape — white gown against black sand, "
        "warm skin against freezing air."
    ),
    emotion="Awe-struck tenderness — the universe conspired for this moment",
    aesthetic="Cinematic, desaturated landscape with warm skin tones, subtle film grain",
    wardrobe_bride="Flowing white gown with long train catching arctic wind",
    wardrobe_groom="Dark tailored wool coat over white shirt, no tie, wind-touched hair",
    makeup_default="Dewy, barely-there — skin glows naturally against the cold",
    avoid_global=[
        "oversaturated aurora",
        "tropical warmth",
        "stiff poses",
        "generic model faces",
        "extra fingers or limbs",
        "snow that looks like white noise",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="cool_diffused",
    pose_energy="tender",
    variants=[
        PromptVariant(
            id="iceland_intimate",
            intent="Private moment at the edge of the world",
            framing="close",
            action="Foreheads gently touching, aurora reflected in their eyes",
            emotion_focus="Quiet awe, as if the lights are dancing just for them",
            avoid_local=["distorted facial features", "unnatural skin smoothing"],
        ),
        PromptVariant(
            id="iceland_epic",
            intent="Two tiny figures against an infinite landscape",
            framing="wide",
            action="Standing together on black sand, glacier and aurora behind them",
            emotion_focus="Small against the universe, yet unshakable together",
            avoid_local=["blurry figures", "lost facial detail", "disproportionate bodies"],
        ),
        PromptVariant(
            id="iceland_candid",
            intent="A stolen laugh in the coldest place on earth",
            framing="medium",
            action="Genuine laughter, his arms around her from behind, snowflakes in the air",
            emotion_focus="Warmth that defies the cold — unscripted joy",
            avoid_local=["fake smiles", "awkward hand placement"],
        ),
        PromptVariant(
            id="iceland_departure",
            intent="Walking into forever",
            framing="wide",
            action="Walking away on black sand, gown trailing, aurora arching overhead",
            emotion_focus="A quiet promise — wherever we go, we go together",
            avoid_local=["unnatural gait", "floating fabric", "disconnected couple"],
        ),
    ],
)

_BRIEF_CYBERPUNK = CreativeBrief(
    package_id="cyberpunk",
    story="Love is the only real thing in a synthetic world.",
    visual_essence=(
        "Rain-slicked neon streets, holographic ads flickering overhead. "
        "They don't belong here — and that's what makes them magnetic. "
        "Wedding elegance colliding with digital chaos."
    ),
    emotion="Defiant romance — tender in a world that is anything but",
    aesthetic="High contrast, neon cyan-magenta palette, wet reflections, noir edge",
    wardrobe_bride="Structured modern gown with metallic accents, architectural silhouette",
    wardrobe_groom="Black suit with subtle holographic trim, sharp, futuristic",
    makeup_default="Bold graphic liner, glass skin, metallic lip accent",
    avoid_global=[
        "daylight leaks",
        "warm pastoral tones",
        "costume-party feel",
        "unreadable faces in darkness",
        "extra fingers or limbs",
        "cheap cosplay aesthetic",
    ],
    shot_scale="mixed",
    subject_arrangement="couple",
    lighting_bias="neon_reflective",
    pose_energy="dramatic",
    variants=[
        PromptVariant(
            id="cyber_portrait",
            intent="Two faces lit by a world they chose to ignore",
            framing="close",
            action="Intense locked eyes, neon reflections dancing on wet skin",
            emotion_focus="Electric tension — the world buzzes but they are still",
            avoid_local=["muddy neon colors", "unnatural skin texture"],
        ),
        PromptVariant(
            id="cyber_alley",
            intent="Elegance crashing into chaos",
            framing="wide",
            action="Full body in neon alley, holographic rain, dramatic silhouettes",
            emotion_focus="Defiant beauty — they own this street tonight",
            avoid_local=["lost figure detail", "illegible faces", "flat lighting"],
        ),
        PromptVariant(
            id="cyber_playful",
            intent="Finding joy in the machine",
            framing="medium",
            action="Laughing together under a holographic umbrella, city blurred behind",
            emotion_focus="Playful rebellion — love as an act of defiance",
            avoid_local=["stiff poses", "empty expressions", "over-busy background"],
        ),
        PromptVariant(
            id="cyber_reflection",
            intent="The real and the reflected",
            framing="medium",
            action="Reflection shot in a rain puddle, neon world inverted beneath them",
            emotion_focus="Duality — which version of them is the real one?",
            avoid_local=["broken symmetry", "muddy reflections", "distorted anatomy"],
        ),
    ],
)

# ---------------------------------------------------------------------------
# 套餐 ID → Brief 映射（含旧 ID 兼容）
# Phase 4: 从 _briefs_phase4.py 合并完整 10 套
# ---------------------------------------------------------------------------

from context._briefs_phase4 import (
    _BRIEF_FRENCH,
    _BRIEF_MINIMAL,
    _BRIEF_ONSEN,
    _BRIEF_STARCAMP,
    _BRIEF_CHINESE_CLASSIC,
    _BRIEF_WESTERN_ROMANTIC,
    _BRIEF_ARTISTIC_FANTASY,
    _BRIEF_TRAVEL_DESTINATION,
)

_BRIEFS: dict[str, CreativeBrief] = {
    # Phase 1
    "iceland": _BRIEF_ICELAND,
    "cyberpunk": _BRIEF_CYBERPUNK,
    # Phase 4
    "french": _BRIEF_FRENCH,
    "minimal": _BRIEF_MINIMAL,
    "onsen": _BRIEF_ONSEN,
    "starcamp": _BRIEF_STARCAMP,
    "chinese-classic": _BRIEF_CHINESE_CLASSIC,
    "western-romantic": _BRIEF_WESTERN_ROMANTIC,
    "artistic-fantasy": _BRIEF_ARTISTIC_FANTASY,
    "travel-destination": _BRIEF_TRAVEL_DESTINATION,
}

_DEFAULT_BRIEF = _BRIEF_ICELAND


def get_brief(package_id: str) -> CreativeBrief:
    """获取套餐基础 brief。未覆盖的套餐返回默认 brief（不报错）。"""
    return _BRIEFS.get(package_id, _DEFAULT_BRIEF).model_copy(deep=True)
