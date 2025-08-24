import pytest
from companion_ai.core import config


def test_classify_complexity_thresholds():
    simple = "hi how are you"
    assert config.classify_complexity(simple) == 0

    medium = "Can you explain how this function works? It has some parts I'm not fully getting?"
    c_med = config.classify_complexity(medium)
    assert c_med >= 1

    analytical = "Please analyze and compare architectures and explain step-by-step how we could optimize latency in this system?"  # has reasoning keywords
    c_high = config.classify_complexity(analytical)
    assert c_high >= 2

    long_reasoning = " ".join(["analysis" for _ in range(170)])
    assert config.classify_complexity(long_reasoning) == 3


def test_choose_model_chat_reasoning_escalation():
    # For low complexity chat should not pick reasoning model
    m1 = config.choose_model('chat', complexity=0)
    m2 = config.choose_model('chat', complexity=2)
    # When complexity escalates, either reasoning role or same primary allowed
    assert m2 in {config.MODEL_ROLES.get('reasoning'), config.MODEL_ROLES.get('chat.primary')}
    # Ensure escalation can change model (if reasoning defined and differs)
    if config.MODEL_ROLES.get('reasoning') and config.MODEL_ROLES.get('reasoning') != config.MODEL_ROLES.get('chat.primary'):
        assert m2 == config.MODEL_ROLES.get('reasoning')


def test_choose_model_memory_paths():
    high_summary = config.choose_model('summary', importance=0.9)
    low_summary = config.choose_model('summary', importance=0.1)
    assert high_summary in {config.MODEL_ROLES.get('memory.summary_high'), config.MODEL_ROLES.get('chat.primary')}
    assert low_summary in {config.MODEL_ROLES.get('memory.summary_standard'), config.MODEL_ROLES.get('chat.fast_fallback')}

    facts_model = config.choose_model('facts')
    assert facts_model in {config.MODEL_ROLES.get('memory.fact_extract'), config.MODEL_ROLES.get('chat.fast_fallback')}

    insight_high = config.choose_model('insight', importance=0.8)
    insight_low = config.choose_model('insight', importance=0.2)
    assert insight_high in {config.MODEL_ROLES.get('memory.summary_high'), config.MODEL_ROLES.get('chat.primary')}
    assert insight_low in {config.MODEL_ROLES.get('memory.summary_standard'), config.MODEL_ROLES.get('chat.fast_fallback')}
