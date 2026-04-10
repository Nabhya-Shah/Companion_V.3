from web_companion import app
import companion_ai.web.system_routes as _sys_mod


def test_health_includes_readiness_snapshot():
    client = app.test_client()
    res = client.get('/api/health')

    assert res.status_code == 200
    data = res.get_json()

    assert 'readiness' in data
    readiness = data['readiness']
    assert isinstance(readiness, dict)
    assert readiness.get('status') in {'ready', 'degraded'}
    assert 'api_auth_configured' in readiness
    assert 'jobs_worker_alive' in readiness
    assert 'mem0_enabled' in readiness
    assert 'mem0_initialized' in readiness
    assert 'brain_dir_exists' in readiness
    assert 'data_dir_exists' in readiness
    assert 'memory_write_queue_depth' in readiness
    assert 'memory_write_queue_oldest_created_at' in readiness
    assert 'local_runtime' in readiness

    local_runtime = readiness['local_runtime']
    assert isinstance(local_runtime, dict)
    assert 'runtime' in local_runtime
    assert 'profile' in local_runtime
    assert 'selected_runtime_available' in local_runtime
    assert 'cloud_fallback_enabled' in local_runtime
    assert 'available_backends' in local_runtime


def test_health_trace_id_roundtrip_via_header():
    client = app.test_client()
    res = client.get('/api/health', headers={'X-Trace-ID': 'trace-health-123'})

    assert res.status_code == 200
    assert res.headers.get('X-Trace-ID') == 'trace-health-123'

    data = res.get_json()
    assert data.get('trace_id') == 'trace-health-123'


def test_health_readiness_degrades_on_queue_backlog(monkeypatch):
    rows = [{'created_at': '2026-03-31T21:00:00'} for _ in range(101)]
    monkeypatch.setattr(_sys_mod.write_queue, 'list_queued_writes', lambda limit=5000: rows)

    client = app.test_client()
    res = client.get('/api/health')

    assert res.status_code == 200
    readiness = res.get_json().get('readiness', {})
    assert readiness.get('memory_write_queue_depth') == 101
    assert readiness.get('status') == 'degraded'
    assert 'memory_write_queue_backlog' in (readiness.get('reasons') or [])


def test_health_readiness_degrades_when_queue_probe_fails(monkeypatch):
    def _boom(limit=5000):
        raise RuntimeError('queue read failed')

    monkeypatch.setattr(_sys_mod.write_queue, 'list_queued_writes', _boom)

    client = app.test_client()
    res = client.get('/api/health')

    assert res.status_code == 200
    readiness = res.get_json().get('readiness', {})
    assert readiness.get('status') == 'degraded'
    assert 'memory_write_queue_probe_failed' in (readiness.get('reasons') or [])


def test_health_readiness_degrades_when_local_runtime_unavailable_without_fallback(monkeypatch):
    monkeypatch.setattr(_sys_mod, '_local_runtime_snapshot', lambda: {
        'runtime': 'vllm',
        'profile': 'quality',
        'chat_provider': 'cloud_primary',
        'min_vram_gb': 16,
        'cloud_fallback_enabled': False,
        'vllm_available': False,
        'ollama_available': False,
        'selected_runtime_available': False,
        'available_backends': [],
        'memory_provider_effective': 'local',
        'memory_provider_configured': 'auto',
    })

    client = app.test_client()
    res = client.get('/api/health')

    assert res.status_code == 200
    readiness = res.get_json().get('readiness', {})
    assert readiness.get('status') == 'degraded'
    assert 'local_runtime_unavailable_no_fallback' in (readiness.get('reasons') or [])
