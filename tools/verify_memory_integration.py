import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY_MEMORY")

from companion_ai import memory_v2
from companion_ai import memory_graph
from companion_ai.core import config

def verify_mem0_initialization():
    print("\n--- 1. Testing Mem0 Initialization ---")
    try:
        mem = memory_v2.get_memory()
        print(f"[PASS] Mem0 initialized successfully")
        
        # Check if Qdrant path is correct
        stats = memory_v2.get_memory_stats("verify_test_user")
        print(f"Stats check: {stats}")
        return True
    except Exception as e:
        print(f"[FAIL] Mem0 init failed: {e}")
        return False

def verify_knowledge_graph_initialization():
    print("\n--- 2. Testing Knowledge Graph Initialization ---")
    try:
        kg = memory_graph.get_knowledge_graph()
        stats = kg.get_stats()
        print(f"[PASS] Knowledge Graph initialized. Stats: {stats}")
        return True
    except Exception as e:
        print(f"[FAIL] KG init failed: {e}")
        return False

def verify_data_flow():
    print("\n--- 3. Testing Data Flow (Add -> Retrieve) ---")
    user_id = "verify_test_user_" + str(int(time.time()))
    
    # 1. Add to Mem0
    print(" Adding fact to Mem0...")
    test_msg = "My favorite futuristic fruit is the Quantum Apple."
    msgs = [{"role": "user", "content": test_msg}]
    result = memory_v2.add_memory(msgs, user_id=user_id)
    print(f" Mem0 Add Result: {result}")
    
    # 2. Add to KG
    print(" Adding relationship to KG...")
    rel = memory_graph.Relationship(
        source="Quantum Apple",
        target="Future",
        relation_type="belongs_to",
        context="User mentioned favorite futuristic fruit",
        timestamp="2025-12-07T12:00:00Z"
    )
    kg_success = memory_graph.get_knowledge_graph().add_relationship(rel)
    print(f" KG Add Result: {kg_success}")

    # Wait a moment for consistency if needed (local vector DB might need flush, though Mem0 is usually sync)
    time.sleep(1)

    # 3. Retrieve from Mem0
    print(" searching Mem0...")
    mem_results = memory_v2.search_memories("Quantum Apple", user_id=user_id)
    print(f" Mem0 Search Results: {mem_results}")
    
    mem_found = any("Quantum Apple" in m.get('memory', '') for m in mem_results)
    
    # 4. Retrieve from KG
    print(" searching KG...")
    kg_results = memory_graph.search_graph("Quantum Apple", mode="GRAPH_COMPLETION")
    print(f" KG Search Results: {kg_results}")
    
    kg_found = any(r.get('name') == "Quantum Apple" for r in kg_results) or \
               any(r.get('source') == "Quantum Apple" for r in kg_results)

    if mem_found:
        print("[PASS] Mem0 successfully stored and retrieved fact.")
    else:
        print("[FAIL] Mem0 failed to retrieve fact.")

    if kg_found:
        print("[PASS] KG successfully stored and retrieved entity.")
    else:
        print("[FAIL] KG failed to retrieve entity.")

    # Cleanup
    memory_v2.clear_all_memories(user_id=user_id)
    # KG cleanup isn't as simple, but test data is minimal
    
    return mem_found and kg_found

if __name__ == "__main__":
    print("Starting Memory Verification...")
    if verify_mem0_initialization() and verify_knowledge_graph_initialization():
        verify_data_flow()
