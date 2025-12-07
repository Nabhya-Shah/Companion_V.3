
from companion_ai.memory_v2 import get_memory, search_memories, get_all_memories
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

print("--- All Memories ---")
all_mems = get_all_memories(user_id="default")
for m in all_mems:
    print(f"- {m.get('memory', m.get('text'))} (ID: {m.get('id')})")

print("\n--- Search 'color' ---")
results = search_memories("What is my favorite color?", user_id="default", limit=5)
for r in results:
    print(f"- {r.get('memory', r.get('text'))} (Score: {r.get('score')})")

print("\n--- Search 'sister' ---")
results = search_memories("Do I have any siblings?", user_id="default", limit=5)
for r in results:
    print(f"- {r.get('memory', r.get('text'))} (Score: {r.get('score')})")
