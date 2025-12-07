import sys
import os
import time
import logging

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Configure logging to see the "Merged" messages
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY_SEMANTIC")

from companion_ai import memory_graph

def verify_semantic_matching():
    print("\n--- Testing Semantic Entity Matching ---")
    
    kg = memory_graph.get_knowledge_graph()
    
    if not kg.semantic_model:
        print("[SKIP] Semantic matching NOT available (sentence-transformers missing?)")
        return

    # 1. Add Baseline Entity
    print(" Adding baseline entity: 'JavaScript'...")
    e1 = memory_graph.Entity(
        name="JavaScript",
        entity_type="concept",
        attributes={"type": "language"},
        first_mentioned="", last_mentioned=""
    )
    kg.add_entity(e1)
    
    # 2. Add Variant Entity (Synonym/Abbreviation)
    print(" Adding variant entity: 'JS' (should merge)...")
    e2 = memory_graph.Entity(
        name="JS",
        entity_type="unknown", # Different type to test semantic cross-type matching
        attributes={"used_for": "web"},
        first_mentioned="", last_mentioned=""
    )
    kg.add_entity(e2)
    
    # 3. Check Status
    # expecting "JS" specifically to NOT be a node if it merged into "JavaScript" 
    # OR if the returning function returns the *matched* entity, then add_entity logic updates the matched one.
    
    # Let's inspect the graph
    has_js = kg.graph.has_node("JS")
    has_javascript = kg.graph.has_node("JavaScript")
    
    print(f" Graph has 'JavaScript': {has_javascript}")
    print(f" Graph has 'JS': {has_js}")
    
    if has_javascript and not has_js:
        print("[PASS] 'JS' was merged into 'JavaScript' (Node 'JS' does not exist)")
        
        # Check aliases
        node_data = kg.graph.nodes["JavaScript"]
        aliases = node_data.get("aliases", [])
        print(f" JavaScript aliases: {aliases}")
        if "JS" in aliases:
             print("[PASS] 'JS' found in aliases")
        else:
             print("[WARN] 'JS' merged but not in aliases (check logic)")
             
    elif has_javascript and has_js:
        # It didn't merge
        print("[FAIL] 'JS' was created as a separate node. (Similarity threshold too high?)")
        
        # Calculate similarity manually to debug
        emb1 = kg.semantic_model.encode("JavaScript", convert_to_tensor=True)
        emb2 = kg.semantic_model.encode("JS", convert_to_tensor=True)
        from torch.nn.functional import cosine_similarity
        sim = cosine_similarity(emb1.unsqueeze(0), emb2.unsqueeze(0)).item()
        print(f" Calculated Similarity: {sim:.4f}")
        
    else:
        print("[FAIL] Unexpected graph state.")
        
    # Cleanup
    # memory_graph.clear_graph() # Optional, maybe keep for manual inspection

if __name__ == "__main__":
    verify_semantic_matching()
