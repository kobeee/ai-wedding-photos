from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, BackgroundTasks

from config import settings
from models.schemas import (
    GenerateRequest,
    GenerateResponse,
    TaskStatus,
    TaskStatusEnum,
    PackageInfo,
    PackageCategory,
    IssueCategory,
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

def _collect_reference_images(user_id: str) -> list[tuple[bytes, str]]:
    """收集用户上传的所有照片作为参考图（同步读取）。"""
    upload_dir = user_upload_dir(user_id)
    refs: list[tuple[bytes, str]] = []
    for ext_pattern in ("*.jpg", "*.jpeg", "*.png"):
        for fpath in sorted(upload_dir.glob(ext_pattern)):
            data = fpath.read_bytes()
            mime = "image/png" if fpath.suffix.lower() == ".png" else "image/jpeg"
            refs.append((data, mime))
            if len(refs) >= 6:
                return refs
    return refs


async def _dual_path_fix(
    img_bytes: bytes,
    report,
    render_prompt: str,
    refs: list[tuple[bytes, str]],
    user_id: str,
) -> bytes:
    """
    双路径修复：
    - physical issues → Nano Banana 局部重绘
    - emotional issues → GPT Image I2I 修复
    """
    physical = report.physical_issues
    emotional = report.emotional_issues

    result = img_bytes

    if physical:
        phys_desc = "; ".join(i.description for i in physical)
        fix_prompt = (
            f"Fix these physical issues in the wedding photo: {phys_desc}. "
            f"Maintain the original composition and style. "
            f"Ensure correct anatomy, no artifacts, consistent lighting."
        )
        try:
            result = await nano_banana_service.image_to_image(
                prompt=fix_prompt,
                image_data=result,
            )
            logger.info("Physical fix applied for user %s", user_id)
        except Exception:
            logger.warning("Physical fix via Nano failed for user %s", user_id)

    if emotional:
        emo_desc = "; ".join(i.description for i in emotional)
        fix_prompt = (
            f"Improve the emotional quality: {emo_desc}. "
            f"Make expressions more natural and warm. "
            f"Keep the same scene, lighting, and wardrobe."
        )
        try:
            # 保存临时文件给 GPT edit API
            _, tmp_path = await save_generated_image(user_id, result, ext=".png")
            edit_url = await gpt_image_service.edit(
                image_path=tmp_path,
                prompt=fix_prompt,
            )
            # 下载编辑后的图片
            import httpx as _httpx
            async with _httpx.AsyncClient(timeout=60) as client:
                resp = await client.get(edit_url)
                resp.raise_for_status()
                result = resp.content
            logger.info("Emotional fix applied for user %s", user_id)
        except Exception:
            logger.warning("Emotional fix via GPT failed for user %s", user_id)

    return result


async def _generation_pipeline(task_id: str, req: GenerateRequest) -> None:
    """
    生成流水线（后台任务）:
    1. 收集参考图
    2. Director 生成 Camera Schema → 渲染 Prompt
    3. Nano Banana Pro 生成底图
    4. VLM 质检 + 双路径修复（最多 3 轮）
    5. 质量评分决定流程走向
    """
    task = _tasks[task_id]
    task.status = TaskStatusEnum.processing
    task.message = "收集参考图..."
    task.progress = 5

    try:
        # Step 1: 收集参考图
        refs = _collect_reference_images(req.user_id)
        task.progress = 10
        task.message = f"找到 {len(refs)} 张参考图，正在生成拍摄方案..."

        # Step 2: Director 生成 Camera Schema
        makeup = req.makeup_style.value if req.makeup_style else "natural"
        gender = req.gender.value if req.gender else "female"

        camera_schema, base_prompt = await director_service.direct(
            package_id=req.package_id,
            makeup_style=makeup,
            gender=gender,
            preferences={
                k: v for k, v in {
                    "groom_style": req.groom_style,
                    "bride_style": req.bride_style,
                }.items() if v
            } or None,
        )
        task.progress = 15
        task.message = f"拍摄方案就绪：{camera_schema.scene[:30]}..."

        result_urls: list[str] = []
        total_score = 0.0

        # 变体 prompt 后缀
        variant_hints = [
            "Close-up intimate portrait, gentle expressions.",
            "Full-body shot, both standing side by side.",
            "Candid moment, looking at each other with genuine smiles.",
            "Artistic angle, walking together into the distance.",
        ]

        photos_per_package = max(settings.photos_per_package, 1)
        max_fix_rounds = max(settings.max_fix_rounds, 1)

        for i in range(photos_per_package):
            step_base = 15 + i * 20

            variant_prompt = f"{base_prompt} {variant_hints[i % len(variant_hints)]}"
            task.progress = step_base
            task.message = f"正在生成第 {i + 1}/{photos_per_package} 张..."

            # Step 3: 生成底图
            img_bytes: bytes | None = None
            for attempt in range(3):
                try:
                    if refs:
                        img_bytes = await nano_banana_service.multi_reference_generate(
                            prompt=variant_prompt,
                            reference_images=refs,
                        )
                    else:
                        img_bytes = await nano_banana_service.text_to_image(
                            prompt=variant_prompt,
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

            task.progress = step_base + 8
            task.message = f"质检第 {i + 1} 张..."
            task.status = TaskStatusEnum.quality_check

            # Step 4: VLM 质检 + 双路径修复循环
            photo_score = 0.0
            for fix_round in range(max_fix_rounds):
                report, fix_prompt = await vlm_checker_service.check_and_suggest_fix_prompt(
                    image_data=img_bytes,
                    original_prompt=variant_prompt,
                )
                photo_score = report.score

                logger.info(
                    "Photo %d round %d: score=%.2f, passed=%s, issues=%d",
                    i + 1, fix_round + 1, report.score, report.passed,
                    len(report.issues),
                )

                # 质量评分决策
                if report.score >= settings.quality_excellent:
                    # 优秀，直接交付
                    break
                elif report.score >= settings.quality_acceptable:
                    # 合格，可以交付
                    break
                elif report.score >= settings.quality_fixable:
                    # 需修复
                    if fix_round < max_fix_rounds - 1:
                        task.message = f"修复第 {i + 1} 张（第 {fix_round + 1} 轮）..."
                        task.status = TaskStatusEnum.processing
                        img_bytes = await _dual_path_fix(
                            img_bytes, report, variant_prompt, refs, req.user_id,
                        )
                    # 最后一轮修复后直接用
                else:
                    # < 0.70 重新生成
                    if fix_round < max_fix_rounds - 1:
                        task.message = f"重新生成第 {i + 1} 张..."
                        task.status = TaskStatusEnum.processing
                        try:
                            if refs:
                                img_bytes = await nano_banana_service.multi_reference_generate(
                                    prompt=variant_prompt,
                                    reference_images=refs,
                                )
                            else:
                                img_bytes = await nano_banana_service.text_to_image(
                                    prompt=variant_prompt,
                                )
                        except Exception:
                            logger.warning("Regeneration failed for photo %d", i + 1)
                            break

            total_score += photo_score

            # 保存结果
            file_id, path = await save_generated_image(req.user_id, img_bytes)
            url = f"/api/files/outputs/{req.user_id}/{path.name}"
            result_urls.append(url)
            task.status = TaskStatusEnum.processing

        # Step 5: 完成
        task.result_urls = result_urls
        task.progress = 100
        task.status = TaskStatusEnum.completed
        task.quality_score = total_score / max(len(result_urls), 1)
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
