"""Tests for P6-C Task Planning & Progress Tracker.

Covers:
  - TaskPlan model construction
  - Plan registry (register / update / complete / cleanup)
  - Plan listener callback mechanism
  - Orchestrator plan execution (_handle_plan)
  - Plan API endpoint (/api/plans)
  - SSE plan event draining
"""

import asyncio
import json
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# 1. TaskPlan model tests
# ---------------------------------------------------------------------------

def test_plan_step_to_dict():
    from companion_ai.services.task_planner import PlanStep, StepStatus
    step = PlanStep(id="s1", description="Check weather", action="delegate")
    d = step.to_dict()
    assert d["id"] == "s1"
    assert d["status"] == "queued"
    assert d["description"] == "Check weather"


def test_task_plan_from_llm_json():
    from companion_ai.services.task_planner import TaskPlan
    plan = TaskPlan.from_llm_json({
        "goal": "Morning briefing",
        "steps": [
            {"id": "s1", "description": "Get schedule", "action": "delegate", "params": {"loop": "memory"}},
            {"id": "s2", "description": "Get weather", "action": "delegate", "params": {"loop": "tools"}},
        ],
    })
    assert plan.goal == "Morning briefing"
    assert len(plan.steps) == 2
    assert plan.steps[0].action == "delegate"


def test_task_plan_to_dict():
    from companion_ai.services.task_planner import TaskPlan, PlanStep
    plan = TaskPlan(id="abc", goal="Test", steps=[
        PlanStep(id="s1", description="Step 1", action="answer"),
    ])
    d = plan.to_dict()
    assert d["id"] == "abc"
    assert d["goal"] == "Test"
    assert len(d["steps"]) == 1


# ---------------------------------------------------------------------------
# 2. Plan registry tests
# ---------------------------------------------------------------------------

def test_register_and_get_plan():
    from companion_ai.services.task_planner import (
        TaskPlan, PlanStep, _ACTIVE_PLANS, _PLANS_LOCK,
        register_plan, get_active_plan, get_all_active_plans,
    )
    # Clean up
    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()

    plan = TaskPlan(id="test1", goal="Test", steps=[
        PlanStep(id="s1", description="A", action="answer"),
    ])
    register_plan(plan)
    assert get_active_plan("test1") is plan
    all_plans = get_all_active_plans()
    assert any(p["id"] == "test1" for p in all_plans)

    # Cleanup
    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()


def test_update_step_status():
    from companion_ai.services.task_planner import (
        TaskPlan, PlanStep, StepStatus, _ACTIVE_PLANS, _PLANS_LOCK,
        register_plan, update_step_status,
    )
    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()

    plan = TaskPlan(id="test2", goal="Test", steps=[
        PlanStep(id="s1", description="A", action="answer"),
    ])
    register_plan(plan)
    update_step_status("test2", "s1", StepStatus.RUNNING)
    assert plan.steps[0].status == StepStatus.RUNNING

    update_step_status("test2", "s1", StepStatus.COMPLETED, result="done")
    assert plan.steps[0].status == StepStatus.COMPLETED
    assert plan.steps[0].result == "done"

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()


def test_complete_plan():
    from companion_ai.services.task_planner import (
        TaskPlan, PlanStep, _ACTIVE_PLANS, _PLANS_LOCK,
        register_plan, complete_plan,
    )
    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()

    plan = TaskPlan(id="test3", goal="Test", steps=[])
    register_plan(plan)
    complete_plan("test3", summary="All good")
    assert plan.final_summary == "All good"

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()


# ---------------------------------------------------------------------------
# 3. Plan listener callback tests
# ---------------------------------------------------------------------------

def test_plan_listener_receives_events():
    from companion_ai.services.task_planner import (
        TaskPlan, PlanStep, StepStatus, _ACTIVE_PLANS, _PLANS_LOCK,
        _PLAN_LISTENERS,
        register_plan, update_step_status, complete_plan,
    )
    events = []

    def listener(event_type, plan_id, data):
        events.append((event_type, plan_id))

    _PLAN_LISTENERS.append(listener)
    try:
        with _PLANS_LOCK:
            _ACTIVE_PLANS.clear()

        plan = TaskPlan(id="listen1", goal="Test", steps=[
            PlanStep(id="s1", description="A", action="answer"),
        ])
        register_plan(plan)
        update_step_status("listen1", "s1", StepStatus.RUNNING)
        complete_plan("listen1", summary="ok")

        assert ("plan.created", "listen1") in events
        assert ("step.updated", "listen1") in events
        assert ("plan.completed", "listen1") in events
    finally:
        _PLAN_LISTENERS.remove(listener)
        with _PLANS_LOCK:
            _ACTIVE_PLANS.clear()


# ---------------------------------------------------------------------------
# 4. Orchestrator plan execution
# ---------------------------------------------------------------------------

def test_orchestrator_handle_plan():
    """Orchestrator._handle_plan executes steps and synthesizes."""
    from companion_ai.orchestrator import Orchestrator, OrchestratorDecision, OrchestratorAction
    from companion_ai.services.task_planner import _ACTIVE_PLANS, _PLANS_LOCK

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()

    orch = Orchestrator()

    # Mock _execute_decision for sub-steps so we don't hit real LLM
    async def mock_execute(decision, user_msg, ctx):
        return f"Result for {decision.loop or 'answer'}", {"source": "mock"}

    # Mock _get_client_and_model to return a fake client for synthesis
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock(content="Combined answer")]
    mock_resp.choices[0].message.content = "Combined answer"
    mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
    mock_client.chat.completions.create.return_value = mock_resp

    decision = OrchestratorDecision(
        action=OrchestratorAction.PLAN,
        plan_steps=[
            {"description": "Get time", "action": "delegate", "params": {"loop": "tools", "task": {"operation": "get_time"}}},
            {"description": "Get weather", "action": "delegate", "params": {"loop": "tools", "task": {"operation": "get_weather"}}},
        ],
    )

    with patch.object(orch, '_execute_decision', side_effect=mock_execute):
        with patch.object(orch, '_get_client_and_model', return_value=(mock_client, "test-model", False)):
            result_text, metadata = asyncio.run(
                orch._handle_plan(decision, "What time and weather?", {})
            )

    assert metadata["source"] == "plan"
    assert metadata["steps_total"] == 2
    assert metadata["steps_completed"] == 2
    assert result_text == "Combined answer"

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()


def test_orchestrator_plan_step_failure_captured():
    """If a plan step throws an exception, it's recorded as FAILED but doesn't crash."""
    from companion_ai.orchestrator import Orchestrator, OrchestratorDecision, OrchestratorAction
    from companion_ai.services.task_planner import _ACTIVE_PLANS, _PLANS_LOCK

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()

    orch = Orchestrator()
    call_count = 0

    async def mock_execute(decision, user_msg, ctx):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Step 1 kaboom")
        return "Step 2 ok", {"source": "mock"}

    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = "Partial result"
    mock_resp.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
    mock_client.chat.completions.create.return_value = mock_resp

    decision = OrchestratorDecision(
        action=OrchestratorAction.PLAN,
        plan_steps=[
            {"description": "Will fail", "action": "delegate", "params": {"loop": "tools"}},
            {"description": "Will succeed", "action": "delegate", "params": {"loop": "tools"}},
        ],
    )

    with patch.object(orch, '_execute_decision', side_effect=mock_execute):
        with patch.object(orch, '_get_client_and_model', return_value=(mock_client, "test-model", False)):
            result_text, metadata = asyncio.run(
                orch._handle_plan(decision, "Test", {})
            )

    assert metadata["steps_completed"] == 1
    assert metadata["steps_total"] == 2

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()


# ---------------------------------------------------------------------------
# 5. Plan API endpoint
# ---------------------------------------------------------------------------

def test_plans_api_endpoint():
    """GET /api/plans returns active plans."""
    from companion_ai.services.task_planner import (
        TaskPlan, PlanStep, _ACTIVE_PLANS, _PLANS_LOCK, register_plan,
    )

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()

    plan = TaskPlan(id="api1", goal="API test", steps=[
        PlanStep(id="s1", description="Step", action="answer"),
    ])
    register_plan(plan)

    # Use a minimal Flask test client
    try:
        from companion_ai.web import create_app
        app = create_app()
        with app.test_client() as client:
            resp = client.get('/api/plans')
            assert resp.status_code == 200
            data = resp.get_json()
            assert "plans" in data
            assert any(p["id"] == "api1" for p in data["plans"])
    finally:
        with _PLANS_LOCK:
            _ACTIVE_PLANS.clear()


# ---------------------------------------------------------------------------
# 6. SSE plan event queue
# ---------------------------------------------------------------------------

def test_plan_event_queue_populated():
    """Registering a plan pushes an event into the chat_routes queue."""
    from companion_ai.services.task_planner import (
        TaskPlan, PlanStep, _ACTIVE_PLANS, _PLANS_LOCK, register_plan,
    )
    from companion_ai.web.chat_routes import _plan_event_queue

    # Drain any existing events
    while not _plan_event_queue.empty():
        _plan_event_queue.get_nowait()

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()

    plan = TaskPlan(id="queue1", goal="Queue test", steps=[])
    register_plan(plan)

    assert not _plan_event_queue.empty()
    evt = _plan_event_queue.get_nowait()
    assert evt["event_type"] == "plan.created"
    assert evt["plan_id"] == "queue1"

    with _PLANS_LOCK:
        _ACTIVE_PLANS.clear()


# ---------------------------------------------------------------------------
# 7. OrchestratorDecision parses plan_steps
# ---------------------------------------------------------------------------

def test_decision_parses_plan_action():
    from companion_ai.orchestrator import OrchestratorDecision, OrchestratorAction
    raw = json.dumps({
        "action": "plan",
        "plan_steps": [
            {"description": "Step A", "action": "delegate", "params": {"loop": "tools"}},
            {"description": "Step B", "action": "answer", "params": {}},
        ],
    })
    decision = OrchestratorDecision.from_json(raw)
    assert decision.action == OrchestratorAction.PLAN
    assert len(decision.plan_steps) == 2
    assert decision.plan_steps[0]["description"] == "Step A"
