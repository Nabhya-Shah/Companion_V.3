#!/usr/bin/env python3
"""Deep dive into all stored memories"""

import sqlite3
import json
import pickle
from pathlib import Path

# Memory DB
db_path = Path(__file__).parent.parent / "data" / "companion_ai.db"
db = sqlite3.connect(db_path)
db.row_factory = sqlite3.Row

print("=" * 70)
print("USER PROFILE (What the AI knows about you)")
print("=" * 70)
for row in db.execute('SELECT key, value, confidence, reaffirmations FROM user_profile ORDER BY last_updated DESC'):
    conf = row['confidence'] or 0
    reaff = row['reaffirmations'] or 0
    print(f"  {row['key']}: {row['value']}")
    print(f"      (confidence: {conf:.0%}, reaffirmations: {reaff})")
print()

print("=" * 70)
print("CONVERSATION SUMMARIES (last 10)")
print("=" * 70)
for row in db.execute('SELECT summary_text, timestamp FROM conversation_summaries ORDER BY timestamp DESC LIMIT 10'):
    print(f"  [{row['timestamp']}]")
    summary = row['summary_text'][:150] if row['summary_text'] else "N/A"
    print(f"    {summary}...")
    print()

print("=" * 70)
print("AI INSIGHTS")
print("=" * 70)
for row in db.execute('SELECT insight_text, category, timestamp FROM ai_insights ORDER BY timestamp DESC'):
    print(f"  [{row['category']}] {row['insight_text']}")
print()

# Knowledge Graph (pickle file)
kg_path = Path(__file__).parent.parent / "data" / "knowledge_graph.pkl"
if kg_path.exists():
    with open(kg_path, 'rb') as f:
        kg = pickle.load(f)
    
    g = kg.get('graph')
    if g and hasattr(g, 'nodes'):
        print("=" * 70)
        print("USER NODE ATTRIBUTES (what AI thinks about you)")
        print("=" * 70)
        user_data = g.nodes.get('User', {})
        for k, v in user_data.get('attributes', {}).items():
            print(f"  {k}: {v}")
        print()
        
        print("=" * 70)
        print("WEIRD/INTERESTING ENTITIES")
        print("=" * 70)
        weird = ['paranoia', 'wizard', 'chaotic', 'bug', 'pineapple', 'bagel', 
                 'mug', 'blanket', 'herbal', 'sunrise', 'caffeine', 'foil', 'cat',
                 'Blade Runner', 'Attack on Titan', 'Mushishi', 'balance', 'coffee',
                 'reality', 'poetic', 'grass', 'night']
        for node, data in g.nodes(data=True):
            if any(w.lower() in node.lower() for w in weird):
                etype = data.get('entity_type', '?')
                print(f"  [{etype}] {node}")
                if data.get('attributes'):
                    for k, v in list(data['attributes'].items())[:3]:
                        print(f"      {k}: {v}")
        print()
        
        print("=" * 70)
        print("MOST MENTIONED ENTITIES (Top 25)")
        print("=" * 70)
        sorted_nodes = sorted(g.nodes(data=True), 
                              key=lambda x: x[1].get('mention_count', 0), 
                              reverse=True)
        for node, data in sorted_nodes[:25]:
            mc = data.get('mention_count', 0)
            etype = data.get('entity_type', '?')
            print(f"  [{etype:12}] {node:35} (mentions: {mc})")
        
        print()
        print("=" * 70)
        print("INTERESTING RELATIONSHIPS")
        print("=" * 70)
        for src, tgt, data in list(g.edges(data=True))[:30]:
            rtype = data.get('relation_type', '?')
            ctx = data.get('context', '')[:50]
            print(f"  {src} --[{rtype}]--> {tgt}")
            if ctx:
                print(f"      Context: {ctx}...")
        
        print()
        print("=" * 70)
        print("KNOWLEDGE GRAPH STATS")
        print("=" * 70)
        print(f"  Total Entities: {g.number_of_nodes()}")
        print(f"  Total Relationships: {g.number_of_edges()}")

print()
print("=" * 70)
print("MEMORY DB STATS")
print("=" * 70)
profile_count = db.execute('SELECT COUNT(*) FROM user_profile').fetchone()[0]
summary_count = db.execute('SELECT COUNT(*) FROM conversation_summaries').fetchone()[0]
insight_count = db.execute('SELECT COUNT(*) FROM ai_insights').fetchone()[0]
print(f"  Profile Facts: {profile_count}")
print(f"  Summaries: {summary_count}")
print(f"  Insights: {insight_count}")
