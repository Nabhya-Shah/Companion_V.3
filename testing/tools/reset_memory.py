#!/usr/bin/env python3
"""Reset memory database to completely fresh state"""

import sqlite3
import os
from datetime import datetime

db_path = 'data/companion_ai.db'

print("="*80)
print("🔄 MEMORY DATABASE RESET")
print("="*80)

# Backup current database
backup_path = f'data/companion_ai_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.db'
if os.path.exists(db_path):
    import shutil
    shutil.copy(db_path, backup_path)
    print(f"\n✅ Backup created: {backup_path}")

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Show current state
print("\n📊 CURRENT DATABASE STATE:")
print("-"*80)

cursor.execute("SELECT COUNT(*) FROM user_profile")
profile_count = cursor.fetchone()[0]
print(f"  Profile facts: {profile_count}")

cursor.execute("SELECT COUNT(*) FROM conversation_summaries")
summary_count = cursor.fetchone()[0]
print(f"  Summaries: {summary_count}")

cursor.execute("SELECT COUNT(*) FROM ai_insights")
insight_count = cursor.fetchone()[0]
print(f"  Insights: {insight_count}")

cursor.execute("SELECT COUNT(*) FROM pending_profile_facts")
pending_count = cursor.fetchone()[0]
print(f"  Pending facts: {pending_count}")

total = profile_count + summary_count + insight_count + pending_count
print(f"\n  TOTAL RECORDS: {total}")

# Confirm deletion
print("\n⚠️  WARNING: This will DELETE ALL MEMORY DATA!")
print("   - All profile facts")
print("   - All conversation summaries")
print("   - All insights")
print("   - All pending facts")
print("\nThis gives you a completely fresh start.")
print(f"A backup has been saved to: {backup_path}")

confirm = input("\n❓ Are you sure you want to RESET everything? (type 'RESET' to confirm): ").strip()

if confirm == 'RESET':
    print("\n🗑️  Deleting all records...")
    
    cursor.execute("DELETE FROM user_profile")
    deleted_profile = cursor.rowcount
    print(f"  ✓ Deleted {deleted_profile} profile facts")
    
    cursor.execute("DELETE FROM conversation_summaries")
    deleted_summaries = cursor.rowcount
    print(f"  ✓ Deleted {deleted_summaries} summaries")
    
    cursor.execute("DELETE FROM ai_insights")
    deleted_insights = cursor.rowcount
    print(f"  ✓ Deleted {deleted_insights} insights")
    
    cursor.execute("DELETE FROM pending_profile_facts")
    deleted_pending = cursor.rowcount
    print(f"  ✓ Deleted {deleted_pending} pending facts")
    
    cursor.execute("DELETE FROM memory_consolidation")
    deleted_consolidation = cursor.rowcount
    print(f"  ✓ Deleted {deleted_consolidation} consolidation records")
    
    # Reset auto-increment sequences
    cursor.execute("DELETE FROM sqlite_sequence")
    print(f"  ✓ Reset ID sequences")
    
    conn.commit()
    
    print("\n✅ DATABASE RESET COMPLETE!")
    print("\n📊 NEW STATE:")
    print("-"*80)
    print("  Profile facts: 0")
    print("  Summaries: 0")
    print("  Insights: 0")
    print("  Pending facts: 0")
    print("\n🎉 You now have a completely clean slate!")
    print("   The companion will learn about you from scratch with the improved fact extraction.")
    
else:
    print("\n❌ Reset cancelled. No changes made.")

conn.close()

print("\n" + "="*80)
