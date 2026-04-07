from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from config import settings
from context.briefs import CreativeBrief, PromptVariant
from context.reference_selector import ReferenceSet
from context.slot_renderer import SlotPayload
from context.thresholds import (
    decide_repair,
    meets_delivery_floor,
    passes_final_delivery_gate,
    summarize_final_delivery_failure,
)
from models.schemas import DeliverableKind, RenderTrack, VerifiabilityAssessment
from services.editorial_pipeline import run_editorial_pipeline
from services.makeup_reference import MakeupReference
from services.vlm_checker import QualityReport, vlm_checker_service

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
        brief_summary = f"{brief.story} {brief.emotion}"
        identity_refs = ref_set.identity_refs if ref_set is not None and ref_set.has_identity else []
        max_attempts = max(settings.v14_max_attempts, 1)
        last_report: QualityReport | None = None

        for attempt in range(max_attempts):
            if progress_callback is not None:
                await progress_callback(
                    min(0.10 + attempt * 0.28, 0.68),
                    f"正在执行 V14 两轮生成第 {attempt + 1}/{max_attempts} 次...",
                )

            pipeline = await run_editorial_pipeline(
                brief=brief,
                variant=hero_variant,
                slots=slots,
                gender=gender,
                ref_set=ref_set if ref_set is not None and ref_set.has_identity else None,
                bride_makeup_ref=bride_makeup_ref if gender in {"couple", "female"} else None,
                groom_makeup_ref=groom_makeup_ref if gender in {"couple", "male"} else None,
                track="final",
            )

            if progress_callback is not None:
                await progress_callback(
                    min(0.26 + attempt * 0.28, 0.82),
                    f"正在统一质检第 {attempt + 1}/{max_attempts} 次结果...",
                )

            report, _ = await vlm_checker_service.check_and_suggest_fix_prompt(
                image_data=pipeline.final_image,
                original_prompt=pipeline.review_prompt,
                brief_summary=brief_summary,
                reference_images=identity_refs,
                track=RenderTrack.final,
                gender=gender,
            )
            last_report = report

            if report.inspection_unavailable:
                if settings.allow_degraded_delivery_on_vlm_unavailable:
                    logger.warning("Final inspection unavailable, degrading delivery by configuration")
                    return OrchestratedPhoto(
                        assets=[
                            OrchestratedAsset(
                                image_data=pipeline.final_image,
                                kind=DeliverableKind.final_select,
                                track=RenderTrack.final,
                                quality_score=max(report.score, 0.0),
                                verifiability=report.verifiability,
                                user_visible=True,
                                notes=[
                                    "vlm inspection unavailable",
                                    "delivery degraded by configuration",
                                ],
                            )
                        ]
                    )
                raise RuntimeError("Final quality inspection unavailable")

            repair_decision = decide_repair(
                hard_fail=report.hard_fail,
                identity_match=report.identity_match,
                brief_alignment=report.brief_alignment,
                aesthetic_score=report.aesthetic_score,
                fix_round=attempt,
                max_rounds=max_attempts,
                track="final",
            )
            final_gate_ok = passes_final_delivery_gate(report.verifiability, gender=gender)
            score_ok = meets_delivery_floor(report.score, track="final")

            if final_gate_ok and score_ok and repair_decision.mode == "deliver":
                if progress_callback is not None:
                    await progress_callback(0.90, "正式成片通过质检，正在整理交付...")
                return OrchestratedPhoto(
                    assets=[
                        OrchestratedAsset(
                            image_data=pipeline.final_image,
                            kind=DeliverableKind.final_select,
                            track=RenderTrack.final,
                            quality_score=report.score,
                            verifiability=report.verifiability,
                            user_visible=True,
                            notes=[
                                "v14 final track passed unified quality gate",
                                repair_decision.reason,
                            ],
                        )
                    ]
                )

            failure_reason = summarize_final_delivery_failure(report.verifiability, gender=gender)
            logger.warning(
                "V14 final attempt %d/%d rejected: %s | decision=%s | avg=%.2f",
                attempt + 1,
                max_attempts,
                failure_reason,
                repair_decision.reason,
                report.score,
            )

            if attempt < max_attempts - 1 and progress_callback is not None:
                await progress_callback(
                    min(0.32 + attempt * 0.28, 0.86),
                    f"当前结果未通过统一质检，正在重试第 {attempt + 2}/{max_attempts} 次...",
                )

        if last_report is not None:
            logger.warning(
                "V14 final delivery failed after %d attempt(s): %s",
                max_attempts,
                summarize_final_delivery_failure(last_report.verifiability, gender=gender),
            )
        return OrchestratedPhoto()


production_orchestrator_service = ProductionOrchestratorService()
