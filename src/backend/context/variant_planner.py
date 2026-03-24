"""变体计划 — 获取套餐绑定的 variant 列表。

variant 必须是"镜头意图 + 人物状态 + 画面关系"，不是纯 shot label。
每个 variant 有自己的 avoid。
"""

from __future__ import annotations

from context.briefs import CreativeBrief, PromptVariant


def get_variants(brief: CreativeBrief, count: int = 4) -> list[PromptVariant]:
    """从 brief 中获取 variant 列表，数量不足时循环复用。"""
    if not brief.variants:
        return [_default_variant(i) for i in range(count)]

    result: list[PromptVariant] = []
    for i in range(count):
        result.append(brief.variants[i % len(brief.variants)])
    return result


def _default_variant(index: int) -> PromptVariant:
    """兜底 variant — 当 brief 没有定义 variants 时使用。"""
    defaults = [
        PromptVariant(
            id=f"default_{index}",
            intent="An intimate moment between two people in love",
            framing="close",
            action="Gentle expressions, foreheads close, eyes meeting",
            emotion_focus="Quiet tenderness",
            avoid_local=["stiff poses", "empty expressions"],
        ),
        PromptVariant(
            id=f"default_{index}",
            intent="The full picture of their story",
            framing="wide",
            action="Full body, standing together, environment visible",
            emotion_focus="Grounded and real",
            avoid_local=["lost facial detail", "disproportionate bodies"],
        ),
        PromptVariant(
            id=f"default_{index}",
            intent="A moment they did not plan",
            framing="medium",
            action="Candid laughter, natural movement, genuine connection",
            emotion_focus="Unscripted joy",
            avoid_local=["fake smiles", "awkward hand placement"],
        ),
        PromptVariant(
            id=f"default_{index}",
            intent="Walking toward what comes next",
            framing="wide",
            action="Walking together, looking ahead or at each other",
            emotion_focus="Quiet confidence in each other",
            avoid_local=["unnatural gait", "disconnected body language"],
        ),
    ]
    return defaults[index % len(defaults)]
