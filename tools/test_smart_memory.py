"""Test smart memory loading - only loads when relevant."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from companion_ai.core.context_builder import build_system_prompt_with_meta

def estimate_tokens(text: str) -> int:
    """Rough GPT token estimate: ~1 token per 4 chars"""
    return len(text) // 4

def test_message(msg: str, desc: str):
    result = build_system_prompt_with_meta(msg, "")
    prompt = result['system_prompt']
    tokens = estimate_tokens(prompt)
    has_memory = "loves_python_programming" in prompt or "python_is_great" in prompt
    
    print(f"\n{desc}")
    print(f"  Message: '{msg}'")
    print(f"  Tokens: {tokens}")
    print(f"  Memory loaded: {'YES ❌' if has_memory else 'NO ✅'}")
    print(f"  Mode: {result['mode']}")
    
    return tokens, has_memory

print("=" * 70)
print("SMART MEMORY LOADING TEST")
print("=" * 70)

tests = [
    ("hey", "Casual greeting", False),
    ("how are you?", "Simple question", False),
    ("what's up?", "Casual chat", False),
    ("what's my favorite programming language?", "Explicit memory query", True),
    ("do you remember what I told you?", "Explicit recall", True),
    ("tell me about Python", "Topic query", False),
    ("I'm working on a Python project", "Contextual mention", False),
    ("explain quantum computing", "Technical/informational", False),
    ("remember that time we talked about Python?", "Implicit - 'remember that'", True),
    ("like i said before, I prefer Python", "Implicit - 'like i said'", True),
    ("you know i love coding", "Implicit - 'you know i'", True),
    ("i told you my favorite language", "Implicit - 'i told you'", True),
    ("i love working with Python", "Context clue - 'i love'", True),
    ("i prefer Java over JavaScript", "Context clue - 'i prefer'", True),
]

results = []
for msg, desc, should_have_memory in tests:
    tokens, has_memory = test_message(msg, desc)
    correct = "✅" if (has_memory == should_have_memory) else "❌ WRONG"
    results.append((desc, tokens, has_memory, should_have_memory, correct))
    print(f"  Expected memory: {should_have_memory} {correct}")

print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

casual_no_memory = [r for r in results if not r[2]]
memory_queries = [r for r in results if r[2]]
wrong = [r for r in results if "❌" in r[4]]

avg_no_memory = sum(r[1] for r in casual_no_memory) / len(casual_no_memory) if casual_no_memory else 0
avg_with_memory = sum(r[1] for r in memory_queries) / len(memory_queries) if memory_queries else 0

print(f"\nCasual chat (no memory): ~{int(avg_no_memory)} tokens")
print(f"Memory queries: ~{int(avg_with_memory)} tokens")
print(f"Savings on casual chat: ~{int(avg_with_memory - avg_no_memory)} tokens per message")

print(f"\n✅ Accuracy: {len(results) - len(wrong)}/{len(results)} correct")
if wrong:
    print("\n❌ Incorrect detections:")
    for r in wrong:
        print(f"  - {r[0]}")
else:
    print("✅ All detections correct!")
