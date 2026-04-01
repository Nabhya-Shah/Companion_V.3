"""System tools — time, memory search, background tasks, vision, computer use."""
from __future__ import annotations

import datetime
import json
import os
import uuid
from typing import Dict

from companion_ai.services.jobs import add_job
from companion_ai.core import config as core_config
from companion_ai.tools.registry import tool
from companion_ai.tools.remote_actions import RemoteActionRequest, execute_simulated_action

try:
    from companion_ai.memory.mem0_backend import search_memories
except ImportError:
    search_memories = None


COMPUTER_USE_AUDIT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data",
    "computer_use_audit.jsonl",
)


def _audit_computer_use(
    attempt_id: str,
    action: str,
    text: str,
    status: str,
    *,
    reason: str = "",
    result: str = "",
    error: str = "",
) -> None:
    record = {
        "attempt_id": attempt_id,
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "action": str(action or ""),
        "text": str(text or ""),
        "status": status,
        "reason": reason,
        "result_preview": (result or "")[:240],
        "error": error,
    }
    try:
        os.makedirs(os.path.dirname(COMPUTER_USE_AUDIT_PATH), exist_ok=True)
        with open(COMPUTER_USE_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=True) + "\n")
    except Exception:
        # Never break tool execution due to audit logging failure.
        pass


def audit_computer_use_policy_rejection(action: str, text: str, reason: str, error: str) -> None:
    """Record a requested+rejected pair when policy blocks execution pre-dispatch."""
    attempt_id = uuid.uuid4().hex[:12]
    _audit_computer_use(attempt_id, action, text, "requested")
    _audit_computer_use(attempt_id, action, text, "rejected", reason=reason, error=error)


# ---------------------------------------------------------------------------
# Background task
# ---------------------------------------------------------------------------

@tool('start_background_task', schema={
    "type": "function",
    "function": {
        "name": "start_background_task",
        "description": "Start a long-running task in the background. Use this for research, deep analysis, or any task that might take more than a few seconds. IMPORTANT: Do NOT wait for this task to complete. It runs asynchronously. Just confirm to the user that it has started.",
        "parameters": {
            "type": "object",
            "properties": {
                "description": {
                    "type": "string",
                    "description": "A human-readable description of the task (e.g., 'Research quantum physics')"
                },
                "tool_name": {
                    "type": "string",
                    "description": "The name of the internal tool to run (currently supports: 'research_topic')"
                },
                "tool_args": {
                    "type": "object",
                    "description": "Arguments for the tool (e.g., {'query': 'quantum physics'})"
                }
            },
            "required": ["description", "tool_name", "tool_args"]
        }
    }
}, plugin='background', risk_tier='medium', category='automation')
def tool_background_task(description: str, tool_name: str = "", tool_args: Dict = None) -> str:
    """Start a background task."""
    if tool_args is None:
        tool_args = {}

    # For legacy calls where args might be mixed
    if isinstance(description, dict):
        args = description
        description = args.get('description', 'Unknown Task')
        tool_name = args.get('tool_name', 'unknown')
        tool_args = args.get('tool_args', {})

    job_id = add_job(description, tool_name, tool_args)
    return f"Started background task '{description}' with ID: {job_id}. I will notify you when it is complete. Do NOT wait for it."


# ---------------------------------------------------------------------------
# Time
# ---------------------------------------------------------------------------

@tool('get_current_time', schema={
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "Get the current date and time in ISO format",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
}, risk_tier='low', category='utility')
def tool_time(_: str = "") -> str:
    """Get current time in ISO format."""
    return datetime.datetime.now().isoformat(timespec='seconds')


# ---------------------------------------------------------------------------
# Memory search
# ---------------------------------------------------------------------------

@tool('memory_search', schema={
    "type": "function",
    "function": {
        "name": "memory_search",
        "description": "Search the user's long-term memory (vector database) for specific facts, preferences, or past conversations. Use this when you need to recall something specific that isn't in the immediate context.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The search query to find relevant memories."
                }
            },
            "required": ["query"]
        }
    }
}, risk_tier='low', category='memory')
def tool_memory_search(query: str) -> str:
    """Search Mem0 vector database for relevant memories."""
    if not search_memories:
        return "Memory search unavailable (Mem0 not loaded)."

    try:
        results = search_memories(query, limit=5)
        if not results:
            return f"No memories found for '{query}'."

        output = [f"Memory Search Results for '{query}':"]
        for i, res in enumerate(results, 1):
            text = res.get('memory', res.get('text', str(res)))
            score = res.get('score', 0)
            meta = res.get('metadata') or {}
            created_at = res.get('created_at') or meta.get('created_at')
            date = created_at[:10] if created_at else 'Unknown date'
            q_label = res.get('quality_confidence_label', 'medium')
            contradiction_state = res.get('quality_contradiction_state', 'none')
            output.append(
                f"{i}. {text} (Date: {date}, Quality: {q_label}, State: {contradiction_state}, Relevance: {score:.2f})"
            )

        return "\n".join(output)
    except Exception as e:
        return f"Error searching memory: {str(e)}"


# ---------------------------------------------------------------------------
# Vision / Computer Use
# ---------------------------------------------------------------------------

@tool('look_at_screen', schema={
    "type": "function",
    "function": {
        "name": "look_at_screen",
        "description": "Take a screenshot of the user's current screen and analyze it. Use this when the user asks you to 'look at this', 'see my screen', 'what am I doing', or asks for help with something visible on their monitor.",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Specific question about the screen content (e.g., 'What code is this?', 'Help me with this error', 'Describe the image'). Defaults to general description."
                }
            },
            "required": []
        }
    }
}, risk_tier='medium', category='vision')
def tool_look_at_screen(prompt: str = "What is on the screen?") -> str:
    """Analyze the current screen content."""
    try:
        from companion_ai.agents.vision import vision_manager
        return vision_manager.analyze_current_screen(prompt)
    except Exception as e:
        return f"Error analyzing screen: {e}"


@tool('use_computer', schema={
    "type": "function",
    "function": {
        "name": "use_computer",
        "description": "DIRECTLY CONTROL the computer. Use this to OPEN applications, CLICK buttons, TYPE text, or navigate the UI. Do not just advise the user to do it—DO IT yourself. Example: to open Notepad, click the 'Start' button or type 'Notepad'.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "Action to perform: 'click' (click element), 'type' (text), 'press' (key), 'launch' (open app via Run), 'scroll_up', 'scroll_down'",
                    "enum": ["click", "type", "press", "launch", "scroll_up", "scroll_down"]
                },
                "text": {
                    "type": "string",
                    "description": "If action='click', the description of the element (e.g., 'Submit Button', 'File Menu'). If action='type', the text to type."
                }
            },
            "required": ["action"]
        }
    }
}, risk_tier='high', requires_approval=True, category='computer_control')
def tool_use_computer(action: str, text: str = "") -> str:
    """Execute computer control actions."""
    attempt_id = uuid.uuid4().hex[:12]
    _audit_computer_use(attempt_id, action, text, "requested")

    if not core_config.ENABLE_COMPUTER_USE:
        message = "Computer Use is disabled by policy (ENABLE_COMPUTER_USE=false)."
        _audit_computer_use(
            attempt_id,
            action,
            text,
            "rejected",
            reason="feature_disabled",
            error=message,
        )
        return message

    valid_actions = {"click", "type", "press", "launch", "scroll_up", "scroll_down"}
    if action not in valid_actions:
        message = f"Unknown action: {action}"
        _audit_computer_use(attempt_id, action, text, "rejected", reason="unknown_action", error=message)
        return message

    try:
        from companion_ai.computer_agent import computer_agent
    except Exception as e:
        message = "Computer Use runtime unavailable (computer_agent module not loaded)."
        _audit_computer_use(attempt_id, action, text, "rejected", reason="runtime_unavailable", error=str(e))
        return message

    try:
        computer_agent.mark_action()

        if action == "click":
            if not text:
                message = "Error: 'text' (element description) is required for click action."
                _audit_computer_use(attempt_id, action, text, "rejected", reason="invalid_input", error=message)
                return message
            result = computer_agent.click_element(text)
        elif action == "type":
            if not text:
                message = "Error: 'text' (content to type) is required for type action."
                _audit_computer_use(attempt_id, action, text, "rejected", reason="invalid_input", error=message)
                return message
            result = computer_agent.type_text(text, enter=True)
        elif action == "press":
            result = computer_agent.press_key(text)
        elif action == "launch":
            result = computer_agent.launch_app(text)
        elif action == "scroll_up":
            result = computer_agent.scroll("up")
        elif action == "scroll_down":
            result = computer_agent.scroll("down")

        _audit_computer_use(attempt_id, action, text, "completed", result=result)
        return result

    except Exception as e:
        message = f"Computer Use Error: {e}"
        _audit_computer_use(attempt_id, action, text, "error", reason="exception", error=str(e))
        return message


@tool('remote_action_simulator', schema={
    "type": "function",
    "function": {
        "name": "remote_action_simulator",
        "description": "Run a simulator-only remote/mobile action envelope for capability and policy testing. No real device calls are executed.",
        "parameters": {
            "type": "object",
            "properties": {
                "capability": {"type": "string", "description": "Remote capability name, e.g. read_status or notify."},
                "action": {"type": "string", "description": "Action verb, e.g. read, ping, execute."},
                "target": {"type": "string", "description": "Optional target identifier."},
                "params": {"type": "object", "description": "Optional simulator parameters."},
                "approval_token": {"type": "string", "description": "Required for non-read actions."},
            },
            "required": ["capability", "action"]
        }
    }
}, plugin='background', risk_tier='medium', category='automation')
def tool_remote_action_simulator(
    capability: str,
    action: str,
    target: str = "",
    params: Dict | None = None,
    approval_token: str = "",
) -> str:
    envelope = execute_simulated_action(
        RemoteActionRequest(
            capability=capability,
            action=action,
            target=target,
            params=params or {},
            approval_token=approval_token,
        )
    )
    import json

    return json.dumps(envelope, ensure_ascii=True)
