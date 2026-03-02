"""Companion AI tool system — registry, policy, and domain tools.

This package replaces the old monolithic tools.py. All public API is
re-exported here so existing ``from companion_ai.tools import X`` imports
continue to work unchanged.
"""
from __future__ import annotations

# --- Infrastructure (registry, policy, dispatch) ---
from companion_ai.tools.registry import (        # noqa: F401
    tool,
    list_tools,
    list_plugins,
    get_plugin_catalog,
    get_plugin_policy_state,
    set_workspace_plugin_policy,
    get_execution_mode,
    set_execution_mode,
    execution_mode,
    evaluate_tool_policy,
    run_tool,
    get_function_schemas,
    execute_function_call,
    mark_tool_requires_approval,
    unmark_tool_requires_approval,
    tool_requires_approval,
    list_approval_required_tools,
    resolve_approval,
    get_pending_approvals,
)

# --- Import domain modules to trigger @tool registration ---
from companion_ai.tools.system_tools import (    # noqa: F401
    tool_background_task,
    tool_time,
    tool_memory_search,
    tool_look_at_screen,
    tool_use_computer,
    add_job,           # re-export so monkeypatch on `tools_module.add_job` still works
)
from companion_ai.tools.brain_tools import (     # noqa: F401
    tool_brain_search,
    tool_brain_read,
    tool_brain_write,
    tool_brain_list,
)
from companion_ai.tools.browser_tools import (   # noqa: F401
    tool_browser_goto,
    tool_browser_click,
    tool_browser_type,
    tool_browser_read,
    tool_browser_press,
)
from companion_ai.tools.file_tools import (      # noqa: F401
    tool_read_pdf,
    tool_read_image,
    tool_read_docx,
    tool_list_files,
    tool_find_file,
)
from companion_ai.tools.research_tools import (  # noqa: F401
    tool_wikipedia,
)

__all__ = [
    # Registry
    'tool', 'list_tools', 'run_tool', 'get_function_schemas', 'execute_function_call',
    # Plugins
    'list_plugins', 'get_plugin_catalog', 'get_plugin_policy_state', 'set_workspace_plugin_policy',
    # Policy
    'get_execution_mode', 'set_execution_mode', 'execution_mode', 'evaluate_tool_policy',
    # Approval
    'mark_tool_requires_approval', 'unmark_tool_requires_approval',
    'tool_requires_approval', 'list_approval_required_tools',
    'resolve_approval', 'get_pending_approvals',
    # Tool functions (used by tool_loop.py and tests)
    'tool_brain_read', 'tool_brain_write', 'tool_brain_list', 'tool_brain_search',
    'tool_read_pdf', 'tool_read_image', 'tool_read_docx', 'tool_list_files', 'tool_find_file',
    'tool_memory_search', 'tool_look_at_screen', 'tool_use_computer',
    'tool_browser_goto', 'tool_browser_click', 'tool_browser_type', 'tool_browser_read', 'tool_browser_press',
    'tool_wikipedia', 'tool_background_task', 'tool_time',
    'add_job',
]
