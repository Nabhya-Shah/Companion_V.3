# Companion AI Roadmap (Post-Phase 1)

Date: 2026-02-20

## Current Status

- ✅ Phase 1 (Quick Wins) complete:
  - Runtime reliability restored (`run_companion.py`, legacy compatibility shims)
  - Core security baseline added (localhost-or-token API guard)
  - Python environment migrated to 3.11 with automated setup script
  - Focused regression tests passing on Python 3.11

## Tracking Views

- Execution roadmap: this file
- Feature-first tracker: `FEATURE_TRACKER_ARTIFACT.md`

## Phase 2 (Month 1-2): Core Features for Daily Use

Goal: Make the assistant reliable, safe, and genuinely useful every day.

| Task | Effort | Dependencies | Success Criteria |
|---|---:|---|---|
| Session-scoped memory model | 1-2 weeks | Existing memory backends | Memories are isolated by session/user channel; no cross-thread bleed |
| Memory quality pipeline | 1-2 weeks | Session scoping | Better recall precision; fewer duplicate/contradictory facts in UI |
| API hardening pass | 1 week | Current security baseline | Debug/ops endpoints fully gated; auth behavior consistent on all routes |
| Web UI simplification | 1-2 weeks | Stable endpoints | Fewer clicks for core chat/memory actions; no duplicate/confusing controls |
| Tool safety policy | 1 week | Tool registry | High-risk tools require explicit allowlist + clear user-visible denial messages |
| Reliability + test expansion | 1-2 weeks | Above tasks | Integration tests for chat/memory/security pass consistently in CI/local |

### Phase 2 Priority Order

1. Session-scoped memory model
2. API hardening pass
3. Memory quality pipeline
4. Web UI simplification
5. Tool safety policy
6. Reliability + test expansion

### Phase 2 Deliverables

- Stable “daily companion” mode with:
  - Predictable memory recall
  - Safe localhost defaults
  - Clean UI for chat + memory
  - Clear error handling and recovery behavior

## Phase 3 (Month 3-6): Advanced Capabilities

Goal: Move from “good chat app” to “assistant platform”.

| Task | Effort | Dependencies | Success Criteria |
|---|---:|---|---|
| Skill/plugin registry with gating | 2-4 weeks | Tool safety policy | Pluggable skills with env/bin checks and workspace override precedence |
| Sandbox execution modes | 2-4 weeks | Registry + policy | Non-main contexts execute with stricter restrictions |
| Unified realtime control plane | 3-5 weeks | Stable APIs | Loops/tools/UI share one event stream model with clear state transitions |
| Scheduled automations (cron-style) | 1-2 weeks | Control plane | User can configure recurring tasks reliably |
| Profile/workspace separation | 2-3 weeks | Session memory model | Distinct memory + settings profiles (personal/work/etc.) |
| Packaging/deployment profile | 1-2 weeks | Core stability | Reproducible local deploy with one-command setup and health checks |

## Architecture Direction

- **Orchestrator-first**: every message flows through the cloud orchestrator (Groq primary).
- **Local specialists**: Ollama loops for memory, tools, vision — autonomous execution, orchestrator-controlled state.
- **Unified knowledge**: merge brain + uploads + fact store into one recall interface.
- **Persona as differentiator**: evolving personality, not just a chat wrapper.
- **Policy-driven safety**: tools, plugins, automations respect explicit controls.
- **Local-first**: no cloud dependency except Groq for primary chat.
- **Split monoliths**: `web_companion.py` → blueprints, `tools.py` → directory, `llm_interface.py` → directory.
- **Remove dead paths**: legacy chat, vestigial configs, unused compatibility shims.

## Immediate Sprint Plan (Next 2 Weeks)

### Sprint A (Week 1)

- [x] Implement session key model (`session_id`, `channel_id`, `profile_id`) in memory writes/reads
- [x] Add migration logic for legacy memory rows
- [x] Add tests for memory isolation and retrieval correctness
- [x] Lock all debug/ops endpoints behind auth guard explicitly

### Sprint B (Week 2)

- [x] Simplify settings + memory panels in UI
- [x] Add safe tool allowlist with blocked-tool telemetry
- [x] Add end-to-end smoke script (`health`, `chat`, `memory`, `models`)
- [x] Add release checklist for “daily-use ready” builds

### Sprint C (Week 3) — Memory Quality Pipeline

- [x] Add hybrid quality ledger (SQLite) for confidence/provenance/conflict state keyed by scoped memory IDs
- [x] Sync Mem0 memory payloads into quality ledger and expose ledger-backed quality fields on `/api/memory`
- [x] Improve prompt recall ranking to prefer high-confidence, non-contradictory memories
- [x] Align tool `memory_search` output ordering with shared quality scoring signals
- [x] Add backend contradiction lifecycle flow hardening (pending/review/resolved transitions) with focused tests

### Day 0 (Phase 3 Kickoff)

- [x] Create feature-first tracking artifact (`FEATURE_TRACKER_ARTIFACT.md`)
- [x] Fix Mem0 fallback reliability path for decommissioned model errors
- [x] Add regression test for Mem0 fallback path

### Sprint D (Phase 3 - Week 1)

- [x] Add initial plugin registry surface (`/api/plugins`) and plugin policy hooks
- [x] Add plugin gating tests and telemetry assertions
- [x] Expand plugin manifest/override precedence (workspace/env/default)

### Sprint E (Phase 3 - Week 2)

- [x] Add sandbox execution mode (`main`/`restricted`) and enforce restricted-tool blocking
- [x] Unify realtime SSE envelope (`event` + `payload`) while keeping backward compatibility
- [x] Restore tasks API with real job data + cancellation + timeline support
- [x] Add scheduled automations MVP (`/api/schedules`, interval-based recurring jobs)

### Sprint F (Phase 3 - Week 3)

- [x] Add workspace-aware memory scope (`workspace_id`) while preserving existing defaults
- [x] Add workspace-aware brain storage roots for non-default workspaces
- [x] Add release profile checker script (`scripts/release_profile_check.py`)
- [x] Validate packaging profile with smoke + release checks on Python 3.11

### Phase 3 Completion Note

- ✅ Phase 3 MVP completed across all roadmap tracks.
- Follow-up enhancements can iterate on polish/UX depth without blocking core capability.

### Phase 3 Polish (Post-MVP, In Progress)

- [x] Add plugin policy control-plane endpoint (`/api/plugins/policy`) with auth-protected updates
- [x] Add workspace scope visibility endpoint (`/api/context`) for UI/debug clarity
- [x] Add focused control-plane regression tests for policy + context endpoints
- [x] Add realtime diagnostics polish (`seq` in SSE envelope + `/api/events/diagnostics` endpoint)
- [x] Add scheduler ergonomics polish (`cadence` parsing + timezone/retry settings + retry backoff tracking)
- [x] Add plugin manifest/catalog polish (`/api/plugins/catalog` + richer plugin metadata)
- [x] Add workspace switch UX polish (`/api/context/switch` + settings controls + migration toggle)

### Phase 3 Final Status

- ✅ Phase 3 complete (MVP + Polish v1).
- ✅ Control-plane, scheduler, plugin, and workspace tracks now all have shipped endpoints and regression coverage.

## Phase 4 (Feature-First) — Kickoff

### Sprint P4-A1 (File Handling V2 — Slice 1)

- [x] Add multi-file attachment upload endpoint (`/api/upload/batch`)
- [x] Add uploaded files listing endpoint (`/api/upload/list`)
- [x] Add multi-file knowledge upload/index endpoint (`/api/brain/upload/batch`)
- [x] Update knowledge tab client flow to batch upload on multi-select/drag-drop
- [x] Add focused backend regression tests (`tests/test_phase4_file_workflow.py`)

### Sprint P4-A2 (File Handling V2 — Slice 2)

- [x] Add uploaded-file text extraction endpoint (`/api/upload/extract`)
- [x] Add uploaded-file summary endpoint (`/api/upload/summarize`)
- [x] Add uploaded-files text search endpoint (`/api/upload/search`)
- [x] Add Knowledge tab “Recent Uploads” actions for summary + extract
- [x] Expand focused Phase 4 API tests for extract/summarize/search

### Sprint P4-B1 (Knowledge Workspace V2 — Slice 1)

- [x] Add workspace brain files listing endpoint (`/api/brain/files`)
- [x] Add workspace brain file delete endpoint (`/api/brain/file`)
- [x] Add index removal helper for deleted brain files (`BrainIndex.remove_file`)
- [x] Add Knowledge tab delete controls for indexed files
- [x] Expand focused Phase 4 API tests for brain files list/delete

### Sprint P4-C1 (Memory Review Center — Slice 1)

- [x] Add bulk pending fact action endpoint (`/api/pending_facts/bulk`)
- [x] Add memory panel pending-facts inbox with per-item approve/reject actions
- [x] Add bulk approve-all / reject-all memory review controls
- [x] Add focused Phase 4 tests for pending-facts bulk actions

### Sprint P4-D1 (Automation Management — Slice 1)

- [x] Add schedule update endpoint (`PUT /api/schedules/<id>`) with partial field patching
- [x] Add schedule delete endpoint (`DELETE /api/schedules/<id>`) with not-found handling
- [x] Extend jobs service with `update_schedule(...)` and `delete_schedule(...)`
- [x] Add/expand focused tests for schedule update/delete in control-plane + service suites

### Sprint P4-D2 (Automation Management — Slice 2)

- [x] Extend Tasks sidebar to also render configured schedules
- [x] Add schedule pause/resume action in UI (`POST /api/schedules/<id>/toggle`)
- [x] Add schedule edit action in UI (`PUT /api/schedules/<id>`)
- [x] Add schedule delete action in UI (`DELETE /api/schedules/<id>`)
- [x] Validate updated automation flow with focused Phase 3/4 regression suite

### Sprint P4-E1 (Integration Controls — Slice 1)

- [x] Add Settings UI plugin toggles for enable/disable control of capability groups
- [x] Add Settings action to apply plugin policy via (`POST /api/plugins/policy`)
- [x] Refresh plugin catalog state immediately after policy updates
- [x] Add/extend focused tests for unknown-plugin policy validation and auth contract handling

### Sprint P4-E2 (Smart Home Reliability — Slice 1)

- [x] Add Loxone health helper for configured/connected state resolution
- [x] Add Smart Home API endpoint (`GET /api/loxone/health`) for modal status checks
- [x] Add Smart Home modal status banner with setup/connectivity guidance messaging
- [x] Add focused tests for Loxone health endpoint states

### Sprint P4-E3 (Smart Home Reliability — Slice 2)

- [x] Fix Loxone dim command path in local tool loop (`set_brightness` alignment)
- [x] Expose updated Loxone integration helpers in package exports
- [x] Add focused loop-level consistency tests for light dim success/failure handling

### Sprint P4-F1 (Automation Policy Visibility — Slice 1)

- [x] Add tool-policy evaluation helper for non-executing visibility checks
- [x] Enrich schedule list payload with policy block metadata (`blocked_by_policy`, reason/message)
- [x] Show policy warning state on schedule cards in Tasks sidebar
- [x] Add focused tests for tool policy helper and schedule policy metadata propagation

### Sprint P4-F2 (Smart Home UX — Slice 3)

- [x] Add Smart Home modal quick actions (`All On`, `All Off`, `Refresh`)
- [x] Add clearer Smart Home action feedback (success/error toasts for room/mode actions)
- [x] Add focused API tests for all-lights command routes

### Sprint P4-F3 (Automation UX — Slice 2)

- [x] Add Tasks sidebar action to create new schedules (`+ Schedule`)
- [x] Add prompt-based cadence creation flow backed by (`POST /api/schedules`)
- [x] Fix Smart Home controls placement regression so status/actions render in Smart Home modal
- [x] Add focused control-plane test for cadence validation error path

### Sprint P4-F4 (Automation UX — Slice 3)

- [x] Parse schedule `tool_args` into dict payloads in schedule listing for reliable edit/list behavior
- [x] Show richer schedule observability in Tasks sidebar (human interval, next run, failure details)
- [x] Add focused jobs-service test coverage for tool_args parsing + observability fields

### Sprint P4-F5 (Automation UX — Slice 4)

- [x] Add schedule run-now endpoint (`POST /api/schedules/<id>/run`) with auth and not-found/error handling
- [x] Add jobs service helper to enqueue a specific schedule immediately while updating failure/last-run observability
- [x] Add Tasks sidebar `Run now` action on schedule cards with success/error toast feedback
- [x] Add focused control-plane + jobs-service coverage for run-now success/failure flows

### Sprint P4-F6 (Automation UX — Slice 5)

- [x] Enforce tool policy checks before schedule enqueue for due-run and run-now execution paths
- [x] Persist policy-denied failures into schedule observability fields (`consecutive_failures`, `last_error`, `last_run_at`)
- [x] Map run-now policy-denied failures to user-visible `400` responses in control-plane API
- [x] Add focused jobs-service/control-plane regression coverage for policy-denied execution flows

### Phase 4 Final Status

- ✅ Phase 4 complete across file workflow, memory review, automation UX, integration reliability, and policy-enforced automation execution.
- ✅ Consolidated closure regression pass: `74 passed` across Phase 4 + critical Phase 3 guardrail suites.
- ✅ Web mode startup validated in-session (`run_companion.py --web --no-browser` reaches `Running on http://127.0.0.1:5000`).

## Long-Range Product Vision (2026+)

### North Star

Companion AI becomes a trustworthy, local-first personal operations assistant that can:
- reason over your memory and documents with high precision,
- automate recurring workflows safely,
- coordinate real-world integrations (home/dev/work) under explicit policy,
- and remain transparent, debuggable, and resilient for daily use.

### Product Pillars

1. **Reliability by default** — predictable runtime behavior, clear state transitions, graceful failure recovery.
2. **Safety with control** — policy-driven tools, explicit scopes, and reversible actions.
3. **Memory that stays useful** — high-quality recall, conflict-aware facts, and explainable provenance.
4. **Automation that users trust** — visible schedules, clear run outcomes, easy intervention controls.
5. **Local-first extensibility** — plugin/integration growth without cloud lock-in.

## Phase 5 (Next 1-2 Months): Architecture Activation & Spring Clean

Goal: activate the orchestrator-first architecture, clean dead code, split monoliths, and unify knowledge — making the codebase match the documented vision.

### Track A: Spring Clean (Dead Code & Legacy Removal)

| Task | Effort | Success Criteria |
|---|---:|---|
| Remove `build_full_prompt()` from `llm_interface.py` | 1 day | No references, tests pass |
| Remove `should_use_groq()` and always-true branches | 1 day | Clean routing logic |
| Remove `ENABLE_COMPOUND`, `ENABLE_ENSEMBLE`, vestigial model aliases | 1 day | `config.py` only has active settings |
| Remove legacy `/api/chat` (non-streaming) endpoint | 1 day | Only SSE `/api/chat/send` remains |
| Unwire `ComputerLoop` from registry (keep code, just shelve) | 1 day | Loop registry only has memory/tool/vision |
| Consolidate compatibility shims (`memory_v2.py`, `memory_graph.py`, `persona_evolution.py`) | 2-3 days | All imports point to real modules, shims deleted |

### Track B: Orchestrator Activation

| Task | Effort | Success Criteria |
|---|---:|---|
| Set `USE_ORCHESTRATOR=true` as default | 1 day | All chat flows go through orchestrator |
| Wire orchestrator → local loop delegation path | 1-2 weeks | DELEGATE decisions invoke the correct loop |
| Wire orchestrator → quick tool path (Groq zero-shot) | 1 week | TOOL decisions use fast Groq model |
| Wire orchestrator → memory operations | 1 week | MEMORY decisions hit unified knowledge system |
| Add orchestrator fallback (graceful degradation if Groq down) | 2-3 days | Falls back to direct LLM call |
| Add orchestrator routing tests | 1 week | Each decision type has focused test coverage |

### Track C: Monolith Splitting

| Task | Effort | Success Criteria |
|---|---:|---|
| Split `web_companion.py` → Flask Blueprints (`web/`) | 2-3 weeks | Same endpoints, cleaner code, all tests pass |
| Split `tools.py` → `tools/` directory (registry + domain modules) | 1-2 weeks | Same tool surface, modular structure |
| Split `llm_interface.py` → `llm/` directory (providers + router) | 1-2 weeks | Same LLM behavior, separated concerns |

### Track D: Unified Knowledge System

| Task | Effort | Success Criteria |
|---|---:|---|
| Merge brain folder + uploads + brain index into single doc pipeline | 1-2 weeks | One upload/index/search flow |
| Merge `pending_profile_facts` into main confidence system | 1 week | Low-confidence = flagged, no separate pending table |
| Create single knowledge entry point (`remember` / `recall`) | 1 week | Orchestrator has one API for all knowledge ops |

### Track E: Persona Foundation

| Task | Effort | Success Criteria |
|---|---:|---|
| Audit current persona system (`persona.py` + `companion.yaml`) | 2-3 days | Clear understanding of what evolves and how |
| Define persona evolution triggers (conversation patterns, memory events) | 1 week | Documented trigger → evolution mapping |
| Wire persona state into orchestrator context | 2-3 days | Orchestrator responses reflect persona traits |

### Proposed Sprint Order (Phase 5)

- **P5-A**: Spring clean — dead code, legacy removal, shim consolidation
- **P5-B**: Orchestrator activation — wire routing, loops, tools, memory
- **P5-C**: Monolith split — web_companion → blueprints first, then tools, then LLM
- **P5-D**: Knowledge unification — doc pipeline, confidence merge, single entry point
- **P5-E**: Persona foundation — audit, triggers, orchestrator integration

## Phase 6 (2-4 Months): Daily-Life Intelligence

Goal: make Companion AI genuinely useful for daily personal operations.

| Track | Outcome | Candidate Deliverables | Success Criteria |
|---|---|---|---|
| Workflow templates | Reusable personal routines | Daily briefing, inbox triage, routine reminders | Users can launch repeatable workflows in ≤2 steps |
| Human-in-the-loop | Safer autonomy | Approval checkpoints for high-impact actions | High-risk steps require explicit confirmation |
| Cross-skill orchestration | Multi-step task completion | Structured plans with progress visibility | Complex tasks complete with per-step status |
| Proactive insights | Timely, low-noise suggestions | Daily/weekly digests from memory + schedule signals | Suggestions feel relevant, not spammy |
| Context packaging | Better reasoning quality | Scoped context bundles from memory/files/events | Lower hallucination in multi-step runs |

## Phase 7 (4-6 Months): Ecosystem & Integration Growth

Goal: grow integrations and plugins without compromising safety.

| Track | Outcome | Candidate Deliverables | Success Criteria |
|---|---|---|---|
| Plugin SDK maturity | Faster safe extensions | Stable plugin contract, validation tooling, examples | New plugins can be added with clear compatibility checks |
| Integration lifecycle | Safer external connectivity | Health checks, scoped credentials, per-integration policy | Integrations degrade gracefully with actionable health states |
| Workspace maturity | Better personal/work isolation | Rich presets, migration tooling, profile export | Zero unintended cross-workspace memory bleed |

## Phase 8 (6-12 Months): Personal Intelligence Layer

Goal: evolve into a proactive but policy-bounded intelligence layer.

| Track | Outcome | Candidate Deliverables | Success Criteria |
|---|---|---|---|
| Long-horizon memory | Durable trust in recall | Memory pruning, confidence decay, contradiction mediation | Memory stays accurate over months without manual cleanup |
| Personal knowledge ops | Strategic support | Goal tracking, project maps, cross-document synthesis | Can summarize progress and blockers across ongoing projects |
| Persona depth | Distinctive personality | Emotional intelligence, style adaptation, growth arcs | Companion feels like a real assistant, not a generic chatbot |

## Program-Level Risks & Mitigations

- **Risk: reliability regressions from rapid feature growth**  
  **Mitigation:** enforce focused regression suites per slice + milestone consolidation runs.
- **Risk: policy complexity confusing users**  
  **Mitigation:** maintain plain-language policy diagnostics in UI and APIs.
- **Risk: legacy compatibility drag**  
  **Mitigation:** moderate cleanup strategy with deprecation windows and explicit rollback paths.
- **Risk: artifact drift (roadmap/tracker/docs mismatch)**  
  **Mitigation:** mandatory update cadence on roadmap + feature tracker + relevant docs each slice.

## Success Metrics (Across Phases 5-8)

- **Architecture**: orchestrator handles all messages, loops activate on delegation, no bypass paths.
- **Code quality**: monoliths split, dead code removed, clean imports throughout.
- **Knowledge**: unified recall interface, merged fact/pending system, single doc pipeline.
- **Reliability**: stable startup and long-session operation with minimal manual recovery.
- **Control plane**: no silent failures; all task/schedule failures carry a user-visible reason.
- **Persona**: responses reflect evolving personality traits grounded in conversation history.
- **Velocity**: each slice ships with tests and artifact updates in the same change window.

## Immediate Next Execution Window (Phase 5 Kickoff)

1. Kick off **Phase 5 / Sprint P5-A** (spring clean — dead code and legacy removal).
2. Run focused test suite after each cleanup step.
3. Then proceed to **P5-B** (orchestrator activation and wiring).
4. Keep this roadmap + `FEATURE_TRACKER_ARTIFACT.md` synchronized per delivered slice.
5. Promote only validated slices into release-profile checks.

## Definition of Done (for Phase 2)

- 95%+ successful startup rate on clean machine with setup script
- No unauthenticated access to sensitive endpoints outside localhost
- Memory retrieval quality: user confirms recall relevance in real usage
- Core tests + smoke checks green on Python 3.11
- UI supports common daily workflow in <=3 clicks per action

## Notes for You (Non-technical execution)

When we execute this roadmap, each task will include:
- exact file edits
- exact commands
- what success looks like
- rollback steps if anything breaks

This artifact is the working source-of-truth for upcoming implementation phases.