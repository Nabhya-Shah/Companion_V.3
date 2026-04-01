# Companion V3

Companion V3 is a web-first personal AI assistant with orchestrator-based routing, hybrid memory, policy-gated tools, workflows, and optional smart-home integration.

## Canonical Docs

Documentation and planning are centralized:

1. PLAN.md: canonical current-state reference (architecture, features, operations, validation, known gaps).
2. ROADMAP.md: canonical future plan (priorities, milestones, NEW.md strategy integration).

Supporting docs are index/archive only.

## Quick Start (Linux)

1. python3 -m venv .venv
2. source .venv/bin/activate
3. python -m pip install --upgrade pip
4. python -m pip install -r requirements.txt
5. Configure environment variables in .env (GROQ_API_KEY required for cloud-orchestrated paths)
6. python run_companion.py
7. Open http://127.0.0.1:5000

## Common Commands

1. CLI chat: ./.venv/bin/python chat_cli.py
2. Full tests: ./.venv/bin/python -m pytest -q
3. Smoke checks: ./.venv/bin/python scripts/smoke_daily_use.py
4. Production WSGI serve: ./.venv/bin/gunicorn -c gunicorn.conf.py wsgi:app

## Notes

1. Python 3.11 or 3.12 is recommended.
2. Windows setup script remains available at scripts/setup_python311.ps1.
