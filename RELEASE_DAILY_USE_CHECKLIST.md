# Daily-Use Release Checklist

Use this checklist before marking a build as daily-use ready.

## 1) Environment & Startup

- [ ] Python is 3.11.x in `.venv`
- [ ] `pip install -r requirements.txt` completes without critical errors
- [ ] `python run_companion.py --web` starts cleanly on localhost
- [ ] `/api/health` returns `200` and includes memory + metrics payload

## 2) Security & Access

- [ ] `API_AUTH_TOKEN` is set for non-localhost usage
- [ ] Debug/admin endpoints reject missing or invalid token
- [ ] Sensitive actions (`/api/memory/clear`, `/api/debug/*`, `/api/shutdown`) require valid token
- [ ] Tool policy is reviewed (`TOOL_ALLOWLIST`) for the target environment

## 3) Memory & UX

- [ ] Memory reads/writes remain session/profile scoped
- [ ] Legacy memory migration still works for first scoped access
- [ ] Memory panel loads and supports refresh/search/edit/delete
- [ ] Settings panel actions (export/clear chat/clear memory) work as expected

## 4) Tools & Policy

- [ ] Expected tools run successfully under current allowlist
- [ ] Blocked tools return explicit allowlist denial message
- [ ] Blocked tool attempts appear in metrics telemetry (`tools.blocked`)

## 5) Validation

- [ ] Focused regression tests pass (`pytest -q tests/test_auth_guard.py tests/test_session_scoping.py tests/test_tools.py tests/test_models_endpoint.py tests/test_model_selection.py tests/test_routing_recent_endpoint.py`)
- [ ] Smoke script passes (`python scripts/smoke_daily_use.py`)
- [ ] Manual chat sanity check passes in web UI

## 6) Release Notes

- [ ] Roadmap artifact updated for completed sprint items
- [ ] User-facing behavior changes documented in `README.md`
- [ ] Known caveats and rollback notes recorded
