#!/usr/bin/env python3
"""
Simple Azure TTS test script to diagnose connection issues
"""

import os
import pytest
from dotenv import load_dotenv

try:
    import azure.cognitiveservices.speech as speechsdk  # type: ignore
    _AZURE_IMPORTED = True
except Exception:
    _AZURE_IMPORTED = False

# Force reload environment variables
load_dotenv(override=True)

@pytest.mark.skipif(not _AZURE_IMPORTED, reason="Azure Speech SDK not installed")
def test_azure_tts():
    """Test Azure TTS connection if credentials + sdk available, else skip."""
    speech_key = os.getenv("AZURE_SPEECH_KEY")
    speech_region = os.getenv("AZURE_SPEECH_REGION")
    if not (speech_key and speech_region):
        pytest.skip("Azure credentials not set")
    speech_config = speechsdk.SpeechConfig(subscription=speech_key, region=speech_region)
    speech_config.speech_synthesis_voice_name = "en-US-AriaNeural"
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config)
    result = synthesizer.speak_text_async("Test TTS").get()
    assert result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted

if __name__ == "__main__":
    test_azure_tts()