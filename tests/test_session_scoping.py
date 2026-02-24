from companion_ai.core import config as core_config
from web_companion import app
import web_companion


def test_chat_passes_scoped_mem0_user_id(monkeypatch):
    captured = {}

    def fake_process_message(self, user_message, full_conversation_history=None, memory_user_id=None):
        captured["memory_user_id"] = memory_user_id
        return "ok", True

    monkeypatch.setattr(web_companion.ConversationSession, "process_message", fake_process_message)

    client = app.test_client()
    res = client.post(
        "/api/chat",
        json={
            "message": "hello",
            "session_id": "sessA",
            "profile_id": "home",
        },
    )

    assert res.status_code == 200
    data = res.get_json()
    assert data["session_id"] == "sessA"
    assert data["profile_id"] == "home"
    assert captured["memory_user_id"] == f"{core_config.MEM0_USER_ID}::p:home::s:sessA"


def test_chat_passes_workspace_scoped_mem0_user_id(monkeypatch):
    captured = {}

    def fake_process_message(self, user_message, full_conversation_history=None, memory_user_id=None):
        captured["memory_user_id"] = memory_user_id
        return "ok", True

    monkeypatch.setattr(web_companion.ConversationSession, "process_message", fake_process_message)

    client = app.test_client()
    res = client.post(
        "/api/chat",
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

    monkeypatch.setattr(web_companion.memory_v2, "get_all_memories", fake_get_all_memories)

    client = app.test_client()
    res = client.get("/api/memory?session_id=sessB&profile_id=work")

    assert res.status_code == 200
    assert captured["user_id"] == f"{core_config.MEM0_USER_ID}::p:work::s:sessB"


def test_clear_memory_uses_scoped_user_id(monkeypatch):
    captured = {}

    monkeypatch.setattr(web_companion.core_config, "USE_MEM0", True)
    monkeypatch.setattr(web_companion.core_config, "API_AUTH_TOKEN", "secret")
    monkeypatch.setattr(web_companion, "clear_all_memory", lambda: None)
    monkeypatch.setattr(web_companion.memory_v2, "_reset_memory", lambda: None)

    def fake_clear_all_memories(user_id="default"):
        captured["user_id"] = user_id
        return True

    monkeypatch.setattr(web_companion.memory_v2, "clear_all_memories", fake_clear_all_memories)

    client = app.test_client()
    res = client.post(
        "/api/memory/clear",
        json={"session_id": "sessC", "profile_id": "private"},
        headers={"X-API-TOKEN": "secret"},
    )

    assert res.status_code == 200
    assert captured["user_id"] == f"{core_config.MEM0_USER_ID}::p:private::s:sessC"
