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
from context.reference_selector import select_references
from context.slot_renderer import render_slots
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
    DeliverableKind,
    GenerateRequest,
    GenerateResponse,
    PackageCategory,
    PackageInfo,
    ResultAssetInfo,
    TaskStatus,
    TaskStatusEnum,
)
from services.delivery_image import prepare_delivery_image
from services.director import director_service
from services.makeup_reference import resolve_selected_makeup_reference
from services.nano_banana import NanoRequestTooLargeError, nano_banana_service
from services.production_orchestrator import production_orchestrator_service
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
    photo_status: str = DeliverableKind.final_select.value
    user_visible: bool = True
    result_asset: ResultAssetInfo | None = None


@dataclass
class GenerationOutcome:
    status: TaskStatusEnum
    progress: int
    message: str
    quality_score: float
    result_urls: list[str]
    assets: list[GeneratedAsset]
    result_assets: list[ResultAssetInfo] | None = None
    failure_reason: str = ""


def _visible_generated_assets(assets: list[GeneratedAsset]) -> list[GeneratedAsset]:
    return [asset for asset in assets if asset.user_visible]


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
        gender = req.gender.value if req.gender else "couple"
        ref_set = select_references(upload_dir, gender=gender)

        await notify(
            progress=8,
            message=(
                f"找到 {ref_set.count} 张参考图，准备创意方案..."
                if ref_set.has_identity
                else "未找到参考图，将生成风格样片..."
            ),
        )

        brief = get_brief(req.package_id)
        bride_makeup_style = (
            req.bride_makeup_style.value
            if req.bride_makeup_style
            else (req.makeup_style.value if req.makeup_style else "refined")
        )
        groom_makeup_style = (
            req.groom_makeup_style.value
            if req.groom_makeup_style
            else (req.makeup_style.value if req.makeup_style else "natural")
        )
        preferences = {
            key: value
            for key, value in {
                "groom_style": req.groom_style,
                "bride_style": req.bride_style,
            }.items()
            if value
        } or None

        slots = render_slots(
            makeup_style=req.makeup_style.value if req.makeup_style else "natural",
            gender=gender,
            preferences=preferences,
            bride_makeup_style=bride_makeup_style,
            groom_makeup_style=groom_makeup_style,
        )

        bride_makeup_ref = await resolve_selected_makeup_reference(
            req.user_id,
            "female",
            bride_makeup_style,
            req.bride_makeup_reference_url,
        )
        groom_makeup_ref = await resolve_selected_makeup_reference(
            req.user_id,
            "male",
            groom_makeup_style,
            req.groom_makeup_reference_url,
        )

        if preferences:
            await notify(message="根据您的偏好调整创意方案...")
            brief = await director_service.edit_brief(brief, preferences)

        variants = get_variants(brief, count=max(photos_per_package, 1))

        await notify(
            progress=12,
            message=f"创意方案就绪：{brief.story[:30]}...",
        )

        assets: list[GeneratedAsset] = []
        total_score = 0.0
        rejected_photos = 0
        visible_assets = 0
        photo_span = max(88 // max(photos_per_package, 1), 1)

        for index, variant in enumerate(variants):
            step_base = 12 + index * photo_span
            quality_check_progress = min(step_base + max(44 // max(photos_per_package, 1), 8), 96)
            post_photo_progress = min(step_base + max(80 // max(photos_per_package, 1), 16), 96)

            await notify(
                progress=step_base,
                message=f"正在生成第 {index + 1}/{photos_per_package} 张正式成片...",
            )

            for attempt in range(3):
                try:
                    async def report_photo_progress(stage_progress: float, stage_message: str) -> None:
                        bounded_progress = max(0.0, min(stage_progress, 1.0))
                        dynamic_ceiling = max(quality_check_progress - 1, step_base + 1)
                        mapped_progress = min(
                            step_base + 1 + int((dynamic_ceiling - step_base - 1) * bounded_progress),
                            dynamic_ceiling,
                        )
                        await notify(
                            progress=mapped_progress,
                            message=f"第 {index + 1}/{photos_per_package} 张: {stage_message}",
                        )

                    orchestrated_photo = await production_orchestrator_service.run_photo(
                        brief=brief,
                        hero_variant=variant,
                        slots=slots,
                        gender=gender,
                        ref_set=ref_set if ref_set.has_identity else None,
                        bride_makeup_ref=bride_makeup_ref if gender in {"couple", "female"} else None,
                        groom_makeup_ref=groom_makeup_ref if gender in {"couple", "male"} else None,
                        progress_callback=report_photo_progress,
                    )
                    break
                except NanoRequestTooLargeError as exc:
                    raise RuntimeError(
                        "参考图请求体积仍然过大，请保留清晰近照，避免超大原图后重试"
                    ) from exc
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
                    await notify(
                        progress=max(step_base + 1, min(quality_check_progress - 1, step_base + 3)),
                        message=f"第 {index + 1}/{photos_per_package} 张正式成片遇到波动，正在重试第 {attempt + 2}/3 次...",
                    )
                    await asyncio.sleep(2)

            if not orchestrated_photo.assets:
                rejected_photos += 1
                continue

            await notify(
                status=TaskStatusEnum.quality_check,
                progress=quality_check_progress,
                message=f"第 {index + 1}/{photos_per_package} 张正在统一质检...",
            )

            for staged_asset in orchestrated_photo.assets:
                delivery_bytes = await prepare_delivery_image(staged_asset.image_data)
                _, path = await save_generated_image(req.user_id, delivery_bytes)
                url = f"/api/files/outputs/{req.user_id}/{path.name}"
                result_asset = ResultAssetInfo(
                    url=url,
                    kind=staged_asset.kind,
                    track=staged_asset.track,
                    quality_score=staged_asset.quality_score,
                    user_visible=staged_asset.user_visible,
                    verifiability=staged_asset.verifiability,
                    notes=staged_asset.notes,
                )
                assets.append(
                    GeneratedAsset(
                        url=url,
                        storage_path=path.name,
                        quality_score=staged_asset.quality_score,
                        photo_status=staged_asset.kind.value,
                        user_visible=staged_asset.user_visible,
                        result_asset=result_asset,
                    ),
                )
                if staged_asset.user_visible:
                    total_score += staged_asset.quality_score
                    visible_assets += 1

            if not any(asset.user_visible for asset in orchestrated_photo.assets):
                rejected_photos += 1
                logger.warning("Photo %d produced no visible deliverable", index + 1)
                continue

            await notify(
                status=TaskStatusEnum.processing,
                progress=post_photo_progress,
                message=f"已完成 {visible_assets}/{photos_per_package} 张正式交付片...",
                quality_score=total_score / max(visible_assets, 1),
                result_urls=[item.url for item in assets if item.user_visible],
                result_assets=[
                    item.result_asset.model_dump()
                    for item in assets
                    if item.result_asset is not None
                ],
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

        visible_generated_assets = _visible_generated_assets(assets)
        quality_score = total_score / max(visible_assets, 1)
        final_count = len([item for item in visible_generated_assets if item.photo_status == DeliverableKind.final_select.value])
        if rejected_photos:
            message = (
                f"生成完成，正式交付 {final_count} 张，拦截 {rejected_photos} 张，"
                f"综合评分 {quality_score:.2f}"
            )
        else:
            message = (
                f"生成完成，正式交付 {final_count} 张，"
                f"综合评分 {quality_score:.2f}"
            )

        return GenerationOutcome(
            status=TaskStatusEnum.completed,
            progress=100,
            message=message,
            quality_score=quality_score,
            result_urls=[item.url for item in visible_generated_assets],
            assets=assets,
            result_assets=[
                item.result_asset
                for item in assets
                if item.result_asset is not None
            ],
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
        result_assets=[
            item.model_dump() if hasattr(item, "model_dump") else item
            for item in task.result_assets
        ],
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
        result_assets=outcome.result_assets or [],
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
        visible_assets = _visible_generated_assets(outcome.assets)
        for asset in visible_assets:
            await create_deliverable(
                order_id,
                batch_id,
                req.user_id,
                storage_kind="outputs",
                storage_path=asset.storage_path,
                url=asset.url,
                quality_score=asset.quality_score,
                delivery_tier=asset.delivery_tier,
                photo_status=asset.photo_status,
                metadata=(
                    asset.result_asset.model_dump()
                    if asset.result_asset is not None
                    else {}
                ),
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
            delivered_photos=len(visible_assets),
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
        "result_assets": [item.model_dump() for item in task.result_assets],
    }
