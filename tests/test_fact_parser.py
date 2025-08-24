from companion_ai.llm_interface import extract_profile_facts

# We simulate malformed JSON by monkeypatching generate_groq_response if needed.
# For Phase 0 we just assert function returns dict or empty dict gracefully when parsing fails.

def test_extract_profile_facts_handles_bad_json(monkeypatch):
    def fake_response(prompt: str, model: str = "llama-3.1-8b-instant"):
        return "{not valid json"  # malformed
    monkeypatch.setattr('companion_ai.llm_interface.generate_groq_response', fake_response)
    facts = extract_profile_facts("I am John", "Nice to meet you John")
    assert isinstance(facts, dict)
