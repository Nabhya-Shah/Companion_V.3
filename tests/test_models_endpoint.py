import json
from companion_ai.core import config as core_config
from web_companion import app

def test_models_endpoint_structure():
    """Test that the /api/models endpoint returns the simplified model architecture."""
    client = app.test_client()
    res = client.get('/api/models')
    assert res.status_code == 200
    data = res.get_json()
    
    # Check new simplified structure
    assert 'models' in data, "Missing 'models' key"
    models = data['models']
    assert models.get('PRIMARY_MODEL') == core_config.PRIMARY_MODEL
    assert models.get('TOOLS_MODEL') == core_config.TOOLS_MODEL
    assert models.get('VISION_MODEL') == core_config.VISION_MODEL
    assert models.get('COMPOUND_MODEL') == core_config.COMPOUND_MODEL
    
    # Check flags
    assert 'flags' in data
    flags = data['flags']
    assert 'auto_tools' in flags
    assert 'knowledge_graph' in flags
    assert 'vision' in flags
    
    # Check legacy compatibility fields exist
    assert 'roles' in data
    assert 'ensemble' in data
    assert data['ensemble']['enabled'] == False  # Ensemble is removed
