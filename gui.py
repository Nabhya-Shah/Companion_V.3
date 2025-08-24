#!/usr/bin/env python3
# gui.py - Text-based Companion AI Interface

import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from companion_ai import llm_interface
from companion_ai import memory as db
from companion_ai import memory_ai

def print_banner():
    print("=" * 60)
    print("🤖 PROJECT COMPANION AI - TEXT MODE")
    print("=" * 60)
    print("Type 'quit' or 'exit' to end the conversation")
    print("Type 'memory' to see your profile")
    print("Type 'stats' to see memory statistics")
    print("Type 'cleanup' to run smart memory cleanup")
    print("Type 'clear' to clear the screen")
    print("-" * 60)

async def update_memory_async(user_msg, ai_msg, context):
    """Update memory using smart AI analysis"""
    try:
        # Analyze conversation importance first
        importance_score = memory_ai.analyze_conversation_importance(user_msg, ai_msg, context)
        print(f"🧠 Conversation importance: {importance_score:.2f}")
        
        # Only process if importance is above threshold (raised to reduce API calls)
        if importance_score > 0.4:
            # Generate smart summary with importance-based detail level
            summary = memory_ai.generate_smart_summary(user_msg, ai_msg, importance_score)
            if summary: 
                db.add_summary(summary, relevance_score=importance_score)
                print(f"📝 Memory: {summary}")
            
            # Extract profile facts with confidence scoring
            smart_facts = memory_ai.extract_smart_profile_facts(user_msg, ai_msg)
            if smart_facts:
                for key, fact_data in smart_facts.items():
                    db.upsert_profile_fact(
                        key, 
                        fact_data['value'], 
                        confidence=fact_data['confidence'],
                        source='smart_analysis'
                    )
                print(f"👤 Profile updated: {smart_facts}")
            
            # Generate contextual insight
            insight = memory_ai.generate_contextual_insight(user_msg, ai_msg, context, importance_score)
            if insight:
                category = memory_ai.categorize_insight(insight)
                db.add_insight(insight, category=category, relevance_score=importance_score)
                print(f"💡 {category.title()} insight: {insight}")
        else:
            print("🧠 Low importance conversation - minimal memory storage")
            
    except Exception as e:
        print(f"❌ Smart memory update failed: {e}")
        # Fallback to basic memory update
        try:
            summary = llm_interface.generate_summary(user_msg, ai_msg)
            if summary: 
                db.add_summary(summary)
                print(f"📝 Fallback memory: {summary}")
        except:
            pass

async def main():
    # Initialize database
    db.init_db()
    
    print_banner()
    
    while True:
        try:
            # Get user input
            user_input = input("\n🗣️  You: ").strip()
            
            if not user_input:
                continue
                
            # Handle special commands
            if user_input.lower() in ['quit', 'exit', 'bye']:
                print("\n🤖 Companion AI: Goodbye! It was great talking with you.")
                break
            elif user_input.lower() == 'memory':
                profile = db.get_all_profile_facts()
                summaries = db.get_latest_summary(3)
                insights = db.get_latest_insights(3)
                
                print("\n📊 MEMORY OVERVIEW:")
                print(f"Profile facts: {len(profile)} items")
                print(f"Recent summaries: {len(summaries)} items")
                print(f"Recent insights: {len(insights)} items")
                
                if profile:
                    print("\n👤 Profile:")
                    for key, value in profile.items():
                        print(f"  • {key}: {value}")
                continue
            elif user_input.lower() == 'stats':
                stats = db.get_memory_stats()
                print("\n📊 MEMORY STATISTICS:")
                print(f"Profile facts: {stats['profile_facts']}")
                print(f"Summaries: {stats['summaries']} (avg relevance: {stats['avg_summary_relevance']})")
                print(f"Insights: {stats['insights']} (avg relevance: {stats['avg_insight_relevance']})")
                if stats['recent_actions']:
                    print("\nRecent memory actions:")
                    for action in stats['recent_actions']:
                        print(f"  • {action['action']}: {action['timestamp']}")
                continue
            elif user_input.lower() == 'cleanup':
                print("\n🧠 Running smart memory cleanup...")
                stats = db.smart_memory_cleanup()
                print("✅ Memory cleanup completed!")
                continue
            elif user_input.lower() == 'clear':
                os.system('cls' if os.name == 'nt' else 'clear')
                print_banner()
                continue
            
            # Get memory context
            memory_context = {
                "profile": db.get_all_profile_facts(),
                "summaries": db.get_latest_summary(),
                "insights": db.get_latest_insights()
            }
            
            # Generate AI response
            print("\n🤖 Companion AI is thinking...")
            ai_response = llm_interface.generate_response(user_input, memory_context)
            print(f"🤖 Companion AI: {ai_response}")
            
            # Update memory in background
            asyncio.create_task(update_memory_async(user_input, ai_response, memory_context))
            
        except KeyboardInterrupt:
            print("\n\n🤖 Companion AI: Goodbye! It was great talking with you.")
            break
        except Exception as e:
            print(f"\n❌ Error: {e}")
            print("Let's try again...")

if __name__ == "__main__":
    asyncio.run(main())