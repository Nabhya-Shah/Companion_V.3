# Companion V3 Unified Reference

Status: Canonical current-state document
Last updated: 2026-03-31
Primary platform: Linux (Pop!_OS / Ubuntu-class)

## 1. Documentation Model

Companion documentation is now centralized into two canonical files:

1. PLAN.md (this file): current implementation truth, feature inventory, architecture, operations, validation, and known gaps.
2. ROADMAP.md: future delivery plan, milestone sequencing, and NEW.md strategy integration.

All other documentation/planning markdown files should be treated as index pointers or historical archives.

## 2. Product Purpose

Companion V3 is a web-first personal assistant platform built to be dependable for daily use.

Core product goals:

1. Orchestrator-led request routing.
2. Trustworthy long-horizon memory with provenance.
3. Safe tool execution with policy gating and approvals.
4. Session/profile/workspace isolation.
5. Practical workflows, scheduling, and continuity support.

## 3. Current Feature Inventory

Legend:

- Live: implemented and available in current app.
- Beta/Partial: available but still being hardened.
- Planned: roadmap item not yet shipped.

| Capability Area | Status | What Exists Today | Key Files |
|---|---|---|---|
| Web chat + SSE streaming | Live | Streaming responses, history stream, stop control, diagnostics | companion_ai/web/chat_routes.py, static/chat.js |
| Orchestrator routing | Live | answer, delegate, plan, background, memory_search actions | companion_ai/orchestrator.py |
| Specialist loops | Live | memory loop, tool loop, vision loop | companion_ai/local_loops/ |
| Hybrid memory | Live | Mem0 + SQLite + brain index via unified recall/remember entry points | companion_ai/memory/knowledge.py |
| Memory quality pipeline | Live | confidence labels, pending review, dedup/provenance tracking | companion_ai/memory/sqlite_backend.py, companion_ai/memory/ai_processor.py |
| Retrieval observability | Live | retrieval stage traces and SSE stage events | companion_ai/memory/knowledge.py, companion_ai/conversation_manager.py |
| Tool governance and approvals | Live | allowlists, sandbox mode, risk tiers, approval queue | companion_ai/tools/registry.py |
| Session/profile/workspace scoping | Live | scoped IDs, permission gating by workspace | companion_ai/web/state.py |
| Files/brain knowledge workflows | Live | uploads, extraction, summaries, search, indexing | companion_ai/web/files_routes.py, companion_ai/brain_index.py |
| Jobs/schedules/workflows | Live | schedule CRUD, run-now, task plans, workflow execution | companion_ai/services/jobs.py, companion_ai/services/task_planner.py |
| Persona/insights/continuity | Live | adaptive persona, proactive insights, continuity snapshots | companion_ai/services/persona.py, companion_ai/services/insights.py, companion_ai/services/continuity.py |
| Smart home (Loxone) | Beta/Partial | health + core light control paths | companion_ai/web/loxone_routes.py, companion_ai/integrations/loxone.py |
| Browser/computer-use | Beta/Partial | core pathways exist; hardening and strict safety rollout in roadmap | companion_ai/tools/browser_tools.py, companion_ai/local_loops/tool_loop.py |
| Multi-user throughput hardening | Planned | dedicated concurrency/load hardening not complete | ROADMAP.md |

## 4. Runtime Architecture (Current)

### 4.1 Entrypoints

1. run_companion.py: unified launcher.
2. web_companion.py: compatibility shim for tests/imports.
3. companion_ai/web/__init__.py: Flask app factory, blueprint registration, worker startup.

### 4.2 Request Lifecycle (Chat)

1. Client sends message to /api/chat/send.
2. Security and scope are resolved in companion_ai/web/state.py.
3. ConversationSession.process_message_streaming builds context and delegates to orchestrator when enabled.
4. Orchestrator decides action (answer/delegate/plan/background/memory_search).
5. Loop/tool/memory outputs are merged and streamed back over SSE.
6. Token metadata, retrieval stage events, and memory-save status are attached to stream payloads.

### 4.3 Design Rule

Orchestrator decides, loops execute, memory layer stores/retrieves, and web layer streams + enforces policy.

## 5. Memory and Knowledge Model (Current)

Companion uses a hybrid approach:

1. Mem0: semantic/vector memory backend.
2. SQLite: profile facts, summaries, insights, pending review facts, quality/provenance ledger.
3. Brain index: document chunk indexing/search.
4. Unified API: companion_ai/memory/knowledge.py (remember, recall, recall_with_trace).

Quality controls currently in place:

1. Confidence scoring + labels.
2. Pending-review queue for low-confidence extractions.
3. Dedup and contradiction metadata support.
4. Retrieval stage trace generation for explainability.

## 6. Safety and Governance Model (Current)

Tool execution is policy-first:

1. Tool allowlist and plugin allowlist controls.
2. Risk-tier metadata (low, medium, high).
3. Approval-required flow for high-risk tools.
4. Restricted sandbox mode with blocked tool list.
5. Workspace feature permissions (tools_execute, memory_write, workflows_run, files_upload, retrieval_connectors).

## 7. Web and API Surface (Current)

Primary route groups:

1. Chat/streaming: companion_ai/web/chat_routes.py
2. Memory/review: companion_ai/web/memory_routes.py
3. Files/brain: companion_ai/web/files_routes.py
4. Tools/policies/approvals: companion_ai/web/tools_routes.py
5. System/jobs/diagnostics: companion_ai/web/system_routes.py
6. Media/vision: companion_ai/web/media_routes.py
7. Smart home: companion_ai/web/loxone_routes.py
8. Workflows: companion_ai/web/workflow_routes.py

Frontend modules:

1. static/app.js bootstraps modules.
2. static/chat.js handles stream and rendering.
3. static/memory.js handles memory and insights UI.
4. static/tasks.js handles tasks/schedules/workflows UI.
5. static/settings.js and static/smarthome.js cover settings and smart home controls.

## 8. Operations Runbook

### 8.1 Setup

1. python3 -m venv .venv
2. source .venv/bin/activate
3. python -m pip install --upgrade pip
4. python -m pip install -r requirements.txt

### 8.2 Run

1. Web app: python run_companion.py
2. CLI chat: ./.venv/bin/python chat_cli.py

### 8.3 Tests

1. Full suite: ./.venv/bin/python -m pytest -q
2. Targeted example: ./.venv/bin/python -m pytest tests/test_orchestrator.py tests/test_workflows.py -q
3. Watchdog runner: ./.venv/bin/python tools/pytest_watchdog.py --idle-timeout 0 --max-duration 600 -- -q

### 8.4 Daily-use Release Checklist

1. Web app starts and /api/health returns 200.
2. Auth policy validated for protected endpoints.
3. Memory reads/writes remain scoped and consistent.
4. Tool allowlist behavior checked (allowed + blocked paths).
5. Focus regression tests pass before release.
6. Smoke script passes: ./.venv/bin/python scripts/smoke_daily_use.py

## 9. Validation Snapshot

Last documented full-suite baseline (from prior recorded run):

1. 287 passed
2. 1 skipped
3. 0 failed

Important: treat this as a historical baseline. Re-run tests after significant changes.

Recent live validation artifacts (2026-04-08):

1. OFF lane real UI pre-restart: `data/benchmarks/webchat_off_real_pre_2026-04-08.json`
2. OFF lane real UI post-restart: `data/benchmarks/webchat_off_real_post_2026-04-08.json`
3. ON lane real UI pre-restart: `data/benchmarks/webchat_on_real_pre_2026-04-08.json`
4. ON lane real UI post-restart: `data/benchmarks/webchat_on_real_post_2026-04-08.json`
5. Aggregated comparison: `data/benchmarks/webchat_off_on_real_compare_2026-04-08.json`

Observed outcomes from this run:

1. Both OFF and ON lanes achieved 100% request success in tested UI flows.
2. No `429` / “too many requests” responses were observed.
3. No “trouble connecting to my brain” fallback responses were observed after key wiring.
4. Strict post-restart recall hit rate favored OFF in this specific run.

## 10. Known Gaps and Active Risks

Highest-impact current gaps:

1. Concurrency/load validation needs deeper coverage.
2. Live provider contract checks (non-mocked) should be expanded.
3. Browser/computer-use path needs stricter hardening and observability.
4. Operability improvements needed for throughput and diagnostics at scale.
5. timezone-aware datetime cleanup remains open in multiple modules.

These are tracked in ROADMAP.md.

## 11. Documentation Governance

Rules:

1. Update PLAN.md for any shipped behavior/architecture change.
2. Update ROADMAP.md for any plan/scope/prioritization change.
3. Keep index/pointer docs lightweight and non-duplicative.
4. Move superseded long-form planning docs into docs/archive.

## 12. Canonical and Archive Links

Canonical:

1. PLAN.md (current-state truth)
2. ROADMAP.md (future plan and milestones)

Indexes:

1. README.md (onboarding + canonical links)
2. ARCHITECTURE.md (architecture pointer)
3. IMPROVEMENTS_ROADMAP.md (roadmap pointer)
4. docs/README.md (docs folder index)

Archives:

1. docs/archive/ROADMAP_ARTIFACT.md
2. docs/archive/FEATURE_TRACKER_ARTIFACT.md
3. docs/archive/PLAN_B_BLUEPRINT_ARCHIVE.md
4. docs/archive/IMPLEMENTATION_SPEC_REPO_INSIGHTS_ARCHIVE.md
5. docs/archive/RELEASE_DAILY_USE_CHECKLIST_ARCHIVE.md
