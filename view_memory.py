#!/usr/bin/env python3
"""
Memory Viewer - Export database memory in readable format
"""

import sqlite3
import json
from datetime import datetime
import os

def view_memory():
    """Export memory data in readable format"""
    db_path = "data/companion_ai.db"
    
    if not os.path.exists(db_path):
        print("❌ Database not found at data/companion_ai.db")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        print("=" * 60)
        print("🧠 COMPANION AI MEMORY DATABASE")
        print("=" * 60)
        
        # Profile Facts
        print("\n👤 PROFILE FACTS:")
        print("-" * 40)
        cursor.execute("SELECT key, value, created_at FROM profile_facts ORDER BY created_at DESC")
        facts = cursor.fetchall()
        
        if facts:
            for key, value, created_at in facts:
                readable_key = key.replace('_', ' ').title()
                print(f"• {readable_key}: {value}")
                print(f"  Added: {created_at}")
                print()
        else:
            print("No profile facts stored yet.\n")
        
        # Summaries
        print("\n📝 CONVERSATION SUMMARIES:")
        print("-" * 40)
        cursor.execute("SELECT summary_text, relevance_score, created_at FROM summaries ORDER BY created_at DESC LIMIT 10")
        summaries = cursor.fetchall()
        
        if summaries:
            for i, (summary, relevance, created_at) in enumerate(summaries, 1):
                print(f"{i}. Summary (Relevance: {relevance}):")
                print(f"   {summary}")
                print(f"   Date: {created_at}")
                print()
        else:
            print("No summaries stored yet.\n")
        
        # Insights
        print("\n💡 INSIGHTS:")
        print("-" * 40)
        cursor.execute("SELECT insight_text, insight_type, relevance_score, created_at FROM insights ORDER BY created_at DESC LIMIT 10")
        insights = cursor.fetchall()
        
        if insights:
            for i, (insight, insight_type, relevance, created_at) in enumerate(insights, 1):
                print(f"{i}. {insight_type.title()} Insight (Relevance: {relevance}):")
                print(f"   {insight}")
                print(f"   Date: {created_at}")
                print()
        else:
            print("No insights stored yet.\n")
        
        conn.close()
        print("=" * 60)
        
    except Exception as e:
        print(f"❌ Error reading database: {e}")

def export_memory_to_file():
    """Export memory to a text file"""
    db_path = "data/companion_ai.db"
    
    if not os.path.exists(db_path):
        print("❌ Database not found")
        return
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"memory_export_{timestamp}.txt"
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("COMPANION AI MEMORY EXPORT\n")
            f.write("=" * 50 + "\n")
            f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            
            # Profile Facts
            f.write("PROFILE FACTS:\n")
            f.write("-" * 30 + "\n")
            cursor.execute("SELECT key, value, created_at FROM profile_facts ORDER BY created_at DESC")
            facts = cursor.fetchall()
            
            for key, value, created_at in facts:
                readable_key = key.replace('_', ' ').title()
                f.write(f"• {readable_key}: {value}\n")
                f.write(f"  Added: {created_at}\n\n")
            
            # Summaries
            f.write("\nCONVERSATION SUMMARIES:\n")
            f.write("-" * 30 + "\n")
            cursor.execute("SELECT summary_text, relevance_score, created_at FROM summaries ORDER BY created_at DESC")
            summaries = cursor.fetchall()
            
            for i, (summary, relevance, created_at) in enumerate(summaries, 1):
                f.write(f"{i}. Summary (Relevance: {relevance}):\n")
                f.write(f"   {summary}\n")
                f.write(f"   Date: {created_at}\n\n")
            
            # Insights
            f.write("\nINSIGHTS:\n")
            f.write("-" * 30 + "\n")
            cursor.execute("SELECT insight_text, insight_type, relevance_score, created_at FROM insights ORDER BY created_at DESC")
            insights = cursor.fetchall()
            
            for i, (insight, insight_type, relevance, created_at) in enumerate(insights, 1):
                f.write(f"{i}. {insight_type.title()} Insight (Relevance: {relevance}):\n")
                f.write(f"   {insight}\n")
                f.write(f"   Date: {created_at}\n\n")
        
        conn.close()
        print(f"✅ Memory exported to: {filename}")
        
    except Exception as e:
        print(f"❌ Error exporting memory: {e}")

if __name__ == "__main__":
    print("Choose an option:")
    print("1. View memory in console")
    print("2. Export memory to text file")
    
    choice = input("Enter choice (1 or 2): ").strip()
    
    if choice == "1":
        view_memory()
    elif choice == "2":
        export_memory_to_file()
    else:
        print("Invalid choice. Running console view...")
        view_memory()