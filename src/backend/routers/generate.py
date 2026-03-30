"""生成管线与视觉主题目录。"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Awaitable, Callable

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from config import settings
from context.briefs import get_brief
from context.prompt_assembler import (
    assemble_generation_prompt,
    assemble_nano_repair_prompt,
)
from context.reference_selector import select_references
from context.slot_renderer import render_slots
from context.thresholds import RepairMode, decide_repair, meets_delivery_floor
from context.variant_planner import get_variants
from models.database import (
    count_deliverables,
    create_deliverable,
    get_order,
    get_task,
    save_task,
    update_generation_batch,
    update_order,
    update_task,
)
from models.schemas import (
    DeliverableInfo,
    GenerateRequest,
    GenerateResponse,
    PackageCategory,
    PackageInfo,
    TaskStatus,
    TaskStatusEnum,
)
from services.delivery_image import prepare_delivery_image
from services.director import director_service
from services.gpt_image import gpt_image_service
from services.nano_banana import nano_banana_service
from services.vlm_checker import vlm_checker_service
from utils.storage import save_generated_image, user_upload_dir

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])

_tasks: dict[str, TaskStatus] = {}
_task_owners: dict[str, str] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class GeneratedAsset:
    url: str
    storage_path: str
    quality_score: float
    delivery_tier: str = "4k"


@dataclass
class GenerationOutcome:
    status: TaskStatusEnum
    progress: int
    message: str
    quality_score: float
    result_urls: list[str]
    assets: list[GeneratedAsset]
    failure_reason: str = ""


PACKAGES: dict[str, PackageInfo] = {
    "iceland": PackageInfo(
        id="iceland",
        name="冰岛极光",
        tag="热门",
        category=PackageCategory.travel,
        preview_url="/images/package-iceland.png",
    ),
    "french": PackageInfo(
        id="french",
        name="法式庄园",
        tag="",
        category=PackageCategory.western,
        preview_url="/images/package-french.png",
    ),
    "cyberpunk": PackageInfo(
        id="cyberpunk",
        name="赛博朋克",
        tag="新品",
        category=PackageCategory.artistic,
        preview_url="/images/package-cyberpunk.png",
    ),
    "minimal": PackageInfo(
        id="minimal",
        name="极简影棚",
        tag="",
        category=PackageCategory.artistic,
        preview_url="/images/package-minimal.png",
    ),
    "onsen": PackageInfo(
        id="onsen",
        name="日式温泉",
        tag="",
        category=PackageCategory.travel,
        preview_url="/images/package-onsen.png",
    ),
    "starcamp": PackageInfo(
        id="starcamp",
        name="星空露营",
        tag="",
        category=PackageCategory.travel,
        preview_url="/images/package-starcamp.png",
    ),
    "chinese-classic": PackageInfo(
        id="chinese-classic",
        name="中式经典",
        tag="热门",
        category=PackageCategory.chinese,
        preview_url="/images/hero-bg.png",
    ),
    "western-romantic": PackageInfo(
        id="western-romantic",
        name="西式浪漫",
        tag="",
        category=PackageCategory.western,
        preview_url="/images/featured-minimal.png",
    ),
    "artistic-fantasy": PackageInfo(
        id="artistic-fantasy",
        name="艺术幻想",
        tag="新品",
        category=PackageCategory.artistic,
        preview_url="/images/featured-iceland.png",
    ),
    "travel-destination": PackageInfo(
        id="travel-destination",
        name="旅拍风光",
        tag="",
        category=PackageCategory.travel,
        preview_url="/images/hero-bg.png",
    ),
}


async def _dual_path_fix(
    img_bytes: bytes,
    report,
    render_prompt: str,
    refs: list[tuple[bytes, str]],
    user_id: str,
) -> bytes:
    physical = report.physical_issues
    emotional = report.emotional_issues
    result = img_bytes

    def _select_hints(issues) -> list[str]:
        if not report.repair_hints:
            return [issue.description for issue in issues]
        if physical and emotional:
            return [issue.description for issue in issues]
        return list(report.repair_hints)

    async def _apply_nano_fix(issues, focus: str) -> bytes:
        fix_prompt = assemble_nano_repair_prompt(
            render_prompt=render_prompt,
            repair_hints=_select_hints(issues),
            has_identity_refs=bool(refs),
            focus=focus,
        )
        return await nano_banana_service.repair_with_references(
            prompt=fix_prompt,
            image_data=result,
            reference_images=refs,
        )

    if physical:
        try:
            result = await _apply_nano_fix(physical, "physical")
            logger.info("Physical fix applied for user %s", user_id)
        except Exception:
            logger.warning("Physical fix via Nano failed for user %s", user_id)

    if emotional:
        if settings.enable_gpt_image_repairs:
            fix_prompt = assemble_nano_repair_prompt(
                render_prompt=render_prompt,
                repair_hints=_select_hints(emotional),
                has_identity_refs=bool(refs),
                focus="emotional",
            )
            try:
                _, tmp_path = await save_generated_image(user_id, result, ext=".png")
                edit_url = await gpt_image_service.edit(image_path=tmp_path, prompt=fix_prompt)
                import httpx as _httpx

                async with _httpx.AsyncClient(timeout=60) as client:
                    resp = await client.get(edit_url)
                    resp.raise_for_status()
                    result = resp.content
                logger.info("Emotional fix applied via GPT for user %s", user_id)
                return result
            except Exception:
                logger.warning(
                    "Emotional fix via GPT failed for user %s; falling back to Nano",
                    user_id,
                )

        try:
            result = await _apply_nano_fix(emotional, "emotional")
            logger.info("Emotional fix applied via Nano for user %s", user_id)
        except Exception:
            logger.warning("Emotional fix via Nano failed for user %s", user_id)

    return result


async def _run_generation(
    req: GenerateRequest,
    *,
    photos_per_package: int,
    notify: Callable[..., Awaitable[None]],
) -> GenerationOutcome:
    if not settings.nano_banana_api_key:
        return GenerationOutcome(
            status=TaskStatusEnum.failed,
            progress=100,
            message="Nano Banana service not configured. Set LAOZHANG_NANO_API_KEY or LAOZHANG_API_KEY.",
            quality_score=0.0,
            result_urls=[],
            assets=[],
            failure_reason="Nano Banana service not configured.",
        )
    if req.package_id not in PACKAGES:
        return GenerationOutcome(
            status=TaskStatusEnum.failed,
            progress=100,
            message=f"Invalid package_id: '{req.package_id}'",
            quality_score=0.0,
            result_urls=[],
            assets=[],
            failure_reason=f"Invalid package_id: '{req.package_id}'",
        )

    await notify(
        status=TaskStatusEnum.processing,
        progress=5,
        message="筛选参考图...",
    )

    try:
        upload_dir = user_upload_dir(req.user_id)
        ref_set = select_references(upload_dir)
        selected_refs = ref_set.all_refs

        await notify(
            progress=8,
            message=(
                f"找到 {ref_set.count} 张参考图，准备创意方案..."
                if ref_set.has_identity
                else "未找到参考图，将生成风格样片..."
            ),
        )

        brief = get_brief(req.package_id)
        makeup = req.makeup_style.value if req.makeup_style else "natural"
        gender = req.gender.value if req.gender else "couple"
        preferences = {
            key: value
            for key, value in {
                "groom_style": req.groom_style,
                "bride_style": req.bride_style,
            }.items()
            if value
        } or None

        slots = render_slots(
            makeup_style=makeup,
            gender=gender,
            preferences=preferences,
        )

        if preferences:
            await notify(message="根据您的偏好调整创意方案...")
            brief = await director_service.edit_brief(brief, preferences)

        max_fix_rounds = max(settings.max_fix_rounds, 1)
        variants = get_variants(brief, count=max(photos_per_package, 1))

        await notify(
            progress=12,
            message=f"创意方案就绪：{brief.story[:30]}...",
        )

        assets: list[GeneratedAsset] = []
        total_score = 0.0
        rejected_photos = 0
        degraded_photos = 0

        for index, variant in enumerate(variants):
            step_base = 12 + index * (88 // max(photos_per_package, 1))
            prompt = assemble_generation_prompt(
                brief=brief,
                variant=variant,
                slots=slots,
                has_refs=ref_set.has_identity,
                has_couple_refs=ref_set.has_couple_identity,
                has_couple_anchor=ref_set.has_couple_anchor,
            )

            await notify(
                progress=step_base,
                message=f"正在生成第 {index + 1}/{photos_per_package} 张...",
            )

            img_bytes: bytes | None = None
            for attempt in range(3):
                try:
                    if selected_refs:
                        img_bytes = await nano_banana_service.multi_reference_generate(
                            prompt=prompt,
                            reference_images=selected_refs,
                        )
                    else:
                        img_bytes = await nano_banana_service.text_to_image(prompt=prompt)
                    break
                except Exception:
                    logger.warning(
                        "Generation attempt %d failed for user %s photo %d",
                        attempt + 1,
                        req.user_id,
                        index + 1,
                        exc_info=True,
                    )
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2)

            if img_bytes is None:
                continue

            await notify(
                status=TaskStatusEnum.quality_check,
                progress=step_base + (44 // max(photos_per_package, 1)),
                message=f"质检第 {index + 1} 张...",
            )

            brief_summary = f"{brief.story} {brief.emotion}"
            photo_score = 0.0
            for fix_round in range(max_fix_rounds):
                report, _ = await vlm_checker_service.check_and_suggest_fix_prompt(
                    image_data=img_bytes,
                    original_prompt=prompt,
                    brief_summary=brief_summary,
                )
                photo_score = report.score

                if report.inspection_unavailable:
                    if not settings.allow_degraded_delivery_on_vlm_unavailable:
                        raise RuntimeError("质量检查服务暂不可用，已停止交付以避免输出未审图像")
                    photo_score = settings.quality_acceptable
                    degraded_photos += 1
                    logger.warning(
                        "Photo %d delivered via degraded path because quality check is unavailable",
                        index + 1,
                    )
                    break

                decision = decide_repair(
                    hard_fail=report.hard_fail,
                    identity_match=report.identity_match,
                    brief_alignment=report.brief_alignment,
                    aesthetic_score=report.aesthetic_score,
                    fix_round=fix_round,
                    max_rounds=max_fix_rounds,
                )

                logger.info(
                    "Photo %d decision: %s (%s)",
                    index + 1,
                    decision.mode.value,
                    decision.reason,
                )

                if decision.mode == RepairMode.deliver:
                    break
                if decision.mode == RepairMode.local_fix:
                    await notify(
                        status=TaskStatusEnum.processing,
                        message=f"修复第 {index + 1} 张（第 {fix_round + 1} 轮）...",
                    )
                    img_bytes = await _dual_path_fix(
                        img_bytes,
                        report,
                        prompt,
                        selected_refs,
                        req.user_id,
                    )
                    continue
                if decision.mode == RepairMode.regenerate:
                    await notify(
                        status=TaskStatusEnum.processing,
                        message=f"重新生成第 {index + 1} 张...",
                    )
                    try:
                        if selected_refs:
                            img_bytes = await nano_banana_service.multi_reference_generate(
                                prompt=prompt,
                                reference_images=selected_refs,
                            )
                        else:
                            img_bytes = await nano_banana_service.text_to_image(prompt=prompt)
                    except Exception:
                        logger.warning("Regeneration failed for photo %d", index + 1)
                        break
                    continue

                rejected_photos += 1
                logger.warning(
                    "Photo %d rejected after %d rounds: %s",
                    index + 1,
                    fix_round + 1,
                    decision.reason,
                )
                img_bytes = None
                break

            if img_bytes is None:
                continue

            if not meets_delivery_floor(photo_score):
                rejected_photos += 1
                logger.warning(
                    "Photo %d blocked by final delivery floor: %.2f",
                    index + 1,
                    photo_score,
                )
                continue

            total_score += photo_score
            delivery_bytes = await prepare_delivery_image(img_bytes)
            _, path = await save_generated_image(req.user_id, delivery_bytes)
            url = f"/api/files/outputs/{req.user_id}/{path.name}"
            assets.append(
                GeneratedAsset(
                    url=url,
                    storage_path=path.name,
                    quality_score=photo_score,
                ),
            )
            await notify(
                status=TaskStatusEnum.processing,
                progress=min(step_base + (80 // max(photos_per_package, 1)), 96),
                message=f"已完成 {len(assets)}/{photos_per_package} 张交付片...",
                quality_score=total_score / max(len(assets), 1),
                result_urls=[item.url for item in assets],
            )

        if not assets:
            if rejected_photos:
                message = "本次生成未产出可交付照片，请调整参考图或稍后重试"
            else:
                message = "生成未产出结果，请稍后重试"
            return GenerationOutcome(
                status=TaskStatusEnum.failed,
                progress=100,
                message=message,
                quality_score=0.0,
                result_urls=[],
                assets=[],
                failure_reason=message,
            )

        quality_score = total_score / max(len(assets), 1)
        if rejected_photos and degraded_photos:
            message = (
                f"生成完成，共交付 {len(assets)} 张，拦截 {rejected_photos} 张，"
                f"质检降级 {degraded_photos} 张，综合评分 {quality_score:.2f}"
            )
        elif rejected_photos:
            message = (
                f"生成完成，共交付 {len(assets)} 张，拦截 {rejected_photos} 张，"
                f"综合评分 {quality_score:.2f}"
            )
        elif degraded_photos:
            message = (
                f"生成完成，共 {len(assets)} 张，质检降级 {degraded_photos} 张，"
                f"综合评分 {quality_score:.2f}"
            )
        else:
            message = f"生成完成，共 {len(assets)} 张，综合评分 {quality_score:.2f}"

        return GenerationOutcome(
            status=TaskStatusEnum.completed,
            progress=100,
            message=message,
            quality_score=quality_score,
            result_urls=[item.url for item in assets],
            assets=assets,
        )

    except RuntimeError as exc:
        logger.error("Generation failed for user %s: %s", req.user_id, exc)
        return GenerationOutcome(
            status=TaskStatusEnum.failed,
            progress=100,
            message=str(exc),
            quality_score=0.0,
            result_urls=[],
            assets=[],
            failure_reason=str(exc),
        )
    except Exception:
        logger.exception("Generation failed unexpectedly for user %s", req.user_id)
        return GenerationOutcome(
            status=TaskStatusEnum.failed,
            progress=100,
            message="生成过程中发生内部错误",
            quality_score=0.0,
            result_urls=[],
            assets=[],
            failure_reason="生成过程中发生内部错误",
        )


async def _update_task_state(task_id: str, **fields) -> None:
    task = _tasks.get(task_id)
    if task is None:
        task = TaskStatus(
            task_id=task_id,
            status=TaskStatusEnum.pending,
            progress=0,
            message="任务已创建，等待启动...",
        )
        _tasks[task_id] = task

    for key, value in fields.items():
        if value is not None:
            setattr(task, key, value)

    await update_task(
        task_id,
        status=task.status.value,
        progress=task.progress,
        quality_score=task.quality_score,
        message=task.message,
        result_urls=task.result_urls,
    )


async def _generation_pipeline(task_id: str, req: GenerateRequest) -> None:
    async def notify(**fields) -> None:
        await _update_task_state(task_id, **fields)

    outcome = await _run_generation(
        req,
        photos_per_package=max(settings.photos_per_package, 1),
        notify=notify,
    )
    await _update_task_state(
        task_id,
        status=outcome.status,
        progress=outcome.progress,
        message=outcome.message,
        quality_score=outcome.quality_score,
        result_urls=outcome.result_urls,
    )


async def generate_order_batch(
    order_id: str,
    batch_id: str,
    req: GenerateRequest,
    *,
    requested_photos: int,
) -> None:
    await update_order(order_id, fulfillment_status="processing")
    await update_generation_batch(
        batch_id,
        status="processing",
        started_at=_now_iso(),
    )

    async def notify(**fields) -> None:
        batch_updates: dict[str, object] = {}
        if "status" in fields and fields["status"] is not None:
            status = fields["status"]
            batch_updates["status"] = (
                "processing" if status != TaskStatusEnum.failed else "failed"
            )
        if "progress" in fields and fields["progress"] is not None:
            batch_updates["progress"] = fields["progress"]
        if "message" in fields and fields["message"] is not None:
            batch_updates["message"] = fields["message"]
        if "quality_score" in fields and fields["quality_score"] is not None:
            batch_updates["quality_score"] = fields["quality_score"]
        if "result_urls" in fields and fields["result_urls"] is not None:
            batch_updates["delivered_photos"] = len(fields["result_urls"])
        if batch_updates:
            await update_generation_batch(batch_id, **batch_updates)

    outcome = await _run_generation(
        req,
        photos_per_package=max(requested_photos, 1),
        notify=notify,
    )

    if outcome.status == TaskStatusEnum.completed:
        for asset in outcome.assets:
            await create_deliverable(
                order_id,
                batch_id,
                req.user_id,
                storage_kind="outputs",
                storage_path=asset.storage_path,
                url=asset.url,
                quality_score=asset.quality_score,
                delivery_tier=asset.delivery_tier,
            )

        order = await get_order(order_id)
        deliverable_count = await count_deliverables(order_id)
        promised_photos = int(order["entitlement_snapshot"].get("promised_photos", deliverable_count)) if order else deliverable_count
        fulfillment_status = (
            "delivered" if deliverable_count >= promised_photos else "partially_delivered"
        )
        await update_generation_batch(
            batch_id,
            status="completed",
            progress=100,
            message=outcome.message,
            quality_score=outcome.quality_score,
            delivered_photos=len(outcome.assets),
            completed_at=_now_iso(),
        )
        await update_order(order_id, fulfillment_status=fulfillment_status)
        return

    await update_generation_batch(
        batch_id,
        status="failed",
        progress=100,
        message=outcome.message,
        failure_reason=outcome.failure_reason,
        completed_at=_now_iso(),
    )
    await update_order(order_id, fulfillment_status="failed")


@router.get("/api/packages", response_model=list[PackageInfo])
async def list_packages():
    return list(PACKAGES.values())


@router.get("/api/packages/{package_id}", response_model=PackageInfo)
async def get_package(package_id: str):
    pkg = PACKAGES.get(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found")
    return pkg


@router.post("/api/generate", response_model=GenerateResponse)
async def create_generation_task(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
    request: Request,
):
    if request.state.user_id != req.user_id:
        raise HTTPException(status_code=403, detail="Session token does not match user_id")
    if not settings.nano_banana_api_key:
        raise HTTPException(
            status_code=503,
            detail="Nano Banana service not configured. Set LAOZHANG_NANO_API_KEY or LAOZHANG_API_KEY.",
        )
    if req.package_id not in PACKAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid package_id: '{req.package_id}'. Available: {list(PACKAGES.keys())}",
        )

    task_id = uuid.uuid4().hex[:16]
    _tasks[task_id] = TaskStatus(
        task_id=task_id,
        status=TaskStatusEnum.pending,
        progress=0,
        message="任务已创建，等待启动...",
    )
    _task_owners[task_id] = req.user_id
    await save_task(task_id, req.user_id, req.package_id, status=TaskStatusEnum.pending.value)
    background_tasks.add_task(_generation_pipeline, task_id, req)
    return GenerateResponse(task_id=task_id, status=TaskStatusEnum.pending)


@router.get("/api/generate/{task_id}/status", response_model=TaskStatus)
async def get_task_status(task_id: str, request: Request):
    owner = _task_owners.get(task_id)
    if owner and owner != request.state.user_id:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    task = _tasks.get(task_id)
    if task is None:
        row = await get_task(task_id)
        if row is None or row["user_id"] != request.state.user_id:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        task = TaskStatus(**row)
    return task


@router.get("/api/generate/{task_id}/result")
async def get_task_result(task_id: str, request: Request):
    row = await get_task(task_id)
    if row is None or row["user_id"] != request.state.user_id:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    task = TaskStatus(**row)
    if task.status == TaskStatusEnum.failed:
        raise HTTPException(status_code=500, detail=task.message)
    if task.status != TaskStatusEnum.completed:
        raise HTTPException(
            status_code=202,
            detail=f"Task is still {task.status.value}. Progress: {task.progress}%",
        )
    return {
        "task_id": task.task_id,
        "status": task.status.value,
        "quality_score": task.quality_score,
        "result_urls": task.result_urls,
    }
