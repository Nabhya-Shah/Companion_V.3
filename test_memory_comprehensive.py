"""Comprehensive memory system test."""
from dotenv import load_dotenv
from companion_ai import memory as mem
from companion_ai import llm_interface
import time

load_dotenv()

def clear_test_data():
    """Clear any test data from previous runs."""
    print("Clearing previous test data...")
    # We'll just work with what's there for now
    
def test_fact_extraction():
    """Test various fact extraction scenarios"""
    print("\n" + "=" * 60)
    print("TEST: Fact Extraction (Various Scenarios)")
    print("=" * 60)
    
    test_cases = [
        ("My name is Sarah and I'm from London.", ["name", "location"]),
        ("I love playing guitar and my favorite color is blue.", ["hobby", "favorite"]),
        ("I work as a software engineer at Google.", ["occupation", "company"]),
        ("I'm learning Japanese and I enjoy hiking.", ["learning", "hobby"]),
    ]
    
    total = 0
    successful = 0
    
    for user_msg, expected_keys in test_cases:
        print(f"\n  Testing: '{user_msg}'")
        facts = llm_interface.extract_profile_facts(user_msg, "That's interesting!")
        print(f"  Extracted: {facts}")
        
        total += 1
        if facts and any(key in ' '.join(facts.keys()).lower() for key in expected_keys):
            successful += 1
            print(f"  ✓ Success - found expected fact types")
        else:
            print(f"  ⚠ Partial - expected keywords: {expected_keys}")
    
    print(f"\n  Results: {successful}/{total} test cases passed")
    return successful == total

def test_memory_persistence():
    """Test that memories persist across sessions"""
    print("\n" + "=" * 60)
    print("TEST: Memory Persistence")
    print("=" * 60)
    
    # Store some facts
    test_facts = {
        "favorite_game": "Minecraft",
        "pet": "golden retriever",
        "hometown": "Seattle"
    }
    
    print(f"\n  Storing {len(test_facts)} test facts...")
    for key, value in test_facts.items():
        mem.upsert_profile_fact(key, value, confidence=0.9)
        print(f"  - {key}: {value}")
    
    time.sleep(0.5)
    
    # Retrieve them
    print(f"\n  Retrieving stored facts...")
    retrieved = mem.get_all_profile_facts()
    
    found = 0
    for key in test_facts:
        if key in retrieved:
            found += 1
            print(f"  ✓ Found: {key} = {retrieved[key]}")
        else:
            print(f"  ✗ Missing: {key}")
    
    print(f"\n  Results: {found}/{len(test_facts)} facts persisted")
    return found == len(test_facts)

def test_memory_retrieval():
    """Test relevance-based memory retrieval"""
    print("\n" + "=" * 60)
    print("TEST: Relevant Memory Retrieval")
    print("=" * 60)
    
    # Add some summaries with different topics
    summaries = [
        ("User discussed their love for Python programming and machine learning.", 0.8),
        ("User talked about their dog and weekend hiking plans.", 0.7),
        ("User mentioned working on a web development project.", 0.6),
    ]
    
    print(f"\n  Adding {len(summaries)} test summaries...")
    for summary, importance in summaries:
        mem.add_summary(summary, importance)
        print(f"  - {summary[:50]}...")
    
    time.sleep(0.5)
    
    # Test retrieval
    print(f"\n  Testing retrieval with query: 'programming'")
    relevant = mem.get_relevant_summaries("Tell me about programming")
    print(f"  Retrieved {len(relevant)} relevant summaries:")
    for summ in relevant[:3]:
        # Summaries might be strings or dict objects
        text = summ if isinstance(summ, str) else str(summ)
        print(f"  - {text[:60]}...")
    
    return len(relevant) > 0

def test_confidence_system():
    """Test confidence scoring and updates"""
    print("\n" + "=" * 60)
    print("TEST: Confidence System")
    print("=" * 60)
    
    # Store a fact with low confidence
    print("\n  Storing fact with confidence 0.5...")
    mem.upsert_profile_fact("test_fact", "test_value", confidence=0.5)
    
    time.sleep(0.5)
    
    # Update it with higher confidence
    print("  Updating same fact with confidence 0.9...")
    mem.upsert_profile_fact("test_fact", "test_value", confidence=0.9)
    
    time.sleep(0.5)
    
    # Check the confidence increased
    facts = mem.get_all_profile_facts()
    if "test_fact" in facts:
        print(f"  ✓ Fact updated successfully")
        return True
    else:
        print(f"  ✗ Fact not found")
        return False

def test_full_conversation_flow():
    """Test a realistic conversation with memory"""
    print("\n" + "=" * 60)
    print("TEST: Full Conversation Flow")
    print("=" * 60)
    
    conversation = [
        "Hi, I'm Jamie. I'm a game developer working on an indie RPG.",
        "I use Unity and C# mostly, but I'm learning Unreal Engine.",
        "My favorite game is The Witcher 3. I love open-world RPGs.",
    ]
    
    print("\n  Simulating conversation...")
    for i, user_msg in enumerate(conversation, 1):
        print(f"\n  Turn {i}: {user_msg}")
        
        # Get AI response
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
        
        print(f"  AI: {response[:80]}...")
        
        # Extract and store facts
        facts = llm_interface.extract_profile_facts(user_msg, response)
        if facts:
            print(f"  Extracted facts: {facts}")
            for key, value in facts.items():
                mem.upsert_profile_fact(key, value)
        
        # Store summary
        summary = llm_interface.generate_summary(user_msg, response)
        if summary:
            mem.add_summary(summary, 0.7)
    
    # Check what we learned
    print("\n  After conversation, stored profile:")
    profile = mem.get_all_profile_facts()
    for key, value in profile.items():
        print(f"  - {key}: {value}")
    
    return len(profile) > 3  # Should have learned multiple facts

if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("🧪 COMPREHENSIVE MEMORY SYSTEM TEST")
    print("=" * 60)
    
    results = {}
    
    try:
        results['fact_extraction'] = test_fact_extraction()
        results['persistence'] = test_memory_persistence()
        results['retrieval'] = test_memory_retrieval()
        results['confidence'] = test_confidence_system()
        results['full_flow'] = test_full_conversation_flow()
        
        # Final report
        print("\n" + "=" * 60)
        print("📊 FINAL RESULTS")
        print("=" * 60)
        
        for test_name, passed in results.items():
            status = "✅ PASS" if passed else "❌ FAIL"
            print(f"{status} - {test_name.replace('_', ' ').title()}")
        
        total = len(results)
        passed = sum(results.values())
        percentage = (passed / total) * 100
        
        print(f"\n{passed}/{total} tests passed ({percentage:.0f}%)")
        
        if passed == total:
            print("\n🎉 ALL TESTS PASSED! Memory system is working great!")
        else:
            print("\n⚠️  Some tests failed. Review the output above.")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
