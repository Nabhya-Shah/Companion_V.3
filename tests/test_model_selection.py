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
