"""Tool Router - DEPRECATED

This module is deprecated. Tool routing is now handled directly via Groq 
native function calling in `llm_interface.py`.

This file exists only to provide clear deprecation messaging. Do not import.
"""

raise ImportError(
    "companion_ai.core.tool_router is deprecated. "
    "Tool routing now uses Groq native function calling in llm_interface.py"
)
