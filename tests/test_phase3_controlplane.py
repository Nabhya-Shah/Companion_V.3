import web_companion
from web_companion import app
import companion_ai.web.tools_routes as _tools_mod


def test_tasks_endpoint_returns_ui_shape(monkeypatch):
    monkeypatch.setattr(
        web_companion.job_manager_module,
        'get_tasks_for_ui',
        lambda: [{'id': 't1', 'description': 'Task One', 'state': 'running'}],
    )

    client = app.test_client()
    res = client.get('/api/tasks')
    data = res.get_json()

    assert res.status_code == 200
    assert data['count'] == 1
    assert data['tasks'][0]['id'] == 't1'


def test_schedule_create_requires_auth_when_configured(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(web_companion.job_manager_module, 'add_schedule', lambda *args, **kwargs: 's123')

    client = app.test_client()

    denied = client.post('/api/schedules', json={'description': 'Daily check', 'interval_minutes': 30})
    assert denied.status_code == 401

    ok = client.post(
        '/api/schedules',
        json={'description': 'Daily check', 'interval_minutes': 30, 'tool_name': 'start_background_task', 'tool_args': {}},
        headers={'X-API-TOKEN': 'secret'},
    )
    assert ok.status_code == 200
    assert ok.get_json()['id'] == 's123'


def test_schedule_toggle(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(web_companion.job_manager_module, 'set_schedule_enabled', lambda schedule_id, enabled: True)

    client = app.test_client()
    res = client.post('/api/schedules/s1/toggle', json={'enabled': False}, headers={'X-API-TOKEN': 'secret'})

    assert res.status_code == 200
    assert res.get_json()['enabled'] is False


def test_schedule_run_now_requires_auth_and_returns_job(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(
        web_companion.job_manager_module,
        'run_schedule_now',
        lambda _sid: {'ok': True, 'job_id': 'j123'},
    )

    client = app.test_client()
    denied = client.post('/api/schedules/s1/run')
    assert denied.status_code == 401

    ok = client.post('/api/schedules/s1/run', headers={'X-API-TOKEN': 'secret'})
    assert ok.status_code == 200
    assert ok.get_json()['job_id'] == 'j123'


def test_schedule_run_now_not_found(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(
        web_companion.job_manager_module,
        'run_schedule_now',
        lambda _sid: {'ok': False, 'error': 'Schedule not found'},
    )

    client = app.test_client()
    res = client.post('/api/schedules/missing/run', headers={'X-API-TOKEN': 'secret'})
    assert res.status_code == 404
    assert 'not found' in (res.get_json().get('error') or '').lower()


def test_schedule_run_now_policy_denied_returns_400(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(
        web_companion.job_manager_module,
        'run_schedule_now',
        lambda _sid: {'ok': False, 'error': 'Tool blocked by policy', 'reason': 'policy_denied'},
    )

    client = app.test_client()
    res = client.post('/api/schedules/s1/run', headers={'X-API-TOKEN': 'secret'})
    assert res.status_code == 400
    assert 'policy' in (res.get_json().get('error') or '').lower()


def test_schedule_update(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(web_companion.job_manager_module, 'update_schedule', lambda *args, **kwargs: True)

    client = app.test_client()
    res = client.put(
        '/api/schedules/s1',
        json={
            'description': 'Updated schedule',
            'cadence': '1h',
            'tool_name': 'start_background_task',
            'tool_args': {'x': 1},
        },
        headers={'X-API-TOKEN': 'secret'},
    )

    assert res.status_code == 200
    assert res.get_json()['updated'] is True


def test_schedule_delete(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(web_companion.job_manager_module, 'delete_schedule', lambda _sid: True)

    client = app.test_client()
    res = client.delete('/api/schedules/s1', headers={'X-API-TOKEN': 'secret'})

    assert res.status_code == 200
    assert res.get_json()['deleted'] is True


def test_schedule_create_supports_cadence_timezone_and_retry(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    captured = {}

    def fake_add_schedule(description, interval_minutes, tool_name, tool_args, **kwargs):
        captured['description'] = description
        captured['interval_minutes'] = interval_minutes
        captured['tool_name'] = tool_name
        captured['tool_args'] = tool_args
        captured['kwargs'] = kwargs
        return 's-cadence'

    monkeypatch.setattr(web_companion.job_manager_module, 'add_schedule', fake_add_schedule)

    client = app.test_client()
    res = client.post(
        '/api/schedules',
        json={
            'description': 'Nightly summary',
            'cadence': '2h',
            'tool_name': 'start_background_task',
            'tool_args': {'query': 'summary'},
            'timezone': 'UTC',
            'retry_limit': 3,
            'retry_backoff_minutes': 5,
        },
        headers={'X-API-TOKEN': 'secret'},
    )

    assert res.status_code == 200
    assert res.get_json()['id'] == 's-cadence'
    assert captured['interval_minutes'] == 120
    assert captured['kwargs']['timezone'] == 'UTC'
    assert captured['kwargs']['retry_limit'] == 3
    assert captured['kwargs']['retry_backoff_minutes'] == 5


def test_schedule_create_rejects_bad_cadence(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    client = app.test_client()
    res = client.post(
        '/api/schedules',
        json={
            'description': 'Bad cadence sample',
            'cadence': 'hourly',
            'tool_name': 'start_background_task',
            'tool_args': {},
        },
        headers={'X-API-TOKEN': 'secret'},
    )

    assert res.status_code == 400
    assert 'cadence' in (res.get_json().get('error') or '').lower()


def test_plugin_policy_get(monkeypatch):
    monkeypatch.setattr(
        _tools_mod,
        'get_plugin_policy_state',
        lambda: {'source': 'workspace', 'effective_enabled_plugins': ['core']},
    )

    client = app.test_client()
    res = client.get('/api/plugins/policy')

    assert res.status_code == 200
    assert res.get_json()['source'] == 'workspace'


def test_plugin_catalog_endpoint(monkeypatch):
    monkeypatch.setattr(
        _tools_mod,
        'get_plugin_catalog',
        lambda: [{'name': 'core', 'tool_count': 1, 'tools': [{'name': 'get_current_time'}]}],
    )

    client = app.test_client()
    res = client.get('/api/plugins/catalog')

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['plugins'][0]['name'] == 'core'


def test_plugin_policy_post_requires_auth(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(
        _tools_mod,
        'set_workspace_plugin_policy',
        lambda enabled: {'saved': True, 'effective_enabled_plugins': enabled},
    )

    client = app.test_client()
    denied = client.post('/api/plugins/policy', json={'enabled_plugins': ['core']})
    assert denied.status_code == 401

    ok = client.post(
        '/api/plugins/policy',
        json={'enabled_plugins': ['core']},
        headers={'X-API-TOKEN': 'secret'},
    )
    assert ok.status_code == 200
    assert ok.get_json()['saved'] is True


def test_plugin_policy_post_rejects_unknown_plugin(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    def fake_set_policy(_enabled):
        raise ValueError('Unknown plugin(s): bad_plugin')

    monkeypatch.setattr(_tools_mod, 'set_workspace_plugin_policy', fake_set_policy)

    client = app.test_client()
    res = client.post(
        '/api/plugins/policy',
        json={'enabled_plugins': ['bad_plugin']},
        headers={'X-API-TOKEN': 'secret'},
    )

    assert res.status_code == 400
    assert 'Unknown plugin' in (res.get_json().get('error') or '')


def test_api_context_reports_scoped_ids():
    client = app.test_client()
    res = client.get(
        '/api/context',
        headers={
            'X-Session-ID': 'sess-1',
            'X-Profile-ID': 'profile-1',
            'X-Workspace-ID': 'work-1',
        },
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['session_id'] == 'sess-1'
    assert payload['profile_id'] == 'profile-1'
    assert payload['workspace_id'] == 'work-1'
    assert '::w:work-1::p:profile-1::s:sess-1' in payload['mem0_user_id']


def test_api_context_switch_sets_cookies():
    client = app.test_client()
    res = client.post(
        '/api/context/switch',
        json={
            'workspace_id': 'work-2',
            'profile_id': 'profile-2',
            'session_id': 'sess-2',
            'migrate_legacy': False,
        },
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['switched'] is True
    assert payload['workspace_id'] == 'work-2'
    set_cookie = '\n'.join(res.headers.getlist('Set-Cookie'))
    assert 'companion_workspace_id=work-2' in set_cookie
    assert 'companion_profile_id=profile-2' in set_cookie


def test_events_diagnostics_shape():
    client = app.test_client()
    res = client.get('/api/events/diagnostics')

    assert res.status_code == 200
    payload = res.get_json()
    assert 'history_version' in payload
    assert 'sse_sequence' in payload
    assert 'counters' in payload


def test_remote_action_capabilities_endpoint():
    client = app.test_client()
    res = client.get('/api/remote-actions/capabilities')
    assert res.status_code == 200
    payload = res.get_json()
    assert isinstance(payload.get('capabilities'), list)


def test_remote_action_simulate_rejects_when_disabled(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'REMOTE_ACTIONS_ENABLED', False)
    client = app.test_client()
    res = client.post('/api/remote-actions/simulate', json={'capability': 'read_status', 'action': 'read'})
    assert res.status_code == 403
    payload = res.get_json()
    assert payload.get('reason') == 'disabled'


def test_remote_action_simulate_non_read_requires_token(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'REMOTE_ACTIONS_ENABLED', True)
    monkeypatch.setattr(web_companion.core_config, 'REMOTE_ACTION_CAPABILITY_ALLOWLIST', '*')
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    client = app.test_client()

    denied = client.post(
        '/api/remote-actions/simulate',
        json={'capability': 'notify', 'action': 'execute'},
        headers={'X-API-TOKEN': 'secret'},
    )
    assert denied.status_code == 400
    assert denied.get_json().get('reason') == 'approval_required'

    approval = client.post(
        '/api/remote-actions/approve',
        json={'capability': 'notify', 'action': 'execute'},
        headers={'X-API-TOKEN': 'secret'},
    )
    assert approval.status_code == 200
    token = approval.get_json().get('approval_token')
    assert token

    ok = client.post(
        '/api/remote-actions/simulate',
        json={'capability': 'notify', 'action': 'execute', 'approval_token': token},
        headers={'X-API-TOKEN': 'secret'},
    )
    assert ok.status_code == 200
    payload = ok.get_json()
    assert payload.get('status') == 'completed'


def test_workflow_skills_endpoint_exposes_enabled_flag(monkeypatch):
    class _Manager:
        def reload_workflows(self):
            return True

        def list_skills(self):
            return [{'id': 'wf', 'enabled': True, 'can_run': True}]

    monkeypatch.setattr('companion_ai.web.workflow_routes.get_manager', lambda: _Manager())

    client = app.test_client()
    res = client.get('/api/workflows/skills')
    assert res.status_code == 200
    assert res.get_json()['skills'][0]['id'] == 'wf'
