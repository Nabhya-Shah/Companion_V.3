# main.py (v10.0 - Ollama/Groq integration + Fixed TTS)

import asyncio
import os
import sys
import pyaudio
import torch
import whisper
import traceback
import numpy as np
import threading
import time

# Azure Cognitive Services
import azure.cognitiveservices.speech as speechsdk

# Project Specific Imports
from companion_ai import llm_interface
from companion_ai import memory

# --- NEW: Graceful Shutdown Event ---
shutdown_event = asyncio.Event()

# --- Configuration & Constants ---

# 1. Voice Activity Detection (VAD)
VAD_THRESHOLD = 197  # From your calibration recommendation
VAD_SILENCE_SECONDS = 1.0

# 2. Whisper Model (STT) - Your "speed vs. accuracy" knob.
#    - "tiny.en"   -> Fastest, lowest accuracy.
#    - "base.en"   -> Good balance of speed and accuracy. (Recommended)
#    - "medium.en" -> Slower, more accurate, requires more VRAM.
WHISPER_MODEL = "medium.en"

# 3. Azure TTS Configuration
AZURE_SPEECH_KEY = os.getenv("AZURE_SPEECH_KEY")
AZURE_SPEECH_REGION = os.getenv("AZURE_SPEECH_REGION")
AZURE_VOICE_NAME = "en-US-Ava:DragonHDLatestNeural"

# 4. Audio Settings
AUDIO_DEVICE_INDEX = 1  # "Microphone (High Definition Audio)"
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 16000
CHUNK = 1024
VAD_SILENCE_CHUNKS = int(VAD_SILENCE_SECONDS * (RATE / CHUNK))

# --- Model & Client Initializations ---
if not all([AZURE_SPEECH_KEY, AZURE_SPEECH_REGION]):
    print("FATAL: Azure credentials not found in .env file.")
    sys.exit(1)

print("INFO: Initializing models...")
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"INFO: Using device: {DEVICE}")

print(f"INFO: Loading Whisper model '{WHISPER_MODEL}'...")
whisper_model = whisper.load_model(WHISPER_MODEL, device=DEVICE)
print("INFO: Whisper model loaded.")

from companion_ai import memory as db
db.init_db()
pya = pyaudio.PyAudio()

# --- Dedicated Audio Playback Class ---
class AudioPlayer:
    def __init__(self):
        self.audio_queue = asyncio.Queue()
        self.playback_stream = pya.open(format=pyaudio.paInt16, channels=1, rate=48000, output=True)
        self._is_speaking = False
        self.current_synthesis = None

    async def run(self):
        while not shutdown_event.is_set():
            try:
                audio_data = await asyncio.wait_for(self.audio_queue.get(), timeout=1.0)
                if audio_data is None: continue # Skip sentinel values
                self._is_speaking = True
                self.playback_stream.write(audio_data)
                self.audio_queue.task_done()
            except asyncio.TimeoutError:
                if self._is_speaking and self.audio_queue.empty():
                    self._is_speaking = False
            except asyncio.CancelledError:
                break
        self.playback_stream.stop_stream()
        self.playback_stream.close()

    def play_chunk(self, audio_chunk):
        self.audio_queue.put_nowait(audio_chunk)

    def is_speaking(self):
        return self._is_speaking

    def stop(self):
        if self.current_synthesis:
            self.current_synthesis.stop()

# --- Core Application Logic ---

def record_audio_with_vad(player):
    stream = pya.open(format=FORMAT, channels=CHANNELS, rate=RATE, input=True, frames_per_buffer=CHUNK, input_device_index=AUDIO_DEVICE_INDEX)
    print("\nINFO: Listening...")
    frames, is_speaking, silent_chunks = [], False, 0
    while not shutdown_event.is_set():
        if player.is_speaking():
            stream.read(CHUNK, exception_on_overflow=False); continue
        data = stream.read(CHUNK)
        audio_data_np = np.frombuffer(data, dtype=np.int16)
        rms = np.sqrt(np.mean(np.square(audio_data_np.astype(np.float32))))
        if rms > VAD_THRESHOLD:
            if not is_speaking:
                print(f"INFO: Speech detected (RMS: {rms:.2f}), recording...")
                is_speaking = True
            silent_chunks = 0
            frames.append(data)
        elif is_speaking:
            print(f"INFO: Silence detected (RMS: {rms:.2f}), chunks: {silent_chunks}/{VAD_SILENCE_CHUNKS}")
            frames.append(data)
            silent_chunks += 1
            if silent_chunks > VAD_SILENCE_CHUNKS:
                break
    stream.stop_stream(); stream.close()
    return b''.join(frames)

def transcribe_audio(audio_bytes):
    if not audio_bytes: return ""
    print("INFO: Transcribing audio...")
    try:
        audio_np = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        result = whisper_model.transcribe(audio_np, fp16=(DEVICE=="cuda"))
        return result["text"].strip()
    except Exception as e:
        print(f"ERROR: Transcription failed: {e}"); return ""

def speak_text_azure_stream(text, player):
    """Generates audio using Azure and streams it to the player for low latency."""
    if not text or shutdown_event.is_set(): return
    
    try:
        # Create speech config
        speech_config = speechsdk.SpeechConfig(subscription=AZURE_SPEECH_KEY, region=AZURE_SPEECH_REGION)
        speech_config.set_speech_synthesis_output_format(speechsdk.SpeechSynthesisOutputFormat.Riff48Khz16BitMonoPcm)
        speech_config.speech_synthesis_voice_name = AZURE_VOICE_NAME
        
        # Create an audio output stream that writes to our player
        class AudioOutputStreamCallback(speechsdk.audio.PushAudioOutputStreamCallback):
            def __init__(self, player):
                super().__init__()
                self.player = player
                
            def write(self, audio_buffer: memoryview) -> int:
                # Convert the audio_buffer to bytes and send to the player
                self.player.play_chunk(audio_buffer.tobytes())
                return len(audio_buffer)
                
            def close(self):
                pass
                
        # Create the push stream and set up the callback
        stream_callback = AudioOutputStreamCallback(player)
        audio_stream = speechsdk.audio.PushAudioOutputStream(stream_callback)
        audio_config = speechsdk.audio.AudioOutputConfig(stream=audio_stream)
        
        # Create the speech synthesizer
        synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=audio_config)
        player.current_synthesis = synthesizer
        
        # Synthesize the text (using SSML for more control)
        ssml_string = f"<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-US'><voice name='{AZURE_VOICE_NAME}'>{text}</voice></speak>"
        result = synthesizer.speak_ssml_async(ssml_string).get()
        
        # Check the result
        if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
            print("INFO: Azure TTS streaming completed")
        elif result.reason == speechsdk.ResultReason.Canceled:
            cancellation_details = result.cancellation_details
            print(f"ERROR: Azure TTS canceled: {cancellation_details.reason}")
            if cancellation_details.reason == speechsdk.CancellationReason.Error:
                print(f"ERROR DETAILS: {cancellation_details.error_details}")

    except Exception as e:
        print(f"ERROR: Azure TTS streaming call failed: {e}")

async def main_loop():
    print("\n--- Project Companion AI Activated ---")
    player = AudioPlayer()
    player_task = asyncio.create_task(player.run())

    while not shutdown_event.is_set():
        try:
            # Record user audio (blocking, so run in thread)
            recorded_data = await asyncio.to_thread(record_audio_with_vad, player)
            if shutdown_event.is_set(): break
            
            # Transcribe (blocking, run in thread)
            user_message = await asyncio.to_thread(transcribe_audio, recorded_data)
            if shutdown_event.is_set(): break
            
            if not user_message: continue

            print(f"INFO: User said: {user_message}")
            print("INFO: Companion AI is thinking...")
            memory_context = { "profile": db.get_all_profile_facts(), "summaries": db.get_latest_summary(), "insights": db.get_latest_insights() }
            ai_message = llm_interface.generate_response(user_message, memory_context)
            print(f"INFO: AI Response: {ai_message}")

            # Speak the response (non-blocking by running in a thread)
            await asyncio.to_thread(speak_text_azure_stream, ai_message, player)
            
            # Update memory asynchronously
            asyncio.create_task(update_memory_async(user_message, ai_message, memory_context))

        except Exception as e:
            print(f"FATAL: An error occurred in the main loop: {e}")
            traceback.print_exc(); break
            
    player_task.cancel()
    await asyncio.gather(player_task, return_exceptions=True)

async def update_memory_async(user_msg, ai_msg, context):
    summary = llm_interface.generate_summary(user_msg, ai_msg)
    if summary: db.add_summary(summary)
    facts = llm_interface.extract_profile_facts(user_msg, ai_msg)
    if facts:
        for key, value in facts.items(): db.upsert_profile_fact(key, value)
    insight = llm_interface.generate_insight(user_msg, ai_msg, context)
    if insight: db.add_insight(insight)

if __name__ == "__main__":
    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        print("\nINFO: User requested shutdown. Cleaning up...")
        shutdown_event.set()
    finally:
        asyncio.run(asyncio.sleep(0.5))
        pya.terminate()
        print("\n--- Project Companion AI Deactivated ---")