import web_companion
from web_companion import app


def test_chat_send_stream_includes_retrieval_stage_events(monkeypatch):
    def fake_process_message_streaming(self, user_message, full_conversation_history=None, memory_user_id=None, trace_id=None):
        yield {"type": "meta", "data": {"source": "loop_memory"}}
        yield {
            "type": "retrieval_stage",
            "data": {
                "stage": "retrieve",
                "status": "start",
                "duration_ms": 0,
                "meta": {"provider": "hybrid"},
            },
        }
        yield {
            "type": "retrieval_stage",
            "data": {
                "stage": "retrieve",
                "status": "done",
                "duration_ms": 12,
                "meta": {"provider": "hybrid", "details": {"raw_count": 3}},
            },
        }
        yield "done"

    monkeypatch.setattr(web_companion.ConversationSession, "process_message_streaming", fake_process_message_streaming)

    client = app.test_client()
    res = client.post("/api/chat/send", json={"message": "remember me"})

    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert '"retrieval_stage"' in body
    assert '"stage": "retrieve"' in body
    assert '"status": "start"' in body
    assert '"status": "done"' in body
