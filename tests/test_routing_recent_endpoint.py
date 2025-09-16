from web_companion import app

def test_routing_recent_endpoint():
    client = app.test_client()
    r = client.get('/api/routing/recent?n=5')
    assert r.status_code == 200
    data = r.get_json()
    assert 'count' in data and 'items' in data
    assert isinstance(data['items'], list)
    # If items exist, validate minimal schema
    if data['items']:
        item = data['items'][0]
        assert 'ts' in item
        assert 'routing' in item
        assert isinstance(item['routing'], dict)
