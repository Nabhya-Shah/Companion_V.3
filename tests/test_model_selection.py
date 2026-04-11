"""Tests for simplified 4-model architecture."""
import pytest
from companion_ai.core import config


def test_classify_complexity_thresholds():
    """Test complexity classification (0=casual, 1=normal, 2=complex)."""
    simple = "hi how are you"
    assert config.classify_complexity(simple) == 0

    medium = "Can you explain how this function works? It has some parts I'm not fully getting?"
    c_med = config.classify_complexity(medium)
    assert c_med >= 1

    analytical = "Please analyze and compare architectures and explain step-by-step how we could optimize latency in this system?"
    c_high = config.classify_complexity(analytical)
    assert c_high == 2  # Max is now 2, not 3


def test_choose_model_simplified_routing():
    """Test simplified model routing - all chat goes to PRIMARY_MODEL."""
    # All chat tasks should use PRIMARY_MODEL regardless of complexity
    m1 = config.choose_model('chat', complexity=0)
    m2 = config.choose_model('chat', complexity=2)
    assert m1 == config.PRIMARY_MODEL
    assert m2 == config.PRIMARY_MODEL  # No escalation in simplified architecture


def test_choose_model_task_routing():
    """Test that different tasks route to correct models."""
    # Tools task -> TOOLS_MODEL
    assert config.choose_model('tools') == config.TOOLS_MODEL
    
    # Vision task -> VISION_MODEL
    assert config.choose_model('vision') == config.VISION_MODEL
    
    # Memory/summary/facts -> dedicated memory-processing model
    assert config.choose_model('summary') == config.MEMORY_PROCESSING_MODEL
    assert config.choose_model('facts') == config.MEMORY_PROCESSING_MODEL
    assert config.choose_model('insight') == config.MEMORY_PROCESSING_MODEL
    assert config.choose_model('memory') == config.MEMORY_PROCESSING_MODEL
    assert config.choose_model('memory_processing') == config.MEMORY_PROCESSING_MODEL


def test_memory_processing_model_roles_and_helpers():
    """Memory model helpers should expose explicit memory + embedding roles."""
    model, is_local, provider = config.get_memory_processing_model()
    assert model == config.MEMORY_PROCESSING_MODEL
    assert is_local is False
    assert provider == 'groq'

    monkeypatch_value = config.MEMORY_EXTRACT_PREFER_FAST
    config.MEMORY_EXTRACT_PREFER_FAST = True
    fast_model, fast_local, fast_provider = config.get_memory_processing_model(prefer_fast=True)
    try:
        assert fast_model == config.MEMORY_FAST_MODEL
        assert fast_local is False
        assert fast_provider == 'groq'
    finally:
        config.MEMORY_EXTRACT_PREFER_FAST = monkeypatch_value

    embed_model, embed_provider = config.get_embedding_model()
    assert embed_model == config.EMBEDDING_MODEL
    assert embed_provider == config.EMBEDDING_PROVIDER


def test_memory_processing_model_respects_fast_toggle(monkeypatch):
    monkeypatch.setattr(config, 'MEMORY_EXTRACT_PREFER_FAST', False)

    model, is_local, provider = config.get_memory_processing_model(prefer_fast=True)

    assert model == config.MEMORY_PROCESSING_MODEL
    assert is_local is False
    assert provider == 'groq'


def test_model_roles_mapping():
    """Test MODEL_ROLES dictionary has expected entries."""
    assert config.MODEL_ROLES['chat'] == config.PRIMARY_MODEL
    assert config.MODEL_ROLES['tools'] == config.TOOLS_MODEL
    assert config.MODEL_ROLES['vision'] == config.VISION_MODEL
    assert config.MODEL_ROLES['memory_processing'] == config.MEMORY_PROCESSING_MODEL
    assert config.MODEL_ROLES['embeddings'] == config.EMBEDDING_MODEL
    assert config.MODEL_ROLES['compound'] == "DISABLED"  # V5: Compound removed


def test_local_model_runtime_config_contract():
    cfg = config.get_local_model_runtime_config()

    assert cfg['runtime'] in {'vllm', 'ollama', 'hybrid'}
    assert cfg['profile'] in {'gaming', 'balanced', 'quality'}
    assert isinstance(cfg['allow_cloud_fallback'], bool)
    assert isinstance(cfg['min_vram_gb'], int)
    assert 'preferred_models' in cfg
    assert 'local_heavy' in cfg['preferred_models']
    assert 'embedding' in cfg['preferred_models']
    assert isinstance(cfg.get('local_heavy_model_choices'), list)
    assert 'huihui_ai/qwen3.5-abliterated:27b' in cfg.get('local_heavy_model_choices', [])
    assert 'huihui_ai/gemma-4-abliterated:31b' in cfg.get('local_heavy_model_choices', [])
    assert cfg.get('chat_provider') in {'cloud_primary', 'local_primary'}
    assert cfg.get('chat_provider_configured') in {'cloud_primary', 'local_primary'}
    assert set(cfg.get('chat_provider_choices', [])) == {'cloud_primary', 'local_primary'}


def test_effective_memory_provider_auto_uses_profile(monkeypatch):
    monkeypatch.setattr(config, 'MEMORY_PROCESSING_PROVIDER', 'auto')

    monkeypatch.setattr(config, 'LOCAL_MODEL_PROFILE', 'quality')
    assert config.get_effective_memory_processing_provider() == 'local'

    monkeypatch.setattr(config, 'LOCAL_MODEL_PROFILE', 'gaming')
    assert config.get_effective_memory_processing_provider() == 'groq'


def test_local_runtime_overrides_apply_and_clear(monkeypatch):
    monkeypatch.setattr(config, '_RUNTIME_LOCAL_MODEL_PROFILE_OVERRIDE', None)
    monkeypatch.setattr(config, '_RUNTIME_LOCAL_MODEL_RUNTIME_OVERRIDE', None)
    monkeypatch.setattr(config, '_RUNTIME_LOCAL_HEAVY_MODEL_OVERRIDE', None)
    monkeypatch.setattr(config, '_RUNTIME_LOCAL_CHAT_PROVIDER_OVERRIDE', None)

    cfg = config.set_local_model_runtime_overrides(
        profile='quality',
        runtime='ollama',
        local_heavy_model='huihui_ai/qwen3.5-abliterated:27b',
        chat_provider='local_primary',
    )
    assert cfg['profile'] == 'quality'
    assert cfg['runtime'] == 'ollama'
    assert cfg['profile_override_active'] is True
    assert cfg['runtime_override_active'] is True
    assert cfg['local_heavy_model_override_active'] is True
    assert cfg['chat_provider_override_active'] is True
    assert cfg['chat_provider'] == 'local_primary'
    assert cfg['preferred_models']['local_heavy'] == 'huihui_ai/qwen3.5-abliterated:27b'

    cfg_cleared = config.clear_local_model_runtime_overrides()
    assert cfg_cleared['profile_override_active'] is False
    assert cfg_cleared['runtime_override_active'] is False
    assert cfg_cleared['local_heavy_model_override_active'] is False
    assert cfg_cleared['chat_provider_override_active'] is False


def test_profile_aware_local_heavy_model(monkeypatch):
    monkeypatch.setattr(config, 'LOCAL_HEAVY_MODEL_GAMING', 'qwen-gaming')
    monkeypatch.setattr(config, 'LOCAL_HEAVY_MODEL_BALANCED', 'qwen-balanced')
    monkeypatch.setattr(config, 'LOCAL_HEAVY_MODEL_QUALITY', 'qwen-quality')
    monkeypatch.setattr(config, '_RUNTIME_LOCAL_MODEL_PROFILE_OVERRIDE', 'quality')

    model, is_local = config.get_tool_model('use_computer')
    assert is_local is True
    assert model == 'qwen-quality'
