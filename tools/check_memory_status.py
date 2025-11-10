"""Quick memory summary after conversation."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from companion_ai import memory as db
from companion_ai.memory_graph import get_knowledge_graph

print("=" * 70)
print("MEMORY & KNOWLEDGE GRAPH STATUS")
print("=" * 70)

# Knowledge Graph
kg = get_knowledge_graph()
print(f"\n📊 Knowledge Graph:")
print(f"  Entities: {kg.graph.number_of_nodes()}")
print(f"  Relationships: {kg.graph.number_of_edges()}")

# Profile Facts
facts = db.get_all_profile_facts()
print(f"\n👤 Profile Facts ({len(facts)} total):")
for k, v in list(facts.items())[-8:]:
    print(f"  • {k}: {v}")

# Latest Insights
insights = db.get_latest_insights(3)
print(f"\n💡 Latest Insights:")
for i, ins in enumerate(insights, 1):
    text = ins['insight_text']
    print(f"\n{i}. {text[:200]}{'...' if len(text) > 200 else ''}")

print("\n" + "=" * 70)
