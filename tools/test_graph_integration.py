#!/usr/bin/env python3
"""
End-to-End Knowledge Graph Integration Test

Tests the full flow:
1. Conversations → Entity Extraction
2. Entity/Relationship Detection
3. Graph Construction
4. Memory Insight Queries
5. Graph Persistence
"""
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion_ai.memory_graph import (
    get_knowledge_graph,
    add_conversation_to_graph,
    search_graph,
    get_graph_stats
)

print("=" * 80)
print("🧪 KNOWLEDGE GRAPH END-TO-END INTEGRATION TEST")
print("=" * 80)

# Test 1: Initial State
print("\n1️⃣ Checking initial graph state...")
kg = get_knowledge_graph()
initial_stats = get_graph_stats()
print(f"   Starting with: {initial_stats['total_entities']} entities, {initial_stats['total_relationships']} relationships")

# Test 2: Add realistic conversations
print("\n2️⃣ Adding realistic conversations...")
conversations = [
    (
        "I'm working on a machine learning project using Python and PyTorch",
        "That sounds exciting! PyTorch is great for ML. What kind of project is it?"
    ),
    (
        "It's a computer vision project for my university. I'm using it to detect objects in images.",
        "Computer vision is fascinating! Are you using pre-trained models or training from scratch?"
    ),
    (
        "I'm fine-tuning a pre-trained ResNet model. It's working pretty well so far.",
        "Nice! ResNet is a solid choice for transfer learning. How's the accuracy?"
    ),
    (
        "I'm also interested in natural language processing. I want to learn about transformers.",
        "Transformers are the foundation of modern NLP! Have you tried Hugging Face's library?"
    ),
    (
        "I live in Seattle and work at Microsoft as a software engineer.",
        "Seattle's a great tech hub! What team are you on at Microsoft?"
    )
]

for i, (user_msg, ai_msg) in enumerate(conversations, 1):
    print(f"   Processing conversation {i}/{len(conversations)}...")
    try:
        add_conversation_to_graph(user_msg, ai_msg)
        time.sleep(0.5)  # Small delay to avoid rate limits
    except Exception as e:
        print(f"   ⚠️ Warning: {e}")

# Test 3: Check updated graph
print("\n3️⃣ Checking updated graph state...")
updated_stats = get_graph_stats()
print(f"   Now have: {updated_stats['total_entities']} entities, {updated_stats['total_relationships']} relationships")
print(f"   Change: +{updated_stats['total_entities'] - initial_stats['total_entities']} entities, +{updated_stats['total_relationships'] - initial_stats['total_relationships']} relationships")

if updated_stats['entity_types']:
    print(f"   Entity types: {updated_stats['entity_types']}")

# Test 4: Search Queries
print("\n4️⃣ Testing search queries...")

test_queries = [
    ("Python", "GRAPH_COMPLETION"),
    ("machine learning", "KEYWORD"),
    ("Seattle", "GRAPH_COMPLETION"),
    ("", "IMPORTANT")
]

for query, mode in test_queries:
    display_query = query if query else "(most important)"
    print(f"\n   Query: '{display_query}' (mode: {mode})")
    results = search_graph(query, mode=mode, limit=5)
    if results:
        print(f"   Found {len(results)} results:")
        for j, result in enumerate(results[:3], 1):
            rtype = result.get('type', 'unknown')
            if rtype == 'entity':
                name = result.get('name', 'N/A')
                etype = result.get('entity_type', 'unknown')
                print(f"      {j}. Entity: {name} ({etype})")
            elif rtype == 'relationship':
                source = result.get('source', 'N/A')
                target = result.get('target', 'N/A')
                rel_type = result.get('relation_type', 'related_to')
                print(f"      {j}. Relationship: {source} -{rel_type}→ {target}")
            elif rtype in ['incoming', 'outgoing']:
                source = result.get('source', 'N/A')
                target = result.get('target', 'N/A')
                rel_type = result.get('relation_type', 'related_to')
                print(f"      {j}. {rtype.capitalize()}: {source} -{rel_type}→ {target}")
    else:
        print(f"   No results found")

# Test 5: Most Connected Entities
print("\n5️⃣ Most connected entities:")
if updated_stats['most_connected']:
    for entity in updated_stats['most_connected'][:5]:
        print(f"   - {entity['name']}: {entity['connections']} connections")
else:
    print("   (No connected entities)")

# Test 6: Path Finding
print("\n6️⃣ Testing path finding...")
kg = get_knowledge_graph()
# Get first two entities to test path finding
nodes = list(kg.graph.nodes())
if len(nodes) >= 2:
    source, target = nodes[0], nodes[1]
    print(f"   Finding path: {source} → {target}")
    path = kg.find_path(source, target, max_depth=5)
    if path:
        print(f"   Path found: {' → '.join(path)}")
    else:
        print(f"   No path found")
else:
    print("   Not enough entities for path finding")

# Test 7: Verify Persistence
print("\n7️⃣ Testing graph persistence...")
import pickle
from companion_ai.memory_graph import GRAPH_PATH

if os.path.exists(GRAPH_PATH):
    file_size = os.path.getsize(GRAPH_PATH) / 1024  # KB
    print(f"   ✅ Graph saved to: {GRAPH_PATH}")
    print(f"   File size: {file_size:.2f} KB")
    
    # Reload to verify
    with open(GRAPH_PATH, 'rb') as f:
        data = pickle.load(f)
        saved_nodes = data['graph'].number_of_nodes()
        saved_edges = data['graph'].number_of_edges()
        print(f"   Verified: {saved_nodes} nodes, {saved_edges} edges in saved file")
else:
    print(f"   ⚠️ Graph file not found at {GRAPH_PATH}")

# Final Summary
print("\n" + "=" * 80)
print("📊 FINAL SUMMARY")
print("=" * 80)
final_stats = get_graph_stats()
print(f"Total Entities: {final_stats['total_entities']}")
print(f"Total Relationships: {final_stats['total_relationships']}")
print(f"Average Connections: {final_stats['avg_connections']:.2f}")
print(f"Entity Types: {final_stats['entity_types']}")
print("\n✅ Knowledge Graph Integration Test Complete!")
print("=" * 80)
