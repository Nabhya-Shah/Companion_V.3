# Companion AI Roadmap (Agentic Evolution V.4)

> Last Updated: 2026-03-19
> Status: Pivoting to Heavyweight Automation (Browser and Computer Control)
> Next focus: Phase 1 (Stateful Browser Sessions)

## How To Use This Doc
- `ROADMAP.md` is the only active planning document.
- `FEATURE_TRACKER_ARTIFACT.md` tracks user-visible shipped functionality.
- `ROADMAP_ARTIFACT.md` is archived context only.

## Current Product Direction
After stabilizing orchestrator routing, memory quality, and policy controls, the product shifts back to its original vision: agentic browser and desktop automation with strong safety gates.

The execution order is:
1. Browser Sessions MVP
2. Computer Control MVP
3. Scheduled automation integration
4. Research-gated enhancements

## Success Criteria (Program-Level)
1. Browser task success: >= 85% by end of MVP.
2. Computer-use success: >= 70% before broad enablement.
3. Latency budget: DOM actions <= 2s median; vision actions <= 8s median.
4. Safety: 100% high-risk actions require approval; 0 unapproved executions.
5. Observability: 100% action chains produce lifecycle events in chat UI.

## Active Execution Window

### Phase 1: Browser Sessions MVP (Sprint 1)
Goal: reliable, multi-step browser automation with persistent context.

Deliverables:
- Create `BrowserLoop` using existing Playwright surface in `companion_ai/agents/browser.py`.
- Implement action contract: `navigate`, `click`, `type`, `extract`, `wait`, `screenshot`.
- Add orchestrator routing for browser intents.
- Stream lifecycle traces to chat timeline.
- Add timeout, retry, and resumable step policies.

Success criteria:
- Multi-turn browser flows retain context across steps.
- Browser lifecycle events are visible and ordered in UI.
- Failures return deterministic reasons and retry behavior.

### Phase 2: Computer Control MVP
Goal: hybrid planner-executor architecture for desktop actuation.

Deliverables:
- Create `ComputerLoop` with vision-guided coordinate executor.
- Keep planner-executor separation (orchestrator plans, executor acts, feedback loop adapts).
- Add safety interlocks (approval gates, kill switch, max chain length).
- Add Windows DPI calibration and coordinate normalization safeguards.

Success criteria:
- Controlled desktop actions execute safely on target tasks.
- High-risk actions are blocked without approval.
- Vision failures degrade safely and remain observable.

### Phase 3: Scheduler and Proactive Automation
Goal: recurring and headless routines.

Deliverables:
- Extend `companion_ai/services/jobs.py` to run browser/computer plans.
- Add idempotency markers for scheduled runs.
- Attach run trace IDs to proactive summaries and timeline events.

Success criteria:
- Scheduled runs avoid duplicate side effects on retries.
- Success and failure summaries are traceable in UI.

### Phase 4: Research-Gated Enhancements
Goal: safely integrate high-value external patterns.

Deliverables:
- Pilot memory/context concepts from Cognee and OpenViking incrementally in retrieval paths.
- Benchmark Fara-style executor as optional plugin behind abstraction.

Go/No-go gate for executor substitution:
- Promote only if success improves by >= 10 points or latency improves by >= 20% on target tasks without safety regression.

## Explicit Non-Priorities Right Now
- Full immediate replacement of SQLite/Mem0 backends.
- Enterprise auth or full UI platform migration.
- Mobile automation runtime.

## Definition Of Done For Next Sprint
- `BrowserLoop` orchestrates a multi-step session without losing state.
- Chat UI visualizes each Playwright step in sequence.
- Unapproved high-risk requests return access-denied behavior.
