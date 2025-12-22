# companion_ai/local_loops/tool_loop.py
"""
Tool Loop - Execute simple tools using local model.

Operations:
- get_time: Get current time
- web_search: Search the web
- calculate: Do math
- wikipedia: Look up information

Uses a small local text model for tool selection and execution.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List
from .base import Loop, LoopResult, LoopStatus
from .registry import register_loop

logger = logging.getLogger(__name__)


@register_loop
class ToolLoop(Loop):
    """Simple tool execution loop."""
    
    name = "tools"
    description = "Execute simple tools: time, calculations, web search, wikipedia lookup"
    
    system_prompts = {
        "executor": """You are a tool execution agent. Execute the requested tool
and return the result. Be precise and concise."""
    }
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
    
    def _get_supported_operations(self) -> List[str]:
        return ["get_time", "calculate", "web_search", "wikipedia"]
    
    async def execute(self, task: Dict[str, Any]) -> LoopResult:
        """Execute a tool task.
        
        Task format:
            {"operation": "get_time"}
            {"operation": "calculate", "expression": "2 + 2"}
            {"operation": "web_search", "query": "weather today"}
            {"operation": "wikipedia", "topic": "Python programming"}
        """
        operation = task.get("operation")
        
        if operation == "get_time":
            return await self._get_time()
        elif operation == "calculate":
            return await self._calculate(task.get("expression", ""))
        elif operation == "web_search":
            return await self._web_search(task.get("query", ""))
        elif operation == "wikipedia":
            return await self._wikipedia(task.get("topic", ""))
        else:
            return LoopResult.failure(f"Unknown operation: {operation}")
    
    async def _get_time(self) -> LoopResult:
        """Get current time."""
        try:
            now = datetime.now()
            return LoopResult.success(
                data={
                    "time": now.strftime("%H:%M:%S"),
                    "date": now.strftime("%Y-%m-%d"),
                    "datetime": now.isoformat(),
                    "formatted": now.strftime("%A, %B %d, %Y at %I:%M %p")
                },
                operation="get_time"
            )
        except Exception as e:
            return LoopResult.failure(str(e))
    
    async def _calculate(self, expression: str) -> LoopResult:
        """Evaluate a math expression safely."""
        if not expression:
            return LoopResult.failure("No expression provided")
        
        try:
            # Safe eval with only math operations
            allowed = set("0123456789+-*/().% ")
            if not all(c in allowed for c in expression):
                return LoopResult.failure("Invalid characters in expression")
            
            result = eval(expression)  # Safe because we validated input
            
            return LoopResult.success(
                data={"expression": expression, "result": result},
                operation="calculate"
            )
        except Exception as e:
            return LoopResult.failure(f"Calculation error: {e}")
    
    async def _web_search(self, query: str) -> LoopResult:
        """Perform web search.
        
        Uses existing compound/web search functionality.
        """
        if not query:
            return LoopResult.failure("No query provided")
        
        try:
            # Use existing tools infrastructure
            from companion_ai.tools import execute_function_call
            
            result = execute_function_call(
                "consult_compound",
                {"query": query}
            )
            
            return LoopResult.success(
                data={"query": query, "result": result},
                operation="web_search"
            )
        except Exception as e:
            logger.error(f"Web search failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _wikipedia(self, topic: str) -> LoopResult:
        """Look up Wikipedia article."""
        if not topic:
            return LoopResult.failure("No topic provided")
        
        try:
            from companion_ai.tools import execute_function_call
            
            result = execute_function_call(
                "wikipedia_lookup",
                {"query": topic}
            )
            
            return LoopResult.success(
                data={"topic": topic, "result": result},
                operation="wikipedia"
            )
        except Exception as e:
            logger.error(f"Wikipedia lookup failed: {e}")
            return LoopResult.failure(str(e))
