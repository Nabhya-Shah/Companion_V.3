# companion_ai/web/test_harness.py
"""Temporary test harness blueprint for live integration testing.

Provides:
  - In-memory activity log capturing ALL system events
  - POST /api/test/send — synchronous chat with full metadata
  - GET  /api/test/log  — read the activity log (JSON)
  - POST /api/test/log/clear — wipe the log
  - GET  /api/test/status — system health summary

All data is ephemeral (cleared on server restart).
"""

import json
import logging
import re
import threading
import time
from datetime import datetime
from collections import deque
from typing import Any

from flask import Blueprint, request, jsonify

from companion_ai.core import config as core_config
from companion_ai.web import state

logger = logging.getLogger(__name__)

test_bp = Blueprint('test_harness', __name__, url_prefix='/api/test')

# ---------------------------------------------------------------------------
# Activity Log — in-memory ring buffer (max 500 entries)
# ---------------------------------------------------------------------------

_LOG_MAX = 500
_activity_log: deque = deque(maxlen=_LOG_MAX)
_log_lock = threading.Lock()


def log_activity(category: str, action: str, detail: Any = None):
    """Append an activity to the in-memory log.

    Categories: chat, orchestrator, tool, memory, plan, approval, sse, error
    """
    entry = {
        "ts": datetime.now().isoformat(),
        "category": category,
        "action": action,
        "detail": detail,
    }
    with _log_lock:
        _activity_log.append(entry)
    # Also emit to Python logger for terminal visibility
    logger.info(f"[TEST-LOG] {category}.{action}: {json.dumps(detail, default=str)[:200] if detail else ''}")


# ---------------------------------------------------------------------------
# Monkey-patch key subsystems to feed the activity log
# ---------------------------------------------------------------------------

_hooks_installed = False


def install_hooks():
    """Install logging hooks into orchestrator, tools, memory, etc.

    Safe to call multiple times — only installs once.
    """
    global _hooks_installed
    if _hooks_installed:
        return
    _hooks_installed = True

    # --- Orchestrator decision hook ---
    try:
        from companion_ai.orchestrator import Orchestrator

        _orig_execute = Orchestrator._execute_decision

        async def _hooked_execute(self, decision, user_message, context):
            log_activity("orchestrator", "decision", {
                "action": decision.action.value,
                "loop": decision.loop,
                "has_plan": bool(decision.plan_steps),
                "content_preview": (decision.content or "")[:100] if decision.content else None,
            })
            result = await _orig_execute(self, decision, user_message, context)
            log_activity("orchestrator", "result", {
                "response_preview": (result[0] or "")[:150],
                "metadata": result[1] if isinstance(result[1], dict) else str(result[1])[:100],
            })
            return result

        Orchestrator._execute_decision = _hooked_execute
        log_activity("system", "hook_installed", "orchestrator._execute_decision")
    except Exception as e:
        logger.warning(f"Failed to hook orchestrator: {e}")

    # --- Tool execution hook ---
    try:
        from companion_ai.tools import registry as tool_reg

        _orig_run_tool = tool_reg.run_tool

        def _hooked_run_tool(name, args=None, **kwargs):
            log_activity("tool", "execute", {"tool": name, "args": args})
            result = _orig_run_tool(name, args, **kwargs)
            log_activity("tool", "result", {"tool": name, "result_preview": str(result)[:200]})
            return result

        tool_reg.run_tool = _hooked_run_tool
        log_activity("system", "hook_installed", "tools.run_tool")
    except Exception as e:
        logger.warning(f"Failed to hook tools: {e}")

    # --- Plan events hook ---
    try:
        from companion_ai.services.task_planner import register_plan_listener

        def _plan_hook(event_type, plan_id, data):
            log_activity("plan", event_type, {"plan_id": plan_id, "data_keys": list(data.keys()) if isinstance(data, dict) else None})

        register_plan_listener(_plan_hook)
        log_activity("system", "hook_installed", "task_planner.listener")
    except Exception as e:
        logger.warning(f"Failed to hook planner: {e}")

    # --- Approval events hook ---
    try:
        from companion_ai.tools.registry import get_pending_approvals
        log_activity("system", "hook_installed", "approval (poll-based, no hook needed)")
    except Exception:
        pass

    log_activity("system", "hooks_ready", "All test hooks installed")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@test_bp.route('/send', methods=['POST'])
def harness_send():
    """Send a message and get the FULL response synchronously (no streaming).

    Request: {"message": "Hello!", "session": "test"}
    Response: {user, ai, metadata, tokens, activity_snapshot}
    """
    data = request.json or {}
    trace_id = state.get_request_trace_id(data)
    user_message = data.get('message', '').strip()
    if not user_message:
        return jsonify({'error': 'Empty message'}), 400

    log_activity("chat", "user_message", {"message": user_message})

    session_key, profile_key, mem0_user_id, active_history, active_session = state._get_active_session_state(data)

    try:
        # Process through the full pipeline (same as debug/chat but with activity logging)
        ai_response, memory_saved = active_session.process_message(
            user_message,
            active_history,
            memory_user_id=mem0_user_id,
            trace_id=trace_id,
        )

        if not ai_response or not ai_response.strip():
            ai_response = "I'm here! Sorry, I got a bit stuck there."

        # Strip TTS emotion tags from displayed text
        ai_response = re.sub(r'\[(?:cheerful|whisper|sad|dramatic|excited|neutral|angry|laugh|sigh)\]\s*', '', ai_response, flags=re.IGNORECASE)

        log_activity("chat", "ai_response", {"response": ai_response[:300], "memory_saved": memory_saved})

        entry = {
            'user': user_message,
            'ai': ai_response,
            'timestamp': datetime.now().isoformat(),
            'persona': 'Companion',
            'source': 'test_harness',
        }
        active_history.append(entry)
        with state.history_condition:
            state.history_version += 1
            state.history_condition.notify_all()

        from companion_ai.llm_interface import get_last_token_usage
        token_usage = get_last_token_usage()

        # Snapshot recent activity for this response
        with _log_lock:
            recent = list(_activity_log)[-20:]

        return jsonify({
            'user': user_message,
            'ai': ai_response,
            'tokens': token_usage,
            'memory_saved': memory_saved,
            'history_length': len(active_history),
            'trace_id': trace_id,
            'activity_snapshot': recent,
        })
    except Exception as e:
        log_activity("error", "harness_send", {"error": str(e)})
        logger.error(f"Test harness send error: {e}")
        return jsonify({'error': str(e), 'trace_id': trace_id}), 500


@test_bp.route('/log', methods=['GET'])
def get_log():
    """Return the full activity log as JSON.

    Query params:
      ?last=N — only return the last N entries
      ?category=X — filter by category
    """
    last_n = request.args.get('last', type=int, default=0)
    category = request.args.get('category', '')

    with _log_lock:
        entries = list(_activity_log)

    if category:
        entries = [e for e in entries if e['category'] == category]

    if last_n > 0:
        entries = entries[-last_n:]

    return jsonify({'count': len(entries), 'log': entries})


@test_bp.route('/log/clear', methods=['POST'])
def clear_log():
    """Wipe the activity log."""
    with _log_lock:
        _activity_log.clear()
    log_activity("system", "log_cleared", None)
    return jsonify({'cleared': True})


@test_bp.route('/status', methods=['GET'])
def harness_status():
    """System health summary for test verification."""
    status = {
        'server': 'running',
        'timestamp': datetime.now().isoformat(),
        'log_entries': len(_activity_log),
    }

    # Chat history
    try:
        _, _, _, active_history, _ = state._get_active_session_state()
        status['chat_history_length'] = len(active_history)
    except Exception:
        status['chat_history_length'] = 0

    # Orchestrator
    try:
        from companion_ai.orchestrator import get_orchestrator
        status['orchestrator'] = 'available'
    except Exception:
        status['orchestrator'] = 'unavailable'

    # Active plans
    try:
        from companion_ai.services.task_planner import get_all_active_plans
        status['active_plans'] = len(get_all_active_plans())
    except Exception:
        status['active_plans'] = 0

    # Pending approvals
    try:
        from companion_ai.tools.registry import get_pending_approvals
        status['pending_approvals'] = len(get_pending_approvals())
    except Exception:
        status['pending_approvals'] = 0

    # Workflows
    try:
        from companion_ai.services.workflows import get_manager
        mgr = get_manager()
        status['workflows_loaded'] = len(mgr.workflows)
    except Exception:
        status['workflows_loaded'] = 0

    # Jobs
    try:
        from companion_ai.services import jobs
        status['active_jobs'] = len(jobs.get_active_jobs())
    except Exception:
        status['active_jobs'] = 0

    # Approval config
    try:
        from companion_ai.tools.registry import list_approval_required_tools
        status['approval_required_tools'] = list(list_approval_required_tools())
    except Exception:
        status['approval_required_tools'] = []

    return jsonify(status)
