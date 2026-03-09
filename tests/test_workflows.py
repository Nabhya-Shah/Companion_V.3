import pytest
import json
import os
from unittest.mock import AsyncMock, patch
from companion_ai.services.workflows import WorkflowManager, WORKFLOWS_DIR
from companion_ai.web import create_app

@pytest.fixture
def temp_workflows_dir(tmp_path):
    with patch("companion_ai.services.workflows.WORKFLOWS_DIR", str(tmp_path)):
        yield tmp_path

def test_workflow_loading(temp_workflows_dir):
    wf_file = temp_workflows_dir / "test_wf.json"
    wf_file.write_text(json.dumps({
        "name": "Test",
        "description": "Desc",
        "steps": [
            {"id": "1", "action": "prompt", "text": "Hello"}
        ]
    }))

    manager = WorkflowManager()
    wfs = manager.list_workflows()
    assert len(wfs) == 1
    assert wfs[0]["id"] == "test_wf"
    assert wfs[0]["step_count"] == 1


def test_workflow_reload_skips_unchanged_files(temp_workflows_dir, monkeypatch):
    wf_file = temp_workflows_dir / "test_wf.json"
    wf_file.write_text(json.dumps({
        "name": "Test",
        "description": "Desc",
        "steps": [
            {"id": "1", "action": "prompt", "text": "Hello"}
        ]
    }))

    manager = WorkflowManager()
    logs = []
    monkeypatch.setattr("companion_ai.services.workflows.logger.info", lambda message: logs.append(message))

    changed = manager.reload_workflows()

    assert changed is False
    assert logs == []

def test_workflow_execution(temp_workflows_dir):
    import asyncio
    wf_file = temp_workflows_dir / "test_wf.json"
    wf_file.write_text(json.dumps({
        "name": "Test",
        "description": "Desc",
        "steps": [
            {"id": "1", "action": "prompt", "text": "Step 1", "output_target": "chat"},
            {"id": "2", "action": "prompt", "text": "Step 2"}
        ]
    }))

    manager = WorkflowManager()

    mock_process = AsyncMock()
    mock_process.side_effect = [
        ("Response 1", {"meta": "1"}),
        ("Response 2", {"meta": "2"})
    ]

    with patch("companion_ai.services.workflows.Orchestrator") as MockOrchestrator:
        instance = MockOrchestrator.return_value
        instance.process = mock_process
        
        results = asyncio.run(manager.execute_workflow("test_wf"))
        
        assert len(results) == 2
        assert results[0]["response"] == "Response 1"
        assert results[0]["output_target"] == "chat"
        assert results[1]["response"] == "Response 2"
        assert results[1]["output_target"] is None

        # Verify context accumulates
        call_args = mock_process.call_args_list
        assert call_args[0].kwargs["user_message"] == "Step 1"
        assert call_args[1].kwargs["user_message"] == "Step 2"
        assert "Response 1" in call_args[1].kwargs["context"]["recent_conversation"]


def test_workflow_run_endpoint_executes_without_async_flask_extra(monkeypatch):
    app = create_app()
    client = app.test_client()

    manager = type("Manager", (), {})()
    manager.execute_workflow = AsyncMock(return_value=[
        {"step_id": "1", "response": "Done", "output_target": "chat"}
    ])

    monkeypatch.setattr("companion_ai.web.workflow_routes.get_manager", lambda: manager)

    res = client.post("/api/workflows/sample/run")

    assert res.status_code == 200
    payload = res.get_json()
    assert payload["status"] == "success"
    assert payload["workflow_id"] == "sample"
    assert payload["results"][0]["response"] == "Done"


def test_workflow_run_endpoint_appends_chat_output_to_history(monkeypatch):
    from companion_ai.web import state

    app = create_app()
    client = app.test_client()

    manager = type("Manager", (), {})()
    manager.execute_workflow = AsyncMock(return_value=[
        {"step_id": "summary", "response": "Workflow summary", "output_target": "chat"}
    ])

    monkeypatch.setattr("companion_ai.web.workflow_routes.get_manager", lambda: manager)

    session_key = "wf-session"
    state._session_histories[session_key] = []

    res = client.post(
        "/api/workflows/sample/run",
        headers={"X-Session-ID": session_key},
    )

    assert res.status_code == 200
    assert state._session_histories[session_key][-1]["ai"] == "Workflow summary"
    assert state._session_histories[session_key][-1]["metadata"]["workflow_id"] == "sample"
