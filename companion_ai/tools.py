"""Tool registry & execution with native function calling support.

Supports both legacy text-based tools (Phase 0) and modern JSON Schema
function calling for Groq native integration.
"""
from __future__ import annotations
import datetime, re, os, json
import threading
from contextlib import contextmanager
from typing import Callable, Dict, Any
from companion_ai.memory import sqlite_backend as mem
from companion_ai.services.jobs import add_job  # Import job manager
from companion_ai.core import config as core_config
from companion_ai.core import metrics as core_metrics

try:
    from companion_ai.memory_v2 import search_memories
except ImportError:
    search_memories = None

# Graceful imports for optional dependencies
try:
    import requests
except ImportError:
    requests = None

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    from PIL import Image
    import pytesseract
except ImportError:
    Image = None
    pytesseract = None

try:
    from docx import Document as DocxDocument
except ImportError:
    DocxDocument = None

ToolFn = Callable[[str], str]

# Legacy text-based tools
_TOOLS: Dict[str, ToolFn] = {}

# Modern function calling schemas (JSON Schema format for Groq)
_FUNCTION_SCHEMAS: Dict[str, Dict[str, Any]] = {}

# Phase 3 plugin metadata
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

def tool(name: str, schema: Dict[str, Any] | None = None, plugin: str = 'core'):
    """Decorator to register both legacy and modern function-calling tools.
    
    Args:
        name: Tool identifier
        schema: Optional JSON Schema for native function calling
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

# ============================================================================
# TOOL DEFINITIONS
# ============================================================================

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
}, plugin='background')
def tool_background_task(description: str, tool_name: str = "", tool_args: Dict = None) -> str:
    """Start a background task."""
    if tool_args is None:
        tool_args = {}
    
    # For legacy calls where args might be mixed
    if isinstance(description, dict):
        # Handle case where arguments are passed as a single dict
        args = description
        description = args.get('description', 'Unknown Task')
        tool_name = args.get('tool_name', 'unknown')
        tool_args = args.get('tool_args', {})

    job_id = add_job(description, tool_name, tool_args)
    return f"Started background task '{description}' with ID: {job_id}. I will notify you when it is complete. Do NOT wait for it."

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
})
def tool_time(_: str = "") -> str:
    """Get current time in ISO format."""
    return datetime.datetime.now().isoformat(timespec='seconds')

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
    """Evaluate whether a tool is allowed under current policy.

    Returns a dict with:
      - allowed: bool
      - reason: optional short reason code (sandbox_denied/plugin_denied/allowlist_denied/unknown_tool)
      - message: human-friendly explanation
    """
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

def run_tool(name: str, arg: str) -> str:
    """Execute a tool by name with string argument (legacy interface)."""
    fn = _TOOLS.get(name)
    if not fn:
        return f'Unknown tool: {name}'
    if not _is_tool_allowed(name):
        return _blocked_tool_message(name)
    return fn(arg)

def get_function_schemas(allowed: list[str] | None = None) -> list[Dict[str, Any]]:
    """Get function calling schemas for native tool calling.

    Args:
        allowed: Optional list of tool names to include. If None, returns all.
    """
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
    
    Args:
        function_name: Name of the function to call
        arguments: Dictionary of arguments parsed from JSON
        
    Returns:
        String result from the function
    """
    # Map native function names to tool functions
    tool_fn = _TOOLS.get(function_name)
    if not tool_fn:
        return f'Unknown function: {function_name}'
    if not _is_tool_allowed(function_name):
        return _blocked_tool_message(function_name)
    
    # Handle different function signatures
    elif function_name == 'get_current_time':
        return tool_fn("")
    elif function_name == 'memory_search':
        return tool_fn(arguments.get('query', ''))
    # memory_insight removed - V5 cleanup
    # Brain tools (V5)
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
    # Browser automation tools
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
})
def tool_memory_search(query: str) -> str:
    """Search Mem0 vector database for relevant memories."""
    if not search_memories:
        return "Memory search unavailable (Mem0 not loaded)."
    
    try:
        results = search_memories(query, limit=5)
        if not results:
            return f"No memories found for '{query}'."
        
        output = [f"🧠 Memory Search Results for '{query}':"]
        for i, res in enumerate(results, 1):
            # Handle both dict (Mem0 v2) and object return types if any
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

@tool('brain_search', schema={
    "type": "function",
    "function": {
        "name": "brain_search",
        "description": "Search across all documents in the brain folder (PDFs, text files, notes) using semantic search. Use this to find specific information from uploaded documents or notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What to search for in the brain documents (e.g., 'investment terms', 'meeting notes from last week')"
                }
            },
            "required": ["query"]
        }
    }
})
def tool_brain_search(query: str) -> str:
    """Search brain folder documents semantically."""
    try:
        from companion_ai.brain_index import brain_search
        return brain_search(query)
    except Exception as e:
        return f"Brain search error: {str(e)}"

# memory_insight tool removed - V5 cleanup (consolidated to memory_search)

# ============================================================================
# BRAIN TOOLS - Model-controlled persistent memory (V5)
# ============================================================================

@tool('brain_read', schema={
    "type": "function",
    "function": {
        "name": "brain_read",
        "description": "Read a file from your persistent brain folder. Use this to recall your personality notes, user context, learned rules, or scratchpad. Common paths: 'memories/personality.md', 'memories/user_context.md', 'training/learned_rules.md', 'training/scratchpad.md'",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within brain folder (e.g., 'memories/user_context.md')"
                }
            },
            "required": ["path"]
        }
    }
})
def tool_brain_read(path: str) -> str:
    """Read from brain folder."""
    from companion_ai.brain_manager import brain_read
    return brain_read(path)

@tool('brain_write', schema={
    "type": "function",
    "function": {
        "name": "brain_write",
        "description": "Write or update a file in your persistent brain folder. Use this to remember important facts, update your personality, or save learned rules. CANNOT write to system/ folder. Keep content concise.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Relative path within brain folder (e.g., 'memories/user_context.md')"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (markdown format preferred)"
                },
                "append": {
                    "type": "boolean",
                    "description": "If true, append to existing content instead of overwriting"
                }
            },
            "required": ["path", "content"]
        }
    }
})
def tool_brain_write(path: str, content: str, append: bool = False) -> str:
    """Write to brain folder."""
    from companion_ai.brain_manager import brain_write
    return brain_write(path, content, append)

@tool('brain_list', schema={
    "type": "function",
    "function": {
        "name": "brain_list",
        "description": "List files in your brain folder to see what you have stored. Shows file paths and sizes.",
        "parameters": {
            "type": "object",
            "properties": {
                "subdir": {
                    "type": "string",
                    "description": "Optional subdirectory to list (e.g., 'memories' or 'training'). Empty for all."
                }
            },
            "required": []
        }
    }
})
def tool_brain_list(subdir: str = "") -> str:
    """List brain folder contents."""
    from companion_ai.brain_manager import brain_list
    return brain_list(subdir)


# ============================================================================
# BROWSER AUTOMATION TOOLS (Playwright-based)
# ============================================================================

@tool('browser_goto', schema={
    "type": "function",
    "function": {
        "name": "browser_goto",
        "description": "Navigate the browser to a URL. Opens a new browser if not already open. Use this to visit websites for research, data extraction, or automation.",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL to navigate to (e.g., 'google.com' or 'https://wikipedia.org')"
                }
            },
            "required": ["url"]
        }
    }
})
def tool_browser_goto(url: str) -> str:
    """Navigate browser to URL."""
    try:
        from companion_ai.agents.browser import sync_goto
        return sync_goto(url)
    except Exception as e:
        return f"Browser error: {str(e)}"

@tool('browser_click', schema={
    "type": "function",
    "function": {
        "name": "browser_click",
        "description": "Click an element on the current webpage by CSS selector or text content. More reliable than vision-based clicking.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector (e.g., '#submit-btn', '.menu-item', 'button') or leave empty if using text"
                },
                "text": {
                    "type": "string",
                    "description": "Text content of the element to click (e.g., 'Submit', 'Login'). Use this for buttons/links."
                }
            },
            "required": []
        }
    }
})
def tool_browser_click(selector: str = "", text: str = None) -> str:
    """Click element by selector or text."""
    try:
        from companion_ai.agents.browser import sync_click
        return sync_click(selector, text)
    except Exception as e:
        return f"Browser click error: {str(e)}"

@tool('browser_type', schema={
    "type": "function",
    "function": {
        "name": "browser_type",
        "description": "Type text into an input field on the current webpage. Use CSS selector to identify the input.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "CSS selector for the input field (e.g., '#search', 'input[name=q]', '.email-input')"
                },
                "text": {
                    "type": "string",
                    "description": "Text to type into the field"
                }
            },
            "required": ["selector", "text"]
        }
    }
})
def tool_browser_type(selector: str, text: str) -> str:
    """Type into input field."""
    try:
        from companion_ai.agents.browser import sync_type
        return sync_type(selector, text)
    except Exception as e:
        return f"Browser type error: {str(e)}"

@tool('browser_read', schema={
    "type": "function",
    "function": {
        "name": "browser_read",
        "description": "Read text content from the current webpage or a specific element. Use this to extract information from web pages.",
        "parameters": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "Optional CSS selector to read specific element (e.g., '.article-body', '#content'). Omit to read whole page."
                }
            },
            "required": []
        }
    }
})
def tool_browser_read(selector: str = None) -> str:
    """Read text from page/element."""
    try:
        from companion_ai.agents.browser import sync_get_text
        return sync_get_text(selector)
    except Exception as e:
        return f"Browser read error: {str(e)}"

@tool('browser_press', schema={
    "type": "function",
    "function": {
        "name": "browser_press",
        "description": "Press a keyboard key in the browser (e.g., Enter, Tab, Escape).",
        "parameters": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Key to press (Enter, Tab, Escape, ArrowDown, etc.)"
                }
            },
            "required": ["key"]
        }
    }
})
def tool_browser_press(key: str) -> str:
    """Press keyboard key in browser."""
    try:
        from companion_ai.agents.browser import sync_press_key
        return sync_press_key(key)
    except Exception as e:
        return f"Browser press error: {str(e)}"

@tool('wikipedia_lookup', schema={
    "type": "function",
    "function": {
        "name": "wikipedia_lookup",
        "description": "Look up factual information on Wikipedia. Returns a concise summary of the topic. Best for facts, definitions, historical info.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Topic or term to look up (e.g., 'Python programming', 'Albert Einstein', 'World War 2')"
                }
            },
            "required": ["query"]
        }
    }
})
def tool_wikipedia(query: str) -> str:
    """Look up information on Wikipedia."""
    if not requests:
        return "Wikipedia lookup unavailable (requests library not installed)"
    
    try:
        # Wikipedia API - search for article
        search_url = "https://en.wikipedia.org/w/api.php"
        headers = {
            'User-Agent': 'CompanionAI/1.0 (Educational Assistant)'
        }
        search_params = {
            'action': 'opensearch',
            'search': query,
            'limit': 1,
            'format': 'json'
        }
        
        search_resp = requests.get(search_url, params=search_params, headers=headers, timeout=5.0)
        search_data = search_resp.json()
        
        if not search_data[1]:  # No results
            return f"No Wikipedia article found for '{query}'"
        
        title = search_data[1][0]
        
        # Get article summary
        summary_params = {
            'action': 'query',
            'prop': 'extracts',
            'exintro': True,
            'explaintext': True,
            'titles': title,
            'format': 'json'
        }
        
        summary_resp = requests.get(search_url, params=summary_params, headers=headers, timeout=5.0)
        summary_data = summary_resp.json()
        
        pages = summary_data['query']['pages']
        page = next(iter(pages.values()))
        
        if 'extract' not in page:
            return f"Could not retrieve summary for '{title}'"
        
        extract = page['extract']
        
        # Limit to ~500 chars
        if len(extract) > 500:
            extract = extract[:497] + '...'
        
        return f"📖 Wikipedia - {title}:\n\n{extract}"
        
    except requests.Timeout:
        return "Wikipedia lookup timeout. Try again."
    except Exception as e:
        return f"Wikipedia error: {str(e)[:100]}"

# ============================================================================
# FILE READING TOOLS
# ============================================================================

@tool('read_pdf', schema={
    "type": "function",
    "function": {
        "name": "read_pdf",
        "description": "Extract and read text from a PDF file. Useful for homework, textbooks, research papers. Provide the full file path.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute or relative path to the PDF file (e.g., 'C:/Users/docs/homework.pdf' or 'textbook.pdf')"
                },
                "page_number": {
                    "type": "integer",
                    "description": "Optional: specific page number to read (1-indexed). If not provided, reads first 3 pages."
                }
            },
            "required": ["file_path"]
        }
    }
})
def tool_read_pdf(file_path: str, page_number: int | None = None) -> str:
    """Read text from a PDF file."""
    if not pypdf:
        return "PDF reading unavailable. Install with: pip install pypdf"
    
    if not os.path.exists(file_path):
        return f"File not found: {file_path}"
    
    try:
        with open(file_path, 'rb') as file:
            pdf_reader = pypdf.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            if page_number:
                # Read specific page
                if page_number < 1 or page_number > total_pages:
                    return f"Page {page_number} out of range. PDF has {total_pages} pages."
                
                page = pdf_reader.pages[page_number - 1]  # 0-indexed
                text = page.extract_text()
                
                return f"📄 PDF: {os.path.basename(file_path)} - Page {page_number}/{total_pages}\n\n{text}"
            else:
                # Read first 3 pages
                pages_to_read = min(3, total_pages)
                texts = []
                
                for i in range(pages_to_read):
                    page = pdf_reader.pages[i]
                    page_text = page.extract_text()
                    if page_text.strip():
                        texts.append(f"=== Page {i+1} ===\n{page_text}")
                
                result = '\n\n'.join(texts)
                return f"📄 PDF: {os.path.basename(file_path)} ({total_pages} pages total, showing first {pages_to_read})\n\n{result}"
                
    except Exception as e:
        return f"Error reading PDF: {str(e)[:200]}"

@tool('read_image_text', schema={
    "type": "function",
    "function": {
        "name": "read_image_text",
        "description": "Extract text from an image using OCR (Optical Character Recognition). Works with screenshots, photos of documents, handwritten notes (if clear), math problems.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to image file (jpg, png, bmp, etc.)"
                }
            },
            "required": ["file_path"]
        }
    }
})
def tool_read_image(file_path: str) -> str:
    """Extract text from an image using OCR."""
    if not Image or not pytesseract:
        return "Image OCR unavailable. Install with: pip install Pillow pytesseract\nAlso install Tesseract: https://github.com/tesseract-ocr/tesseract"
    
    if not os.path.exists(file_path):
        return f"Image not found: {file_path}"
    
    try:
        # Open and process image
        img = Image.open(file_path)
        
        # Extract text using Tesseract OCR
        text = pytesseract.image_to_string(img)
        
        if not text.strip():
            return f"No text detected in image: {os.path.basename(file_path)}"
        
        return f"📷 Image OCR: {os.path.basename(file_path)}\n\n{text}"
        
    except pytesseract.TesseractNotFoundError:
        return "Tesseract OCR not installed. Download from: https://github.com/tesseract-ocr/tesseract/releases"
    except Exception as e:
        return f"Error reading image: {str(e)[:200]}"

@tool('read_document', schema={
    "type": "function",
    "function": {
        "name": "read_document",
        "description": "Read text from Word documents (.docx). Useful for essays, assignments, reports.",
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to .docx file"
                }
            },
            "required": ["file_path"]
        }
    }
})
def tool_read_docx(file_path: str) -> str:
    """Read text from a Word document."""
    if not DocxDocument:
        return "Word document reading unavailable. Install with: pip install python-docx"
    
    if not os.path.exists(file_path):
        return f"Document not found: {file_path}"
    
    try:
        doc = DocxDocument(file_path)
        
        # Extract all paragraphs
        paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
        
        if not paragraphs:
            return f"No text found in document: {os.path.basename(file_path)}"
        
        text = '\n\n'.join(paragraphs)
        
        # Limit output
        if len(text) > 3000:
            text = text[:2997] + '...'
        
        return f"📝 Word Document: {os.path.basename(file_path)}\n\n{text}"
        
    except Exception as e:
        return f"Error reading document: {str(e)[:200]}"

@tool('list_files', schema={
    "type": "function",
    "function": {
        "name": "list_files",
        "description": "List files in a directory. Useful for finding homework files, PDFs, images before reading them.",
        "parameters": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path to list (e.g., 'C:/Users/Documents' or '.' for current)"
                },
                "file_type": {
                    "type": "string",
                    "description": "Optional: filter by extension (e.g., 'pdf', 'png', 'docx')"
                }
            },
            "required": ["directory"]
        }
    }
})
def tool_list_files(directory: str, file_type: str | None = None) -> str:
    """List files in a directory with optional filtering."""
    if not os.path.exists(directory):
        return f"Directory not found: {directory}"
    
    if not os.path.isdir(directory):
        return f"Not a directory: {directory}"
    
    try:
        files = []
        for item in os.listdir(directory):
            item_path = os.path.join(directory, item)
            if os.path.isfile(item_path):
                # Filter by file type if specified
                if file_type:
                    if item.lower().endswith(f'.{file_type.lower()}'):
                        files.append(item)
                else:
                    files.append(item)
        
        if not files:
            filter_msg = f" (filtered by .{file_type})" if file_type else ""
            return f"No files found in {directory}{filter_msg}"
        
        # Group by extension
        by_ext: Dict[str, list[str]] = {}
        for f in files:
            ext = f.split('.')[-1].lower() if '.' in f else 'no extension'
            if ext not in by_ext:
                by_ext[ext] = []
            by_ext[ext].append(f)
        
        result = [f"📁 Files in {directory}:\n"]
        for ext, file_list in sorted(by_ext.items()):
            result.append(f"\n{ext.upper()} files ({len(file_list)}):")
            for f in sorted(file_list)[:20]:  # Limit to 20 per type
                result.append(f"  - {f}")
            if len(file_list) > 20:
                result.append(f"  ... and {len(file_list) - 20} more")
        
        return '\n'.join(result)
        
    except Exception as e:
        return f"Error listing directory: {str(e)[:200]}"

@tool('find_file', schema={
    "type": "function",
    "function": {
        "name": "find_file",
        "description": "Search for files by name or keyword in common user directories (Downloads, Documents, Desktop). Returns matching files with full paths.",
        "parameters": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Filename or keyword to search for (e.g., 'Companion AI', 'report', 'homework')"
                },
                "file_type": {
                    "type": "string",
                    "description": "Optional: file extension to filter (e.g., 'pdf', 'docx', 'png')"
                }
            },
            "required": ["filename"]
        }
    }
})
def tool_find_file(filename: str, file_type: str | None = None) -> str:
    """Search for files in common user directories."""
    import os
    from pathlib import Path
    
    # Common directories to search
    user_home = os.path.expanduser("~")
    search_dirs = [
        os.path.join(user_home, "Downloads"),
        os.path.join(user_home, "Documents"),
        os.path.join(user_home, "Desktop"),
    ]
    
    matches = []
    search_term = filename.lower()
    
    for directory in search_dirs:
        if not os.path.exists(directory):
            continue
            
        try:
            for item in os.listdir(directory):
                item_path = os.path.join(directory, item)
                if not os.path.isfile(item_path):
                    continue
                
                # Check if filename matches
                item_lower = item.lower()
                if search_term in item_lower:
                    # Check file type if specified
                    if file_type and not item_lower.endswith(f'.{file_type.lower()}'):
                        continue
                    
                    # Get file size
                    size = os.path.getsize(item_path)
                    size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.1f} MB"
                    
                    matches.append({
                        'name': item,
                        'path': item_path,
                        'size': size_str,
                        'dir': os.path.basename(directory)
                    })
        except Exception:
            continue
    
    if not matches:
        type_msg = f" (*.{file_type})" if file_type else ""
        return f"No files matching '{filename}'{type_msg} found in Downloads, Documents, or Desktop."
    
    # Format results
    result = [f"Found {len(matches)} file(s) matching '{filename}':"]
    for m in matches[:10]:  # Limit to 10 results
        result.append(f"\n📄 {m['name']}")
        result.append(f"   Location: {m['dir']}/")
        result.append(f"   Size: {m['size']}")
        result.append(f"   Full path: {m['path']}")
    
    if len(matches) > 10:
        result.append(f"\n... and {len(matches) - 10} more matches")
    
    return '\n'.join(result)

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
})
def tool_look_at_screen(prompt: str = "What is on the screen?") -> str:
    """Analyze the current screen content."""
    try:
        from companion_ai.vision_manager import vision_manager
        return vision_manager.analyze_current_screen(prompt)
    except Exception as e:
        return f"Error analyzing screen: {e}"

# consult_compound_system tool removed - V5 cleanup (120B has built-in search)

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
})
def tool_use_computer(action: str, text: str = "") -> str:
    """Execute computer control actions."""
    from companion_ai.core import config as core_config
    if not core_config.ENABLE_COMPUTER_USE:
        return "Computer Use is disabled in configuration."

    try:
        from companion_ai.computer_agent import computer_agent

        # Mark activity so UI can show the banner only when actions occur.
        computer_agent.mark_action()
        
        if action == "click":
            if not text: return "Error: 'text' (element description) is required for click action."
            return computer_agent.click_element(text)
            
        elif action == "type":
            if not text: return "Error: 'text' (content to type) is required for type action."
            return computer_agent.type_text(text, enter=True)
            
        elif action == "press":
            return computer_agent.press_key(text)
            
        elif action == "launch":
            return computer_agent.launch_app(text)
            
        elif action == "scroll_up":
            return computer_agent.scroll("up")
            
        elif action == "scroll_down":
            return computer_agent.scroll("down")
            
        else:
            return f"Unknown action: {action}"
            
    except Exception as e:
        return f"Computer Use Error: {e}"

__all__ = ['list_tools', 'run_tool', 'get_function_schemas', 'execute_function_call']
