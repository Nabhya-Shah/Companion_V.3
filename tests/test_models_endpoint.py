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
    assert models.get('MEMORY_PROCESSING_MODEL') == core_config.MEMORY_PROCESSING_MODEL
    assert models.get('MEMORY_FAST_MODEL') == core_config.MEMORY_FAST_MODEL
    assert models.get('EMBEDDING_MODEL') == core_config.EMBEDDING_MODEL
    # COMPOUND_MODEL removed in V5
    
    # Check flags
    assert 'flags' in data
    flags = data['flags']
    assert 'auto_tools' in flags
    assert 'knowledge_graph' in flags
    assert 'vision' in flags
    assert 'memory_extract_prefer_fast' in flags
    
    # Check legacy compatibility fields exist
    assert 'roles' in data
    assert data['roles']['MEMORY_PROCESSING_MODEL'] == core_config.MEMORY_PROCESSING_MODEL
    assert 'ensemble' in data
    assert data['ensemble']['enabled'] == False  # Ensemble is removed
