from companion_ai.core import config as core_config
from web_companion import app
import web_companion
import companion_ai.web.memory_routes as _mem_mod
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor

from companion_ai.local_loops.memory_loop import MemoryLoop


def test_chat_passes_scoped_mem0_user_id(monkeypatch):
    captured = {}

    def fake_process_message_streaming(self, user_message, full_conversation_history=None, memory_user_id=None, trace_id=None):
        captured["memory_user_id"] = memory_user_id
        yield {"type": "meta", "data": {"session_id": "sessA", "profile_id": "home"}}
        yield "ok"

    monkeypatch.setattr(web_companion.ConversationSession, "process_message_streaming", fake_process_message_streaming)

    client = app.test_client()
    res = client.post(
        "/api/chat/send",
        json={
            "message": "hello",
            "session_id": "sessA",
            "profile_id": "home",
        },
    )

    assert res.status_code == 200
    assert captured["memory_user_id"] == f"{core_config.MEM0_USER_ID}::p:home::s:sessA"


def test_chat_passes_workspace_scoped_mem0_user_id(monkeypatch):
    captured = {}

    def fake_process_message_streaming(self, user_message, full_conversation_history=None, memory_user_id=None, trace_id=None):
        captured["memory_user_id"] = memory_user_id
        yield {"type": "meta", "data": {"session_id": "sessA", "profile_id": "home"}}
        yield "ok"

    monkeypatch.setattr(web_companion.ConversationSession, "process_message_streaming", fake_process_message_streaming)

    client = app.test_client()
    res = client.post(
        "/api/chat/send",
        json={
            "message": "hello",
            "session_id": "sessA",
            "profile_id": "home",
            "workspace_id": "work",
        },
    )

    assert res.status_code == 200
    assert captured["memory_user_id"] == f"{core_config.MEM0_USER_ID}::w:work::p:home::s:sessA"


def test_memory_endpoint_uses_scoped_user_id(monkeypatch):
    captured = {}

    monkeypatch.setattr(web_companion.core_config, "USE_MEM0", True)

    def fake_get_all_memories(user_id="default"):
        captured["user_id"] = user_id
        return []

    monkeypatch.setattr(web_companion.mem0, "get_all_memories", fake_get_all_memories)

    client = app.test_client()
    res = client.get("/api/memory?session_id=sessB&profile_id=work")

    assert res.status_code == 200
    assert captured["user_id"] == f"{core_config.MEM0_USER_ID}::p:work::s:sessB"


def test_clear_memory_uses_scoped_user_id(monkeypatch):
    captured = {}

    monkeypatch.setattr(web_companion.core_config, "USE_MEM0", True)
    monkeypatch.setattr(web_companion.core_config, "API_AUTH_TOKEN", "secret")
    monkeypatch.setattr(_mem_mod, "clear_all_memory", lambda: None)
    monkeypatch.setattr(web_companion.mem0, "_reset_memory", lambda: None)

    def fake_clear_all_memories(user_id="default"):
        captured["user_id"] = user_id
        return True

    monkeypatch.setattr(web_companion.mem0, "clear_all_memories", fake_clear_all_memories)

    client = app.test_client()
    res = client.post(
        "/api/memory/clear",
        json={"session_id": "sessC", "profile_id": "private"},
        headers={"X-API-TOKEN": "secret"},
    )

    assert res.status_code == 200
    assert captured["user_id"] == f"{core_config.MEM0_USER_ID}::p:private::s:sessC"


def test_memory_loop_save_uses_scoped_user_id(monkeypatch):
    captured = {}

    def fake_remember(fact, **kwargs):
        captured["fact"] = fact
        captured["user_id"] = kwargs.get("user_id")
        return {"mem0": {"ok": True}, "sqlite": False}

    monkeypatch.setattr("companion_ai.memory.knowledge.remember", fake_remember)

    loop = MemoryLoop()
    result = asyncio.run(loop.execute({
        "operation": "save",
        "fact": "User likes coffee",
        "user_id": f"{core_config.MEM0_USER_ID}::p:home::s:sessA",
    }))

    assert result.status.value == "success"
    assert captured["fact"] == "User likes coffee"
    assert captured["user_id"] == f"{core_config.MEM0_USER_ID}::p:home::s:sessA"


def test_chat_trace_id_header_and_stream_propagation(monkeypatch):
    captured = {}

    def fake_process_message_streaming(self, user_message, full_conversation_history=None, memory_user_id=None, trace_id=None):
        captured["trace_id"] = trace_id
        yield {"type": "meta", "data": {"source": "test"}}
        yield "ok"

    monkeypatch.setattr(web_companion.ConversationSession, "process_message_streaming", fake_process_message_streaming)

    client = app.test_client()
    res = client.post(
        "/api/chat/send",
        json={"message": "hello"},
        headers={"X-Trace-ID": "trace-unit-123"},
    )

    assert res.status_code == 200
    assert captured["trace_id"] == "trace-unit-123"
    assert res.headers.get("X-Trace-ID") == "trace-unit-123"
    body = res.get_data(as_text=True)
    assert '"trace_id": "trace-unit-123"' in body


def test_parallel_chat_requests_preserve_scope_isolation(monkeypatch):
    seen = []
    seen_lock = threading.Lock()

    def fake_process_message_streaming(self, user_message, full_conversation_history=None, memory_user_id=None, trace_id=None):
        with seen_lock:
            seen.append(memory_user_id)
        yield {"type": "meta", "data": {"ok": True}}
        yield "ok"

    monkeypatch.setattr(web_companion.ConversationSession, "process_message_streaming", fake_process_message_streaming)

    def _send(session_id: str, profile_id: str, workspace_id: str):
        client = app.test_client()
        response = client.post(
            "/api/chat/send",
            json={
                "message": "hello",
                "session_id": session_id,
                "profile_id": profile_id,
                "workspace_id": workspace_id,
            },
        )
        assert response.status_code == 200

    cases = [
        ("sess-1", "home", "workspace-a"),
        ("sess-2", "work", "workspace-b"),
    ]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_send, *case) for case in cases]
        for fut in futures:
            fut.result()

    expected = {
        f"{core_config.MEM0_USER_ID}::w:workspace-a::p:home::s:sess-1",
        f"{core_config.MEM0_USER_ID}::w:workspace-b::p:work::s:sess-2",
    }
    assert set(seen) == expected
