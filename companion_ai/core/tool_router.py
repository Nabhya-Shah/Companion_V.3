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
# ARGS: {"tool_name": {"param": "value"}}

TOOL_PATTERN = re.compile(r'TOOLS:\s*\[([^\]]+)\]', re.IGNORECASE)
ARGS_PATTERN = re.compile(r'ARGS:\s*(\{.*\})', re.IGNORECASE | re.DOTALL)


@dataclass
class ToolDecision:
    """Parsed tool decision from 120B."""
    needs_tools: bool
    tools: List[str]
    args: Dict[str, Dict[str, Any]]
    direct_response: Optional[str] = None  # If no tools needed


def parse_tool_decision(model_output: str) -> ToolDecision:
    """Parse 120B's output to determine if tools are needed.
    
    Expected formats:
    1. Direct response (no tools): Just text
    2. Single tool: "TOOLS: [get_current_time]"
    3. Multiple tools: "TOOLS: [memory_insight, get_current_time]"
    4. With args: "TOOLS: [memory_insight]\nARGS: {\"memory_insight\": {\"query\": \"user\", \"mode\": \"IMPORTANT\"}}"
    
    Args:
        model_output: Raw text from 120B
        
    Returns:
        ToolDecision with parsed information
    """
    output = model_output.strip()
    
    # Check for tool pattern
    tool_match = TOOL_PATTERN.search(output)
    
    if not tool_match:
        # No tools requested - this is a direct response
        return ToolDecision(
            needs_tools=False,
            tools=[],
            args={},
            direct_response=output
        )
    
    # Parse tool names
    tools_str = tool_match.group(1)
    tools = [t.strip().strip('"\'') for t in tools_str.split(',')]
    tools = [t for t in tools if t]  # Remove empty strings
    
    logger.info(f"🔧 120B requested tools: {tools}")
    
    # Parse arguments if provided
    args: Dict[str, Dict[str, Any]] = {}
    args_match = ARGS_PATTERN.search(output)
    
    if args_match:
        try:
            args_json = args_match.group(1)
            args = json.loads(args_json)
            logger.info(f"📋 Tool arguments: {args}")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse tool args: {e}")
            # Continue without args - tools can use defaults
    
    return ToolDecision(
        needs_tools=True,
        tools=tools,
        args=args,
        direct_response=None
    )


def get_executor_model(tool_name: str) -> str:
    """Determine which model should execute a given tool.
    
    Args:
        tool_name: Name of the tool to execute
        
    Returns:
        Model identifier string
    """
    # Vision tools need Maverick
    VISION_TOOLS = {'look_at_screen', 'read_image_text', 'analyze_image'}
    
    if tool_name in VISION_TOOLS:
        return 'meta-llama/llama-4-maverick-17b-128e-instruct'
    
    # All other tools use fast 8B
    return 'llama-3.1-8b-instant'


def build_tool_execution_prompt(
    user_message: str,
    tools: List[str],
    args: Dict[str, Dict[str, Any]]
) -> str:
    """Build a prompt for the executor model (8B) to run tools.
    
    The executor just needs to know what to call - no decision making.
    
    Args:
        user_message: Original user request
        tools: List of tool names to execute
        args: Pre-determined arguments for each tool
        
    Returns:
        Prompt string for executor
    """
    prompt_parts = [
        "Execute these tools to answer the user's question.",
        f"User asked: {user_message}",
        "",
        "Tools to use:"
    ]
    
    for tool in tools:
        tool_args = args.get(tool, {})
        if tool_args:
            prompt_parts.append(f"- {tool}: {json.dumps(tool_args)}")
        else:
            prompt_parts.append(f"- {tool}")
    
    prompt_parts.extend([
        "",
        "Call each tool and return the results. Do not add commentary."
    ])
    
    return "\n".join(prompt_parts)


def build_decision_prompt(
    user_message: str,
    available_tools: List[str],
    memory_context: Optional[str] = None
) -> str:
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
