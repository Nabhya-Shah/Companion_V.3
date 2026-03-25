# Companion V3 Improvements Roadmap

Status: Active execution roadmap
Last updated: 2026-03-25
Planning style: Big sprint cycles (no fixed calendar)

## 1. Purpose

This file is the active roadmap for improvements and execution priorities.

Use this together with PLAN.md:
- PLAN.md = current implementation truth
- IMPROVEMENTS_ROADMAP.md = what we build next and how we verify it

## 2. Success Criteria (North Star)

Companion V3 should become a dependable daily-use assistant with:

1. Stable orchestrator-driven behavior under normal failures.
2. Safe and observable tool execution (including higher-risk actions).
3. Trustworthy memory retrieval with explainable provenance.
4. Fast iteration velocity through strong tests and low documentation drift.

## 3. Sprint Framework

Each sprint should define:

1. Scope: 1-2 major outcomes only.
2. Verification: required automated tests plus one manual smoke flow.
3. Ship gate: no unresolved critical regressions.
4. Documentation update: PLAN.md current-state updates after merge.

Definition of done for a sprint:

1. Target tests pass.
2. New behavior has endpoint/UI observability where relevant.
3. Safety policy and fallback behavior are explicit.
4. Docs updated in this file and PLAN.md.

## 4. Active Sprint Backlog

### Sprint A: Runtime Hardening Baseline

Primary outcome:

1. Move from development-only runtime assumptions to deployable baseline behavior.

Scope:

1. Add production app serving path (WSGI server profile + startup instructions).
2. Enforce auth-safe defaults for write and high-risk endpoints.
3. Add health diagnostics endpoint(s) for service readiness and dependency state.
4. Add structured request tracing ID through chat, tools, and memory write flow.

Acceptance gates:

1. Existing tests remain green.
2. New tests for auth default behavior and health endpoint contract pass.
3. Manual smoke: start app, stream chat, run tool, verify trace continuity.

### Sprint B: Browser Workflow Reliability + Observability

Primary outcome:

1. Browser automation is reliable enough for repeatable task workflows.

Scope:

1. Standardize browser runtime bootstrap requirements (Playwright deps, binary checks).
2. Improve browser session lifecycle handling and failure messages.
3. Add browser action telemetry events to aid troubleshooting.
4. Add one realistic end-to-end browser workflow test path.

Acceptance gates:

1. Browser tools have clear success/failure envelopes.
2. One scripted browser workflow passes in a controlled local environment.
3. Failures surface actionable diagnostics instead of generic errors.

### Sprint C: Safe Computer-Use Beta (Feature-Flagged)

Primary outcome:

1. Controlled beta for computer-use actions with explicit safety boundaries.

Scope:

1. Fix computer-use module wiring and remove broken import pathways.
2. Keep feature disabled by default; enable only via explicit flag.
3. Require approval for all high-risk computer-use actions.
4. Add immutable audit trail entries for computer-use attempts.
5. Define hard-blocked actions in beta scope.

Acceptance gates:

1. Disabled mode returns deterministic contract response.
2. Enabled mode requires approval and logs each action.
3. Regression tests cover allowlist, approval, and rejection flows.

### Sprint D: Memory Trust and Provenance UX

Primary outcome:

1. Users can see why memories were surfaced and how reliable they are.

Scope:

1. Expand provenance payloads for recall results and review actions.
2. Expose provenance drill-down endpoint for surfaced memories.
3. Improve frontend memory panel with confidence and source-path visibility.
4. Add contradiction and dedup review ergonomics.

Acceptance gates:

1. Retrieval trace and provenance data are available in API responses.
2. Memory UI can display confidence and origin for surfaced items.
3. Memory quality tests cover provenance consistency.

### Sprint E: Multi-User and Throughput Readiness

Primary outcome:

1. Reliable behavior with concurrent users and heavier write patterns.

Scope:

1. Validate session and workspace isolation under concurrent requests.
2. Add queue pressure controls for durable memory spool handling.
3. Add throughput/load test harness for representative chat + tool scenarios.
4. Define migration path if SQLite writer constraints become a bottleneck.

Acceptance gates:

1. Concurrency tests validate no cross-session leakage.
2. Queue behavior remains bounded and observable under degraded backend conditions.
3. Load baseline is recorded and compared sprint-over-sprint.

## 5. Always-On Tracks (Run Every Sprint)

1. Technical debt cleanup: timezone-aware datetime migration away from utcnow usage.
2. Test quality: prefer adding integration tests for critical user-facing flows.
3. Doc hygiene: keep PLAN.md and this roadmap synchronized at sprint close.
4. Safety reviews: re-evaluate risk tiers for newly added tools/endpoints.

## 6. Execution Order Recommendation

Recommended order for next big work cycles:

1. Sprint A
2. Sprint B
3. Sprint C
4. Sprint D
5. Sprint E

Rationale:

1. Reliability and deployability should come before capability expansion.
2. Browser reliability should be stable before enabling computer-use beta.
3. Memory trust and multi-user scaling should follow once core behavior is hardened.

## 7. Sprint Kickoff Checklist

Use this checklist when starting a new sprint session:

1. Confirm exact scope cut (what is explicitly out of scope).
2. List target files/modules likely to change.
3. List required tests to pass before merge.
4. Define rollback/fallback behavior for risky changes.
5. Define the documentation deltas required at sprint close.

## 8. Change Log

- 2026-03-25: Created active roadmap file to separate future execution planning from current-state canonical docs in PLAN.md.
