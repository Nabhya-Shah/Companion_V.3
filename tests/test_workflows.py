import pytest
import json
import os
from unittest.mock import AsyncMock, patch
from companion_ai.services.workflows import WorkflowManager, WORKFLOWS_DIR

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
