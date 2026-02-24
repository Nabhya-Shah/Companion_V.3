import web_companion
from web_companion import app
import companion_ai.web.memory_routes as _mem_mod


def test_pending_facts_bulk_requires_auth(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    client = app.test_client()
    denied = client.post('/api/pending_facts/bulk', json={'action': 'approve', 'ids': [1, 2]})
    assert denied.status_code == 401


def test_pending_facts_bulk_approve(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(_mem_mod, 'approve_profile_fact', lambda pid: pid in {1, 2})

    client = app.test_client()
    res = client.post(
        '/api/pending_facts/bulk',
        json={'action': 'approve', 'ids': [1, 2, 999]},
        headers={'X-API-TOKEN': 'secret'},
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['processed'] == 2
    assert 999 in payload['failed']


def test_pending_facts_bulk_reject(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(_mem_mod, 'reject_profile_fact', lambda pid: pid == 5)

    client = app.test_client()
    res = client.post(
        '/api/pending_facts/bulk',
        json={'action': 'reject', 'ids': [5, 6]},
        headers={'X-API-TOKEN': 'secret'},
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['processed'] == 1
    assert 6 in payload['failed']
