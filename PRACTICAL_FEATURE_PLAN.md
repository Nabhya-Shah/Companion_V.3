# Practical Feature Plan (Execution-Ready)

Status: Working execution plan
Created: 2026-04-10
Planning basis: ROADMAP + TEMP feature backlog, with priority boost for local models and computer-use.

## 1. Priority Weights (for next 6 weeks)

1. Computer-use and browser action UX/safety: 35%
2. Local model setup and operability: 30%
3. Memory reliability and recall quality: 20%
4. Pilot automation and observability depth: 15%

## 2. Sprint Plan (Practical and Tangible)

### Sprint 1 (Week 1): Local Model Setup MVP

1. Add one-command local model bootstrap script (checks Ollama/vLLM availability and model pull status).
2. Add local model profile presets (balanced, fast, quality) with explicit model-role mapping.
3. Add local-model readiness endpoint output to health payload (installed, reachable, selected profile).
4. Add deterministic fallback reason codes when local path is unavailable.
5. Add UI settings block for local model mode/profile selection.
6. Add smoke script for local-model path validation.

Definition of done:

1. A fresh machine can run one command and get actionable pass/fail guidance.
2. Health endpoint clearly explains local model state.
3. Chat path continues working safely when local models are unavailable.

### Sprint 2 (Week 2): Computer-Use Tangible UX Pack

1. Add browser step preview before execution for high-risk actions.
2. Add action replay from audit records.
3. Add screenshot/video artifact viewer for browser runs.
4. Add anti-stuck recovery with safe abort and clear reason codes.
5. Add policy explanation panel for denied/blocked actions.
6. Add deterministic e2e diagnostics artifacts for every failed browser/computer-use run.

Definition of done:

1. Every browser/computer action has preview, approve, execute, and replay traceability.
2. Failure triage can be done from artifacts without digging through raw logs.

### Sprint 3 (Week 3): Memory Reliability + Pilot Gate

1. Harden mem0 readiness contracts and fallback visibility.
2. Add strict post-restart recall benchmark runner with fixed prompt set.
3. Add Hermes OFF->ON go/no-go decision script and JSON decision artifact.
4. Add pilot comparator endpoint for OFF vs ON latency/error/recall deltas.
5. Add quality posture score report generator from benchmark artifacts.

Definition of done:

1. Pilot lane can be promoted/rolled back with objective gate data.
2. Recall stability regressions are detectable in one command.

## 3. Top 15 Features To Build First (ordered)

1. One-command local model bootstrap.
2. Local model profile presets.
3. Local model readiness details in health payload.
4. Local fallback reason-code contracts.
5. Browser step preview before execution.
6. Browser action replay from audit logs.
7. Browser run artifact viewer.
8. Anti-stuck recovery and safe abort path.
9. Policy explanation panel for blocked tool actions.
10. mem0 readiness hardening and diagnostics.
11. Strict post-restart recall benchmark harness.
12. Hermes OFF->ON go/no-go automation.
13. Pilot comparator summary endpoint.
14. Throughput sustained/burst benchmark extension.
15. Quality posture re-score publisher.

## 4. Autopilot Scope (safe to implement without extra product decisions)

1. Health payload expansions and diagnostics reason codes.
2. Benchmark harnesses and result artifact generation.
3. Browser artifact viewing and replay infrastructure.
4. Tool denial explanation UX.
5. Throughput and provider-canary automation scripts.

## 5. Requires Your Decisions (for local model + computer-use)

### Local Model Decisions

1. Primary local runtime preference: Ollama only, vLLM only, or hybrid.
2. Minimum GPU target for "supported" status (VRAM and model size expectation).
3. Default local models per role (chat, memory processing, embeddings).
4. Fallback policy when local model fails: auto-cloud fallback or hard-fail with warning.
5. Whether local model downloads should be automatic or user-confirmed.

### Computer-Use Decisions

1. Default safety mode: strict preview-required or flexible approve-only.
2. Artifact retention window for screenshots/video/audit bundles.
3. Allowlist strategy: domain-first or action-first.
4. Whether replay is operator-only or available to all authenticated users.
5. Whether high-risk actions require two-step confirmation always.

## 5.1 Decision Lock (2026-04-10)

Resolved from current operator preferences:

1. Local runtime baseline: hybrid (support both vLLM and Ollama, prefer whichever is available).
2. Hardware target baseline: 16 GB VRAM with multiple operating profiles to preserve headroom.
3. Chat default baseline: keep cloud-primary (`openai/gpt-oss-120b`) unless local mode is explicitly preferred.
4. Memory processing direction: prioritize local-heavy quality path when profile allows; keep scheduling-friendly background processing.
5. Computer-use default: approval-required with explicit activity visibility (what it is doing and observing).
6. Computer-use artifact retention: 7-day hot retention, then archive to long-term storage.
7. Computer-use allowlist strategy: action-first.
8. Computer-use replay access: operator-only.
9. Computer-use confirmation policy: two-step confirmation for specific high-risk actions.

Assumptions locked for implementation now:

1. Local model cloud fallback remains enabled by default for continuity.
2. Three local operating profiles are active targets: gaming, balanced, quality.
3. Profile intents: gaming favors responsiveness/headroom, balanced favors reliability, quality favors memory quality.

## 6. Execution Cadence Once You Approve

1. Implement Sprint 1 first with tests and health/smoke validation.
2. Implement Sprint 2 next with deterministic browser artifacts.
3. Implement Sprint 3 and run OFF->ON pilot decision gate.
4. Update PLAN/ROADMAP after each sprint slice ships.
