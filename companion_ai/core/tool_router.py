"""Tool Router - 120B decides, 8B/Maverick executes.

This module handles parsing tool decisions from the primary model (120B)
and routing execution to the appropriate executor model.

Flow:
1. 120B receives user message + context
2. 120B either responds directly OR outputs tool instructions
3. If tools needed, 8B (or Maverick for vision) executes them
4. 120B synthesizes the final response
"""
from __future__ import annotations
import re
import json
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Tool decision format from 120B:
# TOOLS: [tool_name] or TOOLS: [tool1, tool2]
"""Deprecated module.

Tool routing is now handled directly via Groq native function calling in
`llm_interface.py`. This file remains only to avoid import errors; do not
use it. Any import of this module should be treated as a bug.
"""

raise ImportError("companion_ai.core.tool_router is deprecated and unused")
    """Build a prompt for 120B to decide if tools are needed.
    
    Args:
        user_message: The user's message
        available_tools: List of available tool names
        memory_context: Optional memory/context string
        
    Returns:
        Prompt for 120B decision
    """
    tools_list = ", ".join(available_tools)
    
    prompt_parts = [
        "You are deciding how to respond to the user.",
        "",
        f"Available tools: [{tools_list}]",
        "",
        "If you need real-time data (time, weather, calculations, files, memory search), output:",
        "TOOLS: [tool_name]",
        "ARGS: {\"tool_name\": {\"param\": \"value\"}}  (if needed)",
        "",
        "If you can answer directly without tools, just respond normally.",
        "",
    ]
    
    if memory_context:
        prompt_parts.extend([
            "Context:",
            memory_context,
            ""
        ])
    
    prompt_parts.append(f"User: {user_message}")
    
    return "\n".join(prompt_parts)


# Mapping of common intents to likely tools
INTENT_TOOL_HINTS = {
    'time': ['get_current_time'],
    'weather': [],  # Handled by compound
    'calculate': [],  # Handled by compound  
    'remember': ['memory_insight'],
    'memory': ['memory_insight'],
    'know about': ['memory_insight'],
    'file': ['find_file', 'read_pdf', 'read_document'],
    'pdf': ['read_pdf', 'find_file'],
    'screen': ['look_at_screen'],
    'look at': ['look_at_screen'],
    'wikipedia': ['wikipedia_lookup'],
}


def suggest_tools_for_intent(user_message: str) -> List[str]:
    """Quick heuristic to suggest likely tools based on message content.
    
    This helps 120B make faster decisions by providing hints.
    
    Args:
        user_message: The user's message
        
    Returns:
        List of suggested tool names (may be empty)
    """
    message_lower = user_message.lower()
    suggestions = []
    
    for keyword, tools in INTENT_TOOL_HINTS.items():
        if keyword in message_lower:
            suggestions.extend(tools)
    
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in suggestions:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    
    return unique
