import asyncio

from companion_ai.local_loops.memory_loop import MemoryLoop
from companion_ai.orchestrator import Orchestrator, OrchestratorAction, OrchestratorDecision


def test_memory_loop_extract_returns_structured_facts(monkeypatch):
    captured = {}

    def fake_extract(text):
        captured["text"] = text
        return {
            "favorite_food": {
                "value": "ramen",
                "confidence": 0.91,
                "conf_label": "high",
                "evidence": "User: My favorite food is ramen",
                "justification": "Explicitly stated preference.",
                "fact": "User favorite food is ramen",
            }
        }

    monkeypatch.setattr("companion_ai.memory.ai_processor.extract_profile_facts_from_text", fake_extract)

    loop = MemoryLoop()
    result = asyncio.run(loop.execute({
        "operation": "extract",
        "text": "User: My favorite food is ramen\n[Visual context from user's uploaded file: ignore me]\nAI: nice",
    }))

    assert result.status.value == "success"
    assert result.data["count"] == 1
    fact = result.data["extracted_facts"][0]
    assert fact["key"] == "favorite_food"
    assert fact["value"] == "ramen"
    assert "Visual context" not in captured["text"]


def test_memory_loop_extract_degrades_safely(monkeypatch):
    def fake_extract(_text):
        raise RuntimeError("boom")

    monkeypatch.setattr("companion_ai.memory.ai_processor.extract_profile_facts_from_text", fake_extract)

    loop = MemoryLoop()
    result = asyncio.run(loop.execute({"operation": "extract", "text": "User: hi"}))

    assert result.status.value == "error"
    assert "boom" in result.error


def test_orchestrator_auto_extract_saves_high_confidence_and_queues_lower(monkeypatch):
    class FakeLoop:
        async def execute(self, task):
            return type("Result", (), {
                "status": type("Status", (), {"value": "success"})(),
                "data": {
                    "extracted_facts": [
                        {
                            "key": "favorite_food",
                            "value": "ramen",
                            "confidence": 0.91,
                            "conf_label": "high",
                            "evidence": "User: My favorite food is ramen",
                            "justification": "Explicit preference",
                            "fact": "User favorite food is ramen",
                        },
                        {
                            "key": "hobby",
                            "value": "chess",
                            "confidence": 0.42,
                            "conf_label": "low",
                            "evidence": "User: maybe I still play chess sometimes",
                            "justification": "Weakly implied",
                            "fact": "User hobby is chess",
                        },
                    ]
                },
            })()

    upserts = []
    queued = []
    remembers = []

    monkeypatch.setattr("companion_ai.orchestrator.get_loop", lambda name: FakeLoop() if name == "memory" else None)
    monkeypatch.setattr("companion_ai.memory.sqlite_backend.upsert_profile_fact", lambda *args, **kwargs: upserts.append((args, kwargs)))
    monkeypatch.setattr("companion_ai.memory.sqlite_backend.queue_pending_profile_fact", lambda *args, **kwargs: queued.append((args, kwargs)) or True)
    monkeypatch.setattr("companion_ai.memory.knowledge.remember", lambda *args, **kwargs: remembers.append((args, kwargs)) or {"mem0": {"ok": True}, "sqlite": False})
    monkeypatch.setattr("companion_ai.core.config.FACT_AUTO_APPROVE_THRESHOLD", 0.85)

    orch = Orchestrator()
    meta = asyncio.run(orch._maybe_extract_turn_facts(
        OrchestratorDecision(action=OrchestratorAction.ANSWER, content="ok"),
        "I love ramen and maybe play chess.",
        "Noted.",
        {"source": "120b_direct"},
        {"mem0_user_id": "scoped-user"},
    ))

    assert meta["auto_extracted_facts"] == 2
    assert meta["auto_saved_facts"] == 1
    assert meta["auto_review_facts"] == 1
    assert len(upserts) == 1
    assert len(queued) == 1
    assert len(remembers) == 1
    assert remembers[0][0][0] == "User favorite food is ramen"
    assert remembers[0][1]["user_id"] == "scoped-user"
    assert remembers[0][1]["skip_sqlite"] is True


def test_orchestrator_skips_auto_extract_for_memory_loop(monkeypatch):
    called = []

    class FakeLoop:
        async def execute(self, task):
            called.append(task)
            return None

    monkeypatch.setattr("companion_ai.orchestrator.get_loop", lambda name: FakeLoop() if name == "memory" else None)

    orch = Orchestrator()
    meta = asyncio.run(orch._maybe_extract_turn_facts(
        OrchestratorDecision(action=OrchestratorAction.DELEGATE, loop="memory", task={"operation": "save"}),
        "Remember that I like ramen",
        "Saved it.",
        {"source": "loop_memory"},
        {"mem0_user_id": "scoped-user"},
    ))

    assert meta == {}
    assert called == []