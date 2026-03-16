from __future__ import annotations

import os
import time
import uuid
import asyncio
import logging
from pathlib import Path

import aiofiles

from config import settings

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


async def save_upload_file(user_id: str, filename: str, content: bytes) -> tuple[str, Path]:
    """
    保存上传文件，返回 (file_id, 完整路径)。
    """
    file_id = generate_file_id()
    ext = Path(filename).suffix.lower() or ".jpg"
    dest = user_upload_dir(user_id) / f"{file_id}{ext}"
    async with aiofiles.open(dest, "wb") as f:
        await f.write(content)
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
    清理超过 data_retention_hours 的文件。
    返回删除的文件数量。
    """
    cutoff = time.time() - settings.data_retention_hours * 3600
    removed = 0

    for base_dir in (settings.upload_dir, settings.output_dir):
        base = Path(base_dir)
        if not base.exists():
            continue
        for root, dirs, files in os.walk(base):
            for fname in files:
                fpath = Path(root) / fname
                try:
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
