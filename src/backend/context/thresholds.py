"""质检判定阈值与交付策略。

工程落地版 §八：VLM 质检拆成 hard fail / soft fail 两层判定。
hard_fail = true → 修复或重生
identity_match < threshold → 直接重生
brief_alignment 低但 identity 高 → 允许 soft repair
全部达标但不够惊艳 → 可交付
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RepairMode(str, Enum):
    """修复决策。"""
    deliver = "deliver"           # 直接交付
    local_fix = "local_fix"       # 局部修复（Nano i2i 或 GPT edit）
    regenerate = "regenerate"     # 整张重新生成
    reject = "reject"             # 本张不交付


@dataclass
class DeliveryDecision:
    """质检后的交付决策。"""
    mode: RepairMode
    reason: str


# 阈值常量
IDENTITY_MATCH_FLOOR = 0.70      # 低于此值 → 直接重生，修表情没意义
HARD_FAIL_SCORE_FLOOR = 0.60     # hard_fail 且分数极低 → 重生
SOFT_PASS_FLOOR = 0.80           # 高于此值且无 hard_fail → 可交付
MIN_DELIVERY_FLOOR = 0.72        # 最终轮软失败时，低于此值不再交付


def meets_delivery_floor(score: float) -> bool:
    """最终对外可交付的最低综合分。"""
    return score >= MIN_DELIVERY_FLOOR


def decide_repair(
    hard_fail: bool,
    identity_match: float,
    brief_alignment: float,
    aesthetic_score: float,
    fix_round: int,
    max_rounds: int,
) -> DeliveryDecision:
    """根据质检结果决定修复策略。

    决策优先级（工程落地版 §八）：
    1. identity_match 过低 → 重生（脸都不像还修什么）
    2. hard_fail → 看能否局部修，否则重生
    3. 全部达标 → 交付
    4. soft fail → 如果还有修复轮次，局部修；否则交付
    """
    is_last_round = fix_round >= max_rounds - 1

    # Rule 1: 身份不一致 → 重生
    if identity_match < IDENTITY_MATCH_FLOOR:
        if is_last_round:
            return DeliveryDecision(RepairMode.reject, "Identity low after final round")
        return DeliveryDecision(RepairMode.regenerate, f"Identity match {identity_match:.2f} below floor")

    # Rule 2: Hard fail → 局部修或重生
    if hard_fail:
        if is_last_round:
            return DeliveryDecision(RepairMode.reject, "Hard fail remained after final round")
        # 如果分数极低，重生比修补更稳定
        avg = (identity_match + brief_alignment + aesthetic_score) / 3
        if avg < HARD_FAIL_SCORE_FLOOR:
            return DeliveryDecision(RepairMode.regenerate, f"Hard fail with low avg {avg:.2f}")
        return DeliveryDecision(RepairMode.local_fix, "Hard fail, attempting local fix")

    # Rule 3: 全部达标 → 交付
    avg = (identity_match + brief_alignment + aesthetic_score) / 3
    if avg >= SOFT_PASS_FLOOR:
        return DeliveryDecision(RepairMode.deliver, f"All scores pass (avg {avg:.2f})")

    # Rule 4: Soft fail → 局部修；最终轮只允许边缘样本勉强交付
    if is_last_round:
        if not meets_delivery_floor(avg):
            return DeliveryDecision(
                RepairMode.reject,
                f"Soft fail remained below delivery floor (avg {avg:.2f})",
            )
        return DeliveryDecision(RepairMode.deliver, f"Borderline pass on final round (avg {avg:.2f})")
    return DeliveryDecision(RepairMode.local_fix, f"Soft fail (avg {avg:.2f}), attempting improvement")
