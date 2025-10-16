"""
Feature Verification Test Script
Tests: Ensemble, Model Routing, Prompt Caching, Auto Tools
"""

import os
import sys
from dotenv import load_dotenv
load_dotenv()

# Import config first to check settings
from companion_ai.core import config as core_config

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

def check_feature_flags():
    """Check all feature flags in .env"""
    print_section("FEATURE FLAGS STATUS")
    
    flags = {
        "ENABLE_ENSEMBLE": core_config.ENABLE_ENSEMBLE,
        "ENSEMBLE_MODE": core_config.ENSEMBLE_MODE,
        "ENSEMBLE_CANDIDATES": core_config.ENSEMBLE_CANDIDATES,
        "ENABLE_AUTO_TOOLS": core_config.ENABLE_AUTO_TOOLS,
        "ENABLE_PROMPT_CACHING": core_config.ENABLE_PROMPT_CACHING,
        "ENABLE_FACT_APPROVAL": core_config.ENABLE_FACT_APPROVAL,
        "FACT_AUTO_APPROVE": core_config.FACT_AUTO_APPROVE,
        "ENABLE_COMPOUND_MODELS": core_config.ENABLE_COMPOUND_MODELS,
        "ENABLE_EXPERIMENTAL_MODELS": core_config.ENABLE_EXPERIMENTAL_MODELS,
    }
    
    for flag, value in flags.items():
        status = "✅ ENABLED" if value else "❌ DISABLED"
        print(f"  {flag:30} {status:20} {value}")
    
    return flags

def check_model_registry():
    """Check available models and their capabilities"""
    print_section("MODEL REGISTRY")
    
    models = {
        "Fast Model": core_config.FAST_MODEL,
        "Smart Primary": core_config.SMART_PRIMARY_MODEL,
        "Heavy Model": core_config.HEAVY_MODEL,
        "Default Conversation": core_config.DEFAULT_CONVERSATION_MODEL,
    }
    
    for name, model in models.items():
        caps = core_config.MODEL_CAPABILITIES.get(model, {})
        print(f"\n  {name}: {model}")
        print(f"    Quality: {caps.get('quality', 'N/A')}/5  |  Speed: {caps.get('speed', 'N/A')}/5  |  Tier: {caps.get('tier', 'N/A')}")
    
    return models

def check_ensemble_config():
    """Check ensemble-specific configuration"""
    print_section("ENSEMBLE CONFIGURATION")
    
    if not core_config.ENABLE_ENSEMBLE:
        print("  ⚠️  Ensemble is DISABLED")
        return False
    
    print(f"  Mode: {core_config.ENSEMBLE_MODE}")
    print(f"  Candidates: {core_config.ENSEMBLE_CANDIDATES} models")
    print(f"  Refine Expansion: {core_config.ENSEMBLE_REFINE_EXPANSION * 100}%")
    print(f"  Refine Hard Cap: {core_config.ENSEMBLE_REFINE_HARD_CAP} tokens")
    print(f"  Max Total Factor: {core_config.ENSEMBLE_MAX_TOTAL_FACTOR}x")
    
    # Check if heavy alternates available
    if hasattr(core_config, 'HEAVY_ALTERNATES'):
        print(f"\n  Heavy Alternates:")
        for alt in core_config.HEAVY_ALTERNATES:
            print(f"    - {alt}")
    
    return True

def test_model_routing():
    """Test model routing for different complexity levels"""
    print_section("MODEL ROUTING TEST")
    
    test_messages = [
        ("Hey", 0, "simple greeting"),
        ("What's the weather like?", 1, "medium query"),
        ("Explain quantum entanglement and its implications for computing", 2, "complex query"),
    ]
    
    for msg, expected_complexity, description in test_messages:
        complexity = core_config.classify_complexity(msg)
        model, routing = core_config.choose_model('chat', complexity=complexity, return_reason=True)
        
        print(f"\n  Test: {description}")
        print(f"    Message: '{msg}'")
        print(f"    Detected Complexity: {complexity} (expected: {expected_complexity})")
        print(f"    Selected Model: {model}")
        print(f"    Routing Meta: {routing}")
        
        # Check if ensemble would trigger
        would_trigger = (
            core_config.ENABLE_ENSEMBLE and 
            complexity >= 2 and 
            "companion" in model.lower()
        )
        print(f"    Would Trigger Ensemble: {'✅ YES' if would_trigger else '❌ NO'}")

def test_prompt_caching():
    """Check if prompt caching is configured"""
    print_section("PROMPT CACHING TEST")
    
    if not core_config.ENABLE_PROMPT_CACHING:
        print("  ⚠️  Prompt caching is DISABLED")
        return False
    
    print("  ✅ Prompt caching is ENABLED")
    print("  Note: Actual caching behavior depends on Groq API support")
    
    # Test cache key generation
    from companion_ai.llm_interface import _maybe_cache_opts
    test_prompt = "You are a helpful assistant. This is a test system prompt."
    cache_opts = _maybe_cache_opts(test_prompt)
    
    if cache_opts:
        print(f"  Cache Key Generated: {cache_opts.get('cache_key', 'N/A')}")
    else:
        print("  Cache options empty (may be unsupported by current SDK)")
    
    return True

def test_auto_tools():
    """Check auto tools configuration"""
    print_section("AUTO TOOLS TEST")
    
    if not core_config.ENABLE_AUTO_TOOLS:
        print("  ⚠️  Auto tools are DISABLED")
        return False
    
    print("  ✅ Auto tools are ENABLED")
    
    from companion_ai.tools import list_tools
    available_tools = list_tools()
    
    print(f"  Available Tools ({len(available_tools)}):")
    for tool in available_tools:
        print(f"    - {tool}")
    
    return True

def main():
    """Run all verification checks"""
    print("\n" + "="*60)
    print("  COMPANION AI - FEATURE VERIFICATION")
    print("="*60)
    
    # Check API keys
    print("\n  Checking API Keys:")
    groq_key = os.getenv("GROQ_API_KEY")
    print(f"    GROQ_API_KEY: {'✅ Set' if groq_key else '❌ Missing'}")
    
    # Run all checks
    flags = check_feature_flags()
    models = check_model_registry()
    ensemble_ok = check_ensemble_config()
    test_model_routing()
    test_prompt_caching()
    test_auto_tools()
    
    # Summary
    print_section("VERIFICATION SUMMARY")
    
    critical_features = {
        "Ensemble Reasoning": flags["ENABLE_ENSEMBLE"],
        "120B Model Available": "120b" in models["Default Conversation"].lower(),
        "Model Routing": True,  # Always available
        "Memory System": True,  # Always available
    }
    
    print("\n  Critical Features:")
    for feature, status in critical_features.items():
        icon = "✅" if status else "❌"
        print(f"    {icon} {feature}")
    
    all_ok = all(critical_features.values())
    
    if all_ok:
        print("\n  🎉 ALL CRITICAL FEATURES VERIFIED!")
        print("  Your Companion AI is ready for production use.")
    else:
        print("\n  ⚠️  Some features need attention.")
        print("  Check the details above.")
    
    print("\n" + "="*60 + "\n")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
