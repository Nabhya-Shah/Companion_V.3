import web_companion
from web_companion import app
import companion_ai.web.memory_routes as _mem_mod
import time
import pytest


@pytest.fixture(autouse=True)
def _reset_queue_replay_state():
    _mem_mod._queue_replay_last_monotonic_ts = 0.0
    _mem_mod._queue_replay_last_completed_at = ''
    if _mem_mod._QUEUE_REPLAY_LOCK.locked():
        _mem_mod._QUEUE_REPLAY_LOCK.release()
    yield
    _mem_mod._queue_replay_last_monotonic_ts = 0.0
    _mem_mod._queue_replay_last_completed_at = ''
    if _mem_mod._QUEUE_REPLAY_LOCK.locked():
        _mem_mod._QUEUE_REPLAY_LOCK.release()


def test_memory_write_queue_endpoint_requires_auth(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    client = app.test_client()
    res = client.get('/api/memory/write-queue')

    assert res.status_code == 401
    assert res.get_json().get('error') == 'Unauthorized'


def test_memory_write_queue_endpoint_returns_queue_snapshot(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    captured = {}

    def _fake_list(limit=25):
        captured['limit'] = limit
        return [
            {
                'request_id': 'req-1',
                'operation': 'add',
                'user_scope': 'scope-a',
                'created_at': '2026-03-31T21:00:00',
                'payload': {'messages': [{'role': 'user', 'content': 'hello'}]},
            },
            {
                'request_id': 'req-2',
                'operation': 'update',
                'user_scope': 'scope-b',
                'created_at': '2026-03-31T21:01:00',
                'payload': {'memory_id': 'm-22'},
            },
        ]

    monkeypatch.setattr(_mem_mod.write_queue, 'list_queued_writes', _fake_list)

    client = app.test_client()
    res = client.get('/api/memory/write-queue?limit=999', headers={'X-API-TOKEN': 'secret'})

    assert res.status_code == 200
    data = res.get_json()
    assert captured['limit'] == 200
    assert data['queued_count'] == 2
    assert len(data['items']) == 2
    assert data['items'][0]['request_id'] == 'req-1'
    assert data['items'][0]['operation'] == 'add'
    assert data['items'][0]['payload_preview'].startswith('{')
    assert isinstance(data.get('trace_id'), str)


def test_memory_write_queue_replay_requires_auth(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    client = app.test_client()
    res = client.post('/api/memory/write-queue/replay', json={})

    assert res.status_code == 401
    assert res.get_json().get('error') == 'Unauthorized'


def test_memory_write_queue_replay_caps_max_items(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    captured = {}

    def _fake_replay(max_items=None):
        captured['max_items'] = max_items
        return {'replayed': 2, 'remaining': 1, 'failed': 0}

    def _fake_list(limit=100):
        captured['limit'] = limit
        return [
            {'request_id': 'r1'},
            {'request_id': 'r2'},
            {'request_id': 'r3'},
        ]

    monkeypatch.setattr(_mem_mod.mem0, 'replay_queued_writes', _fake_replay)
    monkeypatch.setattr(_mem_mod.write_queue, 'list_queued_writes', _fake_list)

    client = app.test_client()
    res = client.post(
        '/api/memory/write-queue/replay',
        json={'max_items': 9999},
        headers={'X-API-TOKEN': 'secret'},
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['status'] == 'ok'
    assert captured['max_items'] == 200
    assert payload['queued_count'] == 3
    assert payload['replay']['replayed'] == 2
    assert isinstance(payload.get('trace_id'), str)


def test_memory_write_queue_replay_enforces_cooldown(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    _mem_mod._queue_replay_last_monotonic_ts = time.monotonic()

    client = app.test_client()
    res = client.post('/api/memory/write-queue/replay', headers={'X-API-TOKEN': 'secret'})

    assert res.status_code == 429
    payload = res.get_json()
    assert payload['reason'] == 'replay_cooldown'
    assert payload['retry_after_seconds'] > 0


def test_memory_write_queue_replay_reports_in_progress(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    acquired = _mem_mod._QUEUE_REPLAY_LOCK.acquire(blocking=False)
    assert acquired is True
    try:
        client = app.test_client()
        res = client.post('/api/memory/write-queue/replay', headers={'X-API-TOKEN': 'secret'})
    finally:
        _mem_mod._QUEUE_REPLAY_LOCK.release()

    assert res.status_code == 409
    payload = res.get_json()
    assert payload['reason'] == 'replay_in_progress'
