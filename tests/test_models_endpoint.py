import json
import types
from companion_ai.core import config as core_config
from web_companion import app

def test_models_endpoint_structure():
    client = app.test_client()
    res = client.get('/api/models')
    assert res.status_code == 200
    data = res.get_json()
    # Basic top-level keys
    for key in ['roles','routing','ensemble','capabilities','available','flags']:
        assert key in data, f"Missing key {key} in /api/models response"
    # Roles sanity
    roles = data['roles']
    assert 'SMART_PRIMARY_MODEL' in roles and roles['SMART_PRIMARY_MODEL']
    assert 'HEAVY_MODEL' in roles and roles['HEAVY_MODEL']
    # Ensemble section fields
    ens = data['ensemble']
    assert 'enabled' in ens and 'mode' in ens and 'candidates' in ens
    # Capabilities is a dict subset of configured models
    caps = data['capabilities']
    assert isinstance(caps, dict) and len(caps) >= 1
    # Available list should include at least fast model
    assert core_config.DEFAULT_CONVERSATION_MODEL in data['available']
    # Flags presence
    flags = data['flags']
    for f in ['auto_tools','prompt_caching','fact_approval']:
        assert f in flags

a