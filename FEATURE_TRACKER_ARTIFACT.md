# Companion AI Feature Tracker

Date: 2026-02-20

This artifact tracks **user-visible functionality** progress in plain language.

## Architecture Status

| Component | State | Notes |
|-----------|-------|-------|
| Orchestrator | Built, dormant (`USE_ORCHESTRATOR=false`) | Phase 5 activates as default |
| Local Loops | Built, never invoked in default flow | Phase 5 wires to orchestrator |
| Quick Tool Path | Not yet implemented | Phase 5 adds Groq zero-shot routing |
| Unified Knowledge | 5 separate backends | Phase 5 merges into single interface |
| Persona Evolution | Service exists, minimal wiring | Phase 5 audits and connects to orchestrator |

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

- **Roadmap source-of-truth:** `ROADMAP_ARTIFACT.md`
- **Architecture source-of-truth:** `ARCHITECTURE.md`
- **Feature source-of-truth:** this file
- Update both when a feature moves status.

## Phase 5 — Architecture Activation & Spring Clean (In Progress)

| ID | Feature | User Value | Acceptance Signal | Status |
|---|---|---|---|---|
| P5-01 | Dead code removal | Cleaner codebase, fewer confusing paths | No references to removed functions, tests pass | ⏳ Not started |
| P5-02 | Legacy chat endpoint removal | Single clear chat path (SSE only) | `/api/chat` returns 404, `/api/chat/send` works | ⏳ Not started |
| P5-03 | Compatibility shim consolidation | Direct imports, no re-export wrappers | Shim files deleted, all imports updated | ⏳ Not started |
| P5-04 | Orchestrator activation | Every message routed intelligently | `USE_ORCHESTRATOR=true` default, routing tests pass | ⏳ Not started |
| P5-05 | Local loop wiring | Specialist tasks delegated to local models | DELEGATE decisions invoke correct loop | ⏳ Not started |
| P5-06 | Quick tool path | Fast zero-shot tool calls via Groq | Simple tool calls don't hit local models | ⏳ Not started |
| P5-07 | Web blueprint split | Cleaner server code, easier navigation | Same endpoints, `web/` directory structure | ⏳ Not started |
| P5-08 | Tools directory split | Modular tool organization | Same tool surface, `tools/` directory structure | ⏳ Not started |
| P5-09 | LLM directory split | Separated provider concerns | Same LLM behavior, `llm/` directory structure | ⏳ Not started |
| P5-10 | Unified knowledge interface | One "remember/recall" regardless of backend | Single entry point for all knowledge ops | ⏳ Not started |
| P5-11 | Persona orchestrator integration | Companion personality in every response | Persona traits reflected in orchestrator context | ⏳ Not started |
