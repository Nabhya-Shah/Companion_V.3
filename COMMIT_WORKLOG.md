# Commit Worklog (Async Jobs + SSE + Local Computer/Vision)

## What Changed
- Added a SQLite-backed background job system (`data/jobs.db`) with a worker thread.
- Replaced chat/job polling with Server-Sent Events (SSE) to stop HTTP spam.
- Enforced **local-only** computer control for background jobs via Ollama.
- Hardened the local (Ollama) JSON tool loop to prevent “completed with refusal/plain-text” results.
- Added stop/cancel so computer/background work can be halted immediately.
- Made the “Computer Control Active” banner reflect **recent activity**, not mere availability.
- Enabled **always-on local vision** via Ollama (`minicpm-v`) when configured.

## Key Files
- Backend
  - `companion_ai/job_manager.py`: job DB + worker + cancellation + stale-job cleanup.
  - `companion_ai/tools.py`: `start_background_task` tool; `use_computer` marks activity.
  - `companion_ai/llm_interface.py`: tool schema filtering; background-mode tool execution; local JSON tool loop hardening; early return after scheduling.
  - `companion_ai/local_llm.py`: `OllamaClientWrapper` (OpenAI-ish interface) for local execution.
  - `companion_ai/vision_manager.py`: optional local vision backend + screenshot->Ollama vision path.
  - `web_companion.py`: starts worker on boot; SSE endpoints for chat/jobs + computer status; stop cancels jobs; Windows log-file lock tolerance; `/api/shutdown`.
- Frontend
  - `static/app.js`: SSE `/api/chat/stream` (history + job updates); shutdown button.
  - `static/computer-control.js`: SSE `/api/computer/stream` with slow polling fallback.
  - `templates/index.html`: added shutdown button.

## Config / Env Notes
- `.env` is git-ignored.
- Local vision:
  - `USE_LOCAL_VISION=1`
  - `LOCAL_VISION_MODEL=minicpm-v`
- Local background tool model currently used: `qwen2.5-coder:7b` (fallback from local `llama3.1` instability on this machine).
- Mem0 prefers `GROQ_MEMORY_API_KEY` when set.

## How To Verify
- Start web:
  - VS Code task: `start-web-with-logs` (recommended)
- Quick manual checks:
  - Send a request that triggers a background computer job (e.g., “open an online notepad and type …”).
  - Confirm job completion toast + system message result arrives via SSE.
  - Confirm banner only appears when actions occur; STOP cancels jobs.
- Tests:
  - VS Code task: `run-pytests`

## Git Hygiene Checklist
- Confirm no secrets tracked (keys should only exist in local `.env`).
- Confirm `data/` artifacts aren’t being committed (repo `.gitignore` covers this).

## Suggested Commit Breakdown (Optional)
- `feat(web): add SSE for chat + job updates`
- `feat(jobs): add sqlite job queue + worker + cancel/stale cleanup`
- `feat(local): enforce local computer control + harden Ollama tool loop`
- `feat(vision): add local Ollama vision backend`
