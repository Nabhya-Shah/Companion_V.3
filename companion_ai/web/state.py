# companion_ai/web/state.py
"""Shared mutable state, session helpers, and security middleware for the web layer.

Every Blueprint module imports from here rather than owning its own globals,
ensuring a single source of truth for session/history state.

IMPORTANT: For *reassignable* scalars (history_version, sse_sequence, etc.)
always mutate via ``state.X = val`` rather than ``from state import X``.
"""

import os
import uuid
import logging
import threading
from typing import Dict, List, Tuple

from flask import request, jsonify, has_request_context

from companion_ai.conversation_manager import ConversationSession
from companion_ai.core import config as core_config

logger = logging.getLogger(__name__)

# ============================================================================
# Mutable session / history globals
# ============================================================================

conversation_history: List[dict] = []
conversation_session: ConversationSession = ConversationSession()

history_version: int = 0
history_condition: threading.Condition = threading.Condition()

sse_sequence: int = 0
sse_counters: Dict[str, int] = {"history.updated": 0, "job.updated": 0}
sse_last_event_ts: str | None = None

_session_lock: threading.Lock = threading.Lock()
_session_histories: Dict[str, List[dict]] = {}
_session_managers: Dict[str, ConversationSession] = {}
_scope_migration_done: set[str] = set()

# ============================================================================
# Security constants
# ============================================================================

_STRICT_TOKEN_PATH_PREFIXES = (
    "/api/debug",
    "/api/shutdown",
    "/api/memory/clear",
    "/api/brain/reindex",
    "/api/brain/auto-write",
    "/api/tokens/reset",
)


# ============================================================================
# Security helpers
# ============================================================================

def _is_local_request() -> bool:
    """Allow localhost-only API access when no auth token is configured."""
    remote = (request.remote_addr or "").strip()
    return remote in {"127.0.0.1", "::1", "localhost"}


def _extract_api_token(payload: dict | None = None) -> str | None:
    return (
        request.headers.get("X-API-TOKEN")
        or request.args.get("token")
        or ((payload or {}).get("token") if isinstance(payload, dict) else None)
        or request.cookies.get("api_token")
    )


def enforce_api_security():
    """Security baseline (before_request hook):
    - If API_AUTH_TOKEN is set, all /api/* calls must provide it.
    - If no token is set, only localhost can access /api/*.
    """
    if not request.path.startswith("/api/"):
        return None

    payload = None
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        payload = request.get_json(silent=True) or {}

    token = _extract_api_token(payload)

    # Debug/admin paths always require an explicit token, even on localhost.
    if any(request.path.startswith(prefix) for prefix in _STRICT_TOKEN_PATH_PREFIXES):
        if not core_config.API_AUTH_TOKEN:
            return jsonify({"error": "Forbidden: configure API_AUTH_TOKEN for debug/admin endpoints"}), 403
        if not core_config.require_auth(token):
            return jsonify({"error": "Unauthorized"}), 401
        return None

    if core_config.API_AUTH_TOKEN:
        if not core_config.require_auth(token):
            return jsonify({"error": "Unauthorized"}), 401
        return None

    if not _is_local_request():
        logger.warning(
            f"Blocked non-local API request without API_AUTH_TOKEN: "
            f"{request.remote_addr} {request.path}"
        )
        return jsonify({"error": "Forbidden: local access only unless API_AUTH_TOKEN is configured"}), 403

    return None


# ============================================================================
# Scope / session resolution helpers
# ============================================================================

def _sanitize_scope_value(value: str | None, default: str) -> str:
    if not value:
        return default
    cleaned = "".join(ch for ch in str(value) if ch.isalnum() or ch in ("-", "_"))
    return cleaned[:64] if cleaned else default


def _resolve_session_key(payload: dict | None = None) -> str:
    key = None
    if has_request_context():
        key = (
            request.headers.get("X-Session-ID")
            or request.args.get("session_id")
            or request.cookies.get("companion_session_id")
        )
    if not key and isinstance(payload, dict):
        key = payload.get("session_id")
    return _sanitize_scope_value(key, "default")


def _resolve_profile_key(payload: dict | None = None) -> str:
    key = None
    if has_request_context():
        key = (
            request.headers.get("X-Profile-ID")
            or request.args.get("profile_id")
            or request.cookies.get("companion_profile_id")
        )
    if not key and isinstance(payload, dict):
        key = payload.get("profile_id")
    return _sanitize_scope_value(key, "default")


def _resolve_workspace_key(payload: dict | None = None) -> str:
    key = None
    if has_request_context():
        key = (
            request.headers.get("X-Workspace-ID")
            or request.args.get("workspace_id")
            or request.cookies.get("companion_workspace_id")
        )
    if not key and isinstance(payload, dict):
        key = payload.get("workspace_id")
    return _sanitize_scope_value(key, "default")


def _list_known_workspaces() -> list[str]:
    workspaces = {"default"}
    workspace_root = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "BRAIN", "workspaces")
    try:
        if os.path.isdir(workspace_root):
            for name in os.listdir(workspace_root):
                full = os.path.join(workspace_root, name)
                if os.path.isdir(full):
                    workspaces.add(_sanitize_scope_value(name, "default"))
    except Exception:
        pass
    return sorted(workspaces)


def _parse_interval_minutes(data: dict) -> int:
    raw_interval = data.get("interval_minutes")
    if raw_interval not in (None, ""):
        return int(raw_interval)
    cadence = str(data.get("cadence") or "").strip().lower()
    if not cadence:
        return 0
    units = {"m": 1, "h": 60, "d": 1440}
    suffix = cadence[-1:]
    if suffix not in units:
        raise ValueError("cadence must end with 'm', 'h', or 'd' (example: 15m)")
    value = int(cadence[:-1])
    return value * units[suffix]


def _mem0_user_id_for_scope(session_key: str, profile_key: str, workspace_key: str = "default") -> str:
    base = core_config.MEM0_USER_ID or "default"
    if workspace_key and workspace_key != "default":
        return f"{base}::w:{workspace_key}::p:{profile_key}::s:{session_key}"
    return f"{base}::p:{profile_key}::s:{session_key}"


def _get_active_session_state(
    payload: dict | None = None,
) -> Tuple[str, str, str, List[dict], ConversationSession]:
    """Return (session_key, profile_key, mem0_user_id, history_list, manager)."""
    session_key = _resolve_session_key(payload)
    profile_key = _resolve_profile_key(payload)
    workspace_key = _resolve_workspace_key(payload)
    mem0_user_id = _mem0_user_id_for_scope(session_key, profile_key, workspace_key)

    with _session_lock:
        history = _session_histories.setdefault(session_key, [])
        manager = _session_managers.setdefault(session_key, ConversationSession())

    return session_key, profile_key, mem0_user_id, history, manager


def _maybe_migrate_legacy_scope(mem0_user_id: str, profile_key: str, session_key: str) -> None:
    """Best-effort one-time migration from legacy single-user Mem0 scope."""
    if not core_config.USE_MEM0:
        return

    # Avoid copying into the default scope itself.
    if profile_key == "default" and session_key == "default":
        return

    migration_key = f"{profile_key}:{session_key}"
    if migration_key in _scope_migration_done:
        return

    legacy_user_id = core_config.MEM0_USER_ID
    try:
        from companion_ai.memory import mem0_backend as mem0

        scoped = mem0.get_all_memories(user_id=mem0_user_id)
        if scoped:
            _scope_migration_done.add(migration_key)
            return

        result = mem0.migrate_legacy_memories(
            source_user_id=legacy_user_id,
            target_user_id=mem0_user_id,
            max_items=200,
        )
        logger.info(f"Legacy scope migration checked for {migration_key}: {result}")
        _scope_migration_done.add(migration_key)
    except Exception as e:
        logger.warning(f"Legacy scope migration failed for {migration_key}: {e}")
