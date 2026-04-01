import web_companion
from web_companion import app
import companion_ai.web.memory_routes as _mem_mod
import companion_ai.web.state as _web_state

def test_memory_provenance_endpoint():
    client = app.test_client()
    r = client.get('/api/memory?detailed=1')
    assert r.status_code == 200
    data = r.get_json()
    assert 'profile' in data
    assert 'summaries' in data
    assert 'insights' in data
    # Detailed list present
    assert 'profile_detailed' in data
    assert isinstance(data['profile_detailed'], list)
    # If any facts exist verify shape
    if data['profile_detailed']:
        fact = data['profile_detailed'][0]
        for k in ('key','value','confidence','confidence_label','reaffirmations'):
            assert k in fact
        assert fact['confidence_label'] in ('high','medium','low')


def test_memory_provenance_detail_mem0(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'USE_MEM0', True)
    monkeypatch.setattr(_web_state, '_maybe_migrate_legacy_scope', lambda *_: None)
    monkeypatch.setattr(
        web_companion.mem0,
        'get_all_memories',
        lambda user_id=None: [
            {'id': 'm1', 'memory': 'User likes tea', 'metadata': {'frequency': 3, 'origin': 'chat'}}
        ],
    )
    monkeypatch.setattr(_mem_mod, 'bulk_sync_memory_quality_from_mem0', lambda memories, user_scope: 1)
    monkeypatch.setattr(
        _mem_mod,
        'get_memory_quality_map',
        lambda user_scope: {
            'm1': {
                'confidence': 0.91,
                'confidence_label': 'high',
                'reaffirmations': 4,
                'contradiction_state': 'none',
                'provenance_source': 'mem0',
                'metadata': {'origin': 'chat', 'source_turn': 12},
            }
        },
    )

    client = app.test_client()
    r = client.get('/api/memory/provenance/m1?session_id=sA&profile_id=home')

    assert r.status_code == 200
    data = r.get_json()
    assert data['key'] == 'm1'
    assert data['value'] == 'User likes tea'
    assert data['provenance']['source'] == 'mem0'
    assert data['provenance']['confidence_label'] == 'high'
    assert data['provenance']['reaffirmations'] == 4
    assert isinstance(data.get('trace_id'), str)


def test_memory_provenance_detail_sqlite_fallback(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'USE_MEM0', False)
    monkeypatch.setattr(
        _mem_mod,
        'list_profile_facts_detailed',
        lambda: [
            {
                'key': 'favorite_food',
                'value': 'sushi',
                'confidence': 0.76,
                'confidence_label': 'medium',
                'reaffirmations': 2,
                'source': 'user_profile',
                'last_updated': '2026-03-31T20:00:00',
                'first_seen_ts': '2026-03-28T10:00:00',
                'last_seen_ts': '2026-03-31T20:00:00',
                'evidence': 'User said this directly',
            }
        ],
    )

    client = app.test_client()
    r = client.get('/api/memory/provenance/favorite_food?session_id=sA&profile_id=home')

    assert r.status_code == 200
    data = r.get_json()
    assert data['key'] == 'favorite_food'
    assert data['value'] == 'sushi'
    assert data['provenance']['source'] == 'user_profile'
    assert data['provenance']['metadata']['evidence'] == 'User said this directly'


def test_memory_provenance_detail_not_found(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'USE_MEM0', False)
    monkeypatch.setattr(_mem_mod, 'list_profile_facts_detailed', lambda: [])

    client = app.test_client()
    r = client.get('/api/memory/provenance/does-not-exist?session_id=sA&profile_id=home')

    assert r.status_code == 404
    data = r.get_json()
    assert data['error'] == 'Memory fact not found'
    assert data['key'] == 'does-not-exist'
