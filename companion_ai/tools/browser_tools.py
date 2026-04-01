"""Browser automation tools — Playwright-based web interaction."""
from __future__ import annotations

from companion_ai.tools.registry import tool


def _format_browser_error(action: str, err: Exception) -> str:
    text = str(err)
    lower = text.lower()

    if isinstance(err, ModuleNotFoundError) or "no module named 'playwright'" in lower:
        return (
            f"Browser {action} error: Playwright is not installed. "
            "Install with './.venv/bin/python -m pip install playwright' and "
            "'./.venv/bin/playwright install chromium'."
        )

    if "could not launch chrome" in lower or "chrome/chromium not found" in lower:
        return (
            f"Browser {action} error: Chrome/Chromium runtime is unavailable. "
            "Install a browser or set CHROME_PATH to a valid executable."
        )

    return f"Browser {action} error: {text}"


def _normalize_browser_result(action: str, result: str) -> str:
    """Convert known browser runtime failure strings into actionable hints."""
    if not isinstance(result, str):
        return result
    lower = result.lower()

    if "no module named 'playwright'" in lower:
        return _format_browser_error(action, ModuleNotFoundError("No module named 'playwright'"))

    if "could not launch chrome" in lower or "chrome/chromium not found" in lower:
        return _format_browser_error(action, RuntimeError("Could not launch Chrome"))

    return result


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
}, risk_tier='medium', category='browser')
def tool_browser_goto(url: str) -> str:
    """Navigate browser to URL."""
    try:
        from companion_ai.agents.browser import sync_goto
        return _normalize_browser_result("navigate", sync_goto(url))
    except Exception as e:
        return _format_browser_error("navigate", e)


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
}, risk_tier='medium', category='browser')
def tool_browser_click(selector: str = "", text: str = None) -> str:
    """Click element by selector or text."""
    try:
        from companion_ai.agents.browser import sync_click
        return _normalize_browser_result("click", sync_click(selector, text))
    except Exception as e:
        return _format_browser_error("click", e)


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
}, risk_tier='medium', category='browser')
def tool_browser_type(selector: str, text: str) -> str:
    """Type into input field."""
    try:
        from companion_ai.agents.browser import sync_type
        return _normalize_browser_result("type", sync_type(selector, text))
    except Exception as e:
        return _format_browser_error("type", e)


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
}, risk_tier='low', category='browser')
def tool_browser_read(selector: str = None) -> str:
    """Read text from page/element."""
    try:
        from companion_ai.agents.browser import sync_get_text
        return _normalize_browser_result("read", sync_get_text(selector))
    except Exception as e:
        return _format_browser_error("read", e)


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
}, risk_tier='medium', category='browser')
def tool_browser_press(key: str) -> str:
    """Press keyboard key in browser."""
    try:
        from companion_ai.agents.browser import sync_press_key
        return _normalize_browser_result("press", sync_press_key(key))
    except Exception as e:
        return _format_browser_error("press", e)
