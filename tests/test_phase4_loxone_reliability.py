import web_companion
from web_companion import app


def test_loxone_health_connected(monkeypatch):
    async def fake_health():
        return {
            'success': True,
            'configured': True,
            'connected': True,
            'message': 'Connected to Loxone Miniserver',
        }

    import companion_ai.integrations.loxone as loxone_module
    monkeypatch.setattr(loxone_module, 'get_health_status', fake_health)

    client = app.test_client()
    res = client.get('/api/loxone/health')

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['success'] is True
    assert payload['connected'] is True


def test_loxone_health_not_configured(monkeypatch):
    async def fake_health():
        return {
            'success': False,
            'configured': False,
            'connected': False,
            'message': 'Loxone not configured',
        }

    import companion_ai.integrations.loxone as loxone_module
    monkeypatch.setattr(loxone_module, 'get_health_status', fake_health)

    client = app.test_client()
    res = client.get('/api/loxone/health')

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['configured'] is False
    assert 'not configured' in payload['message'].lower()


def test_loxone_light_all_on_route(monkeypatch):
    async def fake_turn_on(room=None):
        assert room == 'all'
        return {'success': True, 'message': 'Turned on all lights'}

    import companion_ai.integrations.loxone as loxone_module
    monkeypatch.setattr(loxone_module, 'turn_on_lights', fake_turn_on)

    client = app.test_client()
    res = client.post('/api/loxone/light/on', json={'room': 'all'})

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['success'] is True
    assert 'all lights' in payload['message'].lower()


def test_loxone_light_all_off_route(monkeypatch):
    async def fake_turn_off(room=None):
        assert room == 'all'
        return {'success': True, 'message': 'Turned off all lights'}

    import companion_ai.integrations.loxone as loxone_module
    monkeypatch.setattr(loxone_module, 'turn_off_lights', fake_turn_off)

    client = app.test_client()
    res = client.post('/api/loxone/light/off', json={'room': 'all'})

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['success'] is True
    assert 'all lights' in payload['message'].lower()
