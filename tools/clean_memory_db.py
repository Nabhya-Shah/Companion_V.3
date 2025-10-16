#!/usr/bin/env python3
"""Clean database of inferential/garbage facts"""

import sqlite3
import re

conn = sqlite3.connect('data/companion_ai.db')
cursor = conn.cursor()

print("="*80)
print("🧹 CLEANING MEMORY DATABASE")
print("="*80)

# Patterns to identify bad facts
bad_patterns = [
    r'^user_is_',
    r'^user_.*ing$',
    r'^ai_',
    r'conversation',
    r'aware',
    r'testing',
    r'explicit',
    r'confusion',
    r'grateful',
    r'quiet',
    r'hyped',
    r'unimpressed',
    r'lazy',
    r'tired',
    r'chill',
    r'not_crazy',
    r'test_fact',  # Remove test data
]

# Get all facts
cursor.execute("SELECT key, value FROM user_profile")
all_facts = cursor.fetchall()

print(f"\nTotal facts in database: {len(all_facts)}")

# Identify bad facts
facts_to_delete = []
for key, value in all_facts:
    if any(re.search(pattern, key, re.IGNORECASE) for pattern in bad_patterns):
        facts_to_delete.append(key)

print(f"\n❌ Found {len(facts_to_delete)} BAD facts to delete:\n")
for i, key in enumerate(facts_to_delete, 1):
    cursor.execute("SELECT value FROM user_profile WHERE key=?", (key,))
    value = cursor.fetchone()[0]
    print(f"{i:3}. {key:40} = {value[:40]}")

if facts_to_delete:
    confirm = input(f"\n⚠️  Delete these {len(facts_to_delete)} facts? (yes/no): ").strip().lower()
    
    if confirm == 'yes':
        for key in facts_to_delete:
            cursor.execute("DELETE FROM user_profile WHERE key=?", (key,))
        conn.commit()
        print(f"\n✅ Deleted {len(facts_to_delete)} bad facts!")
    else:
        print("\n❌ Cancelled. No facts deleted.")
else:
    print("\n✅ No bad facts found!")

# Show remaining facts
print("\n" + "="*80)
print("✅ REMAINING CLEAN FACTS:")
print("="*80)

cursor.execute("SELECT key, value, confidence FROM user_profile ORDER BY key")
clean_facts = cursor.fetchall()

if clean_facts:
    print(f"\nTotal clean facts: {len(clean_facts)}\n")
    for i, (key, value, conf) in enumerate(clean_facts, 1):
        conf_str = f"{conf:.2f}" if conf else "N/A"
        print(f"{i:2}. {key:30} = {value:35} (conf: {conf_str})")
else:
    print("\nNo facts remaining in database.")

conn.close()

print("\n" + "="*80)
print("🎉 DATABASE CLEANING COMPLETE!")
print("="*80)
