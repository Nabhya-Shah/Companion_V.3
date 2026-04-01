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


def test_memory_review_requires_auth(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(_mem_mod.state, 'enforce_feature_permission', lambda *_: None)

    client = app.test_client()
    denied = client.get('/api/memory/review')
    assert denied.status_code == 401


def test_memory_review_returns_filtered_rows(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(_mem_mod.state, 'enforce_feature_permission', lambda *_: None)
    monkeypatch.setattr(_mem_mod.state, '_get_active_session_state', lambda: ('s1', 'p1', 'scope-1', None, None))

    monkeypatch.setattr(
        _mem_mod,
        '_build_memory_review_rows',
        lambda mem0_user_id, limit=80: [
            {
                'key': 'm-conflict',
                'value': 'User hates coriander',
                'confidence': 0.91,
                'confidence_label': 'high',
                'reaffirmations': 2,
                'source': 'mem0',
                'contradiction_state': 'conflict',
                'dedup_candidate_count': 0,
                'dedup_candidates': [],
            },
            {
                'key': 'm-low',
                'value': 'User likes very hot coffee',
                'confidence': 0.41,
                'confidence_label': 'low',
                'reaffirmations': 0,
                'source': 'mem0',
                'contradiction_state': 'none',
                'dedup_candidate_count': 0,
                'dedup_candidates': [],
            },
            {
                'key': 'm-normal',
                'value': 'User owns a bike',
                'confidence': 0.80,
                'confidence_label': 'high',
                'reaffirmations': 1,
                'source': 'mem0',
                'contradiction_state': 'none',
                'dedup_candidate_count': 0,
                'dedup_candidates': [],
            },
        ],
    )

    client = app.test_client()
    res = client.get('/api/memory/review?limit=10', headers={'X-API-TOKEN': 'secret'})

    assert res.status_code == 200
    payload = res.get_json()
    keys = [item['key'] for item in payload['items']]
    assert keys == ['m-conflict', 'm-low']
    assert payload['summary']['conflict_count'] == 1
    assert payload['summary']['low_confidence_count'] == 1


def test_memory_review_update_reaffirm_and_mark_duplicate(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    monkeypatch.setattr(_mem_mod.state, 'enforce_feature_permission', lambda *_: None)
    monkeypatch.setattr(_mem_mod.state, '_get_active_session_state', lambda: ('s1', 'p1', 'scope-1', None, None))
    monkeypatch.setattr(
        _mem_mod,
        '_build_memory_review_rows',
        lambda mem0_user_id, limit=250: [
            {
                'key': 'm1',
                'value': 'User prefers tea',
                'confidence': 0.6,
                'reaffirmations': 3,
                'source': 'mem0',
                'contradiction_state': 'conflict',
                'metadata': {'origin': 'test'},
            }
        ],
    )

    captured = {}

    def fake_upsert(**kwargs):
        captured.update(kwargs)
        return True

    monkeypatch.setattr(_mem_mod, 'upsert_memory_quality_entry', fake_upsert)

    client = app.test_client()

    reaffirm = client.post(
        '/api/memory/review/m1',
        json={'action': 'reaffirm', 'confidence_step': 0.1},
        headers={'X-API-TOKEN': 'secret'},
    )
    assert reaffirm.status_code == 200
    reaffirm_payload = reaffirm.get_json()['updated']
    assert round(reaffirm_payload['confidence'], 2) == 0.70
    assert reaffirm_payload['reaffirmations'] == 4
    assert reaffirm_payload['contradiction_state'] == 'pending'

    mark_dup = client.post(
        '/api/memory/review/m1',
        json={'action': 'mark_duplicate', 'duplicate_of': 'm2'},
        headers={'X-API-TOKEN': 'secret'},
    )
    assert mark_dup.status_code == 200
    mark_payload = mark_dup.get_json()['updated']
    assert mark_payload['contradiction_state'] == 'resolved'
    assert mark_payload['metadata']['duplicate_of'] == 'm2'
    assert captured['memory_id'] == 'm1'
    assert captured['user_scope'] == 'scope-1'


def test_memory_migration_readiness_reports_migrate_now(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')

    queue_rows = [
        {'request_id': f'r{i}', 'created_at': '2025-01-01T00:00:00+00:00'}
        for i in range(510)
    ]
    write_rows = ([{'status': 'accepted_committed'} for _ in range(14)] +
                  [{'status': 'accepted_queued'} for _ in range(4)] +
                  [{'status': 'failed'} for _ in range(2)])

    monkeypatch.setattr(_mem_mod.write_queue, 'list_queued_writes', lambda limit=5000: queue_rows)
    monkeypatch.setattr(_mem_mod, 'list_memory_write_status', lambda limit=500: write_rows)
    monkeypatch.setattr(
        _mem_mod,
        '_load_throughput_baseline',
        lambda: {'results': {'latency_ms': {'p95_ms': 125.0}, 'throughput_rps': 18.2}},
    )

    client = app.test_client()
    res = client.get('/api/memory/migration-readiness', headers={'X-API-TOKEN': 'secret'})

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['level'] == 'migrate_now'
    assert 'queue_backlog_critical' in payload['reasons']
    assert payload['metrics']['queue_depth'] == 510
    assert payload['metrics']['failure_rate'] == 0.1
