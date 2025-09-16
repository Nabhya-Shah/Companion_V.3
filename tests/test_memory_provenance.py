from web_companion import app

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
