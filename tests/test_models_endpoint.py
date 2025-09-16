import json
from companion_ai.core import config as core_config
from web_companion import app

def test_models_endpoint_structure():
    client = app.test_client()
    res = client.get('/api/models')
    assert res.status_code == 200
    data = res.get_json()
    for key in ['roles','routing','ensemble','capabilities','available','flags']:
        assert key in data, f"Missing key {key}"
    roles = data['roles']
    assert roles.get('SMART_PRIMARY_MODEL')
    assert roles.get('HEAVY_MODEL')
    ens = data['ensemble']
    for k in ['enabled','mode','candidates']:
        assert k in ens
    caps = data['capabilities']
    assert isinstance(caps, dict) and caps
    assert core_config.DEFAULT_CONVERSATION_MODEL in data['available']
    flags = data['flags']
    for f in ['auto_tools','prompt_caching','fact_approval']:
        assert f in flags
