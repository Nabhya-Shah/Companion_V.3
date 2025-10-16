#!/usr/bin/env python3
"""Check database schema"""

import sqlite3

conn = sqlite3.connect('data/companion_ai.db')
cursor = conn.cursor()

print("="*80)
print("📊 DATABASE SCHEMA")
print("="*80)

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()

print(f"\nFound {len(tables)} tables:\n")

for table in tables:
    table_name = table[0]
    print(f"\n📋 Table: {table_name}")
    print("-"*80)
    
    # Get table schema
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    
    print("Columns:")
    for col in columns:
        col_id, name, type_, notnull, default, pk = col
        print(f"  - {name:20} {type_:15} {'PRIMARY KEY' if pk else ''}")
    
    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"\nRows: {count}")
    
    # Show sample data
    if count > 0:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
        rows = cursor.fetchall()
        print("\nSample data (first 3 rows):")
        for row in rows:
            print(f"  {row}")

conn.close()

print("\n" + "="*80)
