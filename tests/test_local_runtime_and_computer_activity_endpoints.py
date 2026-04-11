import json

from web_companion import app
import companion_ai.web.system_routes as _sys_mod
from companion_ai.core import config as core_config


def test_local_model_runtime_get_contract():
    client = app.test_client()
    res = client.get('/api/local-model/runtime')

    assert res.status_code == 200
    data = res.get_json()
    assert 'local_models' in data
    assert 'readiness' in data
    assert data['local_models'].get('profile') in {'gaming', 'balanced', 'quality'}
    assert data['local_models'].get('runtime') in {'vllm', 'ollama', 'hybrid'}
    assert data['local_models'].get('chat_provider') in {'cloud_primary', 'local_primary'}


def test_local_model_runtime_post_updates_overrides(monkeypatch):
    client = app.test_client()
    monkeypatch.setattr(core_config, 'API_AUTH_TOKEN', 'secret-token')

    try:
        core_config.clear_local_model_runtime_overrides()
        res = client.post(
            '/api/local-model/runtime',
            headers={'X-API-TOKEN': 'secret-token'},
            json={
                'profile': 'quality',
                'runtime': 'ollama',
                'local_heavy_model': 'huihui_ai/qwen3.5-abliterated:27b',
                'chat_provider': 'local_primary',
            },
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data.get('status') == 'updated'
        assert data['local_models']['profile'] == 'quality'
        assert data['local_models']['runtime'] == 'ollama'
        assert data['local_models']['chat_provider'] == 'local_primary'
        assert data['local_models']['preferred_models']['local_heavy'] == 'huihui_ai/qwen3.5-abliterated:27b'

        clear_res = client.post(
            '/api/local-model/runtime',
            headers={'X-API-TOKEN': 'secret-token'},
            json={'clear_overrides': True},
        )
        assert clear_res.status_code == 200
        clear_data = clear_res.get_json()
        assert clear_data['local_models']['profile_override_active'] is False
        assert clear_data['local_models']['runtime_override_active'] is False
        assert clear_data['local_models']['chat_provider_override_active'] is False
    finally:
        core_config.clear_local_model_runtime_overrides()


def test_computer_use_activity_and_artifact_endpoints(monkeypatch, tmp_path):
    audit_path = tmp_path / 'computer_use_audit.jsonl'
    monkeypatch.setattr(_sys_mod.system_tools_module, 'COMPUTER_USE_AUDIT_PATH', str(audit_path))

    artifact_path = _sys_mod.system_tools_module.get_computer_use_artifact_path('abc123')
    rows = [
        {
            'attempt_id': 'abc123',
            'ts': '2026-04-10T00:00:00+00:00',
            'action': 'press',
            'text': 'Enter',
            'status': 'requested',
            'reason': '',
            'result_preview': '',
            'error': '',
            'artifact_path': artifact_path,
        },
        {
            'attempt_id': 'abc123',
            'ts': '2026-04-10T00:00:01+00:00',
            'action': 'press',
            'text': 'Enter',
            'status': 'completed',
            'reason': '',
            'result_preview': 'pressed:Enter',
            'error': '',
            'artifact_path': artifact_path,
        },
    ]
    with open(audit_path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')

    artifact_payload = {
        'attempt_id': 'abc123',
        'created_at': '2026-04-10T00:00:00+00:00',
        'updated_at': '2026-04-10T00:00:01+00:00',
        'action': 'press',
        'text': 'Enter',
        'events': [
            {'ts': '2026-04-10T00:00:00+00:00', 'status': 'requested', 'reason': '', 'result_preview': '', 'error': ''},
            {'ts': '2026-04-10T00:00:01+00:00', 'status': 'completed', 'reason': '', 'result_preview': 'pressed:Enter', 'error': ''},
        ],
    }
    import os

    os.makedirs(os.path.dirname(artifact_path), exist_ok=True)
    with open(artifact_path, 'w', encoding='utf-8') as f:
        json.dump(artifact_payload, f)

    client = app.test_client()
    activity_res = client.get('/api/computer-use/activity?limit=5')
    assert activity_res.status_code == 200
    activity_data = activity_res.get_json()
    assert activity_data.get('count') == 2
    assert activity_data['items'][0]['status'] == 'completed'

    artifact_res = client.get('/api/computer-use/artifacts/abc123')
    assert artifact_res.status_code == 200
    payload = artifact_res.get_json()
    assert payload.get('attempt_id') == 'abc123'
    assert isinstance(payload.get('events'), list)


def test_computer_use_diagnostics_endpoint(monkeypatch, tmp_path):
    audit_path = tmp_path / 'computer_use_audit.jsonl'
    monkeypatch.setattr(_sys_mod.system_tools_module, 'COMPUTER_USE_AUDIT_PATH', str(audit_path))
    monkeypatch.setattr(core_config, 'API_AUTH_TOKEN', 'secret-token')

    artifact_present = _sys_mod.system_tools_module.get_computer_use_artifact_path('diag-present')
    artifact_missing = _sys_mod.system_tools_module.get_computer_use_artifact_path('diag-missing')
    rows = [
        {
            'attempt_id': 'diag-present',
            'ts': '2026-04-11T00:00:00+00:00',
            'action': 'press',
            'text': 'Enter',
            'status': 'completed',
            'reason': '',
            'result_preview': 'pressed:Enter',
            'error': '',
            'artifact_path': artifact_present,
        },
        {
            'attempt_id': 'diag-missing',
            'ts': '2026-04-11T00:01:00+00:00',
            'action': 'launch',
            'text': 'gnome-terminal',
            'status': 'rejected',
            'reason': 'approval_denied',
            'result_preview': '',
            'error': '',
            'artifact_path': artifact_missing,
        },
        {
            'attempt_id': 'diag-requested',
            'ts': '2026-04-11T00:02:00+00:00',
            'action': 'type',
            'text': 'echo hi',
            'status': 'requested',
            'reason': '',
            'result_preview': '',
            'error': '',
            'artifact_path': '',
        },
    ]

    with open(audit_path, 'w', encoding='utf-8') as f:
        for row in rows:
            f.write(json.dumps(row) + '\n')

    import os

    os.makedirs(os.path.dirname(artifact_present), exist_ok=True)
    with open(artifact_present, 'w', encoding='utf-8') as f:
        json.dump({'attempt_id': 'diag-present', 'events': []}, f)

    monkeypatch.setattr(
        'companion_ai.tools.registry.get_pending_approvals',
        lambda: [
            {'id': 'a1', 'tool_name': 'use_computer'},
            {'id': 'a2', 'tool_name': 'remote_action_simulator'},
        ],
    )

    client = app.test_client()
    res = client.get('/api/computer-use/diagnostics?limit=25', headers={'X-API-TOKEN': 'secret-token'})

    assert res.status_code == 200
    data = res.get_json()
    assert 'policy' in data
    assert data.get('approvals', {}).get('pending_total') == 2
    assert data.get('approvals', {}).get('pending_computer_use') == 1
    assert data.get('audit', {}).get('rows_considered') == 3
    assert data.get('audit', {}).get('status_counts', {}).get('completed') == 1
    assert data.get('audit', {}).get('reason_counts', {}).get('approval_denied') == 1
    assert data.get('audit', {}).get('artifact_missing_count') == 1
