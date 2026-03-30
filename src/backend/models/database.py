"""SQLite 数据层。"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path

import aiosqlite

from config import settings

logger = logging.getLogger(__name__)

_db: aiosqlite.Connection | None = None

_DEFAULT_SKUS = (
    {
        "sku_id": "trial_free",
        "name": "免费体验",
        "description": "3 张样片，确认整体风格与质感。",
        "tag": "体验入口",
        "price": 0,
        "currency": "CNY",
        "active": 1,
        "highlight": 0,
        "sort_order": 1,
        "entitlements": {
            "promised_photos": 3,
            "scene_count": 1,
            "photo_mix": {"couple": 3},
            "rerun_quota": 0,
            "repaint_quota": 0,
            "retention_days": 1,
            "delivery_specs": ["preview", "4k"],
            "preview_policy": "trial",
        },
    },
    {
        "sku_id": "starter_399",
        "name": "轻享 399",
        "description": "3 景 24 张，适合快速确认一套完整婚纱故事。",
        "tag": "入门付费",
        "price": 39900,
        "currency": "CNY",
        "active": 1,
        "highlight": 0,
        "sort_order": 2,
        "entitlements": {
            "promised_photos": 24,
            "scene_count": 3,
            "photo_mix": {"couple": 15, "bride": 6, "groom": 3},
            "rerun_quota": 1,
            "repaint_quota": 0,
            "retention_days": 30,
            "delivery_specs": ["4k"],
            "preview_policy": "full",
        },
    },
    {
        "sku_id": "memory_699",
        "name": "记忆典藏 699",
        "description": "5 景 40 张，当前唯一主推款。",
        "tag": "主推",
        "price": 69900,
        "currency": "CNY",
        "active": 1,
        "highlight": 1,
        "sort_order": 3,
        "entitlements": {
            "promised_photos": 40,
            "scene_count": 5,
            "photo_mix": {"couple": 25, "bride": 10, "groom": 5},
            "rerun_quota": 2,
            "repaint_quota": 1,
            "retention_days": 30,
            "delivery_specs": ["4k"],
            "preview_policy": "full",
        },
    },
    {
        "sku_id": "archive_999",
        "name": "档案珍藏 999",
        "description": "7 景 56 张，适合完整档案级交付。",
        "tag": "高阶",
        "price": 99900,
        "currency": "CNY",
        "active": 1,
        "highlight": 0,
        "sort_order": 4,
        "entitlements": {
            "promised_photos": 56,
            "scene_count": 7,
            "photo_mix": {"couple": 35, "bride": 14, "groom": 7},
            "rerun_quota": 3,
            "repaint_quota": 2,
            "retention_days": 30,
            "delivery_specs": ["4k"],
            "preview_policy": "full",
        },
    },
)


def _token() -> str:
    return f"lst_{uuid.uuid4().hex}"


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def _decode_json(value: str | None, default):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        db_path = Path(settings.db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _db = await aiosqlite.connect(str(db_path))
        _db.row_factory = aiosqlite.Row
        await _init_tables(_db)
    return _db


async def close_db() -> None:
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def _init_tables(db: aiosqlite.Connection) -> None:
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            session_token TEXT UNIQUE NOT NULL,
            photos_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS identities (
            identity_id TEXT PRIMARY KEY,
            kind TEXT NOT NULL DEFAULT 'guest',
            status TEXT NOT NULL DEFAULT 'active',
            photos_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            identity_id TEXT NOT NULL,
            session_token TEXT UNIQUE NOT NULL,
            device_info TEXT NOT NULL DEFAULT '',
            ip TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            expires_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (identity_id) REFERENCES identities(identity_id)
        );

        CREATE TABLE IF NOT EXISTS skus (
            sku_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            tag TEXT NOT NULL DEFAULT '',
            price INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            active INTEGER NOT NULL DEFAULT 1,
            highlight INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            entitlements_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            identity_id TEXT NOT NULL,
            sku_id TEXT NOT NULL,
            package_id TEXT NOT NULL,
            amount INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            payment_status TEXT NOT NULL DEFAULT 'unpaid',
            fulfillment_status TEXT NOT NULL DEFAULT 'not_started',
            service_status TEXT NOT NULL DEFAULT 'normal',
            entitlement_snapshot_json TEXT NOT NULL DEFAULT '{}',
            rerun_used_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            paid_at TEXT,
            expired_at TEXT,
            closed_at TEXT,
            FOREIGN KEY (identity_id) REFERENCES identities(identity_id),
            FOREIGN KEY (sku_id) REFERENCES skus(sku_id)
        );

        CREATE TABLE IF NOT EXISTS payment_transactions (
            payment_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            provider TEXT NOT NULL,
            provider_trade_no TEXT NOT NULL DEFAULT '',
            provider_buyer_id TEXT NOT NULL DEFAULT '',
            amount INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'CNY',
            status TEXT NOT NULL DEFAULT 'pending',
            checkout_url TEXT NOT NULL DEFAULT '',
            notify_payload TEXT NOT NULL DEFAULT '{}',
            paid_at TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );

        CREATE TABLE IF NOT EXISTS generation_batches (
            batch_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            batch_type TEXT NOT NULL DEFAULT 'initial',
            initiated_by TEXT NOT NULL DEFAULT 'system',
            status TEXT NOT NULL DEFAULT 'pending',
            requested_photos INTEGER NOT NULL DEFAULT 0,
            delivered_photos INTEGER NOT NULL DEFAULT 0,
            progress INTEGER NOT NULL DEFAULT 0,
            message TEXT NOT NULL DEFAULT '',
            quality_score REAL NOT NULL DEFAULT 0.0,
            failure_reason TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            started_at TEXT,
            completed_at TEXT,
            FOREIGN KEY (order_id) REFERENCES orders(order_id)
        );

        CREATE TABLE IF NOT EXISTS deliverables (
            deliverable_id TEXT PRIMARY KEY,
            order_id TEXT NOT NULL,
            batch_id TEXT NOT NULL,
            owner_id TEXT NOT NULL,
            storage_kind TEXT NOT NULL DEFAULT 'outputs',
            storage_path TEXT NOT NULL DEFAULT '',
            url TEXT NOT NULL DEFAULT '',
            photo_status TEXT NOT NULL DEFAULT 'delivered',
            quality_score REAL NOT NULL DEFAULT 0.0,
            delivery_tier TEXT NOT NULL DEFAULT '4k',
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (order_id) REFERENCES orders(order_id),
            FOREIGN KEY (batch_id) REFERENCES generation_batches(batch_id)
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

        CREATE INDEX IF NOT EXISTS idx_sessions_token ON sessions(session_token);
        CREATE INDEX IF NOT EXISTS idx_sessions_identity ON sessions(identity_id);
        CREATE INDEX IF NOT EXISTS idx_orders_identity ON orders(identity_id);
        CREATE INDEX IF NOT EXISTS idx_orders_payment_status ON orders(payment_status);
        CREATE INDEX IF NOT EXISTS idx_batches_order ON generation_batches(order_id);
        CREATE INDEX IF NOT EXISTS idx_deliverables_order ON deliverables(order_id);
        CREATE INDEX IF NOT EXISTS idx_tasks_user ON tasks(user_id);
    """)
    await _seed_default_skus(db)
    await db.commit()


async def _seed_default_skus(db: aiosqlite.Connection) -> None:
    for sku in _DEFAULT_SKUS:
        await db.execute(
            """
            INSERT INTO skus (
                sku_id, name, description, tag, price, currency, active, highlight,
                sort_order, entitlements_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(sku_id) DO UPDATE SET
                name=excluded.name,
                description=excluded.description,
                tag=excluded.tag,
                price=excluded.price,
                currency=excluded.currency,
                active=excluded.active,
                highlight=excluded.highlight,
                sort_order=excluded.sort_order,
                entitlements_json=excluded.entitlements_json,
                updated_at=datetime('now')
            """,
            (
                sku["sku_id"],
                sku["name"],
                sku["description"],
                sku["tag"],
                sku["price"],
                sku["currency"],
                sku["active"],
                sku["highlight"],
                sku["sort_order"],
                json.dumps(sku["entitlements"], ensure_ascii=False),
            ),
        )


def _inflate_sku(row: aiosqlite.Row | None) -> dict | None:
    if row is None:
        return None
    payload = dict(row)
    payload["active"] = bool(payload.get("active", 0))
    payload["highlight"] = bool(payload.get("highlight", 0))
    payload["entitlements"] = _decode_json(payload.pop("entitlements_json", "{}"), {})
    return payload


def _inflate_order(row: aiosqlite.Row | None) -> dict | None:
    if row is None:
        return None
    payload = dict(row)
    payload["entitlement_snapshot"] = _decode_json(
        payload.pop("entitlement_snapshot_json", "{}"),
        {},
    )
    return payload


def _inflate_payment(row: aiosqlite.Row | None) -> dict | None:
    if row is None:
        return None
    payload = dict(row)
    payload["notify_payload"] = _decode_json(payload.get("notify_payload"), {})
    return payload


def _inflate_task(row: aiosqlite.Row | None) -> dict | None:
    if row is None:
        return None
    payload = dict(row)
    payload["result_urls"] = _decode_json(payload.get("result_urls"), [])
    return payload


async def create_user(user_id: str | None = None) -> tuple[str, str]:
    db = await get_db()
    identity_id = user_id or uuid.uuid4().hex[:12]
    session_token = _token()
    session_id = _id("sess")
    await db.execute(
        "INSERT OR IGNORE INTO identities (identity_id, kind, status) VALUES (?, 'guest', 'active')",
        (identity_id,),
    )
    await db.execute(
        """
        INSERT INTO sessions (session_id, identity_id, session_token, expires_at)
        VALUES (?, ?, ?, datetime('now', '+' || ? || ' hours'))
        """,
        (session_id, identity_id, session_token, settings.session_ttl_hours),
    )
    await db.execute(
        """
        INSERT INTO users (user_id, session_token)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET session_token=excluded.session_token
        """,
        (identity_id, session_token),
    )
    await db.commit()
    return identity_id, session_token


async def get_user_by_token(token: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT i.identity_id AS user_id, s.session_token, s.session_id, s.expires_at, s.last_seen_at
        FROM sessions s
        JOIN identities i ON i.identity_id = s.identity_id
        WHERE s.session_token = ?
          AND datetime(s.expires_at) > datetime('now')
        """,
        (token,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    await db.execute(
        "UPDATE sessions SET last_seen_at = datetime('now') WHERE session_token = ?",
        (token,),
    )
    await db.commit()
    return dict(row)


async def increment_photos_count(user_id: str, count: int = 1) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE identities SET photos_count = photos_count + ? WHERE identity_id = ?",
        (count, user_id),
    )
    await db.execute(
        "UPDATE users SET photos_count = photos_count + ? WHERE user_id = ?",
        (count, user_id),
    )
    await db.commit()


async def list_skus() -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM skus WHERE active = 1 ORDER BY sort_order ASC, price ASC",
    )
    rows = await cursor.fetchall()
    return [_inflate_sku(row) for row in rows]


async def get_sku(sku_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM skus WHERE sku_id = ?", (sku_id,))
    row = await cursor.fetchone()
    return _inflate_sku(row)


async def create_order(identity_id: str, package_id: str, sku_id: str) -> dict:
    sku = await get_sku(sku_id)
    if sku is None:
        raise ValueError(f"Unknown sku_id '{sku_id}'")

    db = await get_db()
    order_id = _id("ord")
    payment_status = "free_granted" if sku["price"] == 0 else "unpaid"
    paid_at_sql = "datetime('now')" if sku["price"] == 0 else "NULL"
    await db.execute(
        f"""
        INSERT INTO orders (
            order_id, identity_id, sku_id, package_id, amount, currency,
            payment_status, fulfillment_status, service_status,
            entitlement_snapshot_json, paid_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'not_started', 'normal', ?, {paid_at_sql})
        """,
        (
            order_id,
            identity_id,
            sku_id,
            package_id,
            sku["price"],
            sku["currency"],
            payment_status,
            json.dumps(sku["entitlements"], ensure_ascii=False),
        ),
    )
    await db.commit()
    order = await get_order(order_id)
    if order is None:
        raise RuntimeError(f"Failed to create order '{order_id}'")
    return order


async def get_order(order_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM orders WHERE order_id = ?", (order_id,))
    row = await cursor.fetchone()
    return _inflate_order(row)


async def list_orders_for_identity(identity_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM orders WHERE identity_id = ? ORDER BY created_at DESC",
        (identity_id,),
    )
    rows = await cursor.fetchall()
    return [_inflate_order(row) for row in rows]


async def update_order(order_id: str, **fields) -> None:
    if not fields:
        return
    db = await get_db()
    updates = []
    params = []
    for key, value in fields.items():
        column = "entitlement_snapshot_json" if key == "entitlement_snapshot" else key
        updates.append(f"{column} = ?")
        if key == "entitlement_snapshot":
            params.append(json.dumps(value, ensure_ascii=False))
        else:
            params.append(value)
    params.append(order_id)
    await db.execute(
        f"UPDATE orders SET {', '.join(updates)} WHERE order_id = ?",
        params,
    )
    await db.commit()


async def increment_order_rerun_usage(order_id: str) -> None:
    db = await get_db()
    await db.execute(
        "UPDATE orders SET rerun_used_count = rerun_used_count + 1 WHERE order_id = ?",
        (order_id,),
    )
    await db.commit()


async def create_payment_transaction(
    order_id: str,
    provider: str = "mock",
    status: str = "pending",
    checkout_url: str = "",
) -> dict:
    order = await get_order(order_id)
    if order is None:
        raise ValueError(f"Unknown order_id '{order_id}'")

    db = await get_db()
    payment_id = _id("pay")
    await db.execute(
        """
        INSERT INTO payment_transactions (
            payment_id, order_id, provider, amount, currency, status, checkout_url
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            payment_id,
            order_id,
            provider,
            order["amount"],
            order["currency"],
            status,
            checkout_url,
        ),
    )
    if status == "pending":
        await db.execute(
            "UPDATE orders SET payment_status = 'pending' WHERE order_id = ? AND payment_status = 'unpaid'",
            (order_id,),
        )
    await db.commit()
    payment = await get_payment_transaction(payment_id)
    if payment is None:
        raise RuntimeError(f"Failed to create payment '{payment_id}'")
    return payment


async def get_payment_transaction(payment_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM payment_transactions WHERE payment_id = ?",
        (payment_id,),
    )
    row = await cursor.fetchone()
    return _inflate_payment(row)


async def get_latest_payment_for_order(order_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT * FROM payment_transactions
        WHERE order_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (order_id,),
    )
    row = await cursor.fetchone()
    return _inflate_payment(row)


async def confirm_payment(
    payment_id: str,
    *,
    succeed: bool,
    buyer_id: str = "mock-buyer",
    notify_payload: dict | None = None,
) -> dict:
    payment = await get_payment_transaction(payment_id)
    if payment is None:
        raise ValueError(f"Unknown payment_id '{payment_id}'")
    if payment["status"] == "paid":
        return payment

    db = await get_db()
    next_status = "paid" if succeed else "failed"
    await db.execute(
        """
        UPDATE payment_transactions
        SET status = ?, provider_trade_no = ?, provider_buyer_id = ?,
            notify_payload = ?, paid_at = CASE WHEN ? = 'paid' THEN datetime('now') ELSE paid_at END,
            updated_at = datetime('now')
        WHERE payment_id = ?
        """,
        (
            next_status,
            _id("trade"),
            buyer_id,
            json.dumps(notify_payload or {}, ensure_ascii=False),
            next_status,
            payment_id,
        ),
    )
    if succeed:
        await db.execute(
            """
            UPDATE orders
            SET payment_status = 'paid', paid_at = COALESCE(paid_at, datetime('now'))
            WHERE order_id = ?
            """,
            (payment["order_id"],),
        )
    else:
        await db.execute(
            "UPDATE orders SET payment_status = 'failed' WHERE order_id = ?",
            (payment["order_id"],),
        )
    await db.commit()
    confirmed = await get_payment_transaction(payment_id)
    if confirmed is None:
        raise RuntimeError(f"Failed to update payment '{payment_id}'")
    return confirmed


async def create_generation_batch(
    order_id: str,
    *,
    batch_type: str = "initial",
    initiated_by: str = "system",
    requested_photos: int = 0,
) -> dict:
    db = await get_db()
    batch_id = _id("batch")
    await db.execute(
        """
        INSERT INTO generation_batches (
            batch_id, order_id, batch_type, initiated_by, status,
            requested_photos, progress, message
        ) VALUES (?, ?, ?, ?, 'pending', ?, 0, '批次已创建，等待启动...')
        """,
        (batch_id, order_id, batch_type, initiated_by, requested_photos),
    )
    await db.execute(
        "UPDATE orders SET fulfillment_status = 'queued' WHERE order_id = ?",
        (order_id,),
    )
    await db.commit()
    batch = await get_generation_batch(batch_id)
    if batch is None:
        raise RuntimeError(f"Failed to create batch '{batch_id}'")
    return batch


async def get_generation_batch(batch_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM generation_batches WHERE batch_id = ?",
        (batch_id,),
    )
    row = await cursor.fetchone()
    return dict(row) if row else None


async def list_generation_batches(order_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT * FROM generation_batches
        WHERE order_id = ?
        ORDER BY created_at DESC
        """,
        (order_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def update_generation_batch(batch_id: str, **fields) -> None:
    if not fields:
        return
    db = await get_db()
    updates = []
    params = []
    for key, value in fields.items():
        updates.append(f"{key} = ?")
        params.append(value)
    updates.append("updated_at = datetime('now')")
    params.append(batch_id)
    await db.execute(
        f"UPDATE generation_batches SET {', '.join(updates)} WHERE batch_id = ?",
        params,
    )
    await db.commit()


async def create_deliverable(
    order_id: str,
    batch_id: str,
    owner_id: str,
    *,
    storage_kind: str,
    storage_path: str,
    url: str,
    quality_score: float,
    delivery_tier: str = "4k",
    photo_status: str = "delivered",
) -> dict:
    db = await get_db()
    deliverable_id = _id("dlv")
    await db.execute(
        """
        INSERT INTO deliverables (
            deliverable_id, order_id, batch_id, owner_id, storage_kind, storage_path,
            url, photo_status, quality_score, delivery_tier
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            deliverable_id,
            order_id,
            batch_id,
            owner_id,
            storage_kind,
            storage_path,
            url,
            photo_status,
            quality_score,
            delivery_tier,
        ),
    )
    await db.commit()
    deliverables = await list_deliverables(order_id)
    return next(item for item in deliverables if item["deliverable_id"] == deliverable_id)


async def list_deliverables(order_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT deliverable_id, order_id, batch_id, url, photo_status, quality_score,
               delivery_tier, created_at
        FROM deliverables
        WHERE order_id = ?
        ORDER BY created_at ASC
        """,
        (order_id,),
    )
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def list_deliverable_retention_records() -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT d.owner_id, d.storage_kind, d.storage_path, d.created_at,
               o.entitlement_snapshot_json
        FROM deliverables d
        JOIN orders o ON o.order_id = d.order_id
        WHERE d.storage_kind = 'outputs'
        """
    )
    rows = await cursor.fetchall()
    records: list[dict] = []
    for row in rows:
        payload = dict(row)
        entitlements = _decode_json(payload.pop("entitlement_snapshot_json", "{}"), {})
        payload["retention_days"] = int(entitlements.get("retention_days", 1) or 1)
        records.append(payload)
    return records


async def count_deliverables(order_id: str) -> int:
    db = await get_db()
    cursor = await db.execute(
        "SELECT COUNT(*) AS total FROM deliverables WHERE order_id = ?",
        (order_id,),
    )
    row = await cursor.fetchone()
    return int(row["total"]) if row else 0


async def save_task(
    task_id: str,
    user_id: str,
    package_id: str = "",
    status: str = "pending",
) -> None:
    db = await get_db()
    await db.execute(
        """
        INSERT OR REPLACE INTO tasks
        (task_id, user_id, package_id, status)
        VALUES (?, ?, ?, ?)
        """,
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
        params.append(json.dumps(result_urls, ensure_ascii=False))

    if not updates:
        return

    updates.append("updated_at = datetime('now')")
    params.append(task_id)
    await db.execute(
        f"UPDATE tasks SET {', '.join(updates)} WHERE task_id = ?",
        params,
    )
    await db.commit()


async def get_task(task_id: str) -> dict | None:
    db = await get_db()
    cursor = await db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
    row = await cursor.fetchone()
    return _inflate_task(row)


async def get_user_tasks(user_id: str) -> list[dict]:
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM tasks WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [_inflate_task(row) for row in rows]
