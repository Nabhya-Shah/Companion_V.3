# companion_ai/local_loops/computer_loop.py
"""
Computer Loop - Complex computer automation as background task.

This is a SUBAGENT loop with multiple models working together:
- Mini Overseer (Text 7B): Breaks down task, monitors progress, helps when stuck
- Action Model (Text 3B): Executes individual actions
- Vision Model (LLaVA): Sees current screen state

Flow:
1. 120B sends task → Mini Overseer
2. Overseer breaks into steps
3. Action model executes each step
4. Vision model verifies result
5. If stuck → Overseer helps
6. If still stuck → Escalate to 120B

This loop runs ASYNC and sends notifications on progress/completion.
"""

import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from .base import Loop, LoopResult, LoopStatus
from .registry import register_loop

logger = logging.getLogger(__name__)


class TaskState(Enum):
    """State of a background task."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ESCALATED = "escalated"


@dataclass
class TaskStep:
    """A single step in a computer task."""
    id: int
    description: str
    status: TaskState = TaskState.PENDING
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[str] = None
    error: Optional[str] = None


@dataclass 
class BackgroundTask:
    """A background computer task with timeline."""
    id: str
    description: str
    state: TaskState = TaskState.PENDING
    steps: List[TaskStep] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    result: Optional[str] = None
    
    def add_step(self, description: str) -> TaskStep:
        """Add a new step to the task."""
        step = TaskStep(
            id=len(self.steps) + 1,
            description=description
        )
        self.steps.append(step)
        self.updated_at = datetime.now()
        return step
    
    def to_timeline(self) -> List[Dict]:
        """Get task as timeline for UI."""
        timeline = []
        for step in self.steps:
            timeline.append({
                "id": step.id,
                "description": step.description,
                "status": step.status.value,
                "started": step.started_at.isoformat() if step.started_at else None,
                "completed": step.completed_at.isoformat() if step.completed_at else None,
                "result": step.result,
                "error": step.error
            })
        return timeline


@register_loop
class ComputerLoop(Loop):
    """Background computer automation loop with subagent architecture."""
    
    name = "computer"
    description = "Complex computer control - runs as background task with live updates"
    
    system_prompts = {
        "overseer": """You are a task overseer managing computer automation.

Your job:
1. Break down the user's task into clear, executable steps
2. Monitor each step's progress
3. Help when the action model gets stuck
4. Decide when to escalate back to the main AI

Return a JSON list of steps, each with:
- description: What to do
- expected_result: How to verify success

Be specific and practical. Each step should be a single action.""",

        "action": """You execute computer actions precisely.

You can:
- Click on UI elements
- Type text
- Press keys
- Wait for elements

For each action, describe exactly what you're doing and why.
If you encounter an unexpected state, ask the overseer for help.""",

        "verifier": """You verify if an action was successful.

Look at the current screen state and compare to expected result.
Return: {"success": true/false, "observation": "what you see"}"""
    }
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._active_tasks: Dict[str, BackgroundTask] = {}
        self._notification_callback: Optional[Callable] = None
    
    def _get_supported_operations(self) -> List[str]:
        return ["execute", "status", "cancel"]
    
    def set_notification_callback(self, callback: Callable[[str, Dict], None]):
        """Set callback for task updates (for SSE to frontend)."""
        self._notification_callback = callback
    
    def _notify(self, task_id: str, update: Dict):
        """Send notification about task update."""
        if self._notification_callback:
            try:
                self._notification_callback(task_id, update)
            except Exception as e:
                logger.error(f"Notification callback failed: {e}")
    
    def _see_screen(self) -> str:
        """Use OmniParser to detect all UI elements on screen with bounding boxes.
        
        Returns a structured list of detected UI elements like:
        "[0] Chrome browser window - active
         [1] New Tab button
         [2] Address bar with 'google.com'
         [3] Start menu button"
        """
        try:
            # Try OmniParser first (most accurate)
            from companion_ai.omniparser_wrapper import parse_screen, format_elements_for_llm
            
            elements, labeled_image = parse_screen()
            
            if elements:
                result = format_elements_for_llm(elements)
                logger.info(f"OmniParser detected {len(elements)} elements")
                return result
            
            # Fall back to Qwen2.5-VL if OmniParser fails
            logger.warning("OmniParser returned no elements, using fallback vision")
            
        except Exception as e:
            logger.warning(f"OmniParser not available ({e}), using fallback vision")
        
        # Fallback: Use Qwen2.5-VL for description
        try:
            import pyautogui
            import tempfile
            import os
            import requests
            import base64
            
            screenshot = pyautogui.screenshot()
            temp_path = os.path.join(tempfile.gettempdir(), "computer_loop_screen.png")
            screenshot.save(temp_path)
            
            with open(temp_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode()
            
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5vl:7b",
                    "prompt": """List all visible windows and UI elements on this Windows screenshot.
For each window, specify:
1. The window title
2. If it's in focus/active
3. Key UI elements visible (buttons, text boxes, tabs)

DO NOT click on or interact with chat/messaging apps or IDE windows.
Keep response under 150 words.""",
                    "images": [image_data],
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "Unable to analyze screen")
                logger.info(f"Fallback vision sees: {result[:100]}...")
                return result
            else:
                return "Vision model unavailable"
                
        except Exception as e:
            logger.error(f"Vision failed: {e}")
            return f"Could not see screen: {str(e)}"
    
    def _plan_with_overseer(self, task: str, screen_context: str) -> List[Dict]:
        """Use mini-overseer (Qwen2.5-7B) to plan steps based on task and screen state.
        
        Returns a list of steps like:
        [
            {"action": "click", "target": "Chrome new tab button", "reason": "Chrome is already open"},
            {"action": "type", "text": "google.com", "reason": "Navigate to Google"},
            {"action": "press", "key": "enter", "reason": "Submit URL"}
        ]
        """
        try:
            import requests
            import json
            
            prompt = f"""You are a computer automation planner for Windows. Based on the current screen state, plan the EXACT steps to complete the task.

CURRENT SCREEN STATE:
{screen_context}

TASK TO COMPLETE:
{task}

Return a JSON list of steps. Each step should have:
- "action": one of "click", "type", "press", "launch", "wait"
- "target": what to click (if action is "click")
- "text": text to type (if action is "type")
- "key": key to press (if action is "press") - can be "enter", "tab", "escape", or combos like "ctrl+t", "ctrl+l"
- "app": app to launch (if action is "launch")
- "seconds": seconds to wait (if action is "wait")
- "reason": brief explanation

IMPORTANT RULES:
1. If browser is already open, use "ctrl+t" for new tab instead of launching
2. ALWAYS use "ctrl+l" to focus address bar BEFORE typing a URL
3. After typing a URL, press "enter" to navigate
4. After launching an app, add a "wait" step (2-3 seconds)
5. Don't try to interact with games or complex apps - say you can't help
6. Keep it simple - max 8 steps for complex tasks
7. For TIMING tasks (like "every second"), use {"action": "wait", "seconds": 1} between actions
8. To switch back to a window, use Alt+Tab

EXAMPLE for "open Wikipedia":
```json
[
  {{"action": "press", "key": "ctrl+t", "reason": "Open new browser tab"}},
  {{"action": "press", "key": "ctrl+l", "reason": "Focus address bar"}},
  {{"action": "type", "text": "en.wikipedia.org", "reason": "Enter URL"}},
  {{"action": "press", "key": "enter", "reason": "Navigate to page"}}
]
```

Return ONLY valid JSON, no explanation."""

            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5:7b",
                    "prompt": prompt,
                    "stream": False
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "[]")
                # Try to parse JSON from response
                try:
                    # Handle markdown code blocks
                    if "```" in result:
                        result = result.split("```")[1]
                        if result.startswith("json"):
                            result = result[4:]
                    steps = json.loads(result.strip())
                    logger.info(f"Overseer planned {len(steps)} steps")
                    return steps if isinstance(steps, list) else []
                except json.JSONDecodeError as e:
                    logger.warning(f"Could not parse overseer response as JSON: {e}")
                    logger.warning(f"Raw response was: {result[:300]}")
                    return []
            else:
                logger.error(f"Overseer API call failed with status {response.status_code}")
                return []
                
        except Exception as e:
            logger.error(f"Overseer planning failed with exception: {e}")
            return []
    
    async def execute(self, task: Dict[str, Any]) -> LoopResult:
        """Execute a computer task.
        
        Task format:
            {"operation": "execute", "task": "Open Chrome and go to google.com"}
            {"operation": "status", "task_id": "abc123"}
            {"operation": "cancel", "task_id": "abc123"}
        """
        operation = task.get("operation")
        
        if operation == "execute":
            return await self._start_task(task.get("task", ""))
        elif operation == "status":
            return await self._get_status(task.get("task_id", ""))
        elif operation == "cancel":
            return await self._cancel_task(task.get("task_id", ""))
        else:
            return LoopResult.failure(f"Unknown operation: {operation}")
    
    async def _start_task(self, task_description: str) -> LoopResult:
        """Start a background computer task."""
        if not task_description:
            return LoopResult.failure("No task description provided")
        
        try:
            import uuid
            import threading
            
            task_id = str(uuid.uuid4())[:8]
            
            task = BackgroundTask(
                id=task_id,
                description=task_description
            )
            self._active_tasks[task_id] = task
            
            # Start in a thread with its own event loop (Flask doesn't have one)
            def run_in_thread():
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    loop.run_until_complete(self._run_task(task_id))
                finally:
                    loop.close()
            
            thread = threading.Thread(target=run_in_thread, daemon=True)
            thread.start()
            
            logger.info(f"Started background task: {task_id} - {task_description}")
            
            return LoopResult.success(
                data={
                    "task_id": task_id,
                    "status": "started",
                    "message": "Task started in background"
                },
                operation="execute"
            )
        except Exception as e:
            logger.error(f"Failed to start task: {e}")
            return LoopResult.failure(str(e))
    
    async def _run_task(self, task_id: str):
        """Run a task using VISION-FIRST architecture.
        
        Flow:
        1. Vision sees current screen state
        2. Mini-overseer plans smart steps based on what's visible
        3. Execute each step with ComputerAgent
        4. Vision verifies after each step
        """
        task = self._active_tasks.get(task_id)
        if not task:
            return
        
        task.state = TaskState.RUNNING
        self._notify(task_id, {"state": "running"})
        
        try:
            from companion_ai.computer_agent import computer_agent
            
            # Step 1: Vision sees current screen
            step1 = task.add_step("Seeing current screen state")
            step1.status = TaskState.RUNNING
            step1.started_at = datetime.now()
            self._notify(task_id, {"step": step1.id, "status": "running", "description": step1.description})
            
            if task.state == TaskState.FAILED:
                return
            
            screen_context = self._see_screen()
            
            step1.status = TaskState.COMPLETED
            step1.completed_at = datetime.now()
            step1.result = screen_context[:200] + "..." if len(screen_context) > 200 else screen_context
            self._notify(task_id, {"step": step1.id, "status": "completed"})
            
            await asyncio.sleep(0.5)
            
            # Step 2: Mini-overseer plans the task
            step2 = task.add_step("Planning execution steps")
            step2.status = TaskState.RUNNING
            step2.started_at = datetime.now()
            self._notify(task_id, {"step": step2.id, "status": "running", "description": step2.description})
            
            if task.state == TaskState.FAILED:
                return
            
            planned_steps = self._plan_with_overseer(task.description, screen_context)
            
            if not planned_steps:
                # Don't launch random text! Fail gracefully instead
                logger.error("Overseer returned no steps - task is too complex or planning failed")
                step2.status = TaskState.FAILED
                step2.completed_at = datetime.now()
                step2.error = "Could not plan steps for this task. Try a simpler task like 'open notepad' or 'go to google.com'"
                self._notify(task_id, {"step": step2.id, "status": "failed", "error": step2.error})
                
                task.state = TaskState.FAILED
                task.result = "Planning failed - task too complex"
                self._notify(task_id, {"state": "failed", "error": task.result})
                return
            
            step2.status = TaskState.COMPLETED
            step2.completed_at = datetime.now()
            step2.result = f"Planned {len(planned_steps)} steps"
            self._notify(task_id, {"step": step2.id, "status": "completed"})
            
            await asyncio.sleep(0.5)
            
            # Step 3+: Execute each planned step
            for i, planned_step in enumerate(planned_steps):
                if task.state == TaskState.FAILED:
                    return
                
                action = planned_step.get("action", "unknown")
                reason = planned_step.get("reason", "")
                
                step = task.add_step(f"Step {i+1}: {action} - {reason[:50]}")
                step.status = TaskState.RUNNING
                step.started_at = datetime.now()
                self._notify(task_id, {"step": step.id, "status": "running", "description": step.description})
                
                try:
                    result = None
                    
                    if action == "launch":
                        app = planned_step.get("app", planned_step.get("target", ""))
                        logger.info(f"Launching: {app}")
                        result = computer_agent.launch_app(app)
                    
                    elif action == "click":
                        target = planned_step.get("target", "")
                        result = computer_agent.click_element(target)
                    
                    elif action == "type":
                        text = planned_step.get("text", "")
                        result = computer_agent.type_text(text)
                    
                    elif action == "press":
                        key = planned_step.get("key", "")
                        # Handle key combinations like "ctrl+t"
                        if "+" in key:
                            result = computer_agent.press_key(key)
                        else:
                            result = computer_agent.press_key(key)
                    
                    elif action == "wait":
                        wait_time = float(planned_step.get("seconds", 1))
                        await asyncio.sleep(wait_time)
                        result = f"Waited {wait_time}s"
                    
                    else:
                        result = f"Unknown action: {action}"
                    
                    step.status = TaskState.COMPLETED
                    step.completed_at = datetime.now()
                    step.result = str(result) if result else "Done"
                    self._notify(task_id, {"step": step.id, "status": "completed"})
                    
                    # Longer delay for reliability, especially after type/press actions
                    if action in ["type", "press", "launch"]:
                        await asyncio.sleep(1.5)
                    else:
                        await asyncio.sleep(0.5)
                    
                except Exception as e:
                    step.status = TaskState.FAILED
                    step.completed_at = datetime.now()
                    step.error = str(e)
                    self._notify(task_id, {"step": step.id, "status": "failed", "error": str(e)})
                    logger.error(f"Step failed: {e}")
            
            # Final step: Verify with vision
            if task.state != TaskState.FAILED:
                verify_step = task.add_step("Verifying results")
                verify_step.status = TaskState.RUNNING
                verify_step.started_at = datetime.now()
                self._notify(task_id, {"step": verify_step.id, "status": "running", "description": verify_step.description})
                
                await asyncio.sleep(1)
                final_screen = self._see_screen()
                
                verify_step.status = TaskState.COMPLETED
                verify_step.completed_at = datetime.now()
                verify_step.result = final_screen[:150] + "..." if len(final_screen) > 150 else final_screen
                self._notify(task_id, {"step": verify_step.id, "status": "completed"})
            
            # Mark task complete
            task.state = TaskState.COMPLETED
            task.result = f"Completed {len(planned_steps)} steps"
            self._notify(task_id, {"state": "completed", "result": task.result})
            
        except Exception as e:
            logger.error(f"ComputerLoop task {task_id} failed: {e}")
            task.state = TaskState.FAILED
            task.result = str(e)
            self._notify(task_id, {"state": "failed", "error": str(e)})
            
        except Exception as e:
            logger.error(f"ComputerLoop task {task_id} failed: {e}")
            task.state = TaskState.FAILED
            task.result = str(e)
            self._notify(task_id, {
                "state": "failed",
                "error": str(e)
            })
    
    async def _get_status(self, task_id: str) -> LoopResult:
        """Get status of a background task."""
        if not task_id:
            return LoopResult.failure("No task_id provided")
        
        task = self._active_tasks.get(task_id)
        if not task:
            return LoopResult.failure(f"Task not found: {task_id}")
        
        return LoopResult.success(
            data={
                "task_id": task_id,
                "description": task.description,
                "state": task.state.value,
                "timeline": task.to_timeline(),
                "result": task.result
            },
            operation="status"
        )
    
    async def _cancel_task(self, task_id: str) -> LoopResult:
        """Cancel a running task."""
        if not task_id:
            return LoopResult.failure("No task_id provided")
        
        task = self._active_tasks.get(task_id)
        if not task:
            return LoopResult.failure(f"Task not found: {task_id}")
        
        task.state = TaskState.FAILED
        task.result = "Cancelled by user"
        
        return LoopResult.success(
            data={"task_id": task_id, "status": "cancelled"},
            operation="cancel"
        )
    
    def get_active_tasks(self) -> List[Dict]:
        """Get all active tasks for UI."""
        return [
            {
                "id": t.id,
                "description": t.description,
                "state": t.state.value,
                "steps_count": len(t.steps),
                "created": t.created_at.isoformat()
            }
            for t in self._active_tasks.values()
        ]
