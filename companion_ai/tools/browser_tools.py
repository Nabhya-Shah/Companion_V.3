"""Browser automation tools — Playwright-based web interaction."""
from __future__ import annotations

from companion_ai.tools.registry import tool


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
