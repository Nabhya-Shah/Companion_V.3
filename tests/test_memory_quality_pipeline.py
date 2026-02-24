from pathlib import Path

import web_companion
from web_companion import app
from companion_ai.memory import sqlite_backend as sqlite_memory
from companion_ai.memory import mem0_backend


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
    monkeypatch.setattr(web_companion, "_maybe_migrate_legacy_scope", lambda *_: None)

    monkeypatch.setattr(
        web_companion.memory_v2,
        "get_all_memories",
        lambda user_id=None: [{"id": "m1", "memory": "User prefers tea", "metadata": {"frequency": 2}}],
    )
    monkeypatch.setattr(web_companion, "bulk_sync_memory_quality_from_mem0", lambda memories, user_scope: 1)
    monkeypatch.setattr(
        web_companion,
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


def test_delete_fact_removes_quality_entry(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, "USE_MEM0", True)
    monkeypatch.setattr(web_companion.memory_v2, "delete_memory", lambda memory_id: True)

    captured = {}

    def fake_delete_quality(memory_id, user_scope):
        captured["memory_id"] = memory_id
        captured["user_scope"] = user_scope
        return True

    monkeypatch.setattr(web_companion, "delete_memory_quality_entry", fake_delete_quality)

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
    db_path = tmp_path / "quality_transitions.db"
    monkeypatch.setattr(sqlite_memory, "DB_PATH", str(db_path))
    sqlite_memory.init_db()

    conn = sqlite_memory.get_db_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO pending_profile_facts (key, value, confidence, source, status)
        VALUES ('favorite_color', 'blue', 0.7, 'conversation', 'pending')
        """
    )
    pending_id = cur.lastrowid
    cur.execute(
        """
        INSERT INTO pending_profile_facts (key, value, confidence, source, status)
        VALUES ('food', 'pizza', 0.6, 'conversation', 'pending')
        """
    )
    reject_id = cur.lastrowid
    conn.commit()
    conn.close()

    assert pending_id is not None
    assert reject_id is not None

    assert sqlite_memory.approve_profile_fact(pending_id) is True
    assert sqlite_memory.reject_profile_fact(reject_id) is True

    conn2 = sqlite_memory.get_db_connection()
    cur2 = conn2.cursor()
    cur2.execute("SELECT status, reviewed_at FROM pending_profile_facts WHERE id = ?", (pending_id,))
    approved_row = cur2.fetchone()
    cur2.execute("SELECT status, reviewed_at FROM pending_profile_facts WHERE id = ?", (reject_id,))
    rejected_row = cur2.fetchone()
    conn2.close()

    assert approved_row[0] == "approved"
    assert approved_row[1] is not None
    assert rejected_row[0] == "rejected"
    assert rejected_row[1] is not None


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
