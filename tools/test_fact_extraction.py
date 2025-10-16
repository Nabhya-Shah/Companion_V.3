#!/usr/bin/env python3
"""Test the improved fact extraction with fresh database"""

from companion_ai.llm_interface import extract_profile_facts

print("="*80)
print("🧪 TESTING IMPROVED FACT EXTRACTION")
print("="*80)

test_cases = [
    # Should ACCEPT - explicit facts
    ("My name is Alex and I'm 25 years old", ["name", "age"]),
    ("I work as a software engineer at Google", ["occupation"]),
    ("I love Python programming", ["favorite_language", "interest"]),
    ("My favorite game is Minecraft", ["favorite_game"]),
    ("I have a golden retriever named Max", ["pet"]),
    ("I'm learning Japanese", ["learning"]),
    
    # Should REJECT - no facts or inferences
    ("Hey, what's up?", []),
    ("Yeah I'm chill", []),
    ("Nothing much", []),
    ("Lol nice", []),
    ("I'm feeling tired today", []),  # Mood, not a fact
]

print("\n✅ Testing GOOD cases (should extract facts):")
print("-"*80)

for i, (message, expected_keys) in enumerate(test_cases[:6], 1):
    print(f"\n{i}. Input: '{message}'")
    facts = extract_profile_facts(message, "AI response here")
    
    if facts:
        print(f"   ✓ Extracted: {facts}")
        extracted_keys = list(facts.keys())
        # Check if any expected key pattern appears
        has_expected = any(
            any(exp in key for exp in expected_keys) 
            for key in extracted_keys
        )
        if has_expected or not expected_keys:
            print(f"   ✓ PASS")
        else:
            print(f"   ✗ FAIL - expected keys containing: {expected_keys}")
    else:
        if expected_keys:
            print(f"   ✗ FAIL - expected to extract keys containing: {expected_keys}")
        else:
            print(f"   ✓ PASS - correctly returned empty")

print("\n\n❌ Testing BAD cases (should reject/return empty):")
print("-"*80)

for i, (message, expected_keys) in enumerate(test_cases[6:], 1):
    print(f"\n{i}. Input: '{message}'")
    facts = extract_profile_facts(message, "AI response here")
    
    if facts:
        print(f"   ✗ FAIL - extracted {facts} but should be empty!")
    else:
        print(f"   ✓ PASS - correctly rejected (no facts)")

print("\n" + "="*80)
print("🎯 TEST COMPLETE!")
print("="*80)
print("\nIf all tests passed, the fact extraction is working correctly.")
print("You can now use the companion and it will only store explicit facts!")
