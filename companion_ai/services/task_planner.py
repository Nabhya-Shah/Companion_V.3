"""Task planning for multi-step orchestrator execution (P6-C).

Provides a structured plan model and execution engine that the
orchestrator can use for complex multi-step requests. Step status
updates are broadcast via a callback so the SSE stream can push
live progress to the UI.
"""

import logging
import uuid
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    id: str
    description: str
    action: str  # "answer", "delegate", "memory_search"
    params: Dict[str, Any] = field(default_factory=dict)
    status: StepStatus = StepStatus.QUEUED
    result: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "description": self.description,
            "action": self.action,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
        }


@dataclass
class TaskPlan:
    id: str
    goal: str
    steps: List[PlanStep] = field(default_factory=list)
    final_summary: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "final_summary": self.final_summary,
        }

    @classmethod
    def from_llm_json(cls, data: dict) -> "TaskPlan":
        """Parse a plan from the LLM's JSON response."""
        plan_id = str(uuid.uuid4())[:8]
        steps = []
        for i, step_data in enumerate(data.get("steps", [])):
            steps.append(PlanStep(
                id=step_data.get("id", f"step_{i+1}"),
                description=step_data.get("description", f"Step {i+1}"),
                action=step_data.get("action", "answer"),
                params=step_data.get("params", {}),
            ))
        return cls(
            id=plan_id,
            goal=data.get("goal", "Complete request"),
            steps=steps,
        )


# ---------------------------------------------------------------------------
# Active plans registry (for the SSE stream to pick up)
# ---------------------------------------------------------------------------

_ACTIVE_PLANS: Dict[str, TaskPlan] = {}
_PLANS_LOCK = threading.Lock()
_PLAN_LISTENERS: List[Callable] = []


def register_plan_listener(callback: Callable[[str, str, dict], None]) -> None:
    """Register a callback for plan events: callback(event_type, plan_id, data)."""
    _PLAN_LISTENERS.append(callback)


def _emit_plan_event(event_type: str, plan_id: str, data: dict) -> None:
    """Notify all listeners about a plan state change."""
    for cb in _PLAN_LISTENERS:
        try:
            cb(event_type, plan_id, data)
        except Exception as e:
            logger.error(f"Plan listener error: {e}")


def get_active_plan(plan_id: str) -> Optional[TaskPlan]:
    with _PLANS_LOCK:
        return _ACTIVE_PLANS.get(plan_id)


def get_all_active_plans() -> List[dict]:
    with _PLANS_LOCK:
        return [p.to_dict() for p in _ACTIVE_PLANS.values()]


def register_plan(plan: TaskPlan) -> None:
    with _PLANS_LOCK:
        _ACTIVE_PLANS[plan.id] = plan
    _emit_plan_event("plan.created", plan.id, plan.to_dict())


def update_step_status(plan_id: str, step_id: str, status: StepStatus,
                       result: str | None = None, error: str | None = None) -> None:
    with _PLANS_LOCK:
        plan = _ACTIVE_PLANS.get(plan_id)
        if not plan:
            return
        for step in plan.steps:
            if step.id == step_id:
                step.status = status
                step.result = result
                step.error = error
                break

    _emit_plan_event("step.updated", plan_id, {
        "step_id": step_id,
        "status": status.value,
        "result": result,
        "error": error,
        "plan": plan.to_dict() if plan else None,
    })


def complete_plan(plan_id: str, summary: str | None = None) -> None:
    with _PLANS_LOCK:
        plan = _ACTIVE_PLANS.get(plan_id)
        if plan:
            plan.final_summary = summary
    _emit_plan_event("plan.completed", plan_id, {
        "summary": summary,
        "plan": plan.to_dict() if plan else None,
    })
    # Clean up after a short delay so SSE can flush
    def _cleanup():
        import time
        time.sleep(10)
        with _PLANS_LOCK:
            _ACTIVE_PLANS.pop(plan_id, None)
    threading.Thread(target=_cleanup, daemon=True).start()
