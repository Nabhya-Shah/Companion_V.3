# test_all_systems.py
import os
import sys
import pytest
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

# Initialize environment
load_dotenv()

# Import components
from companion_ai.llm_interface import generate_response, generate_groq_response
from companion_ai.memory import init_db, upsert_profile_fact, add_summary, add_insight, get_all_profile_facts

@pytest.mark.skipif(not os.getenv("GROQ_API_KEY"), reason="No GROQ_API_KEY set")
def test_groq():
    print("\n=== TESTING GROQ ===")
    response = generate_groq_response("Hello, this is a Groq test!")
    assert isinstance(response, str) and len(response) > 0



def test_memory():
    print("\n=== TESTING MEMORY ===")
    # Add test data
    upsert_profile_fact("test_key", "test_value")
    add_summary("This is a test summary")
    add_insight("This is a test insight")
    
    # Retrieve data
    print("Profile Facts:", get_all_profile_facts())
    
@pytest.mark.skip(reason="Azure TTS integration test skipped by default")
def test_tts():
    pass

def test_full_flow():
    print("\n=== TESTING FULL FLOW ===")
    memory_context = {
        "profile": get_all_profile_facts(),
        "summaries": [],
        "insights": []
    }
    response = generate_response("Hello, this is a full system test!", memory_context)
    assert isinstance(response, str) and len(response) > 0

if __name__ == "__main__":
    # Initialize database
    init_db()
    
    # Run tests
    test_groq()
    test_memory()
    test_tts()
    test_full_flow()
    
    print("\nAll tests completed!")