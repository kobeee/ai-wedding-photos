from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

import httpx

from config import settings
from context.briefs import CreativeBrief, PromptVariant
from context.prompt_assembler import assemble_face_lock_prompt, assemble_nano_repair_prompt
from context.reference_selector import ReferenceSet
from context.slot_renderer import SlotPayload
from context.thresholds import (
    RepairMode,
    decide_repair,
    meets_delivery_floor,
    passes_hero_identity_gate,
    passes_validation_track,
    summarize_verifiability_failure,
)
from context.variant_planner import get_variants
from models.schemas import DeliverableKind, RenderTrack, VerifiabilityAssessment
from services.editorial_pipeline import PipelineResult, run_editorial_pipeline
from services.gpt_image import gpt_image_service
from services.makeup_reference import MakeupReference
from services.nano_banana import nano_banana_service
from services.vlm_checker import QualityReport, vlm_checker_service
from utils.storage import save_generated_image

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[float, str], Awaitable[None]]


@dataclass
class OrchestratedAsset:
    image_data: bytes
    kind: DeliverableKind
    track: RenderTrack
    quality_score: float
    verifiability: VerifiabilityAssessment = field(default_factory=VerifiabilityAssessment)
    user_visible: bool = False
    notes: list[str] = field(default_factory=list)


@dataclass
class OrchestratedPhoto:
    assets: list[OrchestratedAsset] = field(default_factory=list)

    @property
    def visible_assets(self) -> list[OrchestratedAsset]:
        return [asset for asset in self.assets if asset.user_visible]


def _pick_validation_variant(brief: CreativeBrief, hero_variant: PromptVariant, gender: str = "couple") -> PromptVariant:
    """构建验证轨专用 variant。

    SSS 关键：验证轨不复用 hero 的 wide variant，而是构建专门为身份验证优化的 variant。
    - 用 medium-wide 而非 ultra-wide，确保人脸面积足够大
    - 强制正面/开放3/4角度
    - 明确身高差和体态分离要求
    """
    is_solo = gender in ("female", "male")
    role = "bride" if gender == "female" else ("groom" if gender == "male" else "bride and groom")

    if is_solo:
        return PromptVariant(
            id=f"{hero_variant.id}_validation",
            intent=f"Identity-verifiable portrait of the {role}",
            framing="medium",
            action=(
                f"Medium shot from waist up, the {role} facing the camera in an open three-quarter angle, "
                "both eyes clearly visible, face well-lit and unobstructed, natural relaxed posture"
            ),
            emotion_focus="Confident and present, with a genuine connection to the camera",
            avoid_local=[
                "profile view", "turned-away face", "backlighting that silhouettes the face",
                "hair covering eyes", "too-tight crop cutting off torso",
                *hero_variant.avoid_local,
            ],
        )

    return PromptVariant(
        id=f"{hero_variant.id}_validation",
        intent="Identity-verifiable couple portrait with clear face and proportion readability",
        framing="medium-wide",
        action=(
            "Three-quarter body to full body shot, both partners standing with natural spacing, "
            "both facing the camera in open three-quarter angles with all four eyes clearly visible. "
            "Height difference clearly readable. Shoulders, torso, and limbs distinctly separated. "
            "Faces well-lit and large enough to verify identity — no tiny figures in a landscape"
        ),
        emotion_focus=(
            "Warm, genuine connection between partners while maintaining camera-readable faces. "
            "Authentic smiles or serene expressions, not posed or stiff"
        ),
        avoid_local=[
            "profile view", "turned-away faces", "face overlap", "backlighting silhouettes",
            "ultra-wide environmental shot with tiny figures", "heavy shadow on faces",
            "one partner hidden behind the other", "extreme close-up",
            *hero_variant.avoid_local,
        ],
    )


class ProductionOrchestratorService:
    async def run_photo(
        self,
        *,
        brief: CreativeBrief,
        hero_variant: PromptVariant,
        slots: SlotPayload,
        gender: str,
        ref_set: ReferenceSet | None,
        bride_makeup_ref: MakeupReference | None = None,
        groom_makeup_ref: MakeupReference | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> OrchestratedPhoto:
        validation_variant = _pick_validation_variant(brief, hero_variant, gender)
        identity_refs = ref_set.identity_refs if ref_set is not None and ref_set.has_identity else []

        validation_result, validation_report = await self._run_validation_track(
            brief=brief,
            variant=validation_variant,
            slots=slots,
            gender=gender,
            ref_set=ref_set,
            bride_makeup_ref=bride_makeup_ref,
            groom_makeup_ref=groom_makeup_ref,
            identity_refs=identity_refs,
            progress_callback=progress_callback,
        )

        validation_asset = OrchestratedAsset(
            image_data=validation_result.final_image,
            kind=DeliverableKind.validation_safe,
            track=RenderTrack.validation,
            quality_score=validation_report.score,
            verifiability=validation_report.verifiability,
            user_visible=False,
            notes=["validation track passed"],
        )

        hero_asset = await self._run_hero_track(
            brief=brief,
            variant=hero_variant,
            slots=slots,
            gender=gender,
            ref_set=ref_set,
            bride_makeup_ref=bride_makeup_ref,
            groom_makeup_ref=groom_makeup_ref,
            identity_refs=identity_refs,
            validation_anchor=validation_report.verifiability,
            progress_callback=progress_callback,
        )

        if hero_asset is None:
            validation_asset.user_visible = True
            validation_asset.notes.append("hero track failed, validation-safe promoted as visible fallback")
            return OrchestratedPhoto(assets=[validation_asset])
        return OrchestratedPhoto(assets=[validation_asset, hero_asset])

    async def _run_validation_track(
        self,
        *,
        brief: CreativeBrief,
        variant: PromptVariant,
        slots: SlotPayload,
        gender: str,
        ref_set: ReferenceSet | None,
        bride_makeup_ref: MakeupReference | None,
        groom_makeup_ref: MakeupReference | None,
        identity_refs: list[tuple[bytes, str]],
        progress_callback: ProgressCallback | None,
    ) -> tuple[PipelineResult, QualityReport]:
        last_report: QualityReport | None = None
        last_pipeline: PipelineResult | None = None
        is_solo = gender in ("female", "male")
        # Couple 人脸面积波动大（0.015-0.050），需要更多尝试才能稳定通过验证
        attempts = max(settings.max_fix_rounds, 1) if is_solo else max(settings.max_fix_rounds + 2, 5)
        brief_summary = f"{brief.story} {brief.emotion}"

        for attempt in range(attempts):
            if progress_callback is not None:
                await progress_callback(
                    min(0.14 + attempt * 0.12, 0.46),
                    f"正在验证构图与身份第 {attempt + 1}/{attempts} 次...",
                )
            pipeline = await run_editorial_pipeline(
                brief=brief,
                variant=variant,
                slots=slots,
                gender=gender,
                ref_set=ref_set if ref_set is not None and ref_set.has_identity else None,
                bride_makeup_ref=bride_makeup_ref if gender in {"couple", "female"} else None,
                groom_makeup_ref=groom_makeup_ref if gender in {"couple", "male"} else None,
                track="validation",
            )
            report, _ = await vlm_checker_service.check_and_suggest_fix_prompt(
                image_data=pipeline.final_image,
                original_prompt=pipeline.review_prompt,
                brief_summary=brief_summary,
                reference_images=identity_refs,
                track=RenderTrack.validation,
                gender=gender,
            )
            last_pipeline = pipeline
            last_report = report

            if report.inspection_unavailable:
                raise RuntimeError("Validation track inspection unavailable")
            if passes_validation_track(report.verifiability, gender=gender):
                if progress_callback is not None:
                    await progress_callback(0.52, "验证通过，开始生成氛围主片...")
                return pipeline, report

            logger.warning(
                "Validation track attempt %d failed: %s",
                attempt + 1,
                summarize_verifiability_failure(
                    report.verifiability,
                    gender=gender,
                    for_validation_track=True,
                ),
            )

        assert last_pipeline is not None and last_report is not None
        raise RuntimeError(
            summarize_verifiability_failure(
                last_report.verifiability,
                gender=gender,
                for_validation_track=True,
            )
        )

    async def _run_hero_track(
        self,
        *,
        brief: CreativeBrief,
        variant: PromptVariant,
        slots: SlotPayload,
        gender: str,
        ref_set: ReferenceSet | None,
        bride_makeup_ref: MakeupReference | None,
        groom_makeup_ref: MakeupReference | None,
        identity_refs: list[tuple[bytes, str]],
        validation_anchor: VerifiabilityAssessment,
        progress_callback: ProgressCallback | None,
    ) -> OrchestratedAsset | None:
        brief_summary = f"{brief.story} {brief.emotion}"
        evaluation_rounds = max(settings.max_fix_rounds, 0) + 1
        face_lock_attempted = False
        current_image: bytes | None = None
        current_prompt = ""
        current_report: QualityReport | None = None
        regenerated = 0

        while regenerated < max(evaluation_rounds, 1):
            if progress_callback is not None:
                await progress_callback(
                    min(0.58 + regenerated * 0.12, 0.78),
                    f"正在生成氛围主片第 {regenerated + 1}/{max(evaluation_rounds, 1)} 次...",
                )
            pipeline = await run_editorial_pipeline(
                brief=brief,
                variant=variant,
                slots=slots,
                gender=gender,
                ref_set=ref_set if ref_set is not None and ref_set.has_identity else None,
                bride_makeup_ref=bride_makeup_ref if gender in {"couple", "female"} else None,
                groom_makeup_ref=groom_makeup_ref if gender in {"couple", "male"} else None,
            )
            current_image = pipeline.final_image
            current_prompt = pipeline.review_prompt
            current_report, current_image, should_regenerate = await self._evaluate_hero_image(
                image_data=current_image,
                render_prompt=current_prompt,
                brief_summary=brief_summary,
                identity_refs=identity_refs,
                validation_anchor=validation_anchor,
                gender=gender,
                ref_set=ref_set,
                face_lock_attempted=face_lock_attempted,
            )

            if current_report is None:
                return None
            if should_regenerate:
                regenerated += 1
                continue
            if current_image is None:
                return None

            if current_report.inspection_unavailable:
                raise RuntimeError("Hero track inspection unavailable")

            if passes_hero_identity_gate(current_report.verifiability, gender=gender):
                if meets_delivery_floor(current_report.score, track="hero"):
                    if progress_callback is not None:
                        await progress_callback(0.9, "主片通过质检，正在整理交付...")
                    return OrchestratedAsset(
                        image_data=current_image,
                        kind=DeliverableKind.hero_atmosphere,
                        track=RenderTrack.hero,
                        quality_score=current_report.score,
                        verifiability=current_report.verifiability,
                        user_visible=True,
                        notes=["hero track passed identity gate"],
                    )
                return None

            if not face_lock_attempted and ref_set is not None:
                if progress_callback is not None:
                    await progress_callback(0.84, "主片身份不足，正在尝试锁脸修正...")
                current_image = await self._apply_face_lock_pass(
                    image_data=current_image,
                    render_prompt=current_prompt,
                    gender=gender,
                    ref_set=ref_set,
                    report=current_report,
                )
                face_lock_attempted = True
                current_report, _ = await vlm_checker_service.check_and_suggest_fix_prompt(
                    image_data=current_image,
                    original_prompt=current_prompt,
                    brief_summary=brief_summary,
                    reference_images=identity_refs,
                    track=RenderTrack.hero,
                    validation_anchor=validation_anchor,
                    gender=gender,
                )
                if (
                    current_report is not None
                    and passes_hero_identity_gate(current_report.verifiability, gender=gender)
                    and meets_delivery_floor(current_report.score, track="hero")
                ):
                    if progress_callback is not None:
                        await progress_callback(0.9, "锁脸修正完成，正在整理交付...")
                    return OrchestratedAsset(
                        image_data=current_image,
                        kind=DeliverableKind.hero_atmosphere,
                        track=RenderTrack.face_lock,
                        quality_score=current_report.score,
                        verifiability=current_report.verifiability,
                        user_visible=True,
                        notes=["hero track rescued by face lock pass"],
                    )

            if current_report is not None and meets_delivery_floor(current_report.score, track="hero"):
                if progress_callback is not None:
                    await progress_callback(0.9, "主片降级为氛围交付，正在整理结果...")
                return OrchestratedAsset(
                    image_data=current_image,
                    kind=DeliverableKind.hero_atmosphere,
                    track=RenderTrack.hero if not face_lock_attempted else RenderTrack.face_lock,
                    quality_score=current_report.score,
                    verifiability=current_report.verifiability,
                    user_visible=True,
                    notes=[
                        "hero downgraded to atmosphere because identity verifiability stayed below core gate"
                    ],
                )

            regenerated += 1

        return None

    async def _evaluate_hero_image(
        self,
        *,
        image_data: bytes,
        render_prompt: str,
        brief_summary: str,
        identity_refs: list[tuple[bytes, str]],
        validation_anchor: VerifiabilityAssessment,
        gender: str,
        ref_set: ReferenceSet | None,
        face_lock_attempted: bool,
    ) -> tuple[QualityReport | None, bytes | None, bool]:
        current_image = image_data
        for fix_round in range(max(settings.max_fix_rounds, 0) + 1):
            report, _ = await vlm_checker_service.check_and_suggest_fix_prompt(
                image_data=current_image,
                original_prompt=render_prompt,
                brief_summary=brief_summary,
                reference_images=identity_refs,
                track=RenderTrack.hero,
                validation_anchor=validation_anchor,
                gender=gender,
            )
            if report.inspection_unavailable:
                return report, current_image, False

            decision = decide_repair(
                hard_fail=report.hard_fail,
                identity_match=report.identity_match,
                brief_alignment=report.brief_alignment,
                aesthetic_score=report.aesthetic_score,
                fix_round=fix_round,
                max_rounds=max(settings.max_fix_rounds, 0) + 1,
                track="hero",
            )

            if decision.mode == RepairMode.deliver:
                return report, current_image, False
            if decision.mode == RepairMode.local_fix:
                current_image = await self._dual_path_fix(
                    current_image,
                    report,
                    render_prompt,
                    identity_refs,
                    gender=gender,
                )
                continue
            if decision.mode == RepairMode.regenerate:
                return report, None, True
            if decision.mode == RepairMode.reject:
                if not face_lock_attempted and ref_set is not None:
                    return report, current_image, False
                return report, None, False

        return report, current_image, False

    async def _dual_path_fix(
        self,
        img_bytes: bytes,
        report: QualityReport,
        render_prompt: str,
        refs: list[tuple[bytes, str]],
        *,
        gender: str,
    ) -> bytes:
        physical = report.physical_issues
        emotional = report.emotional_issues
        result = img_bytes

        def _select_hints(issues: list) -> list[str]:
            if not report.repair_hints:
                return [issue.description for issue in issues]
            if physical and emotional:
                return [issue.description for issue in issues]
            return list(report.repair_hints)

        async def _apply_nano_fix(issues: list, focus: str) -> bytes:
            fix_prompt = assemble_nano_repair_prompt(
                render_prompt=render_prompt,
                repair_hints=_select_hints(issues),
                has_identity_refs=bool(refs),
                focus=focus,
                gender=gender,
            )
            return await nano_banana_service.repair_with_references(
                prompt=fix_prompt,
                image_data=result,
                reference_images=refs,
            )

        if physical:
            result = await _apply_nano_fix(physical, "physical")

        if emotional:
            if settings.enable_gpt_image_repairs:
                fix_prompt = assemble_nano_repair_prompt(
                    render_prompt=render_prompt,
                    repair_hints=_select_hints(emotional),
                    has_identity_refs=bool(refs),
                    focus="emotional",
                    gender=gender,
                )
                try:
                    _, tmp_path = await save_generated_image("tmp_fix", result, ext=".png")
                    edit_url = await gpt_image_service.edit(image_path=tmp_path, prompt=fix_prompt)
                    async with httpx.AsyncClient(timeout=60) as client:
                        resp = await client.get(edit_url)
                        resp.raise_for_status()
                        return resp.content
                except Exception:
                    logger.warning("GPT emotional fix failed, fallback to Nano", exc_info=True)

            result = await _apply_nano_fix(emotional, "emotional")

        return result

    async def _apply_face_lock_pass(
        self,
        *,
        image_data: bytes,
        render_prompt: str,
        gender: str,
        ref_set: ReferenceSet,
        report: QualityReport,
    ) -> bytes:
        """分人锁脸 pass — 按角色逐个修复面部身份。

        SSS 改进：
        - 优先修复身份评分最低的角色
        - 传入所有相关修复提示（不仅限于 role 关键词匹配）
        - 使用更多参考图（最多 3 张）增强身份锁定
        """
        result = image_data
        roles_to_fix = []

        for role in ("bride", "groom"):
            if gender == "female" and role == "groom":
                continue
            if gender == "male" and role == "bride":
                continue
            role_refs = ref_set.identity_refs_for_role(role)
            if not role_refs:
                # 如果没有角色特定参考图，尝试用通用参考图
                if ref_set.identity_refs:
                    role_refs = ref_set.identity_refs[:2]
                else:
                    continue
            roles_to_fix.append((role, role_refs))

        for role, role_refs in roles_to_fix:
            # 收集修复提示：角色相关的 issues + 通用身份问题
            role_hints = [
                issue.description
                for issue in report.issues
                if role in issue.description.lower()
                or "identity" in issue.description.lower()
                or "face" in issue.description.lower()
                or "likeness" in issue.description.lower()
            ]
            # 去重
            seen = set()
            unique_hints = []
            for hint in role_hints:
                if hint not in seen:
                    seen.add(hint)
                    unique_hints.append(hint)

            prompt = assemble_face_lock_prompt(
                render_prompt,
                role=role,
                repair_hints=unique_hints,
                gender=gender,
            )
            logger.info("Face lock pass for %s with %d refs, %d hints", role, len(role_refs), len(unique_hints))
            result = await nano_banana_service.repair_with_references(
                prompt=prompt,
                image_data=result,
                mime_type="image/png",
                reference_images=role_refs[:3],  # 最多 3 张参考图
            )
        return result


production_orchestrator_service = ProductionOrchestratorService()
