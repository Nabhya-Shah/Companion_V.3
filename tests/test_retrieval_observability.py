import asyncio

from companion_ai.local_loops.memory_loop import MemoryLoop
from companion_ai.memory.knowledge import recall_with_trace
from companion_ai.conversation_manager import ConversationSession


def test_recall_with_trace_emits_stage_model(monkeypatch):
    monkeypatch.setattr("companion_ai.core.config.USE_MEM0", False)

    results, trace = recall_with_trace(
        "what do you know about my preferences",
        include_mem0=False,
        include_sqlite=False,
        include_brain=False,
        limit=5,
    )

    assert results == []
    assert trace["query"] == "what do you know about my preferences"
    assert trace["result_count"] == 0

    stage_names = [s["name"] for s in trace["stages"]]
    assert stage_names == ["query_expand", "retrieve", "rerank", "answer"]

    for stage in trace["stages"]:
        assert stage["status"] == "ok"
        assert isinstance(stage["duration_ms"], int)
        assert stage["duration_ms"] >= 0


def test_memory_loop_search_attaches_retrieval_trace(monkeypatch):
    expected_trace = {
        "query": "name",
        "stages": [{"name": "retrieve", "status": "ok", "duration_ms": 4, "details": {}}],
        "result_count": 1,
    }

    monkeypatch.setattr(
        "companion_ai.memory.knowledge.recall_with_trace",
        lambda query, limit, user_id: ([{"source": "profile", "text": "User name is Bob"}], expected_trace),
        raising=False,
    )

    loop = MemoryLoop()
    result = asyncio.run(loop.execute({"operation": "search", "query": "name"}))

    assert result.status.value == "success"
    assert result.data["count"] == 1
    assert result.metadata["retrieval_trace"] == expected_trace


def test_recall_with_trace_includes_connector_diagnostics(monkeypatch):
    monkeypatch.setattr("companion_ai.core.config.USE_MEM0", False)
    monkeypatch.setattr("companion_ai.core.config.RETRIEVAL_CONNECTORS_ENABLED", True)

    def fake_search_connectors(request):
        return (
            [
                {
                    "text": "External context note",
                    "score": 0.42,
                    "source": "connector:file_stub",
                    "source_id": "stub-1",
                }
            ],
            {
                "connector_counts": {"file_stub": 1},
                "connector_ms": {"file_stub": 2},
                "enabled_count": 1,
            },
        )

    monkeypatch.setattr(
        "companion_ai.retrieval.adapters.search_connectors",
        fake_search_connectors,
        raising=False,
    )

    results, trace = recall_with_trace(
        "project context",
        include_mem0=False,
        include_sqlite=False,
        include_brain=False,
        limit=5,
    )

    assert len(results) == 1
    retrieve_stage = [s for s in trace["stages"] if s["name"] == "retrieve"][0]
    assert retrieve_stage["details"]["connectors_enabled"] == 1
    assert retrieve_stage["details"]["connector_counts"]["file_stub"] == 1


def test_connector_results_filtered_by_source_allowlist(monkeypatch):
    monkeypatch.setattr("companion_ai.core.config.USE_MEM0", False)
    monkeypatch.setattr("companion_ai.core.config.RETRIEVAL_CONNECTORS_ENABLED", True)
    monkeypatch.setattr(
        "companion_ai.core.config.get_retrieval_connector_source_allowlist",
        lambda: {"allowed_source"},
    )

    from companion_ai.retrieval.connectors import RetrievalConnectorRecord, RetrievalConnectorRequest

    class FakeConnector:
        connector_id = "fake"
        connector_type = "test"

        def search(self, request):
            return [
                RetrievalConnectorRecord(
                    connector_id="fake",
                    connector_type="test",
                    source_id="1",
                    source_type="blocked_source",
                    text="Should be filtered",
                    score=0.4,
                    latency_ms=1,
                ),
                RetrievalConnectorRecord(
                    connector_id="fake",
                    connector_type="test",
                    source_id="2",
                    source_type="allowed_source",
                    text="Should stay",
                    score=0.5,
                    latency_ms=1,
                ),
            ]

    monkeypatch.setattr(
        "companion_ai.retrieval.adapters.get_enabled_connectors",
        lambda: [FakeConnector()],
    )

    from companion_ai.retrieval.adapters import search_connectors

    results, diagnostics = search_connectors(RetrievalConnectorRequest(query="q", limit=5))

    assert len(results) == 1
    assert results[0]["source_type"] == "allowed_source"
    assert diagnostics["connector_counts"]["fake"] == 1


def test_connector_permission_denied_falls_back_to_local_only(monkeypatch):
    monkeypatch.setattr("companion_ai.core.config.USE_MEM0", False)
    monkeypatch.setattr("companion_ai.core.config.RETRIEVAL_CONNECTORS_ENABLED", True)

    monkeypatch.setattr(
        "companion_ai.web.state.get_workspace_permissions",
        lambda workspace_id=None: {
            "tools_execute": True,
            "memory_write": True,
            "workflows_run": True,
            "files_upload": True,
            "retrieval_connectors": False,
        },
        raising=False,
    )

    results, trace = recall_with_trace(
        "project context",
        include_mem0=False,
        include_sqlite=False,
        include_brain=False,
        limit=5,
    )

    assert results == []
    retrieve_stage = [s for s in trace["stages"] if s["name"] == "retrieve"][0]
    assert retrieve_stage["details"]["connectors_enabled"] == 0


def test_streaming_emits_retrieval_stage_events(monkeypatch):
    monkeypatch.setattr("companion_ai.core.config.USE_ORCHESTRATOR", True)
    monkeypatch.setattr("companion_ai.conversation_manager.MEM0_AVAILABLE", False)

    metadata = {
        "source": "loop_memory",
        "loop_result": {
            "status": "success",
            "data": {"count": 1},
            "metadata": {
                "operation": "search",
                "retrieval_trace": {
                    "query": "favorite food",
                    "stages": [
                        {"name": "query_expand", "status": "ok", "duration_ms": 1, "details": {}},
                        {"name": "retrieve", "status": "ok", "duration_ms": 3, "details": {}},
                    ],
                },
            },
        },
    }

    monkeypatch.setattr(
        "companion_ai.orchestrator.process_message",
        lambda user_message, context: ("Found it", metadata),
    )

    session = ConversationSession()
    chunks = list(session.process_message_streaming("what is my favorite food"))

    retrieval_events = [
        c for c in chunks if isinstance(c, dict) and c.get("type") == "retrieval_stage"
    ]
    assert len(retrieval_events) == 4

    done_events = [e["data"] for e in retrieval_events if e.get("data", {}).get("status") in {"done", "error"}]
    done_stages = [e.get("stage") for e in done_events]
    assert done_stages == ["query_expand", "retrieve"]
