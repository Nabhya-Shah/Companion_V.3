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
        return [
            "get_time", "calculate", "web_search", "wikipedia", "brain_read", "brain_list",
            "browser_goto", "browser_click", "browser_type", "browser_read", "browser_press",
            "add_bookmark", "open_bookmark", "enable_browser_control",
            "light_on", "light_off", "light_dim"  # Loxone smart home
        ]
    
    async def execute(self, task: Dict[str, Any]) -> LoopResult:
        """Execute a tool task.
        
        Task format:
            {"operation": "get_time"}
            {"operation": "calculate", "expression": "2 + 2"}
            {"operation": "web_search", "query": "weather today"}
            {"operation": "wikipedia", "topic": "Python programming"}
            {"operation": "brain_read", "path": "notes/todo.md"}
            {"operation": "brain_list", "subdir": "notes"}
        """
        operation = task.get("operation")
        
        if operation == "get_time":
            return await self._get_time()
        elif operation == "calculate":
            return await self._calculate(task.get("expression", ""))
        elif operation == "web_search":
            return await self._web_search(task.get("query", ""))
        elif operation == "add_bookmark":
            return await self._add_bookmark(task.get("name", ""), task.get("url", ""))
        elif operation == "open_bookmark":
            return await self._open_bookmark(task.get("name", ""))
        elif operation == "enable_browser_control":
            return await self._enable_browser_control()
        elif operation == "browser_goto":
            url = task.get("url", "")
            # Smart bookmark check: if URL looks like a name, check bookmarks first
            if url and "." not in url and "://" not in url:
                bookmark_result = await self._open_bookmark(url)
                if bookmark_result.status == LoopStatus.SUCCESS:
                    return bookmark_result
            # Also check if the domain matches a bookmark name (e.g., "bromcom.com" matches bookmark "bromcom")
            elif url:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(url if "://" in url else f"https://{url}")
                    domain = parsed.netloc or parsed.path
                    # Extract first part of domain (e.g., "bromcom" from "bromcom.com")
                    domain_parts = domain.replace("www.", "").split(".")
                    if domain_parts:
                        potential_name = domain_parts[0].lower()
                        bookmark_result = await self._open_bookmark(potential_name)
                        if bookmark_result.status == LoopStatus.SUCCESS:
                            logger.info(f"📚 Using bookmark '{potential_name}' instead of guessed URL")
                            return bookmark_result
                except Exception:
                    pass
            return await self._browser_tool("browser_goto", {"url": url})
        elif operation == "browser_click":
            return await self._browser_tool("browser_click", {"selector": task.get("selector", ""), "text": task.get("text", "")})
        elif operation == "browser_type":
            return await self._browser_tool("browser_type", {"selector": task.get("selector", ""), "text": task.get("text", "")})
        elif operation == "browser_read":
            return await self._browser_tool("browser_read", {"selector": task.get("selector", "")})
        elif operation == "browser_press":
            return await self._browser_tool("browser_press", {"key": task.get("key", "")})
        elif operation == "wikipedia":
            return await self._wikipedia(task.get("topic", ""))
        elif operation == "brain_read":
            return await self._brain_read(task.get("path", ""))
        elif operation == "brain_list":
            return await self._brain_list(task.get("subdir", ""))
        # Loxone Smart Home - Light Control
        elif operation == "light_on":
            return await self._light_on(task.get("room", ""))
        elif operation == "light_off":
            return await self._light_off(task.get("room", ""))
        elif operation == "light_dim":
            return await self._light_dim(task.get("room", ""), task.get("level", 50))
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
        
        Using browser automation since internal search tool was removed.
        """
        if not query:
            return LoopResult.failure("No query provided")
        
        try:
            from companion_ai.tools import execute_function_call
            
            # Use browser to search DuckDuckGo
            search_url = f"https://duckduckgo.com/?q={query.replace(' ', '+')}"
            
            result = execute_function_call(
                "browser_goto",
                {"url": search_url}
            )
            
            return LoopResult.success(
                data={"query": query, "result": f"Opened search for '{query}' in browser."},
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

    async def _brain_read(self, path: str) -> LoopResult:
        """Read from brain folder."""
        if not path:
            return LoopResult.failure("No path provided")
        
        try:
            from companion_ai.tools import tool_brain_read
            
            # Using the direct tool function (sync)
            result = tool_brain_read(path)
            
            return LoopResult.success(
                data={"path": path, "content": result},
                operation="brain_read"
            )
        except Exception as e:
            logger.error(f"Brain read failed: {e}")
            return LoopResult.failure(str(e))

    async def _brain_list(self, subdir: str) -> LoopResult:
        """List brain folder."""
        try:
            from companion_ai.tools import tool_brain_list
            
            # Using the direct tool function (sync)
            result = tool_brain_list(subdir)
            
            return LoopResult.success(
                data={"subdir": subdir, "files": result},
                operation="brain_list"
            )
        except Exception as e:
            logger.error(f"Brain list failed: {e}")
            return LoopResult.failure(str(e))

    async def _browser_tool(self, tool_name: str, args: Dict) -> LoopResult:
        """Execute a browser tool."""
        try:
            from companion_ai.tools import execute_function_call
            
            result = execute_function_call(tool_name, args)
            
            return LoopResult.success(
                data={"result": result, "args": args},
                operation=tool_name
            )
        except Exception as e:
            logger.error(f"Browser tool {tool_name} failed: {e}")
            return LoopResult.failure(f"{tool_name} failed: {str(e)}")

    async def _add_bookmark(self, name: str, url: str) -> LoopResult:
        """Save a bookmark to the brain."""
        try:
            from companion_ai.tools import tool_brain_read, tool_brain_write
            import json
            
            # Read existing
            try:
                content = tool_brain_read("bookmarks.json")
                bookmarks = json.loads(content) if content else {}
            except:
                bookmarks = {}
            
            # Update
            bookmarks[name.lower()] = url
            
            # Write back
            tool_brain_write("bookmarks.json", json.dumps(bookmarks, indent=2), overwrite=True)
            
            return LoopResult.success(
                data={"name": name, "url": url, "message": "Bookmark saved."},
                operation="add_bookmark"
            )
        except Exception as e:
            return LoopResult.failure(f"Failed to save bookmark: {e}")

    async def _open_bookmark(self, name: str) -> LoopResult:
        """Open a bookmark from the brain."""
        try:
            from companion_ai.tools import tool_brain_read
            import json
            
            try:
                content = tool_brain_read("bookmarks.json")
                bookmarks = json.loads(content)
            except:
                return LoopResult.failure("No bookmarks file found in brain.")
            
            # Fuzzy match
            target = name.lower()
            url = bookmarks.get(target)
            
            if not url:
                # Try partial match
                for k, v in bookmarks.items():
                    if target in k or k in target:
                        url = v
                        break
            
            if not url:
                return LoopResult.failure(f"Bookmark '{name}' not found. Available: {list(bookmarks.keys())}")
                
            # Navigate
            return await self._browser_tool("browser_goto", {"url": url})
        except Exception as e:
            return LoopResult.failure(f"Failed to open bookmark: {e}")

    async def _enable_browser_control(self) -> LoopResult:
        """Restart Chrome in debug mode and reset browser agent to reconnect."""
        try:
            import subprocess
            import os
            import time
            import socket
            
            # STEP 1: Reset Playwright state (discard isolated browser)
            logger.info("Resetting browser agent state...")
            from companion_ai.browser_agent import sync_reset
            sync_reset()
            
            # STEP 2: Kill Chrome
            logger.info("Killing Chrome processes...")
            subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
            time.sleep(2)  # Wait for Chrome to fully close
            
            # STEP 3: Launch Chrome with debug flag
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            local_app_data = os.environ.get('LOCALAPPDATA', '')
            user_data = os.path.join(local_app_data, r"Google\Chrome\User Data")
            
            if not os.path.exists(chrome_path):
                return LoopResult.failure("Chrome executable not found at standard location.")
            
            logger.info("Launching Chrome with debug flag...")
            subprocess.Popen([
                chrome_path,
                "--remote-debugging-port=9222",
                f"--user-data-dir={user_data}"
            ])
            
            # STEP 4: Wait for port 9222 to become available
            logger.info("Waiting for Chrome to start on port 9222...")
            for i in range(10):
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    result = sock.connect_ex(('127.0.0.1', 9222))
                    sock.close()
                    if result == 0:
                        logger.info(f"Port 9222 available after {i+1} attempts")
                        break
                except:
                    pass
                time.sleep(0.5)
            
            return LoopResult.success(
                "Chrome restarted in AI Mode! Browser agent will now use YOUR Chrome with all your logins and bookmarks.",
                operation="enable_browser_control"
            )
        except Exception as e:
            return LoopResult.failure(f"Failed to enable browser control: {e}")
    
    # =========================================================================
    # Loxone Smart Home - Light Control
    # =========================================================================
    
    async def _light_on(self, room: str) -> LoopResult:
        """Turn on lights in specified room."""
        try:
            from companion_ai.integrations.loxone import turn_on_lights
            result = await turn_on_lights(room if room else None)
            
            if result.get("success"):
                return LoopResult.success(
                    data=result,
                    operation="light_on"
                )
            else:
                return LoopResult.failure(result.get("error", "Failed to turn on lights"))
        except Exception as e:
            logger.error(f"Light on failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _light_off(self, room: str) -> LoopResult:
        """Turn off lights in specified room."""
        try:
            from companion_ai.integrations.loxone import turn_off_lights
            result = await turn_off_lights(room if room else None)
            
            if result.get("success"):
                return LoopResult.success(
                    data=result,
                    operation="light_off"
                )
            else:
                return LoopResult.failure(result.get("error", "Failed to turn off lights"))
        except Exception as e:
            logger.error(f"Light off failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _light_dim(self, room: str, level: int) -> LoopResult:
        """Dim lights to specified level."""
        try:
            from companion_ai.integrations.loxone import dim_lights
            result = await dim_lights(room, level)
            
            if result.get("success"):
                return LoopResult.success(
                    data=result,
                    operation="light_dim"
                )
            else:
                return LoopResult.failure(result.get("error", "Failed to dim lights"))
        except Exception as e:
            logger.error(f"Light dim failed: {e}")
            return LoopResult.failure(str(e))
