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

from models.schemas import VerifiabilityAssessment


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


# 阈值常量 — SSS 级调优（V12）
IDENTITY_MATCH_FLOOR = 0.80      # 低于此值 → 直接重生，脸已不可交付（从 0.78 提至 0.80）
HARD_FAIL_SCORE_FLOOR = 0.60     # hard_fail 且分数极低 → 重生
SOFT_PASS_FLOOR = 0.90           # SSS 水平才允许直接交付（从 0.88 提至 0.90）
MIN_DELIVERY_FLOOR = 0.85        # 最终轮软失败时，低于此值不再交付（从 0.83 提至 0.85）
VALIDATION_FACE_AREA_FLOOR_COUPLE = 0.025  # 验证轨人脸面积 — couple（每张脸至少 2.5%）
VALIDATION_FACE_AREA_FLOOR_SOLO = 0.035    # 验证轨人脸面积 — solo（单人至少 3.5%）
HERO_FACE_AREA_FLOOR = 0.025        # Hero轨人脸面积（从 0.032 降至 0.025，允许更多氛围图）
VALIDATION_BODY_VISIBILITY_FLOOR = 0.80  # 验证轨身体可见性 — couple（从 0.72 提至 0.80）
VALIDATION_BODY_VISIBILITY_FLOOR_SOLO = 0.60  # 验证轨身体可见性 — solo（半身即可）

# Hero track 专用阈值 — 氛围图允许更大艺术自由度（V13）
HERO_IDENTITY_MATCH_FLOOR = 0.70    # hero 不要求完美脸部匹配（vs validation 0.80）
HERO_SOFT_PASS_FLOOR = 0.85         # hero 不需要 SSS 级才交付（vs 0.90）
HERO_MIN_DELIVERY_FLOOR = 0.80      # hero 交付底线更宽松（vs 0.85）


def meets_delivery_floor(score: float, *, track: str = "validation") -> bool:
    """最终对外可交付的最低综合分。

    V13 起 hero 轨允许使用更宽松的最终交付门槛，避免前面已经按 hero
    策略放宽，最后又被 validation 门槛重新拦回去。
    """
    if track == "hero":
        return score >= HERO_MIN_DELIVERY_FLOOR
    return score >= MIN_DELIVERY_FLOOR


def _relevant_face_ratios(verifiability: VerifiabilityAssessment, gender: str) -> list[float]:
    if gender == "female":
        return [verifiability.face_area_ratio_bride]
    if gender == "male":
        return [verifiability.face_area_ratio_groom]
    return [verifiability.face_area_ratio_bride, verifiability.face_area_ratio_groom]


def passes_validation_track(
    verifiability: VerifiabilityAssessment,
    *,
    gender: str,
) -> bool:
    is_solo = gender in ("female", "male")
    face_ratios = _relevant_face_ratios(verifiability, gender)
    face_floor = VALIDATION_FACE_AREA_FLOOR_SOLO if is_solo else VALIDATION_FACE_AREA_FLOOR_COUPLE
    body_floor = VALIDATION_BODY_VISIBILITY_FLOOR_SOLO if is_solo else VALIDATION_BODY_VISIBILITY_FLOOR
    return (
        verifiability.is_identity_verifiable
        and verifiability.is_proportion_verifiable
        and all(ratio >= face_floor for ratio in face_ratios)
        and verifiability.body_visibility_score >= body_floor
    )


def passes_hero_identity_gate(
    verifiability: VerifiabilityAssessment,
    *,
    gender: str,
) -> bool:
    face_ratios = _relevant_face_ratios(verifiability, gender)
    return (
        verifiability.is_identity_verifiable
        and all(ratio >= HERO_FACE_AREA_FLOOR for ratio in face_ratios)
    )


def summarize_verifiability_failure(
    verifiability: VerifiabilityAssessment,
    *,
    gender: str,
    for_validation_track: bool,
) -> str:
    face_ratios = _relevant_face_ratios(verifiability, gender)
    min_face_ratio = min(face_ratios) if face_ratios else 0.0
    if for_validation_track and not verifiability.is_proportion_verifiable:
        return "Validation track failed: proportions are not verifiable"
    if not verifiability.is_identity_verifiable:
        return "Identity is not verifiable"
    if for_validation_track:
        is_solo = gender in ("female", "male")
        target_floor = VALIDATION_FACE_AREA_FLOOR_SOLO if is_solo else VALIDATION_FACE_AREA_FLOOR_COUPLE
    else:
        target_floor = HERO_FACE_AREA_FLOOR
    if min_face_ratio < target_floor:
        return f"Face area ratio {min_face_ratio:.3f} below floor {target_floor:.3f}"
    is_solo = gender in ("female", "male")
    body_floor = VALIDATION_BODY_VISIBILITY_FLOOR_SOLO if is_solo else VALIDATION_BODY_VISIBILITY_FLOOR
    if for_validation_track and verifiability.body_visibility_score < body_floor:
        return (
            "Validation track failed: "
            f"body visibility {verifiability.body_visibility_score:.2f} below floor "
            f"{body_floor:.2f}"
        )
    if verifiability.notes:
        return verifiability.notes[0]
    return "Verifiability gate failed"


def decide_repair(
    hard_fail: bool,
    identity_match: float,
    brief_alignment: float,
    aesthetic_score: float,
    fix_round: int,
    max_rounds: int,
    *,
    track: str = "validation",
) -> DeliveryDecision:
    """根据质检结果决定修复策略。

    决策优先级（工程落地版 §八）：
    1. identity_match 过低 → 重生（脸都不像还修什么）
    2. hard_fail → 看能否局部修，否则重生
    3. 全部达标 → 交付
    4. soft fail → 如果还有修复轮次，局部修；否则交付

    V13: track="hero" 使用放松的阈值，允许氛围型 hero 图更容易通过。
    """
    # 按 track 选择阈值集
    if track == "hero":
        id_floor = HERO_IDENTITY_MATCH_FLOOR
        soft_floor = HERO_SOFT_PASS_FLOOR
        delivery_floor = HERO_MIN_DELIVERY_FLOOR
    else:
        id_floor = IDENTITY_MATCH_FLOOR
        soft_floor = SOFT_PASS_FLOOR
        delivery_floor = MIN_DELIVERY_FLOOR

    is_last_round = fix_round >= max_rounds - 1

    # Rule 1: 身份不一致 → 重生
    if identity_match < id_floor:
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
    if avg >= soft_floor:
        return DeliveryDecision(RepairMode.deliver, f"All scores pass (avg {avg:.2f})")

    # Rule 4: Soft fail → 局部修；最终轮只允许边缘样本勉强交付
    if is_last_round:
        if avg < delivery_floor:
            return DeliveryDecision(
                RepairMode.reject,
                f"Soft fail remained below delivery floor (avg {avg:.2f})",
            )
        return DeliveryDecision(RepairMode.deliver, f"Borderline pass on final round (avg {avg:.2f})")
    return DeliveryDecision(RepairMode.local_fix, f"Soft fail (avg {avg:.2f}), attempting improvement")
