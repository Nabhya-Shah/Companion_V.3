import web_companion
from web_companion import app
import companion_ai.web.memory_routes as _mem_mod


def test_memory_readiness_requires_auth(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    client = app.test_client()
    res = client.get('/api/memory/readiness')

    assert res.status_code == 401
    assert res.get_json().get('error') == 'Unauthorized'


def test_memory_readiness_returns_contract(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(_mem_mod.mem0, '_memory_instance', object())
    monkeypatch.setattr(_mem_mod.mem0, 'get_runtime_descriptor', lambda: {'provider': 'local', 'model': 'qwen2.5:7b'})
    monkeypatch.setattr(_mem_mod.write_queue, 'list_queued_writes', lambda limit=5000: [])
    monkeypatch.setattr(_mem_mod, 'list_memory_write_status', lambda limit=500: [])

    client = app.test_client()
    res = client.get('/api/memory/readiness', headers={'X-API-TOKEN': 'secret'})

    assert res.status_code == 200
    data = res.get_json()
    assert data.get('status') in {'ready', 'degraded'}
    assert 'mem0' in data
    assert 'write_queue' in data
    assert 'write_status' in data
    assert 'recommendations' in data
    assert isinstance(data.get('trace_id'), str)


def test_memory_readiness_degrades_on_mem0_and_queue_probe_failure(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(web_companion.core_config, 'USE_MEM0', True)
    monkeypatch.setattr(_mem_mod.mem0, '_memory_instance', None)
    monkeypatch.setattr(_mem_mod.mem0, 'get_runtime_descriptor', lambda: {'provider': 'local', 'model': 'qwen2.5:7b'})

    def _queue_boom(limit=5000):
        raise RuntimeError('queue down')

    monkeypatch.setattr(_mem_mod.write_queue, 'list_queued_writes', _queue_boom)
    monkeypatch.setattr(_mem_mod, 'list_memory_write_status', lambda limit=500: [])

    client = app.test_client()
    res = client.get('/api/memory/readiness', headers={'X-API-TOKEN': 'secret'})

    assert res.status_code == 200
    data = res.get_json()
    assert data.get('status') == 'degraded'
    reasons = data.get('reasons') or []
    assert 'mem0_not_initialized' in reasons
    assert 'memory_write_queue_probe_failed' in reasons
