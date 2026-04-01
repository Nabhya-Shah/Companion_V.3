"""Remote action simulator contracts and policy checks (Insert C)."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from companion_ai.core import config as core_config
from companion_ai.tools.registry import consume_approval_token, issue_approval_token


READ_ACTIONS = {"read", "inspect", "status", "get", "list", "ping"}
SUPPORTED_CAPABILITIES = {
    "read_status",
    "ping",
    "notify",
    "toggle",
    "open_app",
    "capture_screen",
}


@dataclass
class RemoteActionRequest:
    capability: str
    action: str
    target: str = ""
    params: dict[str, Any] | None = None
    approval_token: str | None = None


def _capability_allowlist() -> set[str] | None:
    return core_config.get_remote_action_capability_allowlist()


def _is_non_read_action(action: str) -> bool:
    return (action or "").strip().lower() not in READ_ACTIONS


def list_capabilities() -> list[dict[str, Any]]:
    allowlist = _capability_allowlist()
    out = []
    for name in sorted(SUPPORTED_CAPABILITIES):
        out.append(
            {
                "name": name,
                "enabled": bool(core_config.REMOTE_ACTIONS_ENABLED)
                and (allowlist is None or name in allowlist),
                "requires_approval_for_non_read": True,
            }
        )
    return out


def request_execution_token(capability: str, action: str) -> dict[str, Any]:
    if not core_config.REMOTE_ACTIONS_ENABLED:
        return {"ok": False, "error": "Remote actions are disabled by default policy", "reason": "disabled"}

    cap = (capability or "").strip()
    if cap not in SUPPORTED_CAPABILITIES:
        return {"ok": False, "error": f"Unsupported capability '{cap}'", "reason": "unsupported_capability"}

    allowlist = _capability_allowlist()
    if allowlist is not None and cap not in allowlist:
        return {
            "ok": False,
            "error": f"Capability '{cap}' blocked by allowlist policy",
            "reason": "allowlist_denied",
        }

    if not _is_non_read_action(action):
        return {"ok": True, "approval_token": None, "required": False}

    token = issue_approval_token("remote_action_execute", ttl_seconds=core_config.REMOTE_ACTION_APPROVAL_TTL_SECONDS)
    return {"ok": True, "approval_token": token, "required": True}


def execute_simulated_action(request: RemoteActionRequest) -> dict[str, Any]:
    trace_id = f"ra_{uuid.uuid4().hex[:12]}"
    now_iso = datetime.now(timezone.utc).isoformat()

    capability = (request.capability or "").strip()
    action = (request.action or "").strip().lower()
    target = (request.target or "").strip()

    envelope = {
        "trace_id": trace_id,
        "requested_at": now_iso,
        "request": {
            "capability": capability,
            "action": action,
            "target": target,
            "params": request.params or {},
        },
        "policy": {
            "enabled": bool(core_config.REMOTE_ACTIONS_ENABLED),
            "allowlist": sorted(_capability_allowlist() or []),
            "approved": False,
        },
        "lifecycle": [
            {"state": "requested", "ts": now_iso},
        ],
    }

    if not core_config.REMOTE_ACTIONS_ENABLED:
        envelope["status"] = "rejected"
        envelope["reason"] = "disabled"
        envelope["error"] = "Remote actions are disabled by default policy"
        return envelope

    if capability not in SUPPORTED_CAPABILITIES:
        envelope["status"] = "rejected"
        envelope["reason"] = "unsupported_capability"
        envelope["error"] = f"Unsupported capability '{capability}'"
        return envelope

    allowlist = _capability_allowlist()
    if allowlist is not None and capability not in allowlist:
        envelope["status"] = "rejected"
        envelope["reason"] = "allowlist_denied"
        envelope["error"] = f"Capability '{capability}' blocked by allowlist policy"
        return envelope

    if _is_non_read_action(action):
        approved = consume_approval_token(request.approval_token or "", "remote_action_execute")
        envelope["policy"]["approved"] = bool(approved)
        if not approved:
            envelope["status"] = "rejected"
            envelope["reason"] = "approval_required"
            envelope["error"] = "Non-read actions require a valid approval token"
            return envelope

    envelope["lifecycle"].append({"state": "approved", "ts": datetime.now(timezone.utc).isoformat()})
    envelope["lifecycle"].append({"state": "running", "ts": datetime.now(timezone.utc).isoformat()})

    envelope["status"] = "completed"
    envelope["result"] = {
        "provider": "simulator",
        "message": f"Simulated action '{action}' on '{target or capability}'",
        "capability": capability,
        "target": target,
    }
    envelope["lifecycle"].append({"state": "completed", "ts": datetime.now(timezone.utc).isoformat()})
    return envelope
