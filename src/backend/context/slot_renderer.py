"""动态插槽渲染 — 将妆造/性别/偏好转为 prompt 片段。

规则：
- 空值不渲染
- 妆造用视觉语言（英文），不是抽象标签
- 偏好做类型区分，不全塞进一句自然语言
"""

from __future__ import annotations

from dataclasses import dataclass

# 妆造风格 → 英文视觉描述（按性别区分）
_MAKEUP_DESCRIPTIONS: dict[str, str] = {
    "natural": "Dewy, barely-there makeup — light foundation, nude lips, soft natural brows, glowing skin",
    "refined": "Polished elegant makeup — flawless base, soft smoky eyes, rose lips, sculpted highlight",
    "sculpt": "Full-coverage dramatic makeup — contoured bone structure, bold liner, red lips, false lashes",
}

# 男性专用妆造（不适用女性描述）
_MAKEUP_DESCRIPTIONS_MALE: dict[str, str] = {
    "natural": "Clean, natural grooming — even skin tone, well-shaped brows, healthy complexion, matte finish",
    "refined": "Polished grooming — flawless even skin, subtle contour, groomed brows, natural lip color",
    "sculpt": "Editorial grooming — sculpted skin, defined jawline highlight, strong brows, camera-ready finish",
}

# 性别组合 → 英文描述
_PAIRING_DESCRIPTIONS: dict[str, str] = {
    "female": "a bride",
    "male": "a groom",
    "couple": "a bride and groom",
}


@dataclass
class SlotPayload:
    """渲染后的动态插槽内容，每个字段都是可直接嵌入 prompt 的英文片段。"""

    makeup: str = ""
    bride_makeup: str = ""
    groom_makeup: str = ""
    pairing: str = ""
    user_preference: str = ""


def render_slots(
    makeup_style: str = "natural",
    gender: str = "couple",
    preferences: dict | None = None,
    bride_makeup_style: str | None = None,
    groom_makeup_style: str | None = None,
) -> SlotPayload:
    """将原始参数渲染为 prompt 可用的文本片段。"""

    bride_style = bride_makeup_style or makeup_style
    groom_style = groom_makeup_style or makeup_style
    bride_makeup = _MAKEUP_DESCRIPTIONS.get(bride_style, _MAKEUP_DESCRIPTIONS["natural"])
    groom_makeup = _MAKEUP_DESCRIPTIONS_MALE.get(groom_style, _MAKEUP_DESCRIPTIONS_MALE["natural"])

    if gender == "male":
        makeup = groom_makeup
    elif gender == "female":
        makeup = bride_makeup
    else:
        makeup = f"Bride makeup: {bride_makeup}. Groom grooming: {groom_makeup}"

    # 性别 → pairing 描述
    pairing = _PAIRING_DESCRIPTIONS.get(gender, _PAIRING_DESCRIPTIONS["couple"])

    # 用户偏好压缩
    pref_parts: list[str] = []
    if preferences:
        if bride := preferences.get("bride_style"):
            pref_parts.append(f"Bride preference: {bride}")
        if groom := preferences.get("groom_style"):
            pref_parts.append(f"Groom preference: {groom}")

    return SlotPayload(
        makeup=makeup,
        bride_makeup=bride_makeup,
        groom_makeup=groom_makeup,
        pairing=pairing,
        user_preference=". ".join(pref_parts),
    )
