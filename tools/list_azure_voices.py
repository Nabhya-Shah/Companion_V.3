#!/usr/bin/env python3
"""List available Azure TTS voices"""

import os
import azure.cognitiveservices.speech as speechsdk
from dotenv import load_dotenv

load_dotenv()

speech_key = os.getenv("AZURE_SPEECH_KEY")
speech_region = os.getenv("AZURE_SPEECH_REGION")

if not speech_key or not speech_region:
    print("Azure Speech credentials not found!")
    exit(1)

config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
synthesizer = speechsdk.SpeechSynthesizer(speech_config=config)

print("Fetching available voices...")
result = synthesizer.get_voices_async().get()

# Filter for en-US voices
en_us_voices = [v for v in result.voices if v.locale.startswith("en-US")]

print(f"\n✅ Found {len(en_us_voices)} en-US voices:\n")
print("=" * 80)

# Group by style (Neural, Standard, etc.)
neural_voices = [v for v in en_us_voices if "Neural" in v.short_name]

print(f"\n🎤 NEURAL VOICES ({len(neural_voices)}):")
print("-" * 80)
for i, voice in enumerate(neural_voices[:30], 1):  # Show first 30
    gender = "♀️ F" if str(voice.gender) == "Female" else "♂️ M"
    print(f"{i:2}. {gender} | {voice.short_name:45} | {voice.local_name}")

print("\n" + "=" * 80)
print("\n💡 Recommended voices for companion AI:")
print("   - en-US-AvaNeural (Female, clear and natural)")
print("   - en-US-JennyNeural (Female, warm and friendly)")
print("   - en-US-AriaNeural (Female, versatile)")
print("   - en-US-GuyNeural (Male, professional)")
print("   - en-US-DavisNeural (Male, young and energetic)")
