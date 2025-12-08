"""Environment diagnostics for Companion AI.

Run:
    python scripts/check_env.py

Outputs a report of required / optional variables, current value presence, and
suggested additions (mirrors .env.example but can be used with any env source).
"""
from __future__ import annotations
import os, json, textwrap

REQUIRED = [
    ("GROQ_API_KEY", "Primary Groq key for model inference"),
]
OPTIONAL = [
    ("GROQ_VISION_API_KEY", "Dedicated Groq key for vision (Maverick) - falls back to GROQ_API_KEY"),
    ("GROQ_MEMORY_API_KEY", "Secondary Groq key (falls back to GROQ_API_KEY)"),
    ("API_AUTH_TOKEN", "Protects write endpoints (fact approval, memory clear)"),
    ("AZURE_SPEECH_KEY", "Azure TTS key"),
    ("AZURE_SPEECH_REGION", "Azure region for TTS"),
    ("SERPER_API_KEY", "Serper API key for custom web search"),
]
FLAGS = [
    "ENABLE_KNOWLEDGE_GRAPH",
    "ENABLE_FACT_EXTRACTION",
    "ENABLE_TOOL_CALLING",
    "ENABLE_VISION",
    "ENABLE_AUTO_TOOLS",
    # ENABLE_COMPOUND removed - V5 uses 120B built-in search
]

def present(name: str) -> bool:
    return bool(os.getenv(name))

def main():
    report = {"required": {}, "optional": {}, "flags": {}}
    missing_required = []
    for k, desc in REQUIRED:
        val = os.getenv(k)
        if not val:
            missing_required.append(k)
        report['required'][k] = {"present": bool(val), "description": desc}
    for k, desc in OPTIONAL:
        val = os.getenv(k)
        report['optional'][k] = {"present": bool(val), "description": desc}
    for f in FLAGS:
        v = os.getenv(f)
        report['flags'][f] = {"set": v is not None, "value": v}
    print("=== Companion AI Environment Check ===")
    print("=== V5 Architecture ===")
    print()
    print("Cloud Models (Groq):")
    print("  - PRIMARY (120B): openai/gpt-oss-120b")
    print("  - TOOLS (8B): llama-3.1-8b-instant")
    print("  - VISION (Maverick): meta-llama/llama-4-maverick-17b-128e-instruct")
    print()
    print("Local Models (Ollama):")
    print("  - llama3.2, minicpm-v, qwen2.5-coder")
    print()
    if missing_required:
        print("Missing required variables:", ", ".join(missing_required))
    else:
        print("All required variables present.")
    print()
    print(json.dumps(report, indent=2))
    print()
    print(textwrap.dedent("""
    Notes:
      - Use .env (loaded via python-dotenv) OR system environment
      - GROQ_VISION_API_KEY is optional - if not set, uses GROQ_API_KEY for vision
      - This script is for quick sanity before running `run_companion.py`.
    """))

if __name__ == "__main__":
    main()
