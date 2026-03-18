import json
from pathlib import Path

from companion_ai.memory import mem0_backend
from companion_ai.memory import sqlite_backend


class _FakeMem0:
    def __init__(self):
        self.add_calls = []

    def add(self, payload, user_id="default", metadata=None):
        self.add_calls.append({"payload": payload, "user_id": user_id, "metadata": metadata or {}})
        return {"results": [{"event": "ADD", "id": "m-1", "text": "stored"}]}

    def get_all(self, user_id="default"):
        return {"results": []}


def _read_jsonl(path: Path):
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_add_memory_queues_on_backend_failure(monkeypatch, tmp_path):
    sqlite_backend.clear_all_memory()
    queue_path = tmp_path / "memory_write_spool.jsonl"

    monkeypatch.setattr(mem0_backend.write_queue, "QUEUE_PATH", str(queue_path))

    def _boom():
        raise RuntimeError("mem0 down")

    monkeypatch.setattr(mem0_backend, "get_memory", _boom)

    result = mem0_backend.add_memory(
        [{"role": "user", "content": "hello queue"}],
        user_id="queue-user",
        request_id="req-queued-1",
    )

    write_status = result.get("write_status", {})
    assert write_status.get("status") == "accepted_queued"

    rows = _read_jsonl(queue_path)
    assert len(rows) == 1
    assert rows[0]["request_id"] == "req-queued-1"
    assert rows[0]["operation"] == "add"

    status_row = sqlite_backend.get_memory_write_status("req-queued-1")
    assert status_row is not None
    assert status_row["status"] == "accepted_queued"


def test_replay_queued_writes_commits_and_clears_spool(monkeypatch, tmp_path):
    sqlite_backend.clear_all_memory()
    queue_path = tmp_path / "memory_write_spool.jsonl"
    fake = _FakeMem0()

    monkeypatch.setattr(mem0_backend.write_queue, "QUEUE_PATH", str(queue_path))
    monkeypatch.setattr(mem0_backend, "get_memory", lambda: fake)

    # First call queues (backend down)
    def _boom_once():
        raise RuntimeError("transient down")

    monkeypatch.setattr(mem0_backend, "get_memory", _boom_once)
    queued = mem0_backend.add_memory(
        [{"role": "user", "content": "safe message"}],
        user_id="replay-user",
        request_id="req-replay-1",
    )
    assert queued.get("write_status", {}).get("status") == "accepted_queued"

    # Recovery path: replay should now commit and drain queue
    monkeypatch.setattr(mem0_backend, "get_memory", lambda: fake)
    replay_stats = mem0_backend.replay_queued_writes()

    assert replay_stats["replayed"] == 1
    assert replay_stats["remaining"] == 0
    assert _read_jsonl(queue_path) == []

    status_row = sqlite_backend.get_memory_write_status("req-replay-1")
    assert status_row is not None
    assert status_row["status"] == "accepted_committed"


def test_add_memory_short_circuits_if_request_already_committed(monkeypatch):
    sqlite_backend.clear_all_memory()
    sqlite_backend.log_memory_write_status(
        request_id="req-committed-1",
        user_scope="idempotent-user",
        operation="add",
        status="accepted_committed",
        backend="mem0",
        payload={"messages": []},
    )

    def _should_not_run():
        raise AssertionError("get_memory should not be called for committed request")

    monkeypatch.setattr(mem0_backend, "get_memory", _should_not_run)

    result = mem0_backend.add_memory(
        [{"role": "user", "content": "ignored"}],
        user_id="idempotent-user",
        request_id="req-committed-1",
    )

    assert result["status"] == "accepted_committed"
    assert result["reason"] == "idempotent_replay"
