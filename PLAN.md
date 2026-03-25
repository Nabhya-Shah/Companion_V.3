# Companion V3 Unified Technical Reference

Status: Canonical documentation source
Last updated: 2026-03-25
Primary platform: Linux (Pop!_OS / Ubuntu-class distros)

## 1. Purpose and Scope

This file is the single source of truth for Companion V3 architecture, operations, validation status, and roadmap direction.

It supersedes overlapping details that previously lived in multiple docs. Other docs should link here instead of duplicating technical state.

## 2. What Companion V3 Is

Companion V3 is a web-first personal assistant platform with:

- A cloud orchestrator that decides how each message is handled.
- Local specialist loops for memory, tools, and vision tasks.
- Hybrid persistent memory and retrieval (Mem0 + SQLite + brain document index).
- Policy-gated tool execution and optional human approval flows.
- Session/profile/workspace scoped state.
- Optional smart home integration.

Design rule: orchestrator controls routing, loops execute, storage is managed through unified memory pathways.

## 3. Runtime Architecture (Validated)

### 3.1 Entry and Serving

- Web entrypoint: run_companion.py
- Web compatibility shim: web_companion.py
- App factory and blueprints: companion_ai/web/__init__.py

Primary runtime path:

1. User sends message to /api/chat/send (SSE).
2. Session state is resolved in companion_ai/web/state.py.
3. ConversationSession process_message_streaming is called.
4. If USE_ORCHESTRATOR=true (default), companion_ai/orchestrator.py routes to:
   - direct answer
   - delegated loop
   - plan execution
   - background path
   - memory search
5. Response is streamed to UI with metadata and retrieval stage events where available.
6. Memory save is queued/asynchronous where appropriate.

### 3.2 Core Modules

- Orchestrator: companion_ai/orchestrator.py
- Session manager: companion_ai/conversation_manager.py
- LLM router/providers: companion_ai/llm/
- Tool registry/policy: companion_ai/tools/registry.py
- Local loops: companion_ai/local_loops/
- Memory stack: companion_ai/memory/
- Web APIs: companion_ai/web/
- Services (jobs/workflows/persona/insights/token budget): companion_ai/services/

## 4. Memory and Knowledge System

Companion currently uses a hybrid memory model:

- Mem0 backend for vector-style memory writes and semantic retrieval.
- SQLite for profile facts, pending review facts, summaries, insights, and quality/provenance ledger.
- Brain document index for uploaded/brain files and chunk search.
- Unified entry points in companion_ai/memory/knowledge.py:
  - remember
  - recall
  - recall_with_trace

Quality controls implemented:

- Confidence labels and thresholds.
- Pending-review workflow for low confidence facts.
- Dedup and contradiction metadata.
- Retrieval stage tracing and score explainability fields.

## 5. Tools and Safety Model

Tool execution is centralized through companion_ai/tools/registry.py with:

- Plugin allowlists.
- Tool allowlists.
- Restricted sandbox mode with blocked tool set.
- Per-tool risk metadata.
- Human approval queue and resolve endpoints.

Remote action tooling is simulator-first and policy-gated.

## 6. Linux Migration Status

As of this update, the repository is Linux-ready for core development workflows.

Completed migration work:

- VS Code tasks now support Linux-native venv paths with Windows overrides.
- Browser-control helper in tool loop is now cross-platform and no longer Windows-only.
- Browser agent executable detection now supports Linux/macOS/Windows candidate paths.
- Brain index filename extraction is now OS-agnostic (basename).
- Windows-specific wording removed from local inference error messaging.
- Brain manager path example text made OS-neutral.

Known remaining portability caveats:

- scripts/setup_python311.ps1 remains Windows-only by design.
- Some external tooling assumptions (Playwright browser binaries, optional local LLM servers) remain environment-dependent.

## 7. Validation Status (Executed on Linux)

Automated verification completed in this workspace:

- Targeted core tests: orchestrator, workflows, memory quality, jobs service, retrieval stage events.
- Full test suite run.

Current result:

- 287 passed
- 1 skipped
- 0 failed

Observed warnings:

- Deprecation warnings for datetime.utcnow usage in several modules.
- These are non-blocking but should be modernized to timezone-aware datetime APIs.

## 8. Operations Runbook (Linux)

### 8.1 Environment

- Python: 3.11 or 3.12 recommended.
- Create venv:
  - python3 -m venv .venv
  - ./.venv/bin/python -m pip install --upgrade pip
  - ./.venv/bin/python -m pip install -r requirements.txt

### 8.2 Run

- Web app:
  - ./.venv/bin/python run_companion.py

- CLI chat:
  - ./.venv/bin/python chat_cli.py

### 8.3 Tests

- Full suite:
  - ./.venv/bin/python -m pytest -q

- Example targeted suite:
  - ./.venv/bin/python -m pytest tests/test_orchestrator.py tests/test_workflows.py -q

## 9. API Surface (High-Level)

Main blueprints and route groups:

- Chat and streaming: companion_ai/web/chat_routes.py
- Memory and fact review: companion_ai/web/memory_routes.py
- Files and brain uploads/search: companion_ai/web/files_routes.py
- Tools, policies, approvals, context: companion_ai/web/tools_routes.py
- System, jobs, schedules, continuity, diagnostics: companion_ai/web/system_routes.py
- Media and vision: companion_ai/web/media_routes.py
- Smart home: companion_ai/web/loxone_routes.py
- Workflow execution endpoints: companion_ai/web/workflow_routes.py

## 10. Frontend Surface (High-Level)

Modules in static:

- app.js bootstraps all panels.
- chat.js handles message stream, pipeline rendering, retrieval stage display.
- tasks.js handles tasks/schedules/workflows approvals UI.
- memory.js handles facts, pending review, insights.
- settings.js handles models/metrics/tokens/budget UI.
- smarthome.js handles room control interactions.

## 11. Roadmap Direction

Priority remains practical and safe agentic capability growth on top of stable core behavior:

1. Strengthen browser-session workflows and observability.
2. Incrementally improve computer-use pathways with strict safety controls.
3. Keep memory quality and provenance explainability robust.
4. Reduce technical debt warnings (timezone-aware datetime, stale docs prevention).

## 12. Documentation Policy

To prevent drift:

- PLAN.md is canonical for architecture and operational truth.
- README.md is onboarding-oriented and links here.
- ARCHITECTURE.md and ROADMAP.md are index documents that point to relevant PLAN sections.
- Artifact docs under docs/archive remain historical and should not be treated as current architecture state.

## 13. Historical Notes

This repository previously carried planning content aligned to an external Hermes/OpenWebUI-first stack in PLAN.md. That content is now archived by replacement in favor of repository-actual implementation truth.
