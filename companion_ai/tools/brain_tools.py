"""Brain tools — persistent brain folder read/write/list/search."""
from __future__ import annotations

from companion_ai.tools.registry import tool


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
