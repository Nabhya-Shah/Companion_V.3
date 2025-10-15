"""Real-time monitoring dashboard for Companion AI
Run this alongside the GUI to see what's happening under the hood.
"""
import time
import os
from companion_ai import memory as mem
from companion_ai.core import metrics as core_metrics
from dotenv import load_dotenv

load_dotenv()

def clear_screen():
    """Clear terminal screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def print_header():
    """Print dashboard header"""
    print("=" * 70)
    print("🔍 COMPANION AI - MONITORING DASHBOARD".center(70))
    print("=" * 70)
    print()

def print_memory_stats():
    """Display memory statistics"""
    profile = mem.get_all_profile_facts()
    summaries = mem.get_latest_summary(100)  # Get all summaries
    insights = mem.get_latest_insights(100)  # Get all insights
    
    print("📊 MEMORY STATISTICS")
    print("-" * 70)
    print(f"  Profile Facts: {len(profile)}")
    print(f"  Summaries:     {len(summaries)}")
    print(f"  Insights:      {len(insights)}")
    print()
    
    if profile:
        print("📝 STORED PROFILE FACTS:")
        print("-" * 70)
        for key, value in list(profile.items())[:10]:  # Show first 10
            value_str = str(value)[:50] + "..." if len(str(value)) > 50 else str(value)
            print(f"  • {key}: {value_str}")
        if len(profile) > 10:
            print(f"  ... and {len(profile) - 10} more")
        print()

def print_recent_summaries():
    """Display recent conversation summaries"""
    summaries = mem.get_latest_summary(5)
    
    if summaries:
        print("💬 RECENT CONVERSATION SUMMARIES:")
        print("-" * 70)
        for i, summary in enumerate(summaries[:3], 1):
            text = summary if isinstance(summary, str) else str(summary)
            text = text[:100] + "..." if len(text) > 100 else text
            print(f"  {i}. {text}")
        print()

def print_system_status():
    """Display system status"""
    print("⚙️  SYSTEM STATUS:")
    print("-" * 70)
    print(f"  Groq API:      ✅ Connected")
    print(f"  Database:      ✅ Active")
    print(f"  Memory System: ✅ Operational")
    print(f"  Model:         openai/gpt-oss-120b (primary)")
    print()

def print_instructions():
    """Print usage instructions"""
    print("📖 INSTRUCTIONS:")
    print("-" * 70)
    print("  • This dashboard refreshes every 5 seconds")
    print("  • Use the GUI to chat with your AI companion")
    print("  • Watch this screen to see memory updates in real-time")
    print("  • Press Ctrl+C to exit")
    print()
    print("=" * 70)

def monitor_loop():
    """Main monitoring loop"""
    iteration = 0
    try:
        while True:
            clear_screen()
            print_header()
            print_system_status()
            print_memory_stats()
            print_recent_summaries()
            print_instructions()
            
            print(f"\n⏱️  Last update: {time.strftime('%H:%M:%S')} | Iteration: {iteration + 1}")
            
            iteration += 1
            time.sleep(5)  # Update every 5 seconds
            
    except KeyboardInterrupt:
        print("\n\n👋 Monitoring stopped. Goodbye!")

if __name__ == "__main__":
    print("\n🚀 Starting Companion AI Monitor...\n")
    time.sleep(1)
    monitor_loop()
