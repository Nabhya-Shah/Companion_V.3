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

# ---------------------------------------------------------------------------
# @tool decorator
# ---------------------------------------------------------------------------

def tool(name: str, schema: Dict[str, Any] | None = None, plugin: str = 'core'):
    """Decorator to register both legacy and modern function-calling tools.

    Args:
        name: Tool identifier
        schema: Optional JSON Schema for native function calling
        plugin: Plugin group name (default 'core')
    """
    def wrap(fn: ToolFn):
        _TOOLS[name] = fn
        normalized_plugin = (plugin or 'core').strip() or 'core'
        _TOOL_PLUGIN[name] = normalized_plugin
        _PLUGIN_TOOLS.setdefault(normalized_plugin, set()).add(name)
        if schema:
            _FUNCTION_SCHEMAS[name] = schema
        return fn
    return wrap

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
            tool_entries.append({
                'name': tool_name,
                'description': description,
                'sandbox_blocked_in_restricted': tool_name in _SANDBOX_BLOCKED_TOOLS,
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

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def run_tool(name: str, arg: str) -> str:
    """Execute a tool by name with string argument (legacy interface)."""
    fn = _TOOLS.get(name)
    if not fn:
        return f'Unknown tool: {name}'
    if not _is_tool_allowed(name):
        return _blocked_tool_message(name)
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
