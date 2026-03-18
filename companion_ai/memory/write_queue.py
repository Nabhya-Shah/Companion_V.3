"""Durable memory write queue.

Provides JSONL-based append/replay semantics for memory write operations.
Used when live backend writes fail so requests are not lost.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from threading import Lock
from typing import Callable

logger = logging.getLogger(__name__)

MODULE_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(MODULE_DIR, '..'))
DATA_DIR = os.path.join(PROJECT_ROOT, 'data')
QUEUE_PATH = os.path.join(DATA_DIR, 'memory_write_spool.jsonl')

_queue_lock = Lock()


def _ensure_parent(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def _normalize_envelope(envelope: dict) -> dict:
    out = dict(envelope or {})
    out.setdefault('request_id', '')
    out.setdefault('user_scope', 'default')
    out.setdefault('operation', 'add')
    out.setdefault('payload', {})
    out.setdefault('created_at', datetime.now().isoformat())
    return out


def enqueue_write(envelope: dict, queue_path: str | None = None) -> dict:
    """Append a write envelope to durable spool.

    Returns status envelope for API/UI/reporting.
    """
    queue_path = queue_path or QUEUE_PATH
    normalized = _normalize_envelope(envelope)
    _ensure_parent(queue_path)

    with _queue_lock:
        with open(queue_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(normalized, ensure_ascii=False) + '\n')

    return {
        'request_id': normalized.get('request_id'),
        'status': 'accepted_queued',
        'backend': 'spool',
        'reason': 'backend_unavailable',
        'committed_at': None,
    }


def replay_writes(
    handler: Callable[[dict], dict],
    queue_path: str | None = None,
    max_items: int | None = None,
) -> dict:
    """Replay queued writes through handler.

    Handler receives a normalized envelope and should return a status dict
    containing at least `status`.

    Only records returning `accepted_committed` are removed from the spool.
    Others remain for future replay attempts.
    """
    queue_path = queue_path or QUEUE_PATH
    if not os.path.exists(queue_path):
        return {'replayed': 0, 'remaining': 0, 'failed': 0}

    with _queue_lock:
        with open(queue_path, 'r', encoding='utf-8') as f:
            raw_lines = [line.rstrip('\n') for line in f if line.strip()]

    replayed = 0
    failed = 0
    kept: list[str] = []

    for idx, raw in enumerate(raw_lines):
        if max_items is not None and replayed >= max_items:
            kept.extend(raw_lines[idx:])
            break

        try:
            envelope = _normalize_envelope(json.loads(raw))
        except Exception as e:
            failed += 1
            kept.append(raw)
            logger.warning(f"Invalid queued memory write line kept: {e}")
            continue

        try:
            result = handler(envelope) or {}
            if result.get('status') == 'accepted_committed':
                replayed += 1
            else:
                failed += 1
                kept.append(raw)
        except Exception as e:
            failed += 1
            kept.append(raw)
            logger.warning(f"Replay handler failed for request {envelope.get('request_id')}: {e}")

    _ensure_parent(queue_path)
    with _queue_lock:
        with open(queue_path, 'w', encoding='utf-8') as f:
            for line in kept:
                f.write(line + '\n')

    return {
        'replayed': replayed,
        'remaining': len(kept),
        'failed': failed,
    }


def list_queued_writes(queue_path: str | None = None, limit: int = 100) -> list[dict]:
    """Read queued write envelopes (newest first)."""
    queue_path = queue_path or QUEUE_PATH
    if not os.path.exists(queue_path):
        return []

    with _queue_lock:
        with open(queue_path, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f if line.strip()]

    rows: list[dict] = []
    for raw in reversed(lines[-limit:]):
        try:
            rows.append(_normalize_envelope(json.loads(raw)))
        except Exception:
            continue
    return rows
