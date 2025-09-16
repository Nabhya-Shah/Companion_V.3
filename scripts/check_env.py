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
    ("GROQ_MEMORY_API_KEY", "Secondary Groq key (falls back to GROQ_API_KEY)"),
    ("API_AUTH_TOKEN", "Protects write endpoints (fact approval, memory clear)"),
    ("AZURE_SPEECH_KEY", "Azure TTS key"),
    ("AZURE_SPEECH_REGION", "Azure region for TTS"),
]
FLAGS = [
    "ENABLE_ENSEMBLE","ENABLE_EXPERIMENTAL_MODELS","ENABLE_COMPOUND_MODELS",
    "ENABLE_FACT_APPROVAL","FACT_AUTO_APPROVE","VERIFY_FACTS_SECOND_PASS",
    "ENABLE_PROMPT_CACHING"
]
ENSEMBLE = [
    "ENSEMBLE_MODE","ENSEMBLE_CANDIDATES","ENSEMBLE_REFINE_EXPANSION","ENSEMBLE_REFINE_HARD_CAP"
]

def present(name: str) -> bool:
    return bool(os.getenv(name))

def main():
    report = {"required": {}, "optional": {}, "flags": {}, "ensemble": {}}
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
    for e in ENSEMBLE:
        v = os.getenv(e)
        report['ensemble'][e] = {"set": v is not None, "value": v}
    print("=== Companion AI Environment Check ===")
    if missing_required:
        print("Missing required variables:", ", ".join(missing_required))
    else:
        print("All required variables present.")
    print()
    print(json.dumps(report, indent=2))
    print()
    print(textwrap.dedent("""
    Notes:
      - Use .env (loaded via python-dotenv) OR system environment; .env.example just documents fields.
      - If you already centrally manage env vars (e.g., shell profile, CI, secrets manager) you can delete .env.example if undesired.
      - This script is for quick sanity before running `run_companion.py`.
    """))

if __name__ == "__main__":
    main()
