# Companion V3

Companion V3 is a web-first personal AI assistant with orchestrator-based routing, hybrid persistent memory, tool safety policies, and optional smart home integration.

Canonical current-state technical documentation now lives in PLAN.md.

## Documentation

- Canonical current-state reference: PLAN.md
- Active improvements roadmap: IMPROVEMENTS_ROADMAP.md
- Architecture index: ARCHITECTURE.md
- Roadmap index: ROADMAP.md
- Documentation folder index: docs/README.md
- Historical artifacts: docs/archive/ROADMAP_ARTIFACT.md and docs/archive/FEATURE_TRACKER_ARTIFACT.md

## Linux Quick Start

1. Create and activate virtual environment:
   - python3 -m venv .venv
   - source .venv/bin/activate
2. Install dependencies:
   - python -m pip install --upgrade pip
   - python -m pip install -r requirements.txt
3. Configure environment variables in .env:
   - GROQ_API_KEY is required for cloud-orchestrated chat paths.
4. Run web app:
   - python run_companion.py
5. Open:
   - http://127.0.0.1:5000

## Common Commands

- Run CLI chat:
  - ./.venv/bin/python chat_cli.py
- Run tests:
  - ./.venv/bin/python -m pytest -q
- Run smoke checks:
  - ./.venv/bin/python scripts/smoke_daily_use.py

## Notes

- Python 3.11 or 3.12 is recommended.
- Windows bootstrap script still exists for Windows users: scripts/setup_python311.ps1.
- VS Code tasks are now cross-platform with Linux defaults and Windows overrides.
