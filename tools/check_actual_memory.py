#!/usr/bin/env python3
"""View actual memory database contents"""

import sqlite3
from datetime import datetime

conn = sqlite3.connect('data/companion_ai.db')
cursor = conn.cursor()

print("="*80)
print("🧠 YOUR ACTUAL MEMORY DATABASE")
print("="*80)

# Profile facts
print("\n👤 PROFILE FACTS:")
print("-"*80)
cursor.execute("""
    SELECT key, value, confidence, source, last_updated 
    FROM user_profile 
    ORDER BY last_updated DESC
""")
facts = cursor.fetchall()

if facts:
    print(f"\nTotal: {len(facts)} facts\n")
    for i, (key, value, conf, source, created) in enumerate(facts, 1):
        conf_str = f"{conf:.2f}" if conf else "N/A"
        created_date = created[:10] if created else "N/A"
        print(f"{i:3}. {key:35} = {value:30} | conf:{conf_str} | {created_date}")
else:
    print("  No facts stored")

# Summaries
print("\n\n📝 CONVERSATION SUMMARIES:")
print("-"*80)
cursor.execute("""
    SELECT id, summary_text, relevance_score, timestamp 
    FROM conversation_summaries 
    ORDER BY timestamp DESC
""")
summaries = cursor.fetchall()

if summaries:
    print(f"\nTotal: {len(summaries)} summaries\n")
    for i, (sid, text, imp, created) in enumerate(summaries[:15], 1):
        imp_str = f"{imp:.2f}" if imp else "N/A"
        created_date = created[:10] if created else "N/A"
        print(f"{i:2}. [{sid}] {text[:65]:65} | {imp_str} | {created_date}")
else:
    print("  No summaries stored")

# Insights
print("\n\n💡 INSIGHTS:")
print("-"*80)
cursor.execute("""
    SELECT id, insight_text, relevance_score, timestamp 
    FROM ai_insights 
    ORDER BY timestamp DESC
""")
insights = cursor.fetchall()

if insights:
    print(f"\nTotal: {len(insights)} insights\n")
    for i, (iid, text, imp, created) in enumerate(insights[:10], 1):
        imp_str = f"{imp:.2f}" if imp else "N/A"
        created_date = created[:10] if created else "N/A"
        print(f"{i:2}. [{iid}] {text[:65]:65} | {imp_str} | {created_date}")
else:
    print("  No insights stored")

conn.close()

print("\n" + "="*80)
