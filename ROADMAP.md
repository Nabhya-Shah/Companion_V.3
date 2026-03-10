# Companion AI — Master Roadmap & Sprint Plan

> **Last Updated**: 2026-03-10  
> **Status**: Phase 6 complete; Groq-first provider decision locked; next focus is Phase 7 quick-tool and memory work  
> **Tests**: 219 passing

---

## Project Overview

Personal AI companion with orchestrator brain, persistent memory, knowledge graph, scheduled automations, smart home integration, and evolving persona. Built with Python 3.11, Flask, a Groq-first cloud path plus local vLLM/Ollama specialists, Mem0 + Qdrant vectors, and a vanilla JS frontend.

---

## Completed Phases

| Phase | Name | Status | Summary |
|-------|------|--------|---------|
| P1 | Foundation | ✅ Done | Flask app, basic chat, Groq integration |
| P2 | Memory System | ✅ Done | SQLite facts, Mem0 vectors, conflict detection, dedup, confidence scoring |
| P3 | Knowledge & Brain | ✅ Done | Document upload, brain index, knowledge graph, D3 visualizer |
| P4 | Orchestrator & Loops | ✅ Done | 120B routing brain, local loops (memory, tool, vision), job scheduler |
| P5 | Code Quality | ✅ Done | Monolith splits (llm/, tools/, web/), dead code removal, 211 tests |
| P6-A/B/C/D | Features | ✅ Done | Workflows, approvals, planning, scheduled tasks, plugin policy, proactive insights |

---

## Recent Work: Performance Optimizations (2026-03-09)

**Goal**: Eliminate unexpected token burn from background systems and page loads.

**Issues Fixed**:
1. ✅ Workflow reload spam — `reload_workflows()` logged on every Tasks poll even when files unchanged
2. ✅ Automatic Mem0 migration — fresh sessions triggered migration work on every memory read
3. ✅ Eager frontend loading — page bootstrap hit `/api/memory` and `/api/brain/files` before panels opened
4. ✅ Session scope leaks — memory operations could bleed across sessions within same profile

**Solutions**:
- Change-aware workflow reload using `(filename, mtime_ns, size)` signature
- Moved migration trigger to explicit context-switch only (removed from read path)
- Lazy-loaded memory/knowledge panels — data loads only when panel opens
- Session-scoped Mem0 `user_id` format propagated throughout orchestrator and loops

**Impact**:
- Fresh page load: 0 memory/brain endpoint hits
- Tasks panel poll: no workflow reload logs
- Test suite: 219 passing (+8 from baseline)

**Files Modified**: `services/workflows.py`, `web/memory_routes.py`, `static/app.js`, `static/memory.js`, `orchestrator.py`, `local_loops/memory_loop.py`

---

## Next Execution Window: Phase 7 (Groq-First Execution)

**Decision**: Groq remains the primary provider.

Provider benchmarking is complete enough to stop spending roadmap time on provider churn. Groq tied for best benchmark score, had the best latency profile, and already matches the repo's architecture and key-rotation setup. Mistral can remain a future fallback candidate on paper, but it is not the active roadmap path. Gemini remains useful for later experiments, not for the default runtime.

The roadmap should now move back to product work on top of the existing Groq-first assumptions: OpenAI-compatible chat clients, Groq key rotation, a Groq-native tool path for light tools, and local specialists for heavy work.

### Current Provider Baseline

| Workload | Current Provider / Model | Why it exists now | Planning implication |
|----------|--------------------------|-------------------|----------------------|
| Primary chat + orchestrator | Groq `openai/gpt-oss-120b` | Strong reasoning + current production baseline | Migration target must preserve structured routing quality |
| Fast tool execution | Groq `llama-3.1-8b-instant` | Cheap, fast light-tool path on OpenAI-style API | Good candidate to replace or bypass with quick-tool routing |
| Cloud vision | Groq `meta-llama/llama-4-maverick-17b-128e-instruct` | Existing image analysis path | Alternate providers must match streaming + multimodal needs |
| Memory AI / extraction | Groq `meta-llama/llama-4-scout-17b-16e-instruct` | Structured extraction and cloud fallback | Could be replaced, reduced, or pushed more local |
| Local heavy specialist path | Local vLLM `Qwen/Qwen2.5-3B-Instruct` | Heavy tools stay local to save cloud spend | Provider strategy must preserve local-first capability |
| Local vision fallback | Ollama `llava:13b` | Local image analysis fallback | Still useful even if primary cloud provider changes |

### Provider Decision Outcome

| Candidate | Outcome | Why |
|-----------|---------|-----|
| **Groq** | Chosen default | Matched best benchmark score and won on latency while already fitting current architecture |
| **Mistral** | Keep as backup candidate only | Comparable score, but slower and not worth primary-path migration work now |
| **Gemini** | Defer | Comparable score, but much slower in this harness and not worth default-path complexity |

### Sprint P7-A (Completed) — Provider Baseline & Decision

**Goal**: confirm whether the roadmap should stay Groq-first or pivot.

- [x] Inventory provider touchpoints across chat, tools, vision, memory, embeddings, and orchestrator routing
- [x] Document Groq-specific behavior and key-rotation assumptions
- [x] Benchmark the strongest alternatives against Companion workloads
- [x] Decide whether to pivot or stay Groq-first

**Deliverables**:
- Provider architecture baseline table
- Migration seam map
- Dependency list for provider-sensitive roadmap items

**Current seam inventory**:

| Seam | Current file(s) | Current assumption | Migration risk |
|------|------------------|--------------------|----------------|
| Model + key configuration | `companion_ai/core/config.py` | Groq keys, Groq key rotation, Groq-first model IDs, light/heavy routing policy | High |
| Primary chat client | `companion_ai/llm/router.py` | Imports Groq client globals directly and assumes Groq-backed default chat path | High |
| Tool loop implementation | `companion_ai/llm/groq_provider.py` | Groq SDK objects, Groq/OpenAI-style `tool_calls`, Groq-oriented synthesis loop, local-model exception handling | High |
| Orchestrator decision path | `companion_ai/orchestrator.py` | `_get_client_and_model()` is effectively Groq-primary only for orchestration | High |
| Memory AI extraction | `companion_ai/memory/ai_processor.py` | Dedicated `groq_memory_client` for importance, summaries, and fact extraction | Medium |
| Mem0 fallback LLM | `companion_ai/memory/mem0_backend.py` | Groq fallback model and Groq API key assumptions when local path is unavailable | Medium |
| Knowledge graph extraction | `companion_ai/memory/knowledge_graph.py` | Uses `groq_memory_client` directly for graph-oriented inference | Medium |
| Vision cloud path | `companion_ai/agents/vision.py`, `companion_ai/local_loops/vision_loop.py` | `GROQ_VISION_API_KEY` and Groq-hosted vision model as current cloud path | Medium |
| TTS provider path | `companion_ai/services/tts.py` | Hard-coded Groq speech endpoint and voice naming assumptions | Medium |
| Local specialist backend | `companion_ai/local_llm.py` | Local vLLM exposes OpenAI-style API; Ollama retained as separate fallback style | Low |
| Token budget reporting | `companion_ai/services/token_budget.py` | Groq free-limit heuristics embedded in budget guidance | Low |

**Minimum provider adapter surface**:

- `chat_complete(messages, model, **opts)`
- `chat_stream(messages, model, **opts)`
- `tool_complete(messages, tools, tool_choice, model, **opts)`
- `structured_complete(messages, response_format, model, **opts)`
- `vision_complete(messages_or_parts, model, **opts)`
- `embeddings_create(input, model, **opts)`
- `list_models()`
- `usage_from_response(response)`

**Initial dependency split**:

- Provider-sensitive next items: quick-tool path, memory extraction completion, token-budget redesign, any primary-chat/provider migration
- Provider-independent next items: mobile work, UI polish, some workflow UX improvements, selected Phase 7 plugin/integration ergonomics

**Success criteria**:
- No major model call path remains undocumented
- Groq-specific code paths are distinguishable from transport-agnostic logic
- The team can describe exactly what must be abstracted before shadow-mode migration

### Sprint P7-B (Completed) — Benchmark Gate

**Goal**: produce a go/no-go benchmark gate before resuming product work.

- [x] Benchmark Groq against viable alternatives for Companion workload classes
- [x] Score candidates for reasoning quality, tool-call reliability, and streaming behavior
- [x] Decide the active architecture move: stay Groq-first
- [x] Record why the other providers are not advancing now

**Benchmark rubric**:

| Criterion | Weight | What Companion needs |
|-----------|--------|----------------------|
| Routing + reasoning quality | 25% | Stable JSON or structured decision-making for orchestrator-style flows |
| Tool/function-call reliability | 20% | Predictable schema adherence and low repair overhead |
| Streaming behavior | 15% | Clean SSE-friendly incremental responses without brittle parsing |
| Cost / generous usage envelope | 15% | Better economics than Groq-first everywhere, or a clearly justified tradeoff |
| Multimodal + embeddings fit | 10% | Enough coverage for current vision and future memory/search work |
| Migration effort | 10% | Limited rewrites in provider code and low blast radius across the app |
| Usage visibility + auditing | 5% | Usable token/cost accounting for regressions and rollout control |

**Research-backed shortlist**:

| Provider | Role in shortlist | Current live evidence | Main strengths | Main concerns |
|----------|-------------------|-----------------------|----------------|---------------|
| **Gemini direct** | Primary migration candidate | OpenAI compatibility docs, streaming, function calling, structured outputs, embeddings, multimodal, current pricing/free tier, current model/deprecation pages | Broadest feature consolidation, generous free tier, strong multimodal + embeddings, current model momentum | OpenAI compatibility is still beta; preview-model churn and deprecations require careful pinning |
| **OpenRouter** | Best abstraction / fallback layer candidate | OpenAI-like normalized API, SSE streaming, tool calling, structured outputs, provider routing, cost/usage reporting, current model marketplace | Best hedge against vendor lock-in, rich usage visibility, many low-cost or free model choices, easy shadow routing | Behavior varies by upstream model/provider; not a single-model quality guarantee |
| **Fireworks** | Strong direct open-weight cloud candidate | OpenAI-compatible chat completions, streaming, tools, structured outputs, prompt caching, perf metrics, broad model library, current pricing | Mature direct API, strong observability, broad open-model lineup, competitive serverless pricing | Less compelling free/generous entry than Gemini/Cerebras; still another direct provider to manage |
| **Cerebras** | Speed-specialist candidate | Current chat completions API, structured outputs, parallel tool calls, GPT-OSS-120B at ~3000 tok/s, free/developer tiers, current pricing | Exceptional speed, credible for coding/orchestrator experiments, direct API is fairly clean | Narrower current model surface, weaker multimodal story, GPT-OSS pricing above Groq on developer tier |
| **Together AI** | Secondary open-model candidate | Current chat docs, streaming docs, function-calling docs, broad price sheet, many hosted models | Breadth of open models, reasonable pricing, documented multi-step/parallel tool calling | Weaker evidence collected here for structured-output observability and platform-level migration advantages versus Fireworks/OpenRouter |
| **Groq** | Control baseline / fallback | Current production path, OpenAI compatibility, tool use, prompt caching, structured outputs, current model/pricing/rate-limit docs | Known-good behavior, strong latency, already wired into Companion | Current architecture lock-in, cost pressure, less reason to stay exclusive |

**Weighted comparison snapshot**:

| Provider | Routing / reasoning (25) | Tool reliability (20) | Streaming (15) | Cost / free tier (15) | Multimodal / embeddings (10) | Migration effort (10) | Usage visibility (5) | Total / 100 |
|----------|---------------------------|------------------------|----------------|-----------------------|------------------------------|----------------------|----------------------|-------------|
| Gemini direct | 22 | 16 | 12 | 14 | 10 | 8 | 3 | **85** |
| Fireworks | 20 | 18 | 13 | 11 | 8 | 8 | 5 | **83** |
| OpenRouter | 19 | 14 | 13 | 13 | 8 | 9 | 5 | **81** |
| Groq (baseline) | 20 | 17 | 14 | 12 | 7 | 10 | 4 | **84** |
| Cerebras | 18 | 16 | 14 | 10 | 5 | 8 | 4 | **75** |
| Together AI | 17 | 15 | 12 | 11 | 6 | 7 | 3 | **71** |

**Interpretation**:

- **Gemini direct** is the strongest single-provider replacement candidate if the goal is to improve cost/free-tier posture while also gaining multimodal and embedding breadth.
- **OpenRouter** is the strongest architectural hedge if the goal is to reduce lock-in and enable shadow-mode routing across multiple providers.
- **Fireworks** is the strongest pure open-weight direct-provider alternative for a more provider-stable, model-rich migration than Together AI.
- **Cerebras** is compelling for speed-sensitive orchestrator or coding experiments, but not yet the best full-stack replacement for Companion's current mix.
- **Together AI** remains viable, but it no longer looks like the leading direct alternative once Fireworks and Cerebras are included in the comparison.

**Benchmark outcome**:

1. Keep **Groq** as the production default.
2. Use Groq key rotation to absorb rate-limit pressure.
3. Do not spend current roadmap time on provider abstraction or migration.
4. Resume product work with the existing Groq-first architecture.

**Deliverables**:
- Ranked provider shortlist
- Benchmark rubric for Companion workloads
- Shadow-mode migration recommendation

**Success criteria**:
- At least 3 credible provider options or hybrids are scored against real Companion requirements
- The roadmap can justify why one candidate advances and the others do not
- Product work for the next sprint is gated by an explicit provider decision, not by intuition

### Post-Decision Next Work

- Prioritize `P7-03 Quick Tool Path`
- Then complete `P7-04 Memory extraction completion`
- Keep mobile UX deferred unless it becomes a cheap follow-on to higher-value work

---

## Historical: P6 Makeover (Completed)

This section is retained as the execution record for the completed P6 makeover work.

### Known Bugs (Pre-Sprint)

| Bug | Root Cause | File | Line |
|-----|-----------|------|------|
| **Memory toast fires on every message** | `memory_saved = core_config.USE_MEM0` hardcoded `True` | `web/chat_routes.py` | L105 |
| **~3K tokens for "Hello"** | 800-token orchestrator prompt + 120-token capabilities always injected + 10 memories fetched for greetings + `max_tokens=1000` for routing JSON | `orchestrator.py`, `context_builder.py`, `config.py` | L263, L66-78, L269 |
| **Companion doesn't know P6 features** | Workflows, approvals, planning not mentioned in any prompt | `context_builder.py`, `companion.yaml` | L66-78 |
| **Broken import (runtime crash)** | `from companion_ai.vision_manager import vision_manager` — module doesn't exist | `tools/system_tools.py` | L156 |

### Codebase Audit Findings

**Dead Code / Stale References:**
- `agents/__init__.py` references nonexistent `computer.py` module
- `memory_extraction.py` referenced in README + ARCHITECTURE but doesn't exist (lives in `memory/ai_processor.py`)
- Missing `core/__init__.py` (inconsistent with all other subpackages)
- Orphaned scripts: `safe_run_browser.ps1`, `safe_run_trainer.ps1`
- Stale `package.json` (only Playwright, browser agent shelved)
- `pyrightconfig.json` excludes nonexistent `OmniParser` directory

**Unused Dependencies (requirements.txt):**
- `openai-whisper` — no import found
- `pyautogui` — no import found
- `FlagEmbedding` — no import found

**Git Hygiene:**
- `companion_ai/data/` contains runtime DBs (brain_index.db, companion_ai.db, jobs.db) — should be gitignored

**Frontend:**
- `app.js` — 3,693 lines (monolith)
- `app.css` — 3,299 lines (monolith)
- `index.html` — 12 inline `style=` attributes
- 3 orphaned sidebar panes (`pane-tokens`, `pane-models`, `pane-metrics`) — HTML+JS exist but no tab buttons to reach them
- `graph.html` — 991 lines, fully self-contained with embedded CSS/JS

**Largest Python Files:**
1. `memory/sqlite_backend.py` — 1,155 lines
2. `llm/groq_provider.py` — 966 lines
3. `memory/knowledge_graph.py` — 792 lines
4. `orchestrator.py` — 709 lines
5. `services/jobs.py` — 650 lines

---

## Sprint Plan

### Phase 1: Backend Bug Fixes

- [x] **Bug A — False memory toast**
  - Replace `memory_saved = core_config.USE_MEM0` with actual result from Mem0 thread
  - Use a mutable container (`dict`) to thread the result back after stream completes
  
- [x] **Bug B — Token waste**
  - Reduce orchestrator `max_tokens` from 1000 → 300 (routing JSON is ~100 tokens)
  - Gate `[YOUR CAPABILITIES]` block: skip for short greetings (< 15 chars, no question marks)
  - Skip memory retrieval for greeting/filler messages (< 3 meaningful words)
  
- [x] **Bug C — Feature awareness**
  - Update capabilities list: remove `COMPUTER` (shelved), add `WORKFLOWS`, `APPROVALS`, `PLANNING`, `SCHEDULED TASKS`
  - Update `companion.yaml` persona to mention P6 features

- [x] **Bug D — Broken import**
  - Fix `system_tools.py` L156: `from companion_ai.vision_manager` → `from companion_ai.agents.vision`

### Phase 2: Backend Cleanup

- [x] Remove ghost `computer` import from `agents/__init__.py`
- [x] Create empty `core/__init__.py`
- [x] Delete `scripts/safe_run_browser.ps1`, `scripts/safe_run_trainer.ps1`
- [x] Delete stale `package.json`
- [x] Add `companion_ai/data/` to `.gitignore`
- [x] Fix `ARCHITECTURE.md`: remove `memory_extraction.py`, mark `vision.py` as active, remove `computer_loop.py`
- [x] Fix `README.md`: remove `memory_extraction.py` from structure
- [x] Clean `pyrightconfig.json`: remove `OmniParser`
- [x] Audit + trim `requirements.txt` (remove confirmed unused: `openai-whisper`, `pyautogui`, `FlagEmbedding`)
- [x] Add clarity comments to compat shims (`llm_interface.py`, `web_companion.py`)

### Phase 3: UI Redesign — Unified Panel

**Goal**: Replace dual-sidebar (left=tasks, right=memory) + smart-home modal with a single right panel.

**New layout:**
```
┌────────────────────────────────────────────────┐
│  [Brand]                    [icons] [⚙ Settings] │  ← topbar
├────────────────────────────────┬───────────────┤
│                                │  Panel        │
│        Chat Area               │  ┌─────────┐  │
│                                │  │ tab bar │  │
│                                │  ├─────────┤  │
│                                │  │ content │  │
│                                │  │         │  │
│   [Composer bar]               │  │         │  │
│                                │  └─────────┘  │
└────────────────────────────────┴───────────────┘
```

**Panel tabs (5):**

| # | Tab | Content | Moved From |
|---|-----|---------|------------|
| 1 | Tasks | Active tasks + Routines | Left sidebar |
| 2 | Memory | Facts, insights, pending review, search | Right sidebar `pane-memory` |
| 3 | Knowledge | Document upload, indexed files, recent uploads | Right sidebar `pane-knowledge` |
| 4 | Stats | Token usage + Model architecture + Feature flags + Performance metrics | Orphaned `pane-tokens`, `pane-models`, `pane-metrics` (finally accessible!) |
| 5 | Smart Home | Room controls + scenes | Smart home modal |

**Header icons (left to right):**
- Knowledge Graph (external link `/graph`)
- Tasks → opens panel to Tasks tab
- Memory → opens panel to Memory tab
- Knowledge → opens panel to Knowledge tab
- Stats → opens panel to Stats tab
- Smart Home → opens panel to Smart Home tab
- Settings → opens settings modal

**Settings modal (trimmed to 3 sections):**
- Interface (show token counts toggle)
- Data (export chat history)
- Danger Zone (clear chat, reset all memory)

**Removed from Settings UI (still available via API/config):**
- Voice / TTS controls
- Context IDs (workspace, profile, session)
- Plugin management

**Implementation steps:**
- [x] HTML: Replace dual-sidebar + smart-home modal with single `<aside id="sidePanel">`
- [x] HTML: Update topbar icons to target unified panel
- [x] HTML: Trim settings modal to 3 sections
- [x] CSS: Create `.side-panel` styles (slide-in right, ~380px, below topbar)
- [x] CSS: Create `.panel-tabs` icon bar + active states
- [x] CSS: Remove `.tasks-sidebar`, `.memory-sidebar`, `.smart-home-modal` styles
- [x] JS: Create `togglePanel(tabName)` replacing separate sidebar toggles
- [x] JS: Wire header icons → `togglePanel('tasks')` etc.
- [x] JS: Preserve all data-loading functions, call on tab activation
- [x] JS: Remove deleted settings handlers (voice, context, plugins)

### Phase 4: Frontend Cleanup

- [x] CSS purge: remove styles for deleted elements (~90 lines: `.tabs`/`.tab`/`.tabpanes`, `.latency-bar`, `.loxone-control-center`)
- [ ] ~~Move inline `style=` attributes to CSS classes~~ (skipped — 6 `display:none` toggles, low risk)
- [x] JS dead code: remove functions for deleted UI elements (~200 lines: plugin catalog, context panel, dead settings refs, TTS toggle)
- [ ] ~~CSS variable audit~~ (skipped — complementary duplicates kept as low-risk)

### Phase 5: Extras (in priority order)

**D — Animations & Polish**
- [x] Panel open/close: `transform: translateX` transition (0.25s ease) — already had CSS transition
- [x] Panel pane fade-in: `@keyframes paneFadeIn` (opacity + translateY)
- [x] Chat message fade-in animation — already existed
- [x] Loading skeleton states for panel content

**C — Theme Customization**
- [x] Add "Theme" section to Settings (3 swatch buttons in Interface section)
- [x] 3 presets (Midnight/default, Soft Dark, Light) via `[data-theme]` CSS custom property swap
- [x] localStorage persistence + restore on page load
- [x] Visually tested all 3 themes with Playwright

**A — JS Module Split**
- [x] Split `app.js` into: `chat.js`, `panel.js`, `memory.js`, `settings.js`, `tasks.js`, `smarthome.js`, `utils.js`
- [x] Use ES module `import/export` with `<script type="module">`
- [x] Event bus for cross-module communication (no circular deps)
- [x] All 5 panel tabs verified working with Playwright
- [x] 211 backend tests still passing

**B — Mobile-Friendly**
- [ ] Panel becomes full-width overlay on < 768px
- [ ] Composer stacks vertically on narrow screens
- [ ] Header icons collapse into hamburger menu

---

## Verification Checkpoints

| After | Test |
|-------|------|
| Phase 1 | `pytest -q` → 211 pass. "Hello" → no memory toast. Token count < 1500. "What can you do?" → mentions workflows. |
| Phase 2 | `pytest -q` → 211 pass. No broken imports. `.gitignore` covers data/. Docs accurate. |
| Phase 3 | All 5 panel tabs open/close. All data loads correctly. Settings has 3 sections. No console errors. |
| Phase 4 | No visual regressions. No unused CSS classes for deleted elements. |
| Phase 5 | Smooth animations. Themes switch correctly. JS modules load. Mobile viewport renders. |

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Python | 3.11 (venv) |
| Web Server | Flask + SSE |
| Primary LLM | Groq Cloud — `openai/gpt-oss-120b` (orchestrator + primary chat) |
| Fast Tools | Groq Cloud — `llama-3.1-8b-instant` |
| Vision | Groq Cloud — `llama-4-maverick-17b-128e-instruct` |
| Memory AI | Groq Cloud — `llama-4-scout-17b-16e-instruct` |
| Mem0 Backend | Groq (via `MEM0_USE_OLLAMA=false`) |
| Embeddings | `all-MiniLM-L6-v2` (sentence-transformers) |
| Vector Store | Qdrant (local) |
| Fact Store | SQLite |
| Smart Home | Loxone Miniserver |
| Frontend | Vanilla JS + CSS custom properties |
| Knowledge Graph Viz | D3.js |
| Tests | pytest (219 tests, 22+ suites) |

---

## UI Design Inspiration

- ChatGPT — clean single-panel layout, minimal chrome
- Google Gemini — icon-based topbar, spacious chat
- MiniMax — dense but organized sidebar
- Qwen Chat — polished glassmorphism dark theme

**Design tokens (current):**
- Background: `#0a0a0f` (near-black)
- Accent: `#8b5cf6` (purple)
- Font: Inter + JetBrains Mono
- Style: Glassmorphism with `backdrop-filter: blur()`
- Border radius: 12px cards, 8px inputs
- 40+ CSS custom properties for theming

---

## File Map (Quick Reference)

| Area | Key Files |
|------|-----------|
| Entry point | `run_companion.py` → `companion_ai/web/__init__.py` |
| Orchestrator | `companion_ai/orchestrator.py` (709 lines) |
| Chat streaming | `companion_ai/web/chat_routes.py` (385 lines) |
| Context building | `companion_ai/core/context_builder.py` (258 lines) |
| Memory | `companion_ai/memory/sqlite_backend.py` (1,155 lines) |
| Mem0 vectors | `companion_ai/memory/mem0_backend.py` (613 lines) |
| Knowledge graph | `companion_ai/memory/knowledge_graph.py` (792 lines) |
| Tool registry | `companion_ai/tools/registry.py` (506 lines) |
| Persona | `companion_ai/services/persona.py` |
| Jobs/Scheduler | `companion_ai/services/jobs.py` (650 lines) |
| Frontend JS | `static/app.js` (~50 lines entry) + `chat.js` (~560) + `panel.js` (~170) + `memory.js` (~310) + `settings.js` (~240) + `tasks.js` (~530) + `smarthome.js` (~240) + `utils.js` (~160) |
| Frontend CSS | `static/app.css` (~3,270 lines) |
| HTML template | `templates/index.html` (~644 lines) |
| Graph visualizer | `templates/graph.html` (991 lines) |
| Config | `companion_ai/core/config.py` (396 lines) |
| Persona YAML | `prompts/personas/companion.yaml` |
| Tests | `tests/` (22 files, 211 tests) |
