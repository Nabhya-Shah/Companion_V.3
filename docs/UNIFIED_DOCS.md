# Companion V3 - Unified Documentation

This document serves as the master, comprehensive reference for the Companion V3 project. It combines architectural overviews, folder guides, operational policies, and project state information into a single text.

## 1. Product Purpose & Quick Start
Companion V3 is a web-first personal AI assistant built to be dependable for daily use.
**Core goals:**
* Orchestrator-led request routing.
* Trustworthy long-horizon memory with provenance.
* Safe tool execution with policy gating and approvals.
* Session/profile/workspace isolation.
* Practical workflows, scheduling, and continuity support.

### Quick Start (Linux)
1. `python3 -m venv .venv`
2. `source .venv/bin/activate`
3. `python -m pip install --upgrade pip`
4. `python -m pip install -r requirements.txt`
5. Configure environment variables in `.env` (GROQ_API_KEY required for cloud-orchestrated paths)
6. `python run_companion.py`
7. Open `http://127.0.0.1:5000`

### Common Commands
* CLI chat: `./.venv/bin/python chat_cli.py`
* Full tests: `./.venv/bin/python -m pytest -q`
* Smoke checks: `./.venv/bin/python scripts/smoke_daily_use.py`
* Production run: `./.venv/bin/gunicorn -c gunicorn.conf.py wsgi:app`

---

## 2. Codebase Organization & Package Map

### Top-Level Folders
* `run_companion.py`: Main launcher for the app.
* `companion_ai/`: Application backend logic.
* `static/`: Frontend JS/CSS assets.
* `templates/`: HTML templates for the UI.
* `BRAIN/` & `data/`: Runtime directories for your personal notes, memories, logs, and database files.
* `tests/`, `scripts/`, `tools/`: Utility logic and probes.

### `companion_ai/` Subsystems
1. `web/`: Flask app factory and HTTP routes.
2. `llm/`: provider clients, routing, token tracking.
3. `memory/`: memory backends (Mem0, SQLite), quality pipeline, write queue.
4. `tools/`: callable tools and tool-policy execution surface.
5. `services/`: workflows, jobs, persona, insights, continuity.
6. `local_loops/`: specific skill/agent loop executors (e.g. tool loop, memory loop).
7. `orchestration/` & `runtime/`: conversation session, deterministic orchestrator, computer bridging.
8. `brain/`: brain-file manager and semantic brain index.

*Compatibility Modules:* Note that root-level files in `companion_ai/` (like `orchestrator.py`, `computer_agent.py`) are shims intended for legacy hook preservation; real implementations live within `runtime/` and `brain/`.

---

## 3. Current Runtime Architecture

### Flow
1. Client sends message to `/api/chat/send`.
2. Security and scope are resolved in `companion_ai/web/state.py`.
3. `ConversationSession.process_message_streaming` builds context, delegating to the *Orchestrator*.
4. Orchestrator decides on an action mode: answer, delegate, plan, background, or memory_search.
5. Local Loop (tool, memory, vision) outputs are merged and natively streamed back over SSE alongside trace events and metadata.

### Model Tiers
* `LOCAL_CHAT_PROVIDER` manages fallback behavior. If set to `local_primary` but the local target fails, tests and logic currently allow fallback strictly according to policies.
* The system is modular enough that 120B reasoning models orchestrate, and smaller targeted local models act as loop executors/summarizers.

### Memory & Knowledge Model
1. **Mem0:** Semantic vector memory for associative queries.
2. **SQLite:** Profile facts, explicit insights, and provenance/quality ledgers.
3. **Brain Index:** Chunked textual document retrieval.
4. **Governed Extraction:** Memory writes must pass quality pipelines featuring confidence scoring, contradiction detection, and pending-review queues.

---

## 4. Safety & Governance Policies

1. Tool definitions exist inside `companion_ai/tools/registry.py` and are decorated by `risk_tier` and `requires_approval`.
2. The system leverages extensive Policy gating: `TOOL_ALLOWLIST`, `PLUGIN_ALLOWLIST`, Sandbox modes, and manual Approval queues.
3. Operations that write inside the memory "brain" restrict filesystem traversal securely (`_validate_path` checks).
4. System-level desktop interaction (`xdotool`, `Playwright`) exists inside `companion_ai/runtime/computer.py` but is **currently under active review for sandboxing improvements to mitigate Remote Code Execution (RCE) via shell injection.**

---

## 5. Operations & Validation Runbook
* Root files must adhere to `ROOT_STRUCTURE_POLICY.md` (no scratch scripts, no temporary `.md` files).
* Testing baseline mandates zero regressions on core functionality like loop execution, runtime fallback toggling, and memory deduplication. 
* Any new tool addition must explicitly define a risk tier, and any structural behavior modifications require updates to tests and roadmaps.