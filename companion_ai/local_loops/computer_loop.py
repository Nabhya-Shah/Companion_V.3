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
            task_id = str(uuid.uuid4())[:8]
            
            task = BackgroundTask(
                id=task_id,
                description=task_description
            )
            self._active_tasks[task_id] = task
            
            # Start async execution
            asyncio.create_task(self._run_task(task_id))
            
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
        """Run a task in the background.
        
        TODO: Implement full subagent loop when Docker vLLM is ready.
        For now, placeholder that simulates steps.
        """
        task = self._active_tasks.get(task_id)
        if not task:
            return
        
        task.state = TaskState.RUNNING
        self._notify(task_id, {"state": "running"})
        
        try:
            # Placeholder: Simulate breaking task into steps
            task.add_step("Analyzing task requirements")
            task.add_step("Preparing execution environment")
            task.add_step(f"Executing: {task.description}")
            task.add_step("Verifying results")
            
            # Simulate step execution
            for step in task.steps:
                step.status = TaskState.RUNNING
                step.started_at = datetime.now()
                self._notify(task_id, {
                    "step": step.id, 
                    "status": "running",
                    "description": step.description
                })
                
                await asyncio.sleep(1)  # Simulate work
                
                step.status = TaskState.COMPLETED
                step.completed_at = datetime.now()
                step.result = "Completed successfully"
                self._notify(task_id, {
                    "step": step.id,
                    "status": "completed"
                })
            
            task.state = TaskState.COMPLETED
            task.result = "Task completed successfully"
            self._notify(task_id, {
                "state": "completed",
                "result": task.result
            })
            
        except Exception as e:
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
