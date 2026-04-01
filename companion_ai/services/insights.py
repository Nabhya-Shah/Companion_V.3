"""Proactive insights service (P6-D).

Generates lightweight daily digests, stores unread/read state, and supports
both live SSE delivery and offline chat catch-up delivery.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Any


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "insights.db")


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            category TEXT DEFAULT 'digest',
            digest_day TEXT,
            status TEXT DEFAULT 'unread',
            metadata_json TEXT,
            delivered_live INTEGER DEFAULT 0,
            delivered_chat INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS insight_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )

    # Lightweight schema upgrade for existing DBs.
    cols = [row[1] for row in cur.execute("PRAGMA table_info(insights)").fetchall()]
    if "digest_day" not in cols:
        cur.execute("ALTER TABLE insights ADD COLUMN digest_day TEXT")

    # Ensure only one daily digest per day/category when digest_day is present.
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_insights_daily_digest_unique
        ON insights(category, digest_day)
        WHERE digest_day IS NOT NULL
        """
    )
    conn.commit()
    conn.close()


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    metadata_raw = row["metadata_json"] if "metadata_json" in row.keys() else None
    try:
        metadata = json.loads(metadata_raw) if metadata_raw else {}
    except Exception:
        metadata = {}
    return {
        "id": int(row["id"]),
        "title": row["title"],
        "body": row["body"],
        "category": row["category"],
        "status": row["status"],
        "created_at": row["created_at"],
        "metadata": metadata,
    }


def _meta_get(key: str) -> str | None:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM insight_meta WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else None


def _meta_set(key: str, value: str) -> None:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO insight_meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def create_insight(
    title: str,
    body: str,
    category: str = "digest",
    metadata: dict | None = None,
    digest_day: str | None = None,
) -> dict[str, Any]:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO insights (title, body, category, digest_day, status, metadata_json, delivered_live, delivered_chat)
        VALUES (?, ?, ?, ?, 'unread', ?, 0, 0)
        """,
        (
            title.strip(),
            body.strip(),
            category.strip() or "digest",
            digest_day,
            json.dumps(metadata or {}),
        ),
    )
    insight_id = cur.lastrowid
    conn.commit()
    cur.execute("SELECT * FROM insights WHERE id = ?", (insight_id,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)


def list_insights(*, unread_only: bool = False, limit: int = 20) -> list[dict[str, Any]]:
    conn = _get_db()
    cur = conn.cursor()
    if unread_only:
        cur.execute(
            "SELECT * FROM insights WHERE status = 'unread' ORDER BY id DESC LIMIT ?",
            (max(int(limit), 1),),
        )
    else:
        cur.execute("SELECT * FROM insights ORDER BY id DESC LIMIT ?", (max(int(limit), 1),))
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def unread_count() -> int:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS c FROM insights WHERE status = 'unread'")
    row = cur.fetchone()
    conn.close()
    return int(row["c"] if row else 0)


def update_status(insight_id: int, status: str) -> bool:
    if status not in {"unread", "read", "dismissed"}:
        return False
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("UPDATE insights SET status = ? WHERE id = ?", (status, int(insight_id)))
    changed = cur.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def claim_live_insights(limit: int = 5) -> list[dict[str, Any]]:
    """Claim unread insights that have not yet been emitted to live SSE."""
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM insights
        WHERE status = 'unread' AND delivered_live = 0
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(int(limit), 1),),
    )
    rows = cur.fetchall()
    ids = [int(r["id"]) for r in rows]
    if ids:
        q = ",".join(["?"] * len(ids))
        cur.execute(f"UPDATE insights SET delivered_live = 1 WHERE id IN ({q})", tuple(ids))
    conn.commit()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def list_undelivered_chat_insights(limit: int = 5) -> list[dict[str, Any]]:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM insights
        WHERE status = 'unread' AND delivered_chat = 0
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(int(limit), 1),),
    )
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def mark_chat_delivered(insight_ids: list[int]) -> None:
    ids = [int(x) for x in insight_ids if x is not None]
    if not ids:
        return
    conn = _get_db()
    cur = conn.cursor()
    q = ",".join(["?"] * len(ids))
    cur.execute(f"UPDATE insights SET delivered_chat = 1 WHERE id IN ({q})", tuple(ids))
    conn.commit()
    conn.close()


def build_digest_text() -> tuple[str, str, dict[str, Any]] | None:
    """Build a concise daily digest from memory + schedules + pending review state."""
    try:
        from companion_ai.memory import sqlite_backend
        from companion_ai.services import jobs

        facts = sqlite_backend.list_profile_facts_detailed(limit=3)
        pending = sqlite_backend.list_pending_profile_facts()
        schedules = jobs.list_schedules()
    except Exception:
        return None

    enabled = [s for s in schedules if int(s.get("enabled", 0)) == 1]
    upcoming = [s for s in enabled if s.get("next_run_at")]

    if not facts and not pending and not enabled:
        return None

    lines: list[str] = []
    if facts:
        lines.append("Top memory signals:")
        for fact in facts[:3]:
            lines.append(f"- {fact.get('value', '').strip()[:110]}")
    if pending:
        lines.append(f"Pending memory review: {len(pending)} fact(s) need approval/rejection.")
    if upcoming:
        soonest = sorted(upcoming, key=lambda s: str(s.get("next_run_at")))[0]
        lines.append(
            f"Next automation: {soonest.get('description') or 'Scheduled task'} at {soonest.get('next_run_at')}"
        )

    title = "Daily Companion Brief"
    body = "\n".join(lines)
    metadata = {
        "facts": len(facts),
        "pending_facts": len(pending),
        "enabled_schedules": len(enabled),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    return title, body, metadata


def generate_daily_insight_if_due(now: datetime | None = None, force: bool = False) -> dict[str, Any] | None:
    """Generate at most one digest per UTC day unless force=True."""
    now = now or datetime.now(timezone.utc)
    today = now.date().isoformat()
    last_day = _meta_get("last_daily_digest_day")
    if not force and last_day == today:
        return None

    digest = build_digest_text()
    _meta_set("last_daily_digest_day", today)
    if not digest:
        return None

    title, body, metadata = digest
    try:
        return create_insight(
            title=title,
            body=body,
            category="daily_digest",
            metadata=metadata,
            digest_day=today,
        )
    except sqlite3.IntegrityError:
        # Another worker/request already created this day's digest.
        return None


init_db()
