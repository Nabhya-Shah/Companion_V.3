#!/usr/bin/env python3
"""Test Azure TTS with the new voice"""

from companion_ai.tts_manager import AzureTTSManager

print("Initializing TTS Manager...")
tts = AzureTTSManager()

if not tts.is_enabled:
    print("❌ TTS is not enabled. Check your Azure credentials.")
    exit(1)

print(f"✅ TTS enabled with voice: {tts.current_voice}\n")

test_messages = [
    "Hey! I'm your AI companion. How's it going?",
    "Just chilling, maybe hunting for a good show to binge later.",
    "The Truman Show still feels like a weird mirror—watching someone's whole life become TV is oddly comforting and unsettling at once.",
]

for i, msg in enumerate(test_messages, 1):
    print(f"\n🎤 Test {i}/{len(test_messages)}")
    print(f"   Text: {msg[:60]}...")
    print("   Speaking...", end="", flush=True)
    
    success = tts.speak_text(msg, blocking=True)
    
    if success:
        print(" ✅ Success!")
    else:
        print(" ❌ Failed!")
        break

print("\n✨ TTS test complete!")
