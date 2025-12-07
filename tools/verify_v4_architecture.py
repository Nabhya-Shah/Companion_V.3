import sys
import os
import time

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from companion_ai.core import config
from companion_ai import llm_interface

def test_planner_configuration():
    print("\n--- Testing Planner Configuration ---")
    tool_model = config.get_tool_executor()
    print(f"Tool Executor Model: {tool_model}")
    
    if "120b" in tool_model.lower():
        print("[PASS] Planner is correctly set to 120B")
    else:
        print(f"[FAIL] Planner is NOT 120B (Current: {tool_model})")

def test_fact_extraction():
    print("\n--- Testing Structured Fact Extraction ---")
    user_msg = "My name is V4Verifier and I love architecture testing."
    ai_msg = "Hello V4Verifier! It's great to meet someone who enjoys testing."
    
    print(f"Extraction Input: '{user_msg}'")
    
    start_time = time.time()
    facts = llm_interface.extract_profile_facts(user_msg, ai_msg)
    duration = time.time() - start_time
    
    print(f"Extracted Facts: {facts}")
    print(f"Duration: {duration:.2f}s")
    
    if facts and isinstance(facts, dict) and 'name' in facts:
        print("[PASS] Fact extraction working (returned dict)")
        if config.ENABLE_STRUCTURED_FACTS:
             print("[PASS] Structured Outputs ENABLED in config")
        else:
             print("[FAIL] Structured Outputs DISABLED in config")
    else:
        print("[FAIL] Fact extraction failed/empty")

def test_vision_routing():
    print("\n--- Testing Vision Routing Logic ---")
    vision_model = config.choose_model('vision')
    print(f"Vision Model: {vision_model}")
    
    if "maverick" in vision_model.lower() and "17b" in vision_model.lower():
        print("[PASS] Vision routing correctly maps to Maverick")
    else:
        print(f"[FAIL] Vision routing incorrect (Current: {vision_model})")

if __name__ == "__main__":
    print(f"Testing V4 Architecture Configuration...")
    print(f"ENABLE_GROQ_BUILTINS: {config.ENABLE_GROQ_BUILTINS}")
    print(f"ENABLE_COMPOUND: {config.ENABLE_COMPOUND}")
    
    test_planner_configuration()
    test_fact_extraction()
    test_vision_routing()
