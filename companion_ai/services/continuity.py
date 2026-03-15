"""Reflection and project continuity service (P8-03).

Builds lightweight continuity snapshots from persistent signals and stores them
for cross-session recall.
"""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from typing import Any


DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "continuity.db")


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
        CREATE TABLE IF NOT EXISTS continuity_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            summary TEXT NOT NULL,
            projects_json TEXT,
            blockers_json TEXT,
            next_steps_json TEXT,
            open_questions_json TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS continuity_meta (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def _meta_get(key: str) -> str | None:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM continuity_meta WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else None


def _meta_set(key: str, value: str) -> None:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO continuity_meta (key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def _safe_json_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    out: list[str] = []
    for item in parsed:
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    try:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
    except Exception:
        metadata = {}
    return {
        "id": int(row["id"]),
        "summary": row["summary"] or "",
        "projects": _safe_json_list(row["projects_json"]),
        "blockers": _safe_json_list(row["blockers_json"]),
        "next_steps": _safe_json_list(row["next_steps_json"]),
        "open_questions": _safe_json_list(row["open_questions_json"]),
        "metadata": metadata,
        "created_at": row["created_at"],
    }


def list_snapshots(limit: int = 10) -> list[dict[str, Any]]:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM continuity_snapshots ORDER BY id DESC LIMIT ?",
        (max(int(limit), 1),),
    )
    rows = cur.fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def get_latest_snapshot() -> dict[str, Any] | None:
    rows = list_snapshots(limit=1)
    return rows[0] if rows else None


def create_snapshot(
    *,
    summary: str,
    projects: list[str] | None = None,
    blockers: list[str] | None = None,
    next_steps: list[str] | None = None,
    open_questions: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO continuity_snapshots (
            summary, projects_json, blockers_json, next_steps_json,
            open_questions_json, metadata_json
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            (summary or "").strip(),
            json.dumps(projects or []),
            json.dumps(blockers or []),
            json.dumps(next_steps or []),
            json.dumps(open_questions or []),
            json.dumps(metadata or {}),
        ),
    )
    inserted = cur.lastrowid
    conn.commit()
    cur.execute("SELECT * FROM continuity_snapshots WHERE id = ?", (inserted,))
    row = cur.fetchone()
    conn.close()
    return _row_to_dict(row)


def build_reflection_snapshot() -> dict[str, Any] | None:
    """Build a continuity snapshot from existing persistent signals."""
    try:
        from companion_ai.memory.sqlite_backend import (
            get_all_profile_facts,
            list_pending_profile_facts,
            get_latest_summary,
            get_latest_insights,
        )
        from companion_ai.services.jobs import list_schedules
    except Exception:
        return None

    facts = get_all_profile_facts() or {}
    pending = list_pending_profile_facts() or []
    summaries = get_latest_summary(3) or []
    insights = get_latest_insights(3) or []
    schedules = list_schedules() or []

    enabled_schedules = [s for s in schedules if int(s.get("enabled", 0)) == 1]
    projects: list[str] = []
    blockers: list[str] = []
    next_steps: list[str] = []
    open_questions: list[str] = []

    for sched in enabled_schedules[:5]:
        desc = str(sched.get("description") or "").strip()
        if desc and desc not in projects:
            projects.append(desc)
        if int(sched.get("consecutive_failures", 0)) > 0:
            blockers.append(f"Automation failures on: {desc}")
        if sched.get("blocked_by_policy"):
            blockers.append(f"Policy blocked schedule: {desc}")
        next_run = str(sched.get("next_run_at") or "").strip()
        if next_run and desc:
            next_steps.append(f"Run {desc} at {next_run}")

    for key, value in list(facts.items())[:5]:
        key_text = str(key).replace("_", " ").strip()
        if key_text and key_text not in projects:
            projects.append(key_text)
        value_text = str(value).strip()
        if value_text and len(value_text) < 100:
            next_steps.append(f"Use preference context: {value_text}")

    if pending:
        blockers.append(f"Pending memory review: {len(pending)} fact(s)")

    if not projects:
        open_questions.append("What project should we prioritize this week?")
    if not enabled_schedules:
        open_questions.append("Should we set up a recurring routine for project progress?")

    summary_parts: list[str] = []
    if projects:
        summary_parts.append("Active continuity signals: " + ", ".join(projects[:3]))
    if blockers:
        summary_parts.append("Known blockers: " + "; ".join(blockers[:2]))
    if insights:
        first_insight = str(insights[0].get("insight") or "").strip()
        if first_insight:
            summary_parts.append("Recent insight: " + first_insight[:180])
    if summaries:
        first_summary = str(summaries[0].get("summary") or "").strip()
        if first_summary:
            summary_parts.append("Recent recap: " + first_summary[:180])

    summary_text = " ".join(summary_parts).strip()
    if not summary_text:
        return None

    return {
        "summary": summary_text,
        "projects": projects[:5],
        "blockers": blockers[:5],
        "next_steps": next_steps[:5],
        "open_questions": open_questions[:5],
        "metadata": {
            "generated_at": datetime.utcnow().isoformat(),
            "source": "reflection",
            "facts": len(facts),
            "pending_facts": len(pending),
            "enabled_schedules": len(enabled_schedules),
        },
    }


def generate_continuity_if_due(*, force: bool = False) -> dict[str, Any] | None:
    """Generate at most one continuity snapshot per UTC day unless forced."""
    today = datetime.utcnow().date().isoformat()
    last_day = _meta_get("last_continuity_day")
    if not force and last_day == today:
        return None

    snapshot = build_reflection_snapshot()
    _meta_set("last_continuity_day", today)
    if not snapshot:
        return None

    return create_snapshot(**snapshot)


init_db()
