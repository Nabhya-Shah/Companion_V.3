from pathlib import Path

import web_companion
from web_companion import app
from companion_ai.memory import sqlite_backend as sqlite_memory
from companion_ai.memory import mem0_backend
import companion_ai.web.memory_routes as _mem_mod
import companion_ai.web.state as _web_state


def test_bulk_sync_memory_quality_from_mem0_labels(tmp_path, monkeypatch):
    db_path = tmp_path / "quality_pipeline.db"
    monkeypatch.setattr(sqlite_memory, "DB_PATH", str(db_path))
    sqlite_memory.init_db()

    memories = [
        {
            "id": "m-low",
            "memory": "User dislikes cilantro",
            "metadata": {"confidence": 0.2, "frequency": 1},
        },
        {
            "id": "m-high",
            "memory": "User name is Alex",
            "metadata": {"confidence": 0.92, "frequency": 4},
        },
    ]

    synced = sqlite_memory.bulk_sync_memory_quality_from_mem0(memories, user_scope="scope-A")
    quality = sqlite_memory.get_memory_quality_map("scope-A")

    assert synced == 2
    assert quality["m-low"]["confidence_label"] == "low"
    assert quality["m-high"]["confidence_label"] == "high"
    assert quality["m-high"]["reaffirmations"] == 4


def test_memory_endpoint_uses_quality_ledger_metadata(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, "USE_MEM0", True)
    monkeypatch.setattr(_web_state, "_maybe_migrate_legacy_scope", lambda *_: None)

    monkeypatch.setattr(
        web_companion.mem0,
        "get_all_memories",
        lambda user_id=None: [{"id": "m1", "memory": "User prefers tea", "metadata": {"frequency": 2}}],
    )
    monkeypatch.setattr(_mem_mod, "bulk_sync_memory_quality_from_mem0", lambda memories, user_scope: 1)
    monkeypatch.setattr(
        _mem_mod,
        "get_memory_quality_map",
        lambda user_scope: {
            "m1": {
                "confidence": 0.46,
                "confidence_label": "low",
                "reaffirmations": 7,
                "contradiction_state": "pending",
                "provenance_source": "mem0",
            }
        },
    )

    client = app.test_client()
    response = client.get("/api/memory?detailed=1&session_id=sA&profile_id=home")

    assert response.status_code == 200
    data = response.get_json()
    assert data["profile_detailed"][0]["confidence_label"] == "low"
    assert data["profile_detailed"][0]["reaffirmations"] == 7
    assert data["profile_detailed"][0]["contradiction_state"] == "pending"


def test_memory_endpoint_does_not_auto_migrate_legacy_scope(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, "USE_MEM0", True)
    monkeypatch.setattr(
        _web_state,
        "_maybe_migrate_legacy_scope",
        lambda *_: (_ for _ in ()).throw(AssertionError("memory reads should not trigger migration")),
    )
    monkeypatch.setattr(web_companion.mem0, "get_all_memories", lambda user_id=None: [])
    monkeypatch.setattr(_mem_mod, "bulk_sync_memory_quality_from_mem0", lambda memories, user_scope: 0)
    monkeypatch.setattr(_mem_mod, "get_memory_quality_map", lambda user_scope: {})

    client = app.test_client()
    response = client.get("/api/memory?detailed=1&session_id=sA&profile_id=home")

    assert response.status_code == 200
    assert response.get_json()["profile_detailed"] == []


def test_delete_fact_removes_quality_entry(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, "USE_MEM0", True)
    monkeypatch.setattr(web_companion.mem0, "delete_memory", lambda memory_id: True)

    captured = {}

    def fake_delete_quality(memory_id, user_scope):
        captured["memory_id"] = memory_id
        captured["user_scope"] = user_scope
        return True

    monkeypatch.setattr(_mem_mod, "delete_memory_quality_entry", fake_delete_quality)

    client = app.test_client()
    response = client.delete("/api/memory/fact/m123?session_id=s2&profile_id=work")

    assert response.status_code == 200
    assert response.get_json()["deleted"] is True
    assert captured["memory_id"] == "m123"
    assert captured["user_scope"] == f"{web_companion.core_config.MEM0_USER_ID}::p:work::s:s2"


def test_rank_memories_prioritizes_high_confidence_and_non_conflict(tmp_path, monkeypatch):
    db_path = tmp_path / "quality_ranking.db"
    monkeypatch.setattr(sqlite_memory, "DB_PATH", str(db_path))
    sqlite_memory.init_db()

    sqlite_memory.upsert_memory_quality_entry(
        memory_id="m-low",
        memory_text="User likes tea",
        user_scope="scope-B",
        confidence=0.30,
        contradiction_state="none",
    )
    sqlite_memory.upsert_memory_quality_entry(
        memory_id="m-high",
        memory_text="User likes tea with honey",
        user_scope="scope-B",
        confidence=0.90,
        contradiction_state="none",
    )
    sqlite_memory.upsert_memory_quality_entry(
        memory_id="m-conflict",
        memory_text="User hates tea",
        user_scope="scope-B",
        confidence=0.95,
        contradiction_state="conflict",
    )

    memories = [
        {"id": "m-low", "memory": "User likes tea", "score": 0.6},
        {"id": "m-high", "memory": "User likes tea with honey", "score": 0.4},
        {"id": "m-conflict", "memory": "User hates tea", "score": 0.8},
    ]

    ranked = sqlite_memory.rank_memories_by_quality(memories, user_scope="scope-B", query="likes tea")
    ids = [item["id"] for item in ranked]

    assert ids[0] == "m-high"
    assert ids[-1] == "m-conflict"
    assert ranked[0]["quality_confidence_label"] == "high"


def test_mem0_search_uses_quality_ranking(monkeypatch):
    monkeypatch.setattr(
        mem0_backend,
        "get_memory",
        lambda: type(
            "FakeMem0",
            (),
            {
                "search": lambda self, query, user_id, limit: {
                    "results": [
                        {"id": "a", "memory": "User likes tea", "score": 0.4},
                        {"id": "b", "memory": "User likes coffee", "score": 0.4},
                    ]
                }
            },
        )(),
    )
    monkeypatch.setattr(
        sqlite_memory,
        "rank_memories_by_quality",
        lambda memories, user_scope, query=None: [memories[1], memories[0]],
    )

    results = mem0_backend.search_memories("likes", user_id="scope-C", limit=2)
    assert results[0]["id"] == "b"


def test_approve_reject_pending_fact_transitions(tmp_path, monkeypatch):
    """Pending review facts can be promoted into user_profile or rejected cleanly."""
    db_path = tmp_path / "quality_transitions.db"
    monkeypatch.setattr(sqlite_memory, "DB_PATH", str(db_path))
    sqlite_memory.init_db()
    monkeypatch.setattr("companion_ai.core.config.FACT_CONFIDENCE_THRESHOLD", 0.5)
    monkeypatch.setattr("companion_ai.core.config.FACT_AUTO_APPROVE_THRESHOLD", 0.85)

    assert sqlite_memory.queue_pending_profile_fact('favorite_color', 'blue', confidence=0.3, source='auto_extract') is True
    assert sqlite_memory.queue_pending_profile_fact('food', 'pizza', confidence=0.2, source='auto_extract') is True

    pending = sqlite_memory.list_pending_profile_facts()
    pending_by_key = {row['key']: row['id'] for row in pending}
    approve_rowid = pending_by_key['favorite_color']
    reject_rowid = pending_by_key['food']

    # Approve boosts confidence
    assert sqlite_memory.approve_profile_fact(approve_rowid) is True
    # Reject removes the queued row
    assert sqlite_memory.reject_profile_fact(reject_rowid) is True

    conn2 = sqlite_memory.get_db_connection()
    cur2 = conn2.cursor()
    # Approved fact should have high confidence now
    cur2.execute("SELECT confidence FROM user_profile WHERE key = 'favorite_color'")
    approved_row = cur2.fetchone()
    # Rejected fact should be deleted
    cur2.execute("SELECT * FROM user_profile WHERE key = 'food'")
    rejected_row = cur2.fetchone()
    conn2.close()

    assert approved_row is not None
    assert approved_row[0] >= 0.85
    assert rejected_row is None


def test_mem0_add_fallback_on_decommissioned_model(monkeypatch):
    class PrimaryMem:
        def add(self, payload, user_id, metadata=None):
            raise RuntimeError("model_decommissioned")

    class FallbackMem:
        def add(self, payload, user_id, metadata=None):
            return {"results": [{"id": "m1", "memory": "fallback ok", "event": "ADD"}]}

    calls = {"reset": 0}

    monkeypatch.setattr(mem0_backend, "get_memory", lambda: PrimaryMem())
    monkeypatch.setattr(mem0_backend, "get_all_memories", lambda user_id="default": [])

    def fake_reset_memory(use_ollama=True):
        calls["reset"] += 1
        assert use_ollama is False
        return FallbackMem()

    monkeypatch.setattr(mem0_backend, "_reset_memory", fake_reset_memory)

    result = mem0_backend.add_memory(
        [{"role": "user", "content": "my name is sam"}],
        user_id="scope-z",
        metadata={},
    )

    assert "error" not in result
    assert calls["reset"] == 1


def test_mem0_groq_config_uses_helper_model_and_tool_key(monkeypatch):
    monkeypatch.delenv("MEM0_LLM_MODEL", raising=False)
    monkeypatch.delenv("MEM0_GROQ_API_KEY", raising=False)
    monkeypatch.setenv("GROQ_TOOL_API_KEY", "tool-key")
    monkeypatch.delenv("GROQ_MEMORY_API_KEY", raising=False)
    monkeypatch.setattr(mem0_backend.core_config, "MEM0_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    monkeypatch.setattr(mem0_backend.core_config, "MEMORY_FAST_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
    monkeypatch.setattr(mem0_backend.core_config, "GROQ_TOOL_API_KEY", "tool-key")
    monkeypatch.setattr(mem0_backend.core_config, "GROQ_API_KEYS", [])
    monkeypatch.setattr(mem0_backend.core_config, "GROQ_API_KEY", "main-key")

    config = mem0_backend._get_mem0_config(use_ollama=False)

    assert config["llm"]["provider"] == "groq"
    assert config["llm"]["config"]["model"] == "meta-llama/llama-4-scout-17b-16e-instruct"
    assert config["llm"]["config"]["api_key"] == "tool-key"


def test_mem0_runtime_descriptor_uses_groq_helper_model(monkeypatch):
    monkeypatch.delenv("MEM0_LLM_MODEL", raising=False)
    monkeypatch.setattr(mem0_backend.core_config, "MEM0_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")

    runtime = mem0_backend.get_runtime_descriptor(use_ollama=False)

    assert runtime == {
        "provider": "groq",
        "model": "meta-llama/llama-4-scout-17b-16e-instruct",
    }

def test_unified_recall_propagates_reasons(monkeypatch):
    from companion_ai.memory import knowledge
    from companion_ai.core import config as core_config
    
    monkeypatch.setattr(core_config, "USE_MEM0", False)
    
    # Fake sqlite hits returning explainability fields
    def mock_search_memory(*args, **kwargs):
        return [{
            'type': 'profile',
            'text': 'Fact = value',
            'score': 0.9,
            'surfacing_reason': 'Explicit profile fact',
            'score_breakdown': {'overlap': 0.5}
        }]
        
    monkeypatch.setattr('companion_ai.memory.sqlite_backend.search_memory', mock_search_memory)
    
    results = knowledge.recall('test query', include_brain=False, include_sqlite=True, include_mem0=False)
    assert len(results) == 1
    assert results[0]['surfacing_reason'] == 'Explicit profile fact'
    assert 'score_breakdown' in results[0]
import pytest
from companion_ai.memory.sqlite_backend import rank_memories_by_quality

def test_explainable_recall_signals_mocked(monkeypatch):
    memories = [
        {'id': 'mem-1', 'memory': 'I live in Lisbon', 'score': 0.8}
    ]
    def mock_get_memory_quality_map(scope):
        return {
            'mem-1': {'confidence': 0.95, 'confidence_label': 'high', 'contradiction_state': 'none'}
        }
    
    monkeypatch.setattr('companion_ai.memory.sqlite_backend.get_memory_quality_map', mock_get_memory_quality_map)
    ranked = rank_memories_by_quality(memories, 'user', query='Lisbon')
    
    assert len(ranked) == 1
    assert 'score_breakdown' in ranked[0]
    assert 'surfacing_reason' in ranked[0]
    assert 'High' in ranked[0]['surfacing_reason']
    assert 'query match' in ranked[0]['surfacing_reason'].lower()
