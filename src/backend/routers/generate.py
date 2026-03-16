from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, HTTPException, BackgroundTasks

from config import settings
from models.schemas import (
    GenerateRequest,
    GenerateResponse,
    TaskStatus,
    TaskStatusEnum,
    PackageInfo,
    PackageCategory,
)
from services.nano_banana import nano_banana_service
from services.gpt_image import gpt_image_service
from services.vlm_checker import vlm_checker_service
from utils.storage import (
    save_generated_image,
    read_file_bytes,
    user_upload_dir,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generate"])

# ---- 内存任务存储 (生产环境应改用 Redis) ----
_tasks: dict[str, TaskStatus] = {}

# ---- 套餐定义 ----
PACKAGES: dict[str, PackageInfo] = {
    "chinese-classic": PackageInfo(
        id="chinese-classic",
        name="中式经典",
        tag="热门",
        category=PackageCategory.chinese,
        preview_url="/static/packages/chinese-classic.jpg",
    ),
    "western-romantic": PackageInfo(
        id="western-romantic",
        name="西式浪漫",
        tag="",
        category=PackageCategory.western,
        preview_url="/static/packages/western-romantic.jpg",
    ),
    "artistic-fantasy": PackageInfo(
        id="artistic-fantasy",
        name="艺术幻想",
        tag="新品",
        category=PackageCategory.artistic,
        preview_url="/static/packages/artistic-fantasy.jpg",
    ),
    "travel-destination": PackageInfo(
        id="travel-destination",
        name="旅拍风光",
        tag="",
        category=PackageCategory.travel,
        preview_url="/static/packages/travel-destination.jpg",
    ),
}

# ---- 套餐对应的生成 prompt 模板 ----
_PACKAGE_PROMPTS: dict[str, str] = {
    "chinese-classic": (
        "A stunning Chinese traditional wedding portrait. "
        "The bride wears a gorgeous red qipao (cheongsam) with gold embroidery and phoenix patterns, "
        "elaborate golden headdress with dangling ornaments. "
        "The groom wears a traditional red changshan with dragon motifs. "
        "Background: elegant Chinese garden pavilion with red lanterns, peach blossoms. "
        "Warm golden lighting, soft bokeh. Ultra-realistic, 8K, professional photography."
    ),
    "western-romantic": (
        "A breathtaking Western-style wedding portrait. "
        "The bride wears an elegant white lace A-line wedding gown with cathedral veil, "
        "holding a bouquet of white roses and peonies. "
        "The groom wears a classic black tuxedo with bow tie and white boutonniere. "
        "Background: grand European cathedral with stained glass windows, soft sunlight streaming in. "
        "Romantic golden hour lighting. Ultra-realistic, 8K, professional photography."
    ),
    "artistic-fantasy": (
        "A dreamlike fantasy wedding portrait with artistic flair. "
        "The bride wears a flowing ethereal gown with star and moonlight motifs, "
        "silver tiara with crystals, long flowing hair adorned with flowers. "
        "The groom wears a refined dark navy suit with celestial accents. "
        "Background: enchanted forest with bioluminescent flowers, floating lanterns, starlit sky. "
        "Magical ambient lighting with soft glows. Ultra-realistic, 8K, cinematic photography."
    ),
    "travel-destination": (
        "A stunning travel destination wedding portrait. "
        "The bride wears a flowing boho-chic wedding dress, barefoot on pristine sand. "
        "The groom wears a light linen suit, relaxed and elegant. "
        "Background: breathtaking Santorini cliffside with white and blue buildings, "
        "turquoise Aegean Sea, golden sunset sky. "
        "Natural warm sunlight, ocean breeze. Ultra-realistic, 8K, professional photography."
    ),
}

# 生成张数配置
PHOTOS_PER_PACKAGE = 4
MAX_RETRY = 2


def _build_generation_prompt(
    package_id: str,
    groom_style: str | None,
    bride_style: str | None,
    variant: int = 0,
) -> str:
    """根据套餐和用户自定义风格构建 prompt。"""
    base = _PACKAGE_PROMPTS.get(package_id, _PACKAGE_PROMPTS["western-romantic"])

    extras: list[str] = []
    if groom_style:
        extras.append(f"Groom style preference: {groom_style}.")
    if bride_style:
        extras.append(f"Bride style preference: {bride_style}.")

    # 给不同变体加点差异化描述
    variant_hints = [
        "Close-up intimate portrait, gentle expressions.",
        "Full-body shot, both standing side by side.",
        "Candid moment, looking at each other with genuine smiles.",
        "Artistic angle from behind, walking together into the distance.",
    ]
    hint = variant_hints[variant % len(variant_hints)]

    return f"{base} {' '.join(extras)} {hint}"


def _collect_reference_images(user_id: str) -> list[tuple[bytes, str]]:
    """收集用户上传的所有照片作为参考图（同步读取）。"""
    upload_dir = user_upload_dir(user_id)
    refs: list[tuple[bytes, str]] = []

    for ext_pattern in ("*.jpg", "*.jpeg", "*.png"):
        for fpath in sorted(upload_dir.glob(ext_pattern)):
            data = fpath.read_bytes()
            mime = "image/png" if fpath.suffix.lower() == ".png" else "image/jpeg"
            refs.append((data, mime))
            if len(refs) >= 6:  # 最多取6张参考图
                return refs

    return refs


async def _generation_pipeline(task_id: str, req: GenerateRequest) -> None:
    """
    生成流水线（后台任务）:
    1. 收集参考图
    2. 用 Nano Banana Pro 生成底图
    3. VLM 质检
    4. 如需修复则重试
    5. 完成
    """
    task = _tasks[task_id]
    task.status = TaskStatusEnum.processing
    task.message = "Collecting reference images..."
    task.progress = 5

    try:
        # Step 1: 收集参考图
        refs = _collect_reference_images(req.user_id)
        task.progress = 10
        task.message = f"Found {len(refs)} reference image(s). Starting generation..."

        result_urls: list[str] = []

        for i in range(PHOTOS_PER_PACKAGE):
            step_base = 10 + i * 20  # 10, 30, 50, 70

            prompt = _build_generation_prompt(
                req.package_id, req.groom_style, req.bride_style, variant=i
            )

            task.progress = step_base
            task.message = f"Generating photo {i + 1}/{PHOTOS_PER_PACKAGE}..."

            # Step 2: 生成底图
            retry_count = 0
            img_bytes: bytes | None = None

            while retry_count <= MAX_RETRY:
                try:
                    if refs:
                        img_bytes = await nano_banana_service.multi_reference_generate(
                            prompt=prompt,
                            reference_images=refs,
                        )
                    else:
                        img_bytes = await nano_banana_service.text_to_image(prompt=prompt)
                    break
                except Exception:
                    retry_count += 1
                    logger.warning(
                        "Generation attempt %d failed for task %s photo %d",
                        retry_count, task_id, i + 1,
                    )
                    if retry_count > MAX_RETRY:
                        raise
                    await asyncio.sleep(2)

            if img_bytes is None:
                continue

            task.progress = step_base + 10
            task.message = f"Quality checking photo {i + 1}..."

            # Step 3: VLM 质检
            task.status = TaskStatusEnum.quality_check

            report, fix_prompt = await vlm_checker_service.check_and_suggest_fix_prompt(
                image_data=img_bytes,
                original_prompt=prompt,
            )

            logger.info(
                "Photo %d quality: passed=%s, score=%.2f, issues=%s",
                i + 1, report.passed, report.score, report.issues,
            )

            # Step 4: 质检不通过则尝试修复
            if not report.passed and fix_prompt:
                task.message = f"Fixing photo {i + 1} quality issues..."
                task.status = TaskStatusEnum.processing
                try:
                    if refs:
                        img_bytes = await nano_banana_service.multi_reference_generate(
                            prompt=fix_prompt,
                            reference_images=refs,
                        )
                    else:
                        img_bytes = await nano_banana_service.text_to_image(prompt=fix_prompt)
                except Exception:
                    logger.warning("Fix attempt failed for task %s photo %d", task_id, i + 1)
                    # 修复失败就用原图

            # 保存结果
            file_id, path = await save_generated_image(req.user_id, img_bytes)
            url = f"/api/files/outputs/{req.user_id}/{path.name}"
            result_urls.append(url)

            task.status = TaskStatusEnum.processing

        # Step 5: 完成
        task.result_urls = result_urls
        task.progress = 100
        task.status = TaskStatusEnum.completed
        task.message = f"Generated {len(result_urls)} photo(s) successfully."
        logger.info("Task %s completed with %d photos", task_id, len(result_urls))

    except RuntimeError as exc:
        # API key 未配置等
        task.status = TaskStatusEnum.failed
        task.message = str(exc)
        logger.error("Task %s failed: %s", task_id, exc)
    except Exception:
        task.status = TaskStatusEnum.failed
        task.message = "Generation failed due to an internal error."
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
    """
    创建婚纱照生成任务。
    返回 task_id 用于后续查询进度和结果。
    """
    if not settings.laozhang_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set LAOZHANG_API_KEY.",
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
        message="Task created, waiting to start...",
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
        "result_urls": task.result_urls,
    }
