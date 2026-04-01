from web_companion import app
import web_companion
import companion_ai.web.tools_routes as _tools_mod


def test_browser_diagnostics_requires_auth_when_configured(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(
        _tools_mod,
        'core_config',
        web_companion.core_config,
    )
    monkeypatch.setattr(
        'companion_ai.agents.browser.get_runtime_diagnostics',
        lambda: {
            'status': 'ready',
            'playwright_available': True,
            'chrome_found': True,
            'profile_writable': True,
            'reasons': [],
        },
    )

    client = app.test_client()

    denied = client.get('/api/browser/diagnostics')
    assert denied.status_code == 401

    ok = client.get('/api/browser/diagnostics', headers={'X-API-TOKEN': 'secret'})
    assert ok.status_code == 200
    payload = ok.get_json()
    assert payload['status'] == 'ready'
    assert 'trace_id' in payload


def test_browser_diagnostics_shape_local_default():
    client = app.test_client()
    res = client.get('/api/browser/diagnostics')

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['status'] in {'ready', 'degraded'}
    assert 'playwright_available' in payload
    assert 'chrome_found' in payload
    assert 'profile_writable' in payload
    assert 'background_loop_running' in payload
    assert 'reasons' in payload
