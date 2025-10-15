"""Quick personality test - see the new concise, adaptive style in action"""
from dotenv import load_dotenv
from companion_ai import memory as mem
from companion_ai.llm_interface import generate_response

load_dotenv()

def test_personality():
    print("\n" + "="*70)
    print("🎭 NEW PERSONALITY TEST - Concise & Adaptive".center(70))
    print("="*70 + "\n")
    
    # Build memory context
    memory_ctx = {
        "profile": mem.get_all_profile_facts(),
        "summaries": mem.get_latest_summary(5),
        "insights": mem.get_latest_insights(5)
    }
    
    test_messages = [
        "hey what's up?",
        "not much too, start a conversation",
        "eh its alr, a bit tired but thats all really",
        "you dont say...",
        "what's my favorite game?",
    ]
    
    for i, msg in enumerate(test_messages, 1):
        print(f"Test {i}: You say: \"{msg}\"")
        response = generate_response(
            user_message=msg,
            memory_context=memory_ctx,
            persona="Companion"
        )
        print(f"AI says: {response}")
        print("-" * 70 + "\n")
        
        # Check response characteristics
        word_count = len(response.split())
        lines = response.count('\n') + 1
        has_bullets = '-' in response and lines > 2
        
        print(f"  Analysis:")
        print(f"  - Length: {word_count} words, {lines} lines")
        print(f"  - Concise: {'✅' if word_count < 30 else '⚠️ too long'}")
        print(f"  - No bullets: {'✅' if not has_bullets else '❌ has bullets'}")
        print(f"  - Natural: {'✅' if not response.startswith('-') else '⚠️ structured'}")
        print()

if __name__ == "__main__":
    print("Testing new concise personality...")
    print("This should feel like texting a friend who knows you.\n")
    test_personality()
    print("\n✅ Test complete! Now try it in the GUI.")
