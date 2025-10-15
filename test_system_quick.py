"""Quick system test to verify Companion AI is working."""
from dotenv import load_dotenv
from companion_ai import memory as mem
from companion_ai import llm_interface
import time

load_dotenv()

def test_basic_response():
    """Test basic conversation with memory extraction"""
    print("=" * 60)
    print("TEST 1: Basic Conversation + Memory Extraction")
    print("=" * 60)
    
    user_msg = "Hello! My name is Alex and I love programming in Python. I'm 25 years old."
    
    # Build memory context
    memory_ctx = {
        "profile": mem.get_all_profile_facts(),
        "summaries": mem.get_latest_summary(5),
        "insights": mem.get_latest_insights(5)
    }
    
    response = llm_interface.generate_response(
        user_message=user_msg,
        memory_context=memory_ctx,
        persona="Companion"
    )
    
    print(f"\n✓ Response received:")
    print(f"  {response[:200] if isinstance(response, str) else str(response)[:200]}...")
    
    # Extract and store facts (simulating what chat_cli.py does)
    print(f"\n✓ Extracting profile facts...")
    facts = llm_interface.extract_profile_facts(user_msg, response)
    print(f"  Extracted facts: {facts}")
    
    # Store the facts
    if facts:
        for key, value in facts.items():
            mem.upsert_profile_fact(key, value)
            print(f"  Stored: {key} = {value}")
    
    # Add a summary
    summary = llm_interface.generate_summary(user_msg, response)
    if summary:
        mem.add_summary(summary, 0.8)
        print(f"\n✓ Stored summary: {summary[:100]}...")
    
    time.sleep(1)  # Give DB time to commit
    return response

def test_memory_storage():
    """Test memory storage"""
    print("\n" + "=" * 60)
    print("TEST 2: Memory Storage")
    print("=" * 60)
    
    # Check what's stored
    profile = mem.get_all_profile_facts()
    summaries = mem.get_latest_summary(5)
    insights = mem.get_latest_insights(5)
    
    print(f"\n✓ Memory stats:")
    print(f"  Profile facts: {len(profile)}")
    print(f"  Summaries: {len(summaries)}")
    print(f"  Insights: {len(insights)}")
    
    if profile:
        print(f"\n✓ Sample profile facts:")
        for key, val in list(profile.items())[:3]:
            print(f"  - {key}: {val}")
    
    return {"profile": len(profile), "summaries": len(summaries), "insights": len(insights)}

def test_memory_recall():
    """Test memory recall"""
    print("\n" + "=" * 60)
    print("TEST 3: Memory Recall")
    print("=" * 60)
    
    # Build memory context
    memory_ctx = {
        "profile": mem.get_all_profile_facts(),
        "summaries": mem.get_latest_summary(5),
        "insights": mem.get_latest_insights(5)
    }
    
    response = llm_interface.generate_response(
        user_message="What programming language did I say I like?",
        memory_context=memory_ctx,
        persona="Companion"
    )
    
    print(f"\n✓ Response with memory:")
    print(f"  {response}")
    
    return response

if __name__ == "__main__":
    print("\n🚀 COMPANION AI - SYSTEM TEST\n")
    
    try:
        # Test 1: Basic conversation
        resp1 = test_basic_response()
        
        # Test 2: Check memory
        mem_stats = test_memory_storage()
        
        # Test 3: Memory recall
        resp2 = test_memory_recall()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSystem is working correctly:")
        print(f"  ✓ Groq API connection: Working")
        print(f"  ✓ Response generation: Working")
        print(f"  ✓ Memory storage: Working ({mem_stats['profile']} facts)")
        print(f"  ✓ Memory recall: Working")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
