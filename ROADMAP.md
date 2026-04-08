# Companion V3 Unified Roadmap

Status: Canonical roadmap document
Last updated: 2026-03-31
Planning style: milestone and sprint tracks

## 1. Purpose

ROADMAP.md is the single source of truth for future execution.

Use with PLAN.md:

1. PLAN.md = what is true now.
2. ROADMAP.md = what we are doing next and why.

## 2. North Star

Companion should be a dependable daily-use assistant that is:

1. Reliable under normal failures.
2. Safe in tool and automation behavior.
3. Trustworthy in memory recall and provenance.
4. Operationally simple enough to run and evolve quickly.

## 3. Strategy for NEW.md (Plan B) Integration

The external Plan B blueprint is valuable, but this repository will use a selective integration strategy.

### 3.1 Keep Now (Integrate into current stack)

1. Browser plan-approve-execute interaction model with explicit user control.
2. Clear ownership contracts for memory, planning, tools, and generated artifacts.
3. Knowledge folder/write policy conventions for durable user and assistant outputs.
4. Strong phase-gate execution style and checkpoint-based rollout.
5. Expanded service/health check discipline and release readiness gates.

### 3.2 Explore Later (Pilot first, then decide)

1. Optional Hermes orchestrator adapter proof-of-concept behind feature flag.
2. Optional pgvector retrieval lane as secondary/experimental backend.
3. Skill-factory style procedural memory generation with review guardrails.
4. MCP-first externalization for selected high-risk tool domains.

### 3.3 Not Now (Avoid for this repo baseline)

1. Full rip-and-replace of current Flask/web/orchestrator stack with OpenWebUI+Hermes.
2. Mandatory always-on multi-service baseline as default local runtime.
3. Immediate full memory backend migration with high continuity risk.

## 4. Active Delivery Tracks

Legend: `[x]` complete, `[ ]` pending

### Track A: Runtime Hardening Baseline

Outcomes:

1. [x] Deployable baseline behavior beyond dev-only assumptions.
2. [x] Stronger auth-safe defaults on sensitive write and debug paths.
3. [x] Readiness diagnostics for core dependencies.
4. [x] End-to-end trace IDs across chat, tools, and memory writes.

Acceptance gates:

1. [x] Existing regressions remain green.
2. [x] New tests cover auth and readiness contracts.
3. [x] Manual smoke confirms trace continuity.

### Track B: Browser Reliability and Observability

Outcomes:

1. [x] Reliable browser execution lifecycle and clear diagnostics.
2. [x] Plan-approve-execute UX integrated with existing approval model.
3. [x] Action telemetry for easier troubleshooting.
4. [x] One realistic end-to-end browser workflow path.

Acceptance gates:

1. [x] Deterministic success/failure contracts.
2. [x] Actionable error messages surfaced in UI/logs.
3. [x] Regression tests for browser approval and execution flow.

### Track C: Safe Computer-Use Beta (Feature Flagged)

Outcomes:

1. [x] Harden computer-use module wiring and error pathways.
2. [x] Default-off behavior with explicit feature flag enablement.
3. [x] Approval requirement for high-risk computer-use actions.
4. [x] Immutable audit entries for attempted/approved/denied actions.

Acceptance gates:

1. [x] Disabled mode returns deterministic contract response.
2. [x] Enabled mode enforces approval and logs events.
3. [x] Tests cover allowlist, approval, rejection, and fallback.

### Track D: Memory Trust and Provenance UX

Outcomes:

1. [x] Stronger provenance payloads for surfaced memories.
2. [x] Provenance drill-down endpoint and UI rendering.
3. [x] Better confidence/source visibility in memory panel.
4. [x] Better contradiction and dedup review ergonomics.

Acceptance gates:

1. [x] Provenance data present in retrieval/API responses.
2. [x] UI can explain why memories surfaced.
3. [x] Memory quality tests verify consistency.

### Track E: Multi-User and Throughput Readiness

Outcomes:

1. [x] Concurrency validation for session/workspace isolation.
2. [x] Queue pressure controls and bounded behavior under degradation.
3. [x] Throughput/load harness for representative scenarios.
4. [x] Clear migration path if SQLite write constraints are reached.

Acceptance gates:

1. [x] No cross-session leakage under concurrency tests.
2. [x] Bounded queue behavior under backend stress.
3. [x] Baseline throughput metrics recorded and tracked.

## 5. 90-Day Execution Plan

### Now (0-30 days)

1. [x] Complete documentation consolidation and governance lock.
2. [x] Deliver Track A baseline hardening items.
3. [x] Start Track B browser reliability essentials.
4. [x] Add high-impact validation improvements (provider contract canary and concurrency tests).

### Next (30-60 days)

1. [x] Complete Track B and launch Track C feature-flagged beta path.
2. [x] Deliver first memory provenance UX improvements from Track D.
3. [x] Expand operational checks and diagnostics depth.

### Later (60-90 days)

1. [x] Complete Track D and Track E core acceptance gates.
2. [ ] Run pilot for one Explore Later item (Hermes adapter or pgvector lane) with explicit go/no-go criteria.
3. [ ] Re-score quality posture after core track completion.

## 6. Quality and Exit Metrics

Roadmap progress is measured by:

1. Stability: no unresolved critical regressions at sprint close.
2. Safety: zero approval bypasses for high-risk actions.
3. Memory trust: improved provenance visibility and review throughput.
4. Operability: reduced time-to-diagnose incidents and stronger health checks.
5. Validation depth: improved non-mocked and concurrency test coverage.

## 7. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Over-expanding architecture too early | Slower delivery, stability loss | Keep selective integration strategy; pilot before platform swaps |
| Browser automation brittleness | User trust erosion | strict contracts, approvals, telemetry, fail-safe handling |
| Memory quality regressions | Lower assistant trust | provenance-first UX, contradiction handling, targeted memory tests |
| Throughput bottlenecks | Multi-user instability | queue controls, load baselines, migration path planning |
| Documentation drift returns | Team confusion | PLAN+ROADMAP canonical policy and index-only side docs |

## 8. Change Control

1. Update ROADMAP.md whenever priorities/scope change.
2. Update PLAN.md when behavior ships.
3. Keep non-canonical planning docs as archived context only.
4. Document major architecture decisions and reversals here.

## 9. Changelog

- 2026-03-31: Consolidated roadmap sources into unified ROADMAP.md and integrated NEW.md strategy into keep-now/explore-later/not-now tracks.
- 2026-03-31: Track A slice delivered: API trace IDs now propagate through response headers, chat stream metadata, orchestrator delegation, and memory write request IDs; /api/health now includes readiness diagnostics (with targeted tests).
- 2026-03-31: Track A slice delivered: sensitive policy/admin write endpoints now require explicit API_AUTH_TOKEN configuration by default (targeted tests + live endpoint probes passed).
- 2026-03-31: Track A slice delivered: production serving path added (wsgi.py + gunicorn.conf.py + dependency + command docs), validated live on gunicorn.
- 2026-03-31: Track B slice delivered: browser runtime diagnostics endpoint added (/api/browser/diagnostics) with structured readiness reasons and trace correlation (targeted tests + live probe passed).
- 2026-03-31: Track B slice delivered: browser tool failures now return actionable remediation hints for missing Playwright/Chrome runtime issues (targeted tests + live call passed).
- 2026-03-31: Track C slice delivered: computer-use tool now emits deterministic disabled-policy contract responses and append-only audit JSONL records for requested/rejected/completed/error attempts (targeted tests + live runtime probe passed).
- 2026-03-31: Track C slice delivered: enabled-mode use_computer approval paths now produce auditable requested/rejected (approval_denied) and requested/completed records even when execution is blocked pre-dispatch by approval policy (targeted tests + live runtime probe passed).
- 2026-03-31: Track C slice delivered: enabled-mode fallback now returns deterministic runtime-unavailable response when computer agent wiring is absent and logs rejected audit reason=runtime_unavailable (targeted tests + live runtime probe passed).
- 2026-03-31: Track C slice delivered: use_computer policy-gate denials (allowlist/plugin/sandbox path) now also emit pre-dispatch requested/rejected audit records; acceptance coverage now explicitly includes allowlist + approval + rejection + fallback contracts (targeted tests + live runtime probe passed).
- 2026-03-31: Track D slice delivered: added memory provenance drill-down endpoint (/api/memory/provenance/<key>) with trace correlation and structured provenance payload across Mem0 and SQLite fallback paths (targeted tests + live HTTP probes for 404 and 200 contracts passed).
- 2026-03-31: Track D slice delivered: memory panel now exposes inline provenance drill-down (“Why this memory?”) backed by /api/memory/provenance/<key>, including source/quality/state details and metadata rendering (live asset + endpoint probes passed).
- 2026-03-31: Validation slice delivered: tools policy test suite is now isolated from workspace plugin-policy file state via autouse fixture defaults, eliminating environment-coupled false failures (tests/test_tools.py now passes cleanly).
- 2026-03-31: Track E slice delivered: added parallel chat scope-isolation regression coverage to ensure concurrent session/workspace requests preserve distinct mem0_user_id routing (targeted tests + live parallel context probe passed).
- 2026-03-31: Track E slice delivered: added authenticated memory write-queue diagnostics endpoint (/api/memory/write-queue) with bounded snapshots and trace correlation for queue-pressure visibility (targeted tests + live HTTP probe passed).
- 2026-03-31: Track E slice delivered: /api/health readiness now includes memory write-queue depth/oldest timestamp and degrades on backlog/probe failures for faster ops diagnosis under pressure (targeted tests + live health/queue probes passed).
- 2026-03-31: Track E slice delivered: added lightweight throughput/load harness (`scripts/throughput_probe.py`) with JSON artifact output and threshold gating; recorded first baseline in `data/benchmarks/throughput_probe_health.json` (20 requests, concurrency=5, success_rate=1.0, p95=69.67ms, throughput=258.81 rps).
- 2026-03-31: Reliability slice delivered: migrated remaining `datetime.utcnow()` usages in insights/continuity/remote-actions paths to timezone-aware UTC timestamps, removing deprecation warnings from key regression suites (targeted tests + runtime probe passed).
- 2026-03-31: Stabilization slice delivered: fixed full-suite blockers by isolating computer-use audit and jobs-service tests from mutable global plugin/approval state; full watchdog run restored to green (315 passed, 1 skipped).
- 2026-03-31: Reliability slice delivered: migrated workflows service UTC timestamps and approval token expiry to timezone-aware datetimes; regression suite now runs without deprecation warnings (full watchdog run clean).
- 2026-03-31: Track E slice delivered: added bounded write-queue replay controls via `POST /api/memory/write-queue/replay` (auth-gated, bounded `max_items`, cooldown, in-progress guard, trace correlation) with deterministic contracts and targeted tests.
- 2026-03-31: Track E slice delivered: stats panel now surfaces memory queue diagnostics (depth, replay state, queued item previews) with manual refresh and bounded replay action wiring for faster queue-pressure triage.
- 2026-03-31: Track B validation slice delivered: strengthened browser routine Playwright contract assertions to validate workflow response shape and chat delivery invariants for both API precheck and UI-triggered runs.
- 2026-03-31: Track D slice delivered: added contradiction/dedup operator review APIs (`GET /api/memory/review`, `POST /api/memory/review/<key>`) plus memory-panel action wiring (reaffirm, state transitions, mark duplicate) and targeted regression tests.
- 2026-03-31: Track E slice delivered: added migration readiness API (`GET /api/memory/migration-readiness`) and stats-panel guidance rendering to expose queue pressure, failure-rate posture, and migration recommendations with authenticated refresh workflow.
- 2026-03-31: Track B validation slice delivered: added explicit browser approval/execution regressions in approval tests and Playwright e2e strict-mode gating (`E2E_STRICT_PLAYWRIGHT`) for CI-capable deterministic enforcement.
- 2026-03-31: Hermes pilot baseline captured: extended memory-focused regression run completed (49 passed, 0 failed, 0 skipped in 4.63s) with artifact saved at `data/benchmarks/memory_baseline_pre_hermes_2026-03-31.json`.
- 2026-03-31: Hermes pilot detachment slice delivered: added config-gated orchestration router (`ORCHESTRATION_ENGINE`, `ENABLE_HERMES_PILOT`, strict fallback mode) and pilot adapter boundary that preserves current feature parity while allowing one-switch rollback to main orchestration.
- 2026-04-01: Hermes pilot transport slice delivered: pilot adapter now supports real HTTP transport via `HERMES_PILOT_ENDPOINT` with timeout/token controls (`HERMES_PILOT_TIMEOUT_SECONDS`, `HERMES_PILOT_API_TOKEN`), strict contract validation, and safe fallback to main orchestration when pilot path fails (non-strict mode).
- 2026-04-08: Runtime wiring slice delivered: `.env` bootstrap now explicitly supports multipurpose Groq key rotation (`GROQ_API_KEY` + `GROQ_API_KEY_2..`) with dedicated key fields treated as optional overrides.
- 2026-04-08: Live OFF→ON pilot validation rerun completed with real web UI sends (Playwright via `#userInput` + `#sendBtn`) under populated Groq keys: both lanes reached 100% request success, 0 rate-limit hits, and 0 brain-fallback responses; OFF lane showed better strict post-restart recall hit rate in this run while ON lane remained viable for guarded canary rollout.
