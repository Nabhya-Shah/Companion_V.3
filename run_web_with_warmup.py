"""Warm up primary + heavy models (prompt cache) then launch web UI.

This avoids first-turn latency by sending small no-op prompts that exercise
system prompt caching for autonomous tool logic and persona.
"""
from companion_ai.core import config
from companion_ai.llm_interface import generate_model_response
from web_companion import run_web

WARMUP_MESSAGES = [
    ("chat", "(warmup)"),
]

def warmup():
    # We issue a trivial user message with minimal content to warm system prompt.
    # Use both primary and heavy if available.
    base_system = "You are the Companion performing a silent warmup."  # short system
    tried = []
    for purpose, msg in WARMUP_MESSAGES:
        for m in {config.SMART_PRIMARY_MODEL, getattr(config, 'HEAVY_MODEL', config.SMART_PRIMARY_MODEL)}:
            try:
                _ = generate_model_response(msg, base_system, m)
                tried.append(m)
            except Exception:
                pass
    print("Warmup attempted for models:", ", ".join(tried))

if __name__ == '__main__':
    warmup()
    run_web(open_browser_flag=True)
