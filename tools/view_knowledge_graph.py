#!/usr/bin/env python3
"""
View the current state of the Knowledge Graph
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from companion_ai.memory_graph import get_knowledge_graph, get_graph_stats, export_graph

print("=" * 70)
print("KNOWLEDGE GRAPH VIEWER")
print("=" * 70)

# Get graph instance
kg = get_knowledge_graph()

# Show statistics
print("\n📊 GRAPH STATISTICS:")
stats = get_graph_stats()
print(f"  Total Entities: {stats['total_entities']}")
print(f"  Total Relationships: {stats['total_relationships']}")
print(f"  Average Connections per Entity: {stats['avg_connections']:.2f}")
print(f"\n  Entity Types:")
for etype, count in stats['entity_types'].items():
    print(f"    - {etype}: {count}")

print(f"\n  Most Connected Entities:")
for entity in stats['most_connected']:
    print(f"    - {entity['name']}: {entity['connections']} connections")

# Show all entities
print("\n\n🏷️ ALL ENTITIES:")
print("-" * 70)
for i, (node, data) in enumerate(kg.graph.nodes(data=True), 1):
    entity_type = data.get('entity_type', 'unknown')
    mentions = data.get('mention_count', 0)
    importance = data.get('importance', 0)
    attrs = data.get('attributes', {})
    
    print(f"\n{i}. {node} ({entity_type})")
    print(f"   Mentions: {mentions}, Importance: {importance:.2f}")
    if attrs:
        print(f"   Attributes: {attrs}")

# Show all relationships
print("\n\n🔗 ALL RELATIONSHIPS:")
print("-" * 70)
for i, (source, target, data) in enumerate(kg.graph.edges(data=True), 1):
    rel_type = data.get('relation_type', 'related_to')
    strength = data.get('strength', 0.5)
    context = data.get('context', '')
    
    print(f"\n{i}. {source} -{rel_type}→ {target}")
    print(f"   Strength: {strength:.2f}")
    if context:
        print(f"   Context: {context[:100]}")

print("\n" + "=" * 70)
print(f"Total: {stats['total_entities']} entities, {stats['total_relationships']} relationships")
print("=" * 70)
