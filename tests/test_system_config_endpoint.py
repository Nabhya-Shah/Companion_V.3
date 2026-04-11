from web_companion import app


def test_config_endpoint_includes_retrieval_connector_capabilities():
    client = app.test_client()
    res = client.get('/api/config')
    assert res.status_code == 200

    data = res.get_json()
    assert 'retrieval_connectors' in data
    assert 'local_models' in data

    local_models = data['local_models']
    assert 'runtime' in local_models
    assert 'profile' in local_models
    assert 'allow_cloud_fallback' in local_models
    assert 'chat_provider' in local_models
    assert 'chat_provider_choices' in local_models
    assert 'min_vram_gb' in local_models
    assert 'local_heavy_model_choices' in local_models

    rc = data['retrieval_connectors']
    assert 'enabled' in rc
    assert 'allowlist' in rc
    assert 'allowlist_enabled' in rc
    assert 'source_allowlist' in rc
    assert 'timeout_ms' in rc
    assert 'max_results' in rc
    assert 'local_primary' in rc
    assert 'capabilities' in rc
