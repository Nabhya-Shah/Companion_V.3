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
    
    # Memory/summary/facts -> PRIMARY_MODEL
    assert config.choose_model('summary') == config.PRIMARY_MODEL
    assert config.choose_model('facts') == config.PRIMARY_MODEL
    assert config.choose_model('insight') == config.PRIMARY_MODEL
    assert config.choose_model('memory') == config.PRIMARY_MODEL


def test_model_roles_mapping():
    """Test MODEL_ROLES dictionary has expected entries."""
    assert config.MODEL_ROLES['chat'] == config.PRIMARY_MODEL
    assert config.MODEL_ROLES['tools'] == config.TOOLS_MODEL
    assert config.MODEL_ROLES['vision'] == config.VISION_MODEL
    assert config.MODEL_ROLES['compound'] == "DISABLED"  # V5: Compound removed
