# Companion V3 Implementation Spec (From Cross-Repo Research)

Date: 2026-03-18
Status: Ready to implement
Scope: Durable memory semantics, tool runtime governance, retrieval observability, access control hardening, eval harness

## 1) Goals

This spec converts research findings into concrete implementation work for Companion V3.

Primary outcomes:
- Improve memory correctness and recovery behavior before adding more memory intelligence.
- Add policy-aware and auditable tool execution controls.
- Refactor retrieval into observable, stage-based operations.
- Prepare web surfaces for multi-user deployment safety.
- Add regression-resistant agent evaluation focused on routing and tool behavior.

## 2) Non-Goals

- No full architecture rewrite.
- No removal of existing orchestrator/loop split.
- No immediate replacement of all memory providers.
- No RL training system integration.

## 3) Current Baseline (already present)

- Orchestrator-first routing and specialist loops.
- Memory stack with Mem0 + SQLite + brain index + graph components.
- Policy hooks and tool/plugin infrastructure.
- Workflow timeout fallback protections.
- SSE chat streaming with token metadata.

## 4) Phase Plan

### Phase 1: Memory Durability and Lifecycle (highest priority)

#### 4.1 Required behaviors
- Every memory write returns one of:
  - accepted_queued
  - accepted_committed
  - rejected
  - failed
- If memory backends are unavailable, writes are durably spooled to disk.
- Spool replay occurs automatically on backend recovery.
- Replay is idempotent (safe to re-run without duplicate final records).

#### 4.2 Data contracts

Memory write request envelope:

```json
{
  "request_id": "uuid",
  "user_scope": "session_or_user_scope",
  "operation": "add|update|delete",
  "payload": {
    "memory_text": "...",
    "metadata": {}
  },
  "created_at": "iso8601"
}
```

Memory write result envelope:

```json
{
  "request_id": "uuid",
  "status": "accepted_queued|accepted_committed|rejected|failed",
  "backend": "mem0|sqlite|hybrid",
  "reason": "optional_reason",
  "committed_at": "iso8601|null"
}
```

Spool record file format (JSONL): one write envelope per line.

#### 4.3 File-level changes
- `companion_ai/memory/sqlite_backend.py`
  - Add write status persistence table (`memory_write_log`).
  - Add idempotency key support (`request_id`).
- `companion_ai/memory/mem0_backend.py`
  - Introduce durable write API that returns explicit status envelope.
  - Add replay entrypoint for queued writes.
- `companion_ai/memory/ai_processor.py`
  - Route memory writes through new status-returning write path.
- `companion_ai/conversation_manager.py` or `companion_ai/orchestrator.py`
  - Convert memory-save user feedback to status-aware messaging.
- New file: `companion_ai/memory/write_queue.py`
  - JSONL spool append, rotate, replay, and compaction.

#### 4.4 Acceptance criteria
- Simulated Mem0 outage still returns `accepted_queued`.
- Restart + recovery commits queued writes and marks them committed.
- Duplicate replay does not create duplicate memories.

### Phase 2: Tool Runtime Governance

#### 4.5 Required behaviors
- Every tool has runtime metadata:
  - risk_tier (`low|medium|high`)
  - requires_approval (bool)
  - category/plugin
- High-risk tools require explicit approval token before execution.
- Add bounded delegation primitive:
  - max_depth = 1
  - max_parallel_children = 3
  - blocked tools in children (delegation recursion, direct memory writes, unsafe shell)

#### 4.6 Data contracts

Tool metadata extension:

```json
{
  "name": "tool_name",
  "risk_tier": "low|medium|high",
  "requires_approval": true,
  "plugin": "core",
  "sandbox_blocked_in_restricted": false
}
```

Approval request envelope:

```json
{
  "approval_id": "uuid",
  "tool": "tool_name",
  "args": {},
  "reason": "risk_tier_high",
  "requested_at": "iso8601"
}
```

#### 4.7 File-level changes
- `companion_ai/tools/registry.py`
  - Extend tool registration schema with risk metadata.
  - Add approval state handling APIs.
- `companion_ai/local_loops/tool_loop.py`
  - Enforce approval requirement before execution path.
  - Return deterministic denial payload for unapproved calls.
- `companion_ai/tools.py` / domain tool modules
  - Annotate high-risk tools.
- New file: `companion_ai/tools/delegation.py`
  - Implement bounded subtask delegation utility.

#### 4.8 Acceptance criteria
- High-risk tool call cannot run without approval.
- Approval grants exactly one call (single-use token).
- Child delegation cannot recursively spawn children.

### Phase 3: Retrieval Pipeline Observability

#### 4.9 Required behaviors
- Retrieval pipeline becomes explicit stages:
  - query_expand
  - retrieve
  - rerank (optional)
  - answer (optional)
- Emit per-stage timing and count metrics.
- Surface stage events in SSE stream for UI progress display.

#### 4.10 Data contracts

SSE stage event:

```json
{
  "type": "retrieval_stage",
  "stage": "query_expand|retrieve|rerank|answer",
  "status": "start|done|error",
  "duration_ms": 42,
  "meta": {
    "result_count": 12,
    "provider": "local|groq"
  }
}
```

#### 4.11 File-level changes
- `companion_ai/brain_manager.py`
  - Split monolithic search path into stage operators.
- `companion_ai/brain_index.py`
  - Add richer retrieval diagnostics (candidate counts, score summary).
- `companion_ai/web/chat_routes.py`
  - Stream retrieval stage events to SSE clients.
- `static/app.js`
  - Render stage progress row (optional in this phase, required in phase 4 UI pass).

#### 4.12 Acceptance criteria
- SSE stream includes stage start/done events.
- Failures in one stage are visible and mapped to fallback behavior.

### Phase 4: Access Control Hardening for Web Mode

#### 4.13 Required behaviors
- Add feature-level permissions:
  - tools_execute
  - memory_write
  - workflows_run
  - files_upload
- Add optional per-resource grant checks for sensitive resources.
- Distinguish read vs write permissions for operational endpoints.

#### 4.14 Data contracts

Permission model:

```json
{
  "workspace": {
    "tools_execute": false,
    "memory_write": false,
    "workflows_run": false,
    "files_upload": true
  }
}
```

#### 4.15 File-level changes
- `companion_ai/core/config.py`
  - Add permission defaults and policy loading.
- `companion_ai/web/state.py`
  - Add permission resolver helpers.
- `companion_ai/web/chat_routes.py`
  - Enforce tools/memory permission checks at request handling.
- `companion_ai/web/tools_routes.py`, `companion_ai/web/memory_routes.py`, `companion_ai/web/system_routes.py`
  - Enforce action-level permission gates.

#### 4.16 Acceptance criteria
- Unauthorized tool execution is blocked with explicit message.
- Read-only users cannot mutate memory or workflow state.

### Phase 5: Eval Harness and Regression Guardrails

#### 4.17 Required behaviors
- Add deterministic tests for:
  - routing class selection (ANSWER/TOOL/DELEGATE/MEMORY/BACKGROUND)
  - tool approval policy
  - memory queue semantics (`queued` -> `committed`)
  - retrieval stage event emission
- Add smoke benchmark script with pass/fail thresholds.

#### 4.18 File-level changes
- `tests/test_model_selection.py`
  - Extend routing assertions with edge cases.
- `tests/test_tools.py`
  - Add approval-required and deny-path tests.
- New file: `tests/test_memory_write_queue.py`
  - Queue and replay behavior tests.
- New file: `tests/test_retrieval_stage_events.py`
  - SSE event contract validation.
- New file: `scripts/benchmark_agent_regression.py`
  - Lightweight benchmark + summary output.

#### 4.19 Acceptance criteria
- All new tests pass in CI/local.
- Benchmark script returns non-zero on regression threshold breach.

## 5) Execution Order and Timeline

### Week 1 (Quick wins + correctness)
- Implement Phase 1 core queue + status envelopes.
- Implement Phase 2 approval metadata for highest-risk tools only.
- Add initial tests for queue and approval.

### Weeks 2-3 (Observability + hardening)
- Implement Phase 3 stage operators + SSE events.
- Implement Phase 4 permission model and endpoint enforcement.
- Add UI handling for stage events.

### Weeks 4+ (reliability and quality)
- Complete Phase 5 benchmark + regression guardrails.
- Expand delegation capabilities safely.
- Tune metrics and alerting thresholds.

## 6) Migration and Backward Compatibility

- Keep current tool execution APIs; add optional metadata fields so legacy callers continue working.
- Keep current memory add/search interfaces; wrap with status envelope at boundary layer first.
- Introduce queue as additive path, then switch default write strategy after tests pass.

## 7) Risks and Mitigations

- Risk: Added complexity in memory writes.
  - Mitigation: isolate queue logic in `memory/write_queue.py`; keep provider adapters thin.
- Risk: User friction from approval prompts.
  - Mitigation: only gate high-risk tools first; add policy controls to tune.
- Risk: SSE event noise.
  - Mitigation: strict event schema and stage-level aggregation in UI.

## 8) Metrics of Success

- Memory write success rate >= 99% including outage scenarios.
- Zero duplicate memory commits after replay.
- High-risk tool policy violations = 0.
- Retrieval stage visibility present on >= 95% retrieval requests.
- Regression benchmark stable or improving for routing and tool correctness.

## 9) First Implementation Ticket Set (suggested)

1. Add `memory/write_queue.py` with append/replay/idempotency helpers.
2. Add `memory_write_log` in SQLite backend + request_id uniqueness.
3. Update Mem0 backend write path to return status envelopes.
4. Add tool risk metadata and approval request plumbing in registry.
5. Enforce approval in tool loop for marked tools.
6. Add tests for memory queue replay and approval-required tools.

## 10) Definition of Done (per phase)

A phase is done only when:
- Feature implementation is complete.
- Tests are added and passing.
- Failure paths are covered (not only happy paths).
- Logging/metrics are present for the new behavior.
- No regressions in `pytest -q` baseline.
