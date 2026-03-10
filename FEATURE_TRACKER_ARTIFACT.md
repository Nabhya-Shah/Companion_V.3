# Companion AI Feature Tracker

Date: 2026-03-10

This artifact tracks **user-visible functionality** progress in plain language.

## Architecture Status

| Component | State | Notes |
|-----------|-------|-------|
| Orchestrator | **Active** (`USE_ORCHESTRATOR=true` default) | Activated in P5-B with fallback resilience |
| Local Loops | Built, delegation path wired | Full orchestrator→loop routing done |
| Provider Architecture | **Groq-first hybrid** | Primary chat on Groq + local heavy specialist path; provider decision now locked back to Groq |
| Quick Tool Path | Not yet implemented | Still planned; now explicitly tied to Phase 7 provider-first reset |
| Unified Knowledge | **Single `knowledge.py` entry point** | P5-D merged backends, `remember()` / `recall()` |
| Persona Evolution | **Active with triggers** | P5-E: periodic, memory-event, session-end triggers wired |
| Web Layer | **Split into Flask Blueprints** | 7 blueprints in `companion_ai/web/` (P5-C) |
| LLM Interface | **Split into `llm/` package** | 5 submodules in `companion_ai/llm/` (P5-C) |
| Tools | **Split into `tools/` package** | 7 files in `companion_ai/tools/` (P5-C) |

## Current Provider Baseline

| Workload | Current Model / Provider | Planning Note |
|---|---|---|
| Primary chat + orchestrator | Groq `openai/gpt-oss-120b` | Current quality baseline to beat or retain as fallback |
| Fast tool execution | Groq `llama-3.1-8b-instant` | Good candidate for quick-tool bypass or replacement |
| Cloud vision | Groq `meta-llama/llama-4-maverick-17b-128e-instruct` | Streaming + multimodal parity matters for any replacement |
| Memory AI | Groq `meta-llama/llama-4-scout-17b-16e-instruct` | Could be reduced or relocated depending on Phase 7 outcome |
| Local heavy path | vLLM `Qwen/Qwen2.5-3B-Instruct` | Keep local capability regardless of provider changes |
| Local vision fallback | Ollama `llava:13b` | Remains useful even if primary cloud provider changes |

## Live Now

| ID | Feature | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| F-01 | Web chat + streaming replies | Chat in browser with live response updates | `/api/chat/send`, `/api/chat/stream` + manual chat check | ✅ Live |
| F-02 | Memory panel management | View/search/edit/delete/clear memories from UI | `/api/memory`, `/api/memory/fact/<id>`, `/api/memory/clear` | ✅ Live |
| F-03 | Session/profile memory isolation | No cross-thread/profile memory bleed | `tests/test_session_scoping.py` | ✅ Live |
| F-04 | Secure sensitive endpoints | Debug/admin actions require auth policy | `tests/test_auth_guard.py` | ✅ Live |
| F-05 | Tool safety allowlist | Block high-risk tools with clear denial reason | `tests/test_tools.py` + `/api/tools` | ✅ Live |
| F-06 | Health/models/routing visibility | Quick operational transparency | `/api/health`, `/api/models`, `/api/routing/recent` | ✅ Live |
| F-07 | Memory quality pipeline | Better confidence/provenance + conflict-aware recall | `tests/test_memory_quality_pipeline.py` | ✅ Live |

## Recently Completed

| ID | Feature | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| R-01 | Daily-use smoke checks | One command verifies core app health | `scripts/smoke_daily_use.py` | ✅ Completed |
| R-02 | Reliability setup path | Faster clean-machine startup success | `scripts/setup_python311.ps1` + release checklist | ✅ Completed |
| R-03 | Simplified memory/settings UX | Cleaner daily workflow with fewer confusing controls | `templates/index.html` + manual UI check | ✅ Completed |
| R-04 | Startup token-burn reduction | Fresh page load avoids hidden memory/brain work | No `/api/memory` or `/api/brain/files` hit on initial load | ✅ Completed |
| R-05 | Session-scoped Mem0 hardening | Memory stays isolated without auto-migration work on reads | `tests/test_session_scoping.py` + `tests/test_memory_quality_pipeline.py` | ✅ Completed |

## In Progress (Phase 3)

| ID | Feature | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| P3-00 | Day 0 memory fallback hardening | Memory writes survive model decommission paths | Fallback regression test + memory regressions | ✅ Completed |
| P3-01 | Skill/plugin registry with gating | Add capabilities safely with explicit controls | `/api/plugins` + plugin policy tests | ✅ Completed (MVP) |
| P3-02 | Sandbox execution modes | Background/restricted contexts stay safer | Restricted mode blocks high-risk tools | ✅ Completed (MVP) |
| P3-03 | Unified realtime control plane | Consistent task/tool/chat state updates in UI | SSE `event` + `payload` envelope + job updates | ✅ Completed (MVP) |
| P3-04 | Scheduled automations | Run recurring tasks automatically | `/api/schedules` + recurring enqueue loop | ✅ Completed (MVP) |
| P3-05 | Profile/workspace separation | Keep personal/work assistants separated | `workspace_id` scope for memory + brain paths | ✅ Completed (MVP) |
| P3-06 | Packaging/deployment profile | One-command local setup and health verification | `scripts/release_profile_check.py` + smoke pass | ✅ Completed (MVP) |

## Phase 3 Polish (Completed)

| ID | Feature | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| P3-P1 | Plugin ecosystem polish | Rich manifests, plugin metadata UI, safer overrides | `/api/plugins/catalog` + `/api/plugins/policy` + catalog metadata tests | ✅ Completed (Polish v1) |
| P3-P2 | Realtime UX polish | Better timeline visual states + event diagnostics | SSE `seq` tracking + `/api/events/diagnostics` + control-plane tests | ✅ Completed (Polish v1) |
| P3-P3 | Scheduler ergonomics | Human-friendly recurrence builder + retries/timezones | `cadence` input + timezone/retry fields + scheduler retry tests | ✅ Completed (Polish v1) |
| P3-P4 | Workspace UX polish | Explicit workspace/profile switcher and migration helpers | `/api/context/switch` + settings controls + scope switch tests | ✅ Completed (Polish v1) |

## Phase 4 (Completed)

| ID | Feature | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| P4-01 | File Handling V2 (batch + listing) | Upload many files quickly and manage uploaded files more easily | `/api/upload/batch`, `/api/upload/list`, `/api/brain/upload/batch` + `tests/test_phase4_file_workflow.py` | ✅ Slice 1 Completed |
| P4-02 | File Actions V2 (extract/summarize/search) | Quickly inspect uploaded files and pull useful content into chat | `/api/upload/extract`, `/api/upload/summarize`, `/api/upload/search` + knowledge tab action buttons + tests | ✅ Slice 2 Completed |
| P4-03 | Knowledge Workspace V2 (file management) | Manage indexed workspace docs with clear list metadata and delete controls | `/api/brain/files`, `/api/brain/file` + knowledge tab delete action + tests | ✅ Slice 3 Completed |
| P4-04 | Memory Review Center (bulk actions) | Review pending learned facts and approve/reject in batches | `/api/pending_facts/bulk` + pending facts inbox UI + `tests/test_phase4_memory_review.py` | ✅ Slice 4 Completed |
| P4-05 | Scheduler Management V2 (edit/delete) | Update and clean up recurring automations without manual DB resets | `PUT/DELETE /api/schedules/<id>` + jobs service edit/delete support + control-plane/tests | ✅ Slice 5 Completed |
| P4-06 | Automation UX V2 (task sidebar schedules) | Manage schedules directly from UI with fast pause/edit/delete actions | `static/app.js` tasks sidebar now renders schedules with toggle/edit/delete controls against `/api/schedules*` | ✅ Slice 6 Completed |
| P4-07 | Integration Controls V2 (plugin policy UI) | Enable/disable plugin capability groups directly in Settings without editing files manually | Settings plugin toggles + apply action wired to `/api/plugins/policy` + focused policy validation tests | ✅ Slice 7 Completed |
| P4-08 | Smart Home Reliability UX V2 | Show clear configured/connected status and setup guidance before room control actions | `/api/loxone/health` + Smart Home modal status banner + focused reliability endpoint tests | ✅ Slice 8 Completed |
| P4-09 | Smart Home Command Consistency | Keep local loop light-dim actions aligned with integration API to avoid hidden runtime failures | `ToolLoop._light_dim` now uses `set_brightness` + focused loop consistency tests | ✅ Slice 9 Completed |
| P4-10 | Automation Policy Visibility | Surface when a scheduled tool is blocked by current policy so automations don’t fail silently | Schedule payload policy flags + warning label in Tasks sidebar + focused policy tests | ✅ Slice 10 Completed |
| P4-11 | Smart Home Quick Controls UX | Control all lights and refresh status from modal with clearer success/error feedback | Smart Home modal `All On/All Off/Refresh` controls + toast feedback + focused all-lights route tests | ✅ Slice 11 Completed |
| P4-12 | Automation Creation UX | Create recurring automations directly from Tasks sidebar without using API clients | Tasks sidebar `+ Schedule` action + create flow (`POST /api/schedules`) + cadence validation coverage | ✅ Slice 12 Completed |
| P4-13 | Automation Observability UX | See richer schedule state (next run + failures) and preserve schedule tool args on edit/list flows | Jobs schedule payload parses `tool_args` as dict + Tasks sidebar shows next run/failure details + focused jobs tests | ✅ Slice 13 Completed |
| P4-14 | Automation Run-Now UX | Trigger an automation immediately from the schedule card and get instant enqueue feedback | `POST /api/schedules/<id>/run` + Tasks sidebar `Run now` action + focused control-plane/jobs tests | ✅ Slice 14 Completed |
| P4-15 | Automation Policy Enforcement | Prevent blocked schedules from enqueuing and surface policy-denied reason directly in schedule failure state | Scheduler/run-now policy pre-check via `evaluate_tool_policy(..., mode='restricted')` + policy-denied API handling + focused policy execution tests | ✅ Slice 15 Completed |

## Notes

- **Roadmap source-of-truth:** `ROADMAP.md`
- **Archived roadmap detail:** `ROADMAP_ARTIFACT.md`
- **Architecture source-of-truth:** `ARCHITECTURE.md`
- **Feature source-of-truth:** this file
- Update both when a feature moves status.

## Planned Next Window (Phase 7 Execution)

| ID | Feature / Initiative | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| P7-01 | Provider abstraction baseline | Makes future provider changes safer and less disruptive | Provider seam map + documented adapter surface in roadmap | ✅ Research completed |
| P7-02 | Provider shortlist + benchmark gate | Improves chances of lowering cost or raising quality without regressions | Focused benchmark run completed; Groq retained as default | ✅ Decision completed |
| P7-03 | Quick Tool Path | Faster simple answers without paying orchestrator cost every time | Direct lightweight tool route + focused tests | 🟡 Planned |
| P7-04 | Memory extraction completion | Reliable local fact extraction instead of placeholder behavior | `MemoryLoop._extract()` backed by real model call + regression tests | 🟡 Planned |

## Phase 7 Outcome Snapshot

| Rank | Option | Why it matters now | Current recommendation |
|---|---|---|---|
| 1 | Groq | Best overall fit after focused benchmark tie-break by latency and existing architecture | Ship as default |
| 2 | Mistral | Closest viable backup if a second provider is needed later | Keep as paper fallback only |
| 3 | Gemini | Worked, but too slow to justify default-path complexity right now | Defer |

## Phase 5 (Completed)

| ID | Feature | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| P5-01 | Dead code removal | Cleaner codebase, fewer confusing paths | No references to removed functions, tests pass | ✅ Completed (P5-A) |
| P5-02 | Legacy chat endpoint removal | Single clear chat path (SSE only) | `/api/chat` returns 404, `/api/chat/send` works | ✅ Completed (P5-A) |
| P5-03 | Compatibility shim consolidation | Direct imports, no re-export wrappers | 5 shim files deleted, all imports updated | ✅ Completed (P5-A) |
| P5-04 | Orchestrator activation | Every message routed intelligently | `USE_ORCHESTRATOR=true` default, 40 routing tests pass | ✅ Completed (P5-B) |
| P5-05 | Web blueprint split | Cleaner server code, easier navigation | Same endpoints, `web/` directory structure, 120 tests pass | ✅ Completed (P5-C) |
| P5-06 | Tools directory split | Modular tool organization | Same tool surface, `tools/` directory structure, 120 tests pass | ✅ Completed (P5-C) |
| P5-07 | LLM directory split | Separated provider concerns | Same LLM behavior, `llm/` directory structure, 120 tests pass | ✅ Completed (P5-C) |
| P5-08 | Unified knowledge system | Single `remember`/`recall` API for all memory backends | `knowledge.py` entry point, confidence-based facts, 144 tests pass | ✅ Completed (P5-D) |
| P5-09 | Persona foundation | Personality evolves with use, not just on shutdown | `PersonaState` singleton, 3 trigger types, orchestrator integration, 178 tests pass | ✅ Completed (P5-E) |

## Base (Phase 6) — Daily-Life Intelligence (Completed)

| ID | Feature | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| P6-01 | Workflow engine | Run multi-step routines (Morning Briefing) via API | `WorkflowManager` parses JSON steps and executes sequentially | ✅ Complete (P6-A) |
| P6-02 | Routines UI Panel | One-click access to daily automations | User can launch a Workflow from the Web UI manually | ✅ Complete (P6-A) |
| P6-03 | Human-In-The-Loop Approval | Prevents dangerous tools from running without permission | UI shows [Approve/Deny] prompt for `requires_approval` tools | ✅ Complete (P6-B) |
| P6-04 | Task Planning Transparency | Shows the steps the AI commits to before it runs them | Chat UI shows Queued -> In-Progress progress tracker via SSE plan events | ✅ Complete (P6-C) |
| P6-05 | Proactive Insights Engine | Companion surfaces timely digests and reminders without explicit prompting | `services/insights.py` + `/api/insights*` + unread header badge + offline chat injection via `/api/chat/history` + `tests/test_insights.py` | ✅ Complete (P6-D) |
