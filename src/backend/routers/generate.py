"""生成管线 — 基于上下文工程的 AI 婚纱照生成。

Phase 1 改造：
- Director CameraSchema → context/ CreativeBrief
- _collect_reference_images → reference_selector.select_references
- 硬编码 variant_hints → variant_planner.get_variants
- 机械拼接 prompt → prompt_assembler.assemble_generation_prompt
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, HTTPException, BackgroundTasks

from config import settings
from context.briefs import get_brief
from context.prompt_assembler import (
    assemble_generation_prompt,
    assemble_nano_repair_prompt,
)
from context.reference_selector import select_references
from context.slot_renderer import render_slots
from context.thresholds import decide_repair, meets_delivery_floor, RepairMode
from context.variant_planner import get_variants
from models.schemas import (
    GenerateRequest,
    GenerateResponse,
    TaskStatus,
    TaskStatusEnum,
    PackageInfo,
    PackageCategory,
)
from services.director import director_service
from services.nano_banana import nano_banana_service
from services.gpt_image import gpt_image_service
from services.vlm_checker import vlm_checker_service
from utils.storage import (
    save_generated_image,
    user_upload_dir,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])

# ---- 内存任务存储 (Stream C 会替换为 SQLite) ----
_tasks: dict[str, TaskStatus] = {}

# ---- 套餐定义 ----
PACKAGES: dict[str, PackageInfo] = {
    "iceland": PackageInfo(
        id="iceland", name="冰岛极光", tag="热门",
        category=PackageCategory.travel,
    ),
    "french": PackageInfo(
        id="french", name="法式庄园", tag="",
        category=PackageCategory.western,
    ),
    "cyberpunk": PackageInfo(
        id="cyberpunk", name="赛博朋克", tag="新品",
        category=PackageCategory.artistic,
    ),
    "minimal": PackageInfo(
        id="minimal", name="极简影棚", tag="",
        category=PackageCategory.artistic,
    ),
    "onsen": PackageInfo(
        id="onsen", name="日式温泉", tag="",
        category=PackageCategory.travel,
    ),
    "starcamp": PackageInfo(
        id="starcamp", name="星空露营", tag="",
        category=PackageCategory.travel,
    ),
    # 兼容旧 ID
    "chinese-classic": PackageInfo(
        id="chinese-classic", name="中式经典", tag="热门",
        category=PackageCategory.chinese,
    ),
    "western-romantic": PackageInfo(
        id="western-romantic", name="西式浪漫", tag="",
        category=PackageCategory.western,
    ),
    "artistic-fantasy": PackageInfo(
        id="artistic-fantasy", name="艺术幻想", tag="新品",
        category=PackageCategory.artistic,
    ),
    "travel-destination": PackageInfo(
        id="travel-destination", name="旅拍风光", tag="",
        category=PackageCategory.travel,
    ),
}


async def _dual_path_fix(
    img_bytes: bytes,
    report,
    render_prompt: str,
    refs: list[tuple[bytes, str]],
    user_id: str,
) -> bytes:
    """修复流程：默认统一走 Nano，保留 GPT 接口作为受控预留能力。"""
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
                edit_url = await gpt_image_service.edit(
                    image_path=tmp_path,
                    prompt=fix_prompt,
                )
                import httpx as _httpx
                async with _httpx.AsyncClient(timeout=60) as client:
                    resp = await client.get(edit_url)
                    resp.raise_for_status()
                    result = resp.content
                logger.info("Emotional fix applied via GPT for user %s", user_id)
                return result
            except Exception:
                logger.warning("Emotional fix via GPT failed for user %s; falling back to Nano", user_id)

        try:
            result = await _apply_nano_fix(emotional, "emotional")
            logger.info("Emotional fix applied via Nano for user %s", user_id)
        except Exception:
            logger.warning("Emotional fix via Nano failed for user %s", user_id)

    return result


async def _generation_pipeline(task_id: str, req: GenerateRequest) -> None:
    """生成流水线（基于上下文工程重构）:

    1. 筛选参考图（reference_selector）
    2. 获取 Creative Brief + 渲染动态插槽
    3. 按 variant 逐张生成
    4. VLM 质检 + 双路径修复（最多 N 轮）
    """
    task = _tasks[task_id]
    task.status = TaskStatusEnum.processing
    task.message = "筛选参考图..."
    task.progress = 5

    try:
        # Step 1: 筛选参考图
        upload_dir = user_upload_dir(req.user_id)
        ref_set = select_references(upload_dir)
        selected_refs = ref_set.all_refs

        task.progress = 8
        if ref_set.has_identity:
            task.message = f"找到 {ref_set.count} 张参考图，准备创意方案..."
        else:
            task.message = "未找到参考图，将生成风格样片..."

        # Step 2: Creative Brief + 动态插槽
        brief = get_brief(req.package_id)

        makeup = req.makeup_style.value if req.makeup_style else "natural"
        gender = req.gender.value if req.gender else "couple"
        preferences = {
            k: v for k, v in {
                "groom_style": req.groom_style,
                "bride_style": req.bride_style,
            }.items() if v
        } or None

        slots = render_slots(
            makeup_style=makeup,
            gender=gender,
            preferences=preferences,
        )

        # Phase 3: Director 编辑模式 — 只在有偏好时调用
        if preferences:
            task.message = "根据您的偏好调整创意方案..."
            brief = await director_service.edit_brief(brief, preferences)

        # Step 3: 获取变体计划
        photos_per_package = max(settings.photos_per_package, 1)
        max_fix_rounds = max(settings.max_fix_rounds, 1)
        variants = get_variants(brief, count=photos_per_package)

        task.progress = 12
        task.message = f"创意方案就绪：{brief.story[:30]}..."

        result_urls: list[str] = []
        total_score = 0.0
        rejected_photos = 0
        degraded_photos = 0

        for i, variant in enumerate(variants):
            step_base = 12 + i * (88 // photos_per_package)

            # 组装 prompt
            prompt = assemble_generation_prompt(
                brief=brief,
                variant=variant,
                slots=slots,
                has_refs=ref_set.has_identity,
                has_couple_refs=ref_set.has_couple_identity,
            )

            task.progress = step_base
            task.message = f"正在生成第 {i + 1}/{photos_per_package} 张..."

            # Step 4: 生成底图
            img_bytes: bytes | None = None
            for attempt in range(3):
                try:
                    if selected_refs:
                        img_bytes = await nano_banana_service.multi_reference_generate(
                            prompt=prompt,
                            reference_images=selected_refs,
                        )
                    else:
                        img_bytes = await nano_banana_service.text_to_image(
                            prompt=prompt,
                        )
                    break
                except Exception:
                    logger.warning(
                        "Generation attempt %d failed for task %s photo %d",
                        attempt + 1, task_id, i + 1,
                    )
                    if attempt == 2:
                        raise
                    await asyncio.sleep(2)

            if img_bytes is None:
                continue

            task.progress = step_base + (44 // photos_per_package)
            task.message = f"质检第 {i + 1} 张..."
            task.status = TaskStatusEnum.quality_check

            # Step 5: VLM 质检 + thresholds 决策修复循环
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
                        raise RuntimeError(
                            "质量检查服务暂不可用，已停止交付以避免输出未审图像",
                        )
                    photo_score = settings.quality_acceptable
                    degraded_photos += 1
                    logger.warning(
                        "Photo %d delivered via degraded path because quality check is unavailable",
                        i + 1,
                    )
                    break

                logger.info(
                    "Photo %d round %d: score=%.2f, hard_fail=%s, "
                    "identity=%.2f, alignment=%.2f, aesthetic=%.2f, issues=%d",
                    i + 1, fix_round + 1, report.score, report.hard_fail,
                    report.identity_match, report.brief_alignment,
                    report.aesthetic_score, len(report.issues),
                )

                # Phase 2: thresholds 决策
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
                    i + 1, decision.mode.value, decision.reason,
                )

                if decision.mode == RepairMode.deliver:
                    break
                elif decision.mode == RepairMode.local_fix:
                    task.message = f"修复第 {i + 1} 张（第 {fix_round + 1} 轮）..."
                    task.status = TaskStatusEnum.processing
                    img_bytes = await _dual_path_fix(
                        img_bytes, report, prompt, selected_refs, req.user_id,
                    )
                elif decision.mode == RepairMode.regenerate:
                    task.message = f"重新生成第 {i + 1} 张..."
                    task.status = TaskStatusEnum.processing
                    try:
                        if selected_refs:
                            img_bytes = await nano_banana_service.multi_reference_generate(
                                prompt=prompt,
                                reference_images=selected_refs,
                            )
                        else:
                            img_bytes = await nano_banana_service.text_to_image(
                                prompt=prompt,
                            )
                    except Exception:
                        logger.warning("Regeneration failed for photo %d", i + 1)
                        break
                elif decision.mode == RepairMode.reject:
                    rejected_photos += 1
                    logger.warning(
                        "Photo %d rejected after %d rounds: %s",
                        i + 1,
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
                    i + 1,
                    photo_score,
                )
                continue

            # 保存结果
            total_score += photo_score
            _, path = await save_generated_image(req.user_id, img_bytes)
            url = f"/api/files/outputs/{req.user_id}/{path.name}"
            result_urls.append(url)
            task.status = TaskStatusEnum.processing

        # Step 6: 完成
        if not result_urls:
            task.progress = 100
            task.status = TaskStatusEnum.failed
            task.quality_score = 0.0
            if rejected_photos:
                task.message = "本次生成未产出可交付照片，请调整参考图或稍后重试"
            else:
                task.message = "生成未产出结果，请稍后重试"
            return

        task.result_urls = result_urls
        task.progress = 100
        task.status = TaskStatusEnum.completed
        task.quality_score = total_score / max(len(result_urls), 1)
        if rejected_photos and degraded_photos:
            task.message = (
                f"生成完成，共交付 {len(result_urls)} 张，拦截 {rejected_photos} 张，"
                f"质检降级 {degraded_photos} 张，综合评分 {task.quality_score:.2f}"
            )
        elif rejected_photos:
            task.message = (
                f"生成完成，共交付 {len(result_urls)} 张，拦截 {rejected_photos} 张，"
                f"综合评分 {task.quality_score:.2f}"
            )
        elif degraded_photos:
            task.message = (
                f"生成完成，共 {len(result_urls)} 张，质检降级 {degraded_photos} 张，"
                f"综合评分 {task.quality_score:.2f}"
            )
        else:
            task.message = f"生成完成，共 {len(result_urls)} 张，综合评分 {task.quality_score:.2f}"
        logger.info("Task %s completed: %d photos, score=%.2f",
                     task_id, len(result_urls), task.quality_score)

    except RuntimeError as exc:
        task.status = TaskStatusEnum.failed
        task.message = str(exc)
        logger.error("Task %s failed: %s", task_id, exc)
    except Exception:
        task.status = TaskStatusEnum.failed
        task.message = "生成过程中发生内部错误"
        logger.exception("Task %s failed unexpectedly", task_id)


# ---- Endpoints ----

@router.get("/api/packages", response_model=list[PackageInfo])
async def list_packages():
    """获取所有可用套餐列表。"""
    return list(PACKAGES.values())


@router.get("/api/packages/{package_id}", response_model=PackageInfo)
async def get_package(package_id: str):
    """获取单个套餐详情。"""
    pkg = PACKAGES.get(package_id)
    if not pkg:
        raise HTTPException(status_code=404, detail=f"Package '{package_id}' not found")
    return pkg


@router.post("/api/generate", response_model=GenerateResponse)
async def create_generation_task(
    req: GenerateRequest,
    background_tasks: BackgroundTasks,
):
    """创建婚纱照生成任务。"""
    if not settings.nano_banana_api_key:
        raise HTTPException(
            status_code=503,
            detail="Nano Banana service not configured. Set LAOZHANG_NANO_API_KEY or LAOZHANG_API_KEY.",
        )

    if req.package_id not in PACKAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid package_id: '{req.package_id}'. "
            f"Available: {list(PACKAGES.keys())}",
        )

    task_id = uuid.uuid4().hex[:16]
    task = TaskStatus(
        task_id=task_id,
        status=TaskStatusEnum.pending,
        progress=0,
        message="任务已创建，等待启动...",
    )
    _tasks[task_id] = task

    background_tasks.add_task(_generation_pipeline, task_id, req)

    return GenerateResponse(task_id=task_id, status=TaskStatusEnum.pending)


@router.get("/api/generate/{task_id}/status", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """查询生成任务进度。"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return task


@router.get("/api/generate/{task_id}/result")
async def get_task_result(task_id: str):
    """获取生成任务结果。"""
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

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
