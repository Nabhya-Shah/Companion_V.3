from companion_ai.core import config as core_config
from web_companion import app
import web_companion
import companion_ai.web.memory_routes as _mem_mod


def test_chat_passes_scoped_mem0_user_id(monkeypatch):
    captured = {}

    def fake_process_message_streaming(self, user_message, full_conversation_history=None, memory_user_id=None):
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

    def fake_process_message_streaming(self, user_message, full_conversation_history=None, memory_user_id=None):
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
