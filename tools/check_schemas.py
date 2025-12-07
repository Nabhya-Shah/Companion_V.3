import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from companion_ai.tools import get_function_schemas

print(f"Schemas Found: {len(get_function_schemas())}")
for s in get_function_schemas():
    print(f"- {s['function']['name']}")
