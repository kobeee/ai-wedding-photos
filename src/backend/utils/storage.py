from __future__ import annotations

import json
import os
import time
import uuid
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import aiofiles

from config import settings
from models.database import list_deliverable_retention_records

logger = logging.getLogger(__name__)


def ensure_dirs() -> None:
    """启动时确保必要目录存在。"""
    Path(settings.upload_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.output_dir).mkdir(parents=True, exist_ok=True)


def user_upload_dir(user_id: str) -> Path:
    """返回用户上传文件目录，不存在则创建。"""
    p = Path(settings.upload_dir) / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_output_dir(user_id: str) -> Path:
    """返回用户输出文件目录，不存在则创建。"""
    p = Path(settings.output_dir) / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def generate_file_id() -> str:
    return uuid.uuid4().hex[:12]


def upload_metadata_path(image_path: Path) -> Path:
    """返回上传图片对应的 sidecar 元数据路径。"""
    return image_path.with_suffix(image_path.suffix + ".meta.json")


async def save_upload_file(
    user_id: str,
    filename: str,
    content: bytes,
    role: str | None = None,
) -> tuple[str, Path]:
    """
    保存上传文件，返回 (file_id, 完整路径)。
    """
    file_id = generate_file_id()
    ext = Path(filename).suffix.lower() or ".jpg"
    dest = user_upload_dir(user_id) / f"{file_id}{ext}"
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)

    # 可选 sidecar 元数据，用于 couple 场景的参考图筛选。
    metadata = {
        "original_filename": filename,
        "role": role or "",
    }
    meta_dest = upload_metadata_path(dest)
    async with aiofiles.open(meta_dest, "w", encoding="utf-8") as f:
        await f.write(json.dumps(metadata, ensure_ascii=False))

    return file_id, dest


async def save_generated_image(user_id: str, image_data: bytes, ext: str = ".png") -> tuple[str, Path]:
    """
    保存AI生成的图片，返回 (file_id, 完整路径)。
    """
    file_id = generate_file_id()
    dest = user_output_dir(user_id) / f"{file_id}{ext}"
    async with aiofiles.open(dest, "wb") as f:
        await f.write(image_data)
    return file_id, dest


async def read_file_bytes(path: Path) -> bytes:
    """异步读取文件内容。"""
    async with aiofiles.open(path, "rb") as f:
        return await f.read()


async def cleanup_expired_files() -> int:
    """
    清理过期文件：
    - uploads 始终按 data_retention_hours 清理
    - outputs 中已交付文件按订单 retention_days 清理
    - 未绑定订单的 outputs 仍按 data_retention_hours 清理
    返回删除的文件数量。
    """
    upload_cutoff = time.time() - settings.data_retention_hours * 3600
    removed = 0
    deliverable_expiry: dict[Path, float] = {}

    for record in await list_deliverable_retention_records():
        created_at_raw = str(record.get("created_at", "")).strip()
        if not created_at_raw:
            continue
        try:
            created_at = datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                created_at = datetime.strptime(created_at_raw, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                logger.warning("Failed to parse deliverable timestamp: %s", created_at_raw)
                continue

        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=UTC)

        expires_at = created_at + timedelta(days=max(int(record.get("retention_days", 1)), 1))
        deliverable_path = (
            Path(settings.output_dir) / str(record.get("owner_id", "")) / str(record.get("storage_path", ""))
        ).resolve()
        deliverable_expiry[deliverable_path] = expires_at.timestamp()

    for base_dir in (settings.upload_dir, settings.output_dir):
        base = Path(base_dir)
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            for fname in files:
                fpath = Path(root) / fname
                try:
                    resolved = fpath.resolve()
                    cutoff = deliverable_expiry.get(resolved, upload_cutoff)
                    if fpath.stat().st_mtime < cutoff:
                        fpath.unlink()
                        removed += 1
                except OSError:
                    pass
            # 删除空目录
            for d in dirs:
                dpath = Path(root) / d
                try:
                    if dpath.is_dir() and not any(dpath.iterdir()):
                        dpath.rmdir()
                except OSError:
                    pass

    if removed:
        logger.info("Cleaned up %d expired files", removed)
    return removed


async def periodic_cleanup(interval_seconds: int = 3600) -> None:
    """后台定期清理任务。"""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await cleanup_expired_files()
        except Exception:
            logger.exception("Error during periodic cleanup")
