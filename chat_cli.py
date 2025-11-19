"""Lightweight terminal chat entrypoint.

Usage:
  1. Create a .env file (NOT committed) containing:
        GROQ_API_KEY=your_conversation_key
        GROQ_MEMORY_API_KEY=your_memory_key  # optional; falls back to GROQ_API_KEY
        AZURE_SPEECH_KEY=your_azure_key      # optional for voice features
        AZURE_SPEECH_REGION=uksouth          # example
  2. Activate venv
  3. Run: python chat_cli.py

Type /exit or /quit to leave. Type /memstats to see memory counts.

This keeps things minimal: no audio, just text IO using the adaptive Companion persona.
"""
from __future__ import annotations
import os
import sys
import re
from collections import deque
from dotenv import load_dotenv

from companion_ai import memory as mem
from companion_ai import llm_interface
from companion_ai.tts_manager import tts_manager

load_dotenv()

def have_groq() -> bool:
    return bool(os.getenv("GROQ_API_KEY"))

def build_memory_context() -> dict:
    return {
        "profile": mem.get_all_profile_facts(),
        "summaries": mem.get_latest_summary(1),
        "insights": mem.get_latest_insights(3),
    }

def print_banner():
    print("\n=== Companion Chat (Adaptive Persona) ===")
    if not have_groq():
        print("[WARN] GROQ_API_KEY not set – responses will say offline.")
    if tts_manager.is_enabled:
        print(f"[INFO] Voice enabled: {tts_manager.current_voice}")
    else:
        print("[INFO] Voice disabled (missing keys or init failed)")
    print("Commands: /exit /quit /voice [on|off] /memstats /health /help")

def main():
    print_banner()
    recent_inputs: deque[str] = deque(maxlen=3)
    turn_index = 0
    
    # Auto-enable voice if keys are present
    voice_active = tts_manager.is_enabled

    while True:
        try:
            user_raw = input("You> ")
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            break
        user = user_raw.strip()
        if not user:
            continue

        # Command handling (allow trailing punctuation / variants)
        cmd = user.lower().rstrip(' !#.;')
        if cmd in {"/exit", "/quit"}:
            print("Bye.")
            break
        if cmd.startswith("/voice"):
            parts = cmd.split()
            if len(parts) > 1:
                if parts[1] == "on":
                    if tts_manager.is_enabled:
                        voice_active = True
                        print("Voice output ON.")
                    else:
                        print("Cannot enable voice: Azure keys missing or init failed.")
                elif parts[1] == "off":
                    voice_active = False
                    tts_manager.stop_current_speech()
                    print("Voice output OFF.")
            else:
                print(f"Voice is {'ON' if voice_active else 'OFF'}")
            continue
        if cmd in {"/help", "help"}:
            print("Commands: /exit /quit /voice [on|off] /memstats /health /help")
            continue
        if cmd == "/memstats":
            from companion_ai.memory import get_memory_stats
            stats = get_memory_stats()
            print(f"Memory: profiles={stats['profile_facts']} summaries={stats['summaries']} insights={stats['insights']}")
            continue
        if cmd == "/health":
            from companion_ai.core import metrics
            from companion_ai.memory import get_memory_stats
            mstats = metrics.snapshot()
            memstats = get_memory_stats()
            print("Health:")
            print(f"  interactions: {mstats.get('total_interactions')} models={list(mstats.get('models',{}).keys())}")
            for model, data in mstats.get('models', {}).items():
                print(f"   - {model}: count={data['count']} avg={data.get('avg_latency_ms',0)}ms p95={data.get('p95_latency_ms',0)}ms")
            print(f"  memory: facts={memstats['profile_facts']} summaries={memstats['summaries']} insights={memstats['insights']}")
            continue

        # Repetition guard
        normalized = re.sub(r'\s+', ' ', user.lower())
        duplicate = normalized in (re.sub(r'\s+', ' ', prev.lower()) for prev in recent_inputs)
        recent_inputs.append(user)

        ctx = build_memory_context()

        # Adaptive system style (Jarvis-esque) on first conversational turn
        if turn_index == 0:
            # Light prime by injecting a short directive via a preface input augmentation
            user_with_style = user + "\n(Style: concise, competent, adaptive, lightly witty; switch registers instantly based on query difficulty; avoid formal greetings repetition.)"
        else:
            user_with_style = user

        reply = llm_interface.generate_response(user_with_style, ctx, persona="Companion")
        print(f"AI > {reply}")
        
        # Speak response if voice is active
        if voice_active:
            tts_manager.speak_text(reply, blocking=False)

        turn_index += 1

        # Memory gating heuristics
        try:
            if duplicate:
                continue  # skip memory writes for repeated prompt

            # Basic importance proxy: length & presence of preference markers
            importance_hint = 0.6 if any(tok in user.lower() for tok in ["favorite", "like", "love", "prefer", "enjoy"]) else 0.4
            if len(user) < 15 and importance_hint < 0.5:
                importance_hint = 0.2  # deemphasize trivial short turns

            # Throttle: if last 3 inputs are all very short (<18 chars) skip writes
            if len(recent_inputs) == 3 and all(len(x) < 18 for x in recent_inputs):
                continue  # skip all memory artifacts for rapid micro-chat

            # Summaries: only if importance >=0.4 and not trivially short
            if importance_hint >= 0.4 and len(user) > 8:
                summary = llm_interface.generate_summary(user, reply)
                if summary:
                    mem.add_summary(summary, importance_hint)

            # Facts: filter & whitelist
            raw_facts = llm_interface.extract_profile_facts(user, reply)
            if raw_facts:
                for k, v in raw_facts.items():
                    if not _fact_allowed(k, v):
                        continue
                    mem.upsert_profile_fact(k, v)

            # Insights: throttle (every 2nd non-trivial turn with importance >=0.5)
            if importance_hint >= 0.5 and turn_index % 2 == 0:
                insight = llm_interface.generate_insight(user, reply, ctx)
                if insight:
                    mem.add_insight(insight, 'general', importance_hint)
        except Exception as mem_err:
            print(f"[warn] memory update failed: {mem_err}")

def _fact_allowed(key: str, value: str) -> bool:
    """Heuristic filter to reject noisy / path-like / ephemeral facts."""
    key_l = key.lower().strip()
    value_l = str(value).lower().strip()
    # Reject if value looks like a filesystem path or drive reference
    if any(token in value_l for token in ['..\\', '..//', '\\', '/', ':\\']) or value_l.startswith(('c:/', 'd:/', './')):
        return False
    # Reject if key contains path separators
    if '/' in key_l or '\\' in key_l:
        return False
    # Reject overly long or noisy keys
    if len(key_l) > 30 or key_l.count(' ') > 3:
        return False
    # Reject empty or huge values
    if len(value_l) == 0 or len(value_l) > 120:
        return False
    # Reject generic environment noise
    noise_values = {"windows", "virtual environment", "powershell", "scripts"}
    if value_l in noise_values:
        return False
    # Allow whitelisted semantic keys/prefixes (light pass-through)
    whitelist_prefixes = ("favorite", "pref", "interest", "like", "love")
    whitelist_exact = {"name", "age", "location", "country", "city", "timezone", "language", "hobby", "game", "games"}
    if key_l in whitelist_exact or key_l.startswith(whitelist_prefixes):
        return True
    # Basic heuristic: key with alphabetic chars only and value not purely technical
    if not any(c.isalpha() for c in key_l):
        return False
    tech_noise = {"path", "folder", "script", "activate", "venv"}
    if any(t in value_l for t in tech_noise):
        return False
    return True

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
