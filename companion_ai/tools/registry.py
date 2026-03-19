"""Tool registry, plugin system, policy enforcement, and dispatch.

This is the infrastructure layer — all tool definitions live in domain modules
(system_tools, brain_tools, browser_tools, file_tools, research_tools).
"""
from __future__ import annotations

import datetime
import json
import os
import threading
from contextlib import contextmanager
from typing import Callable, Dict, Any

from companion_ai.core import config as core_config
from companion_ai.core import metrics as core_metrics

# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

ToolFn = Callable[[str], str]

# ---------------------------------------------------------------------------
# Global registries (populated by @tool decorators in domain modules)
# ---------------------------------------------------------------------------

# Legacy text-based tools
_TOOLS: Dict[str, ToolFn] = {}

# Modern function calling schemas (JSON Schema format for Groq)
_FUNCTION_SCHEMAS: Dict[str, Dict[str, Any]] = {}

# Plugin metadata
_TOOL_PLUGIN: Dict[str, str] = {}
_PLUGIN_TOOLS: Dict[str, set[str]] = {}
_TOOL_METADATA: Dict[str, Dict[str, Any]] = {}
_EXEC_CONTEXT = threading.local()

_PLUGIN_MANIFEST_HINTS: Dict[str, Dict[str, str]] = {
    'core': {
        'title': 'Core Skills',
        'description': 'Built-in assistant capabilities for time, memory, files, and everyday utility actions.',
        'risk_tier': 'low',
    },
    'background': {
        'title': 'Background Automation',
        'description': 'Asynchronous task execution and job orchestration features.',
        'risk_tier': 'medium',
    },
}

_SANDBOX_BLOCKED_TOOLS = {
    'use_computer',
    'browser_goto',
    'browser_click',
    'browser_type',
    'browser_read',
    'browser_press',
}

# Tools that require explicit user approval before execution
_APPROVAL_REQUIRED_TOOLS: set[str] = set()

# Pending approval requests  {request_id: ApprovalRequest}
_PENDING_APPROVALS: Dict[str, Any] = {}
# Re-entrant lock is required because resolve_approval() can call helpers
# that also touch approval state and acquire the same lock.
_APPROVAL_LOCK = threading.RLock()
_APPROVAL_EVENTS: Dict[str, threading.Event] = {}
_APPROVAL_TOKENS: Dict[str, Dict[str, Any]] = {}

_VALID_RISK_TIERS = {'low', 'medium', 'high'}

# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------

def tool(name: str, schema: Dict[str, Any] | None = None, plugin: str = 'core',
         requires_approval: bool = False, risk_tier: str = 'low', category: str | None = None):
    """Decorator to register both legacy and modern function-calling tools.

    Args:
        name: Tool identifier
        schema: Optional JSON Schema for native function calling
        plugin: Plugin group name (default 'core')
        requires_approval: If True, tool execution will pause for user consent
    """
    def wrap(fn: ToolFn):
        _TOOLS[name] = fn
        normalized_plugin = (plugin or 'core').strip() or 'core'
        normalized_risk = str(risk_tier or 'low').strip().lower()
        if normalized_risk not in _VALID_RISK_TIERS:
            normalized_risk = 'medium'
        normalized_category = (category or normalized_plugin).strip() or normalized_plugin
        _TOOL_PLUGIN[name] = normalized_plugin
        _PLUGIN_TOOLS.setdefault(normalized_plugin, set()).add(name)
        if schema:
            _FUNCTION_SCHEMAS[name] = schema
        enforced_approval = bool(requires_approval or normalized_risk == 'high')
        if enforced_approval:
            _APPROVAL_REQUIRED_TOOLS.add(name)
        _TOOL_METADATA[name] = {
            'name': name,
            'plugin': normalized_plugin,
            'category': normalized_category,
            'risk_tier': normalized_risk,
            'requires_approval': enforced_approval,
        }
        return fn
    return wrap


def mark_tool_requires_approval(name: str) -> None:
    """Programmatically flag a tool as requiring approval."""
    _APPROVAL_REQUIRED_TOOLS.add(name)
    if name in _TOOL_METADATA:
        _TOOL_METADATA[name]['requires_approval'] = True


def unmark_tool_requires_approval(name: str) -> None:
    """Remove the approval requirement from a tool."""
    _APPROVAL_REQUIRED_TOOLS.discard(name)
    if name in _TOOL_METADATA:
        _TOOL_METADATA[name]['requires_approval'] = False


def tool_requires_approval(name: str) -> bool:
    """Check if a tool requires user approval."""
    return name in _APPROVAL_REQUIRED_TOOLS


def list_approval_required_tools() -> list[str]:
    """List all tools that require approval."""
    return sorted(_APPROVAL_REQUIRED_TOOLS)


def set_approval_required_tools(tool_names: list[str]) -> list[str]:
    """Replace approval-required set with provided names (unknown tools ignored)."""
    _APPROVAL_REQUIRED_TOOLS.clear()
    for name in (tool_names or []):
        if name in _TOOLS:
            _APPROVAL_REQUIRED_TOOLS.add(name)

    for name, meta in _TOOL_METADATA.items():
        meta['requires_approval'] = name in _APPROVAL_REQUIRED_TOOLS

    return list_approval_required_tools()


def get_tool_runtime(name: str) -> dict:
    """Return runtime metadata for one tool."""
    if name in _TOOL_METADATA:
        return dict(_TOOL_METADATA[name])
    if name in _TOOLS:
        plugin = _TOOL_PLUGIN.get(name, 'core')
        return {
            'name': name,
            'plugin': plugin,
            'category': plugin,
            'risk_tier': 'low',
            'requires_approval': name in _APPROVAL_REQUIRED_TOOLS,
        }
    return {
        'name': name,
        'plugin': 'unknown',
        'category': 'unknown',
        'risk_tier': 'low',
        'requires_approval': False,
    }


def list_tool_runtime() -> list[dict]:
    """List runtime metadata for all tools."""
    rows = []
    for name in sorted(_TOOLS.keys()):
        rows.append(get_tool_runtime(name))
    return rows

# ---------------------------------------------------------------------------
# Plugin system
# ---------------------------------------------------------------------------

def list_tools() -> list[str]:
    """List all available tool names."""
    return sorted(_TOOLS.keys())


def list_plugins() -> list[dict]:
    """List available plugins and whether they are enabled by policy."""
    allowlist = _get_workspace_plugin_allowlist()
    source = 'workspace' if allowlist is not None else 'env'
    if allowlist is None:
        allowlist = core_config.get_plugin_allowlist()
    if allowlist is None:
        source = 'default'
    rows = []
    for plugin_name in sorted(_PLUGIN_TOOLS.keys()):
        rows.append({
            'name': plugin_name,
            'enabled': True if allowlist is None else (plugin_name in allowlist),
            'tools': sorted(_PLUGIN_TOOLS[plugin_name]),
            'policy_source': source,
        })
    return rows


def get_plugin_catalog() -> list[dict]:
    """Return enriched plugin manifests for UI/admin surfaces."""
    allowlist = _get_workspace_plugin_allowlist()
    source = 'workspace' if allowlist is not None else 'env'
    if allowlist is None:
        allowlist = core_config.get_plugin_allowlist()
    if allowlist is None:
        source = 'default'

    catalog: list[dict] = []
    for plugin_name in sorted(_PLUGIN_TOOLS.keys()):
        hints = _PLUGIN_MANIFEST_HINTS.get(plugin_name, {})
        tools = sorted(_PLUGIN_TOOLS.get(plugin_name, set()))
        tool_entries = []
        for tool_name in tools:
            schema = _FUNCTION_SCHEMAS.get(tool_name) or {}
            fn_data = schema.get('function') if isinstance(schema, dict) else {}
            description = ''
            if isinstance(fn_data, dict):
                description = str(fn_data.get('description') or '').strip()
            runtime_meta = get_tool_runtime(tool_name)
            tool_entries.append({
                'name': tool_name,
                'description': description,
                'sandbox_blocked_in_restricted': tool_name in _SANDBOX_BLOCKED_TOOLS,
                'risk_tier': runtime_meta.get('risk_tier', 'low'),
                'requires_approval': runtime_meta.get('requires_approval', False),
                'category': runtime_meta.get('category', plugin_name),
            })

        catalog.append({
            'name': plugin_name,
            'title': hints.get('title') or plugin_name.replace('_', ' ').title(),
            'description': hints.get('description') or 'Plugin tool bundle',
            'risk_tier': hints.get('risk_tier') or 'medium',
            'enabled': True if allowlist is None else (plugin_name in allowlist),
            'policy_source': source,
            'tool_count': len(tool_entries),
            'tools': tool_entries,
        })
    return catalog


def get_plugin_policy_state() -> dict:
    """Return normalized plugin policy state for control plane clients."""
    policy_path = core_config.PLUGIN_POLICY_PATH
    exists = bool(policy_path and os.path.exists(policy_path))
    workspace_allowlist = _get_workspace_plugin_allowlist()
    env_allowlist = core_config.get_plugin_allowlist()

    if workspace_allowlist is not None:
        effective = sorted(workspace_allowlist)
        source = 'workspace'
    elif env_allowlist is not None:
        effective = sorted(env_allowlist)
        source = 'env'
    else:
        effective = None
        source = 'default'

    return {
        'path': policy_path,
        'exists': exists,
        'source': source,
        'effective_enabled_plugins': effective,
        'available_plugins': sorted(_PLUGIN_TOOLS.keys()),
    }


def set_workspace_plugin_policy(enabled_plugins: list[str]) -> dict:
    """Persist workspace plugin policy (takes precedence over env policy)."""
    policy_path = core_config.PLUGIN_POLICY_PATH
    if not policy_path:
        raise ValueError('PLUGIN_POLICY_PATH is not configured')

    cleaned = sorted({str(item).strip() for item in (enabled_plugins or []) if str(item).strip()})
    known_plugins = set(_PLUGIN_TOOLS.keys())
    unknown = sorted([name for name in cleaned if name not in known_plugins])
    if unknown:
        raise ValueError(f"Unknown plugin(s): {', '.join(unknown)}")

    parent_dir = os.path.dirname(policy_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)

    payload = {
        'enabled_plugins': cleaned,
        'updated_at': datetime.datetime.now().isoformat(timespec='seconds'),
    }
    with open(policy_path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    state = get_plugin_policy_state()
    state['saved'] = True
    return state


def _get_workspace_plugin_allowlist() -> set[str] | None:
    """Workspace policy has precedence over env allowlist when configured."""
    policy_path = core_config.PLUGIN_POLICY_PATH
    try:
        if not policy_path or not os.path.exists(policy_path):
            return None
        with open(policy_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        enabled = payload.get('enabled_plugins')
        if not isinstance(enabled, list):
            return None
        cleaned = {str(item).strip() for item in enabled if str(item).strip()}
        return cleaned
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Execution mode (sandbox)
# ---------------------------------------------------------------------------

def get_execution_mode() -> str:
    mode = getattr(_EXEC_CONTEXT, 'mode', None)
    if mode in {'main', 'restricted'}:
        return mode
    return 'restricted' if core_config.SANDBOX_MODE == 'restricted' else 'main'


def set_execution_mode(mode: str) -> None:
    _EXEC_CONTEXT.mode = 'restricted' if str(mode).lower() == 'restricted' else 'main'


@contextmanager
def execution_mode(mode: str):
    previous = get_execution_mode()
    set_execution_mode(mode)
    try:
        yield
    finally:
        set_execution_mode(previous)

# ---------------------------------------------------------------------------
# Policy evaluation
# ---------------------------------------------------------------------------

def _is_plugin_allowed(plugin_name: str) -> bool:
    allowlist = _get_workspace_plugin_allowlist()
    if allowlist is None:
        allowlist = core_config.get_plugin_allowlist()
    if allowlist is None:
        return True
    return plugin_name in allowlist


def _is_tool_allowed(name: str) -> bool:
    if get_execution_mode() == 'restricted' and name in _SANDBOX_BLOCKED_TOOLS:
        return False
    plugin_name = _TOOL_PLUGIN.get(name, 'core')
    if not _is_plugin_allowed(plugin_name):
        return False
    allowlist = core_config.get_tool_allowlist()
    if allowlist is None:
        return True
    return name in allowlist


def evaluate_tool_policy(name: str, mode: str | None = None) -> dict:
    """Evaluate whether a tool is allowed under current policy."""
    if not name:
        return {
            'allowed': False,
            'reason': 'unknown_tool',
            'message': 'Tool is not specified',
        }

    if name not in _TOOLS:
        return {
            'allowed': False,
            'reason': 'unknown_tool',
            'message': f"Tool '{name}' is not registered",
        }

    def _decision() -> dict:
        if get_execution_mode() == 'restricted' and name in _SANDBOX_BLOCKED_TOOLS:
            return {
                'allowed': False,
                'reason': 'sandbox_denied',
                'message': f"Tool '{name}' blocked by sandbox mode (restricted)",
            }

        plugin_name = _TOOL_PLUGIN.get(name, 'core')
        if not _is_plugin_allowed(plugin_name):
            return {
                'allowed': False,
                'reason': 'plugin_denied',
                'message': f"Tool '{name}' blocked by plugin policy (plugin='{plugin_name}')",
            }

        allowlist = core_config.get_tool_allowlist()
        if allowlist is not None and name not in allowlist:
            return {
                'allowed': False,
                'reason': 'allowlist_denied',
                'message': f"Tool '{name}' blocked by safety allowlist policy",
            }

        return {
            'allowed': True,
            'reason': None,
            'message': 'Allowed',
        }

    if mode is None:
        return _decision()

    previous = get_execution_mode()
    set_execution_mode(mode)
    try:
        return _decision()
    finally:
        set_execution_mode(previous)


def _blocked_tool_message(name: str) -> str:
    decision = evaluate_tool_policy(name)
    decision_type = decision.get('reason') or 'allowlist_denied'
    core_metrics.record_tool(name, blocked=True, success=False, decision_type=decision_type)
    return decision.get('message') or f"Tool '{name}' blocked by safety allowlist policy"


def _approval_timeout_seconds() -> float:
    """Return approval wait timeout, with a shorter default during pytest runs."""
    raw = os.getenv('TOOL_APPROVAL_TIMEOUT_SECONDS', '300')
    try:
        timeout = float(raw)
    except Exception:
        timeout = 300.0

    timeout = max(0.5, timeout)

    # Prevent long-lived accidental waits from making tests appear hung.
    if 'PYTEST_CURRENT_TEST' in os.environ and 'TOOL_APPROVAL_TIMEOUT_SECONDS' not in os.environ:
        return min(timeout, 5.0)

    return timeout

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def _wait_for_approval(name: str, args_summary: str, timeout: float | None = None) -> bool:
    """Block until user approves/denies this tool call. Returns True if approved."""
    if timeout is None:
        timeout = _approval_timeout_seconds()

    import uuid as _uuid
    request_id = str(_uuid.uuid4())[:8]
    event = threading.Event()

    with _APPROVAL_LOCK:
        _APPROVAL_EVENTS[request_id] = event
        _PENDING_APPROVALS[request_id] = {
            'id': request_id,
            'tool': name,
            'args_summary': args_summary,
            'status': 'pending',
            'created_at': datetime.datetime.now().isoformat(),
        }

    import logging as _log
    _log.getLogger(__name__).info(f"Approval request {request_id} created for tool '{name}'")

    # Block until approved/denied or timeout
    approved = event.wait(timeout=timeout)

    with _APPROVAL_LOCK:
        req = _PENDING_APPROVALS.pop(request_id, {})
        _APPROVAL_EVENTS.pop(request_id, None)

    if not approved:
        return False  # timed out
    return req.get('status') == 'approved'


def _issue_approval_token(tool_name: str, ttl_seconds: int = 180) -> str:
    import uuid as _uuid

    token = str(_uuid.uuid4())
    expires_at = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=max(5, int(ttl_seconds)))
    with _APPROVAL_LOCK:
        _APPROVAL_TOKENS[token] = {
            'tool': tool_name,
            'expires_at': expires_at,
            'used': False,
        }
    return token


def consume_approval_token(token: str, tool_name: str) -> bool:
    """Consume single-use approval token for a specific tool."""
    if not token:
        return False

    now = datetime.datetime.now(datetime.timezone.utc)
    with _APPROVAL_LOCK:
        record = _APPROVAL_TOKENS.get(token)
        if not record:
            return False
        if record.get('used'):
            return False
        if record.get('tool') != tool_name:
            return False
        if record.get('expires_at') is None or record.get('expires_at') <= now:
            _APPROVAL_TOKENS.pop(token, None)
            return False
        record['used'] = True
    return True


def issue_approval_token(tool_name: str, ttl_seconds: int = 180) -> str:
    """Issue a single-use approval token for the given tool name."""
    return _issue_approval_token(tool_name, ttl_seconds=ttl_seconds)


def resolve_approval(request_id: str, approved: bool) -> dict | None:
    """Approve or deny a pending tool execution request."""
    with _APPROVAL_LOCK:
        req = _PENDING_APPROVALS.get(request_id)
        event = _APPROVAL_EVENTS.get(request_id)
        if not req or not event:
            return None
        req['status'] = 'approved' if approved else 'denied'
        if approved:
            req['approval_token'] = _issue_approval_token(req.get('tool', ''))
    event.set()
    return req


def get_pending_approvals() -> list[dict]:
    """Return all currently pending approval requests."""
    with _APPROVAL_LOCK:
        return [dict(v) for v in _PENDING_APPROVALS.values() if v.get('status') == 'pending']


def run_tool(name: str, arg: str) -> str:
    """Execute a tool by name with string argument (legacy interface)."""
    fn = _TOOLS.get(name)
    if not fn:
        return f'Unknown tool: {name}'
    if not _is_tool_allowed(name):
        return _blocked_tool_message(name)
    if name in _APPROVAL_REQUIRED_TOOLS:
        if not _wait_for_approval(name, str(arg)[:200]):
            return f"Tool '{name}' was denied or timed out waiting for approval."
    return fn(arg)


def get_function_schemas(allowed: list[str] | None = None) -> list[Dict[str, Any]]:
    """Get function calling schemas for native tool calling."""
    allowed_by_policy = core_config.get_tool_allowlist()
    if not allowed:
        names = set(_FUNCTION_SCHEMAS.keys())
    else:
        names = set(allowed)
    if allowed_by_policy is not None:
        names = names & allowed_by_policy
    return [schema for name, schema in _FUNCTION_SCHEMAS.items() if name in names]


def execute_function_call(function_name: str, arguments: Dict[str, Any]) -> str:
    """Execute a function call from Groq's native function calling.

    Maps tool names to their registered functions with correct argument handling.
    """
    tool_fn = _TOOLS.get(function_name)
    if not tool_fn:
        return f'Unknown function: {function_name}'
    if not _is_tool_allowed(function_name):
        return _blocked_tool_message(function_name)
    if function_name in _APPROVAL_REQUIRED_TOOLS:
        approval_token = ''
        if isinstance(arguments, dict):
            approval_token = str(arguments.get('approval_token') or '').strip()

        if approval_token and consume_approval_token(approval_token, function_name):
            pass
        else:
            summary = json.dumps(arguments, default=str)[:200]
            if not _wait_for_approval(function_name, summary):
                return f"Tool '{function_name}' was denied or timed out waiting for approval."

    # Handle different function signatures
    if function_name == 'get_current_time':
        return tool_fn("")
    elif function_name == 'memory_search':
        return tool_fn(arguments.get('query', ''))
    elif function_name == 'brain_read':
        return tool_fn(arguments.get('path', ''))
    elif function_name == 'brain_write':
        return tool_fn(arguments.get('path', ''), arguments.get('content', ''), arguments.get('append', False))
    elif function_name == 'brain_list':
        return tool_fn(arguments.get('subdir', ''))
    elif function_name == 'brain_search':
        return tool_fn(arguments.get('query', ''))
    elif function_name == 'wikipedia_lookup':
        return tool_fn(arguments.get('query', ''))
    elif function_name == 'read_pdf':
        return tool_fn(arguments.get('file_path', ''), arguments.get('page_number'))
    elif function_name == 'read_image_text':
        return tool_fn(arguments.get('file_path', ''))
    elif function_name == 'read_document':
        return tool_fn(arguments.get('file_path', ''))
    elif function_name == 'list_files':
        return tool_fn(arguments.get('directory', '.'), arguments.get('file_type'))
    elif function_name == 'find_file':
        return tool_fn(arguments.get('filename', ''), arguments.get('file_type'))
    elif function_name == 'look_at_screen':
        return tool_fn(arguments.get('prompt', 'What is on the screen?'))
    elif function_name == 'use_computer':
        return tool_fn(action=arguments.get('action'), text=arguments.get('text'))
    elif function_name == 'remote_action_simulator':
        return tool_fn(
            capability=arguments.get('capability', ''),
            action=arguments.get('action', ''),
            target=arguments.get('target', ''),
            params=arguments.get('params') if isinstance(arguments.get('params'), dict) else {},
            approval_token=arguments.get('approval_token', ''),
        )
    elif function_name == 'start_background_task':
        return tool_fn(
            description=arguments.get('description'),
            tool_name=arguments.get('tool_name'),
            tool_args=arguments.get('tool_args')
        )
    elif function_name == 'browser_goto':
        return tool_fn(arguments.get('url', ''))
    elif function_name == 'browser_click':
        return tool_fn(arguments.get('selector', ''), arguments.get('text'))
    elif function_name == 'browser_type':
        return tool_fn(arguments.get('selector', ''), arguments.get('text', ''))
    elif function_name == 'browser_read':
        return tool_fn(arguments.get('selector'))
    elif function_name == 'browser_press':
        return tool_fn(arguments.get('key', 'Enter'))
    else:
        # Fallback: pass first argument or empty string
        first_arg = next(iter(arguments.values()), '') if arguments else ''
        return tool_fn(str(first_arg))
