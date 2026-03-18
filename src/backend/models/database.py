"""SQLite 数据层 — 任务状态持久化 + 用户档案。"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from config import settings

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接（单例）。"""
    global _db
    if _db is None:
        db_path = Path(settings.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(db_path))
        _db.row_factory = aiosqlite.Row
        await _init_tables(_db)
    return _db


async def close_db() -> None:
    """关闭数据库连接。"""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _init_tables(db: aiosqlite.Connection) -> None:
    """初始化表结构。"""
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            session_token TEXT UNIQUE NOT NULL,
            photos_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            package_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            progress INTEGER NOT NULL DEFAULT 0,
            quality_score REAL NOT NULL DEFAULT 0.0,
            message TEXT NOT NULL DEFAULT '',
            result_urls TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
        CREATE INDEX IF NOT EXISTS idx_users_token ON users(session_token);
    """)
    await db.commit()


# ---- User operations ----

async def create_user(user_id: str | None = None) -> tuple[str, str]:
    """创建用户，返回 (user_id, session_token)。"""
    db = await get_db()
    uid = user_id or uuid.uuid4().hex[:12]
    token = f"lst_{uuid.uuid4().hex}"
    await db.execute(
        "INSERT OR IGNORE INTO users (user_id, session_token) VALUES (?, ?)",
        (uid, token),
    )
    await db.commit()
    return uid, token


async def get_user_by_token(token: str) -> dict | None:
    """通过 session token 查找用户。"""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM users WHERE session_token = ?", (token,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def increment_photos_count(user_id: str, count: int = 1) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE users SET photos_count = photos_count + ? WHERE user_id = ?",
        (count, user_id),
    )
    await db.commit()


# ---- Task operations ----

async def save_task(
    task_id: str,
    user_id: str,
    package_id: str = "",
    status: str = "pending",
) -> None:
    """保存新任务。"""
    db = await get_db()
    await db.execute(
        "INSERT OR REPLACE INTO tasks "
        "(task_id, user_id, package_id, status) VALUES (?, ?, ?, ?)",
        (task_id, user_id, package_id, status),
    )
    await db.commit()


async def update_task(
    task_id: str,
    status: str | None = None,
    progress: int | None = None,
    quality_score: float | None = None,
    message: str | None = None,
    result_urls: list[str] | None = None,
) -> None:
    """更新任务状态。"""
    import json

    db = await get_db()
    updates = []
    params = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if progress is not None:
        updates.append("progress = ?")
        params.append(progress)
    if quality_score is not None:
        updates.append("quality_score = ?")
        params.append(quality_score)
    if message is not None:
        updates.append("message = ?")
        params.append(message)
    if result_urls is not None:
        updates.append("result_urls = ?")
        params.append(json.dumps(result_urls))

    if not updates:
        return

    updates.append("updated_at = datetime('now')")
    params.append(task_id)

    sql = f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?"
    await db.execute(sql, params)
    await db.commit()


async def get_task(task_id: str) -> dict | None:
    """获取任务详情。"""
    import json

    db = await get_db()
    cursor = await db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
    row = await cursor.fetchone()
    if not row:
        return None
    task = dict(row)
    task["result_urls"] = json.loads(task.get("result_urls", "[]"))
    return task


async def get_user_tasks(user_id: str) -> list[dict]:
    """获取用户所有任务。"""
    import json

    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    tasks = []
    for row in rows:
        task = dict(row)
        task["result_urls"] = json.loads(task.get("result_urls", "[]"))
        tasks.append(task)
    return tasks
