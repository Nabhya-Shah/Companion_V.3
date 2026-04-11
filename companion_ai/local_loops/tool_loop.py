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
import re
from datetime import datetime
from typing import Any, Dict, List
from .base import Loop, LoopResult, LoopStatus
from .registry import register_loop

logger = logging.getLogger(__name__)


def _normalize_action_text(value: str) -> str:
    cleaned = (value or "").strip().strip('"\'')
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned.rstrip('.,;')


def _recover_use_computer_args(action: str, text: str, user_request: str) -> tuple[str, str]:
    action_value = str(action or "").strip()
    text_value = str(text or "").strip()
    if action_value:
        return action_value, text_value

    msg = (user_request or "").strip()
    if not msg:
        return "press", text_value or "Enter"

    numbered_steps = [
        m.group(1).strip()
        for m in re.finditer(r'(?m)^\s*\d+[\)\].:-]?\s*(.+)$', msg)
        if m.group(1).strip()
    ]
    if len(numbered_steps) >= 2:
        msg = numbered_steps[0]

    low = msg.lower()

    if re.search(r'\bopen\s+(?:another|new)\s+terminal tab\b', low):
        return "press", "ctrl+shift+t"

    if re.search(r'\bclose\s+(?:the\s+)?(?:current|this)?\s*tab\b', low):
        return "press", "ctrl+shift+w"

    press_match = re.search(r'\bpress\s+([a-z0-9+\-]+)\b', low)
    if press_match:
        key = press_match.group(1)
        return "press", "Enter" if key == "enter" else key

    shortcut_match = re.search(r'\b((?:ctrl|alt|shift|cmd|win)(?:\+[a-z0-9]+)+)\b', low)
    if shortcut_match:
        return "press", shortcut_match.group(1)

    type_match = re.search(
        r'\btype(?:\s+exactly)?(?:\s+this)?(?:\s+text)?\s*:\s*([^\n\r]+)',
        msg,
        flags=re.IGNORECASE,
    )
    if type_match:
        return "type", _normalize_action_text(type_match.group(1))

    type_direct = re.search(r'\btype\s+([^\n\r]+)', msg, flags=re.IGNORECASE)
    if type_direct:
        return "type", _normalize_action_text(type_direct.group(1))

    click_match = re.search(r'\bclick\s+([^\n\r]+)', msg, flags=re.IGNORECASE)
    if click_match:
        return "click", _normalize_action_text(click_match.group(1))

    if 'scroll up' in low:
        return "scroll_up", ""

    if 'scroll down' in low:
        return "scroll_down", ""

    launch_match = re.search(r'\b(?:open|launch)\s+([^\n\r]+)', msg, flags=re.IGNORECASE)
    if launch_match:
        target = _normalize_action_text(launch_match.group(1))
        if target and not re.search(r'\b(?:ctrl|alt|shift|cmd|win)\+', target.lower()):
            return "launch", target[:120]

    if any(k in low for k in ['use computer', 'control my computer', 'computer control']):
        return "press", "Enter"

    return "press", text_value or "Enter"


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
            "get_time", "calculate", "web_search", "wikipedia", "brain_read", "brain_list", "brain_search",
            "browser_goto", "browser_click", "browser_type", "browser_read", "browser_press",
            "use_computer",
            "remote_action_simulator",
            "add_bookmark", "open_bookmark", "enable_browser_control",
            "light_on", "light_off", "light_dim",  # Loxone smart home
            "read_pdf", "read_document", "list_files", "find_file"  # File reading
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
                            logger.info(f"Using bookmark '{potential_name}' instead of guessed URL")
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
        elif operation == "use_computer":
            action, text = _recover_use_computer_args(
                task.get("action", ""),
                task.get("text", ""),
                str(task.get("user_request") or ""),
            )
            return await self._computer_use(action, text)
        elif operation == "remote_action_simulator":
            return await self._remote_action_simulator(task)
        elif operation == "wikipedia":
            return await self._wikipedia(task.get("topic", ""))
        elif operation == "brain_read":
            return await self._brain_read(task.get("path", ""))
        elif operation == "brain_list":
            return await self._brain_list(task.get("subdir", ""))
        elif operation == "brain_search":
            return await self._brain_search(task.get("query", ""))
        # Loxone Smart Home - Light Control
        elif operation == "light_on":
            return await self._light_on(task.get("room", ""))
        elif operation == "light_off":
            return await self._light_off(task.get("room", ""))
        elif operation == "light_dim":
            return await self._light_dim(task.get("room", ""), task.get("level", 50))
        # File Reading
        elif operation == "read_pdf":
            return await self._read_pdf(task.get("file_path", ""), task.get("page_number"))
        elif operation == "read_document":
            return await self._read_document(task.get("file_path", ""))
        elif operation == "list_files":
            return await self._list_files(task.get("directory", "."), task.get("file_type"))
        elif operation == "find_file":
            return await self._find_file(task.get("filename", ""), task.get("file_type"))
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

    async def _brain_search(self, query: str) -> LoopResult:
        """Semantic search across brain documents."""
        if not query:
            return LoopResult.failure("No query provided")
        
        try:
            from companion_ai.brain_index import brain_search
            
            result = brain_search(query)
            
            return LoopResult.success(
                data={"query": query, "results": result},
                operation="brain_search"
            )
        except Exception as e:
            logger.error(f"Brain search failed: {e}")
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

    async def _computer_use(self, action: str, text: str = "") -> LoopResult:
        """Execute direct computer-control tool via function-call registry."""
        try:
            from companion_ai.tools import execute_function_call

            result = execute_function_call(
                "use_computer",
                {"action": action, "text": text},
            )

            return LoopResult.success(
                data={"result": result, "action": action, "text": text},
                operation="use_computer",
            )
        except Exception as e:
            logger.error(f"Computer tool failed: {e}")
            return LoopResult.failure(f"use_computer failed: {str(e)}")

    async def _remote_action_simulator(self, task: Dict[str, Any]) -> LoopResult:
        """Execute simulator-only remote action envelope and return lifecycle-rich metadata."""
        try:
            import json
            from companion_ai.tools import execute_function_call

            payload = {
                "capability": task.get("capability", ""),
                "action": task.get("action", ""),
                "target": task.get("target", ""),
                "params": task.get("params") if isinstance(task.get("params"), dict) else {},
                "approval_token": task.get("approval_token", ""),
            }
            result_raw = execute_function_call("remote_action_simulator", payload)
            try:
                envelope = json.loads(result_raw)
            except Exception:
                envelope = {"status": "error", "error": str(result_raw), "lifecycle": []}

            operation = "remote_action_simulator"
            if envelope.get("status") == "completed":
                return LoopResult.success(
                    data=envelope,
                    operation=operation,
                    domain="remote_action",
                    lifecycle=envelope.get("lifecycle", []),
                )

            return LoopResult.failure(
                envelope.get("error") or "Remote action rejected",
                operation=operation,
                domain="remote_action",
                lifecycle=envelope.get("lifecycle", []),
                reason=envelope.get("reason"),
                envelope=envelope,
            )
        except Exception as e:
            logger.error(f"Remote action simulator failed: {e}")
            return LoopResult.failure(f"remote_action_simulator failed: {str(e)}", operation="remote_action_simulator", domain="remote_action")

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
        """Restart a local browser in debug mode and reset browser agent to reconnect."""
        try:
            import os
            import platform
            import shutil
            import socket
            import subprocess
            import time
            
            # STEP 1: Reset Playwright state (discard isolated browser)
            logger.info("Resetting browser agent state...")
            from companion_ai.agents.browser import sync_reset
            sync_reset()

            system = platform.system().lower()
            user_data = os.path.join(os.path.expanduser("~"), ".companion_chrome")
            os.makedirs(user_data, exist_ok=True)

            # STEP 2: Stop existing browser processes (best effort)
            logger.info("Stopping existing browser processes...")
            if system == "windows":
                subprocess.run(["taskkill", "/F", "/IM", "chrome.exe"], capture_output=True)
                subprocess.run(["taskkill", "/F", "/IM", "msedge.exe"], capture_output=True)
            else:
                for proc in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge"]:
                    subprocess.run(["pkill", "-f", proc], capture_output=True)
            time.sleep(2)  # Wait for Chrome to fully close

            # STEP 3: Launch browser with debug flag
            browser_bin = None
            if system == "windows":
                for candidate in [
                    os.environ.get("CHROME_PATH", ""),
                    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                ]:
                    if candidate and os.path.exists(candidate):
                        browser_bin = candidate
                        break
            else:
                for candidate in [
                    os.environ.get("CHROME_PATH", ""),
                    shutil.which("google-chrome") or "",
                    shutil.which("google-chrome-stable") or "",
                    shutil.which("chromium") or "",
                    shutil.which("chromium-browser") or "",
                    shutil.which("microsoft-edge") or "",
                ]:
                    if candidate and os.path.exists(candidate):
                        browser_bin = candidate
                        break

            if not browser_bin:
                return LoopResult.failure("No Chrome/Chromium executable found. Set CHROME_PATH or install a Chromium-based browser.")

            logger.info(f"Launching browser with debug flag: {browser_bin}")
            subprocess.Popen([
                browser_bin,
                "--remote-debugging-port=9222",
                f"--user-data-dir={user_data}",
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
                "Browser restarted in AI mode. Remote debugging is enabled and the automation agent can reconnect.",
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
                    operation="light_on",
                    domain="smarthome",
                    room=result.get("room") or room or "unknown",
                )
            else:
                return LoopResult.failure(
                    result.get("error", "Failed to turn on lights"),
                    operation="light_on",
                    domain="smarthome",
                    room=room or "unknown",
                )
        except Exception as e:
            logger.error(f"Light on failed: {e}")
            return LoopResult.failure(
                str(e),
                operation="light_on",
                domain="smarthome",
                room=room or "unknown",
            )
    
    async def _light_off(self, room: str) -> LoopResult:
        """Turn off lights in specified room."""
        try:
            from companion_ai.integrations.loxone import turn_off_lights
            result = await turn_off_lights(room if room else None)
            
            if result.get("success"):
                return LoopResult.success(
                    data=result,
                    operation="light_off",
                    domain="smarthome",
                    room=result.get("room") or room or "unknown",
                )
            else:
                return LoopResult.failure(
                    result.get("error", "Failed to turn off lights"),
                    operation="light_off",
                    domain="smarthome",
                    room=room or "unknown",
                )
        except Exception as e:
            logger.error(f"Light off failed: {e}")
            return LoopResult.failure(
                str(e),
                operation="light_off",
                domain="smarthome",
                room=room or "unknown",
            )
    
    async def _light_dim(self, room: str, level: int) -> LoopResult:
        """Dim lights to specified level."""
        try:
            from companion_ai.integrations.loxone import set_brightness
            result = await set_brightness(room, level)
            
            if result.get("success"):
                return LoopResult.success(
                    data=result,
                    operation="light_dim",
                    domain="smarthome",
                    room=result.get("room") or room or "unknown",
                )
            else:
                return LoopResult.failure(
                    result.get("error", "Failed to dim lights"),
                    operation="light_dim",
                    domain="smarthome",
                    room=room or "unknown",
                )
        except Exception as e:
            logger.error(f"Light dim failed: {e}")
            return LoopResult.failure(
                str(e),
                operation="light_dim",
                domain="smarthome",
                room=room or "unknown",
            )

    # =========================================================================
    # File Reading Operations
    # =========================================================================
    
    async def _read_pdf(self, file_path: str, page_number: int = None) -> LoopResult:
        """Read text from a PDF file."""
        if not file_path:
            return LoopResult.failure("No file path provided")
        
        try:
            from companion_ai.tools import tool_read_pdf
            
            result = tool_read_pdf(file_path, page_number)
            
            return LoopResult.success(
                data={"file_path": file_path, "content": result},
                operation="read_pdf"
            )
        except Exception as e:
            logger.error(f"Read PDF failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _read_document(self, file_path: str) -> LoopResult:
        """Read text from a document (docx, txt)."""
        if not file_path:
            return LoopResult.failure("No file path provided")
        
        try:
            from companion_ai.tools import tool_read_docx
            
            result = tool_read_docx(file_path)
            
            return LoopResult.success(
                data={"file_path": file_path, "content": result},
                operation="read_document"
            )
        except Exception as e:
            logger.error(f"Read document failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _list_files(self, directory: str, file_type: str = None) -> LoopResult:
        """List files in a directory."""
        try:
            from companion_ai.tools import tool_list_files
            
            result = tool_list_files(directory, file_type)
            
            return LoopResult.success(
                data={"directory": directory, "files": result},
                operation="list_files"
            )
        except Exception as e:
            logger.error(f"List files failed: {e}")
            return LoopResult.failure(str(e))
    
    async def _find_file(self, filename: str, file_type: str = None) -> LoopResult:
        """Find files matching a name."""
        if not filename:
            return LoopResult.failure("No filename provided")
        
        try:
            from companion_ai.tools import tool_find_file
            
            result = tool_find_file(filename, file_type)
            
            return LoopResult.success(
                data={"filename": filename, "results": result},
                operation="find_file"
            )
        except Exception as e:
            logger.error(f"Find file failed: {e}")
            return LoopResult.failure(str(e))

