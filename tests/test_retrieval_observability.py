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
