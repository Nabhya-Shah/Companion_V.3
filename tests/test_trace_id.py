import threading

from companion_ai.core import config as core_config
import companion_ai.conversation_manager as conv_mod
from companion_ai.conversation_manager import ConversationSession
from web_companion import app


def test_health_endpoint_sets_trace_header():
    client = app.test_client()
    res = client.get('/api/health')

    assert res.status_code == 200
    trace_id = res.headers.get('X-Trace-ID', '')
    assert isinstance(trace_id, str)
    assert trace_id


def test_streaming_mem0_write_uses_trace_request_id(monkeypatch):
    captured = {}

    monkeypatch.setattr(core_config, 'USE_ORCHESTRATOR', False)
    monkeypatch.setattr(conv_mod, 'MEM0_AVAILABLE', True)

    def fake_stream(_user_message, _context):
        yield 'ok'

    monkeypatch.setattr(conv_mod, 'generate_response_streaming', fake_stream)

    def fake_add_memory(messages, user_id='default', metadata=None, request_id=None, allow_queue=True):
        captured['request_id'] = request_id
        return {'write_status': {'status': 'accepted_committed'}}

    monkeypatch.setattr(conv_mod, 'mem0_add_memory', fake_add_memory)

    class _ImmediateThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            if self._target:
                self._target()

    monkeypatch.setattr(threading, 'Thread', _ImmediateThread)

    session = ConversationSession()
    list(session.process_message_streaming('my name is alice', [], memory_user_id='u-test', trace_id='trace-test-001'))

    assert captured['request_id'] == 'trace-test-001:chat_async'
