"""System tools — time, memory search, background tasks, vision, computer use."""
from __future__ import annotations

import datetime
from typing import Dict

from companion_ai.services.jobs import add_job
from companion_ai.core import config as core_config
from companion_ai.tools.registry import tool

try:
    from companion_ai.memory.mem0_backend import search_memories
except ImportError:
    search_memories = None


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
}, plugin='background')
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
})
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
})
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
})
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
})
def tool_use_computer(action: str, text: str = "") -> str:
    """Execute computer control actions."""
    if not core_config.ENABLE_COMPUTER_USE:
        return "Computer Use is disabled in configuration."

    try:
        from companion_ai.computer_agent import computer_agent

        computer_agent.mark_action()

        if action == "click":
            if not text:
                return "Error: 'text' (element description) is required for click action."
            return computer_agent.click_element(text)
        elif action == "type":
            if not text:
                return "Error: 'text' (content to type) is required for type action."
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
