#!/usr/bin/env python3
"""
Test the Knowledge Graph Memory System
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion_ai.memory_graph import (
    get_knowledge_graph,
    Entity,
    Relationship,
    search_graph,
    get_graph_stats,
    add_conversation_to_graph
)

print("=" * 60)
print("Knowledge Graph Memory System Test")
print("=" * 60)

# Test 1: Initialize graph
print("\n1. Initializing knowledge graph...")
kg = get_knowledge_graph()
print(f"✅ Graph loaded: {kg.graph.number_of_nodes()} nodes, {kg.graph.number_of_edges()} edges")

# Test 2: Add entities
print("\n2. Adding test entities...")
entities = [
    Entity("Python", "concept", {"category": "programming_language", "level": "expert"}, "", ""),
    Entity("Machine Learning", "concept", {"category": "technology", "interest": "high"}, "", ""),
    Entity("Companion AI", "project", {"type": "personal_project", "status": "active"}, "", ""),
]

for entity in entities:
    kg.add_entity(entity)

print(f"✅ Added {len(entities)} entities")

# Test 3: Add relationships
print("\n3. Adding test relationships...")
relationships = [
    Relationship("User", "Python", "knows", "User is learning Python", ""),
    Relationship("User", "Companion AI", "created", "User created Companion AI project", ""),
    Relationship("Companion AI", "Python", "uses", "Companion AI is built with Python", ""),
    Relationship("Companion AI", "Machine Learning", "implements", "Companion AI uses ML for memory", ""),
]

for rel in relationships:
    kg.add_relationship(rel)

print(f"✅ Added {len(relationships)} relationships")

# Test 4: Search graph
print("\n4. Testing GRAPH_COMPLETION search for 'Python'...")
results = search_graph("Python", mode="GRAPH_COMPLETION")
print(f"Found {len(results)} results:")
for i, result in enumerate(results[:5], 1):
    print(f"  {i}. {result.get('type', 'unknown')}: {result.get('name', result.get('source', 'N/A'))}")

# Test 5: Get entity relationships
print("\n5. Testing entity relationships...")
user_rels = kg.get_entity_relationships("User")
print(f"User has {len(user_rels)} relationships:")
for rel in user_rels[:5]:
    print(f"  - {rel['source']} -{rel['relation_type']}→ {rel['target']}")

# Test 6: Find path
print("\n6. Testing path finding (User → Machine Learning)...")
path = kg.find_path("User", "Machine Learning")
if path:
    print(f"Path found: {' → '.join(path)}")
else:
    print("No path found")

# Test 7: Get statistics
print("\n7. Knowledge Graph Statistics:")
stats = get_graph_stats()
print(f"  Total Entities: {stats['total_entities']}")
print(f"  Total Relationships: {stats['total_relationships']}")
print(f"  Avg Connections: {stats['avg_connections']:.2f}")
print(f"  Entity Types: {stats['entity_types']}")

# Test 8: Test conversation extraction (if env vars set)
print("\n8. Testing conversation extraction...")
try:
    add_conversation_to_graph(
        "I really enjoy working on Python projects, especially machine learning ones.",
        "That's awesome! Python is great for ML. Are you working on anything specific?"
    )
    print("✅ Conversation added to graph")
except Exception as e:
    print(f"⚠️ Conversation extraction failed (requires API key): {e}")

# Final stats
print("\n" + "=" * 60)
print("Final Graph Statistics:")
final_stats = get_graph_stats()
print(f"  Total Entities: {final_stats['total_entities']}")
print(f"  Total Relationships: {final_stats['total_relationships']}")
print(f"  Most Connected:")
for entity in final_stats['most_connected'][:5]:
    print(f"    - {entity['name']}: {entity['connections']} connections")
print("=" * 60)

print("\n✅ All tests completed!")
