# Companion AI Roadmap

> Last Updated: 2026-03-15
> Status: Groq-first provider decision locked; Next focus is Persona depth
> Tests: 238 passing

## How To Use This Doc

- `ROADMAP.md` is the only active planning document.
- `FEATURE_TRACKER_ARTIFACT.md` tracks user-visible shipped functionality.
- `ROADMAP_ARTIFACT.md` is archived context only and should not be used for current planning.

## Current Product Direction

Companion is no longer blocked on provider exploration. The product advantage is not another round of model churn; it is better long-horizon memory, stronger retrieval quality, and a persona that is grounded in real accumulated context.

The near-term roadmap is therefore:

1. Finish the memory foundation.
2. Improve long-term recall quality.
3. Ground persona depth in structured memory.
4. Keep latency and cost work tactical, not dominant.

## Current Architecture Baseline

| Area | Current baseline | Planning implication |
|---|---|---|
| Primary chat + orchestrator | Groq `openai/gpt-oss-120b` | Keep as production default unless a future change clearly beats it |
| Fast tool execution | Groq `llama-3.1-8b-instant` | Useful for a future quick-tool bypass |
| Memory AI | Groq `meta-llama/llama-4-scout-17b-16e-instruct` plus local loops | Memory work needs an explicit local-vs-cloud model policy |
| Local specialist path | vLLM `Qwen/Qwen2.5-3B-Instruct` | Good fit for extraction, reflection, or recall support when local quality is acceptable |
| Local vision fallback | Ollama `llava:13b` | Keep local fallback capability intact |
| Provider strategy | Groq-first with key rotation | Good enough for now; not the active roadmap problem |

## What Is Completed

| Phase | Status | Notes |
|---|---|---|
| P1 | Complete | Foundation, runtime recovery, security baseline |
| P2 | Complete | Session-scoped memory, memory quality pipeline, API hardening |
| P3 | Complete | Plugin registry, sandboxing, realtime control plane, scheduling, workspace separation |
| P4 | Complete | File workflows, memory review center, automation UX, integration reliability |
| P5 | Complete | Monolith split, unified knowledge, persona foundation, orchestrator-first cleanup |
| P6 | Complete | Workflows, approvals, planning transparency, proactive insights |
| P7-A | Complete | Provider seam inventory and decision baseline |
| P7-B | Complete | Benchmark gate; Groq retained as default |

## Active Execution Window

### P7-03 Memory Extraction Completion (Complete)

Goal: replace placeholder or partial extraction behavior with a real model-backed path that can become the base layer for long-horizon memory.

Deliverables:

- `MemoryLoop._extract()` backed by a real model call
- focused regression coverage for extraction quality and failure handling
- clear separation between extraction logic and persistence logic
- orchestrator now auto-extracts structured facts after non-memory turns and gates Mem0 writes by confidence
- lower-confidence extracted facts now flow into a dedicated pending-review queue with evidence, justification, and basic contradiction hints
- review approval promotes queued facts into the main memory store instead of leaving them as weak profile rows

Success criteria:

- fact extraction works reliably on real conversation snippets
- extraction failures degrade safely without corrupting memory state
- the result format is stable enough to support later consolidation work
- reviewable facts stay visible without polluting trusted memory until approved

### P7-04 Memory Model Manager (Complete)

Goal: introduce a minimal memory-focused routing layer for local models, Groq fallback, and future embedding selection without overbuilding a full provider abstraction platform.

Deliverables:

- explicit model roles for `chat`, `memory_processing`, and `embeddings`
- local-first vs Groq-fallback policy for memory jobs
- documented configuration surface for memory-model selection
- first benchmark lineup defined: `gpt-oss-120b` for chat/orchestration, `llama-3.3-70b-versatile` for primary memory processing, `llama-4-scout-17b-16e-instruct` as the fast memory path, and local `nomic-embed-text` for embeddings

Success criteria:

- memory processing no longer relies on ad hoc provider decisions
- local and cloud memory paths are understandable and testable
- future embedding work has a stable place to live

### P8-01 Long-Horizon Memory Quality (Complete)

Goal: make stored memory trustworthy over weeks and months, not just collectible.

Deliverables:

- better retrieval ranking for stable, relevant memories
- consolidation and dedup improvements across repeated facts
- contradiction handling and confidence/decay rules for older memories
- explainable recall signals for why a memory surfaced

Success criteria:

- recall stays useful over long sessions and repeated use
- stale or conflicting memories are less likely to dominate context
- the system can justify why a surfaced memory matters

### P8-02 Persona Grounded In Memory (Complete)

Goal: make persona evolution reflect persistent user context rather than style-only prompt behavior.

Deliverables:

- structured persona state built from stable preferences, recurring themes, rapport, and ongoing goals
- memory-backed persona update rules instead of broad wholesale rewrites
- focused tests for persona stability and drift control

Success criteria:

- persona feels cumulative rather than reset-prone
- style changes stay grounded in actual interaction history
- user-specific preferences meaningfully shape responses over time

Shipped now:

- persona state tracks ongoing goals and recurring themes
- evolution merges are incremental with caps and history snapshots
- memory-backed seeding from stable profile facts anchors goals/themes to persistent context
- focused regression tests cover drift control and memory grounding

### P8-03 Reflection And Project Continuity (Complete)

Goal: give Companion a stronger sense of continuity across projects, open loops, and recent life context.

Deliverables:

- lightweight reflection/synthesis jobs over recent conversations and documents
- persistent project summaries, blockers, next steps, and open questions
- cross-session continuity summaries that can be recalled without dumping raw history

Success criteria:

- Companion can summarize ongoing projects and open loops coherently
- cross-day continuity feels intentional instead of accidental
- the user gets strategic support, not just reactive answers

Shipped now:

- continuity snapshot service stores summary, projects, blockers, next steps, and open questions
- daily continuity generation runs in background worker (with force-refresh endpoint)
- latest continuity snapshot is injected into dynamic prompt context for cross-session recall
- API endpoints expose latest/history continuity snapshots for UI and diagnostics

### Tactical Supporting Slice: Quick Tool Path

Goal: reduce latency and cost for simple tool-style requests without treating this as the main product differentiator.

Deliverables:

- direct lightweight tool route for obvious exact-answer cases
- focused tests covering routing and fallback behavior

Success criteria:

- simple tool requests avoid unnecessary orchestrator cost
- the fast path does not weaken safety or routing clarity

## Planning Order

1. `P7-03 Memory Extraction Completion`
2. `P7-04 Memory Model Manager`
3. `P8-01 Long-Horizon Memory Quality`
4. `P8-02 Persona Grounded In Memory`
5. `P8-03 Reflection And Project Continuity`
6. Quick Tool Path as a tactical supporting slice

## Explicit Non-Priorities Right Now

- broad provider migration work
- multi-provider abstraction for its own sake
- plugin/integration expansion as the main product focus
- mobile/UI polish unless it unlocks the memory roadmap cheaply

## Risks To Watch

| Risk | Why it matters | Mitigation |
|---|---|---|
| Memory quality without retrieval discipline | Better extraction alone can still produce noisy recall | Pair extraction work with ranking, consolidation, and contradiction handling |
| Persona drift | Persona can become cosmetic or unstable if not grounded | Tie persona updates to structured memory signals and test for stability |
| Over-abstracted model management | A giant provider framework would slow product work | Keep the model manager focused on memory roles only |
| Artifact drift | Planning docs can become contradictory again | Keep only one active roadmap and treat the artifact file as archive-only |

## Definition Of Done For This Window

- memory extraction is real, tested, and dependable
- memory model routing is explicit and understandable
- long-horizon recall quality has measurable improvements
- persona evolution is demonstrably grounded in persistent context
- roadmap and tracker remain consistent after each delivered slice
