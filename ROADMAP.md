# Companion AI — Master Roadmap & Sprint Plan

> **Last Updated**: 2026-03-09  
> **Status**: Phase 6 complete + performance optimizations  
> **Tests**: 219 passing

---

## Project Overview

Personal AI companion with orchestrator brain, persistent memory, knowledge graph, scheduled automations, smart home integration, and evolving persona. Built with Python 3.11, Flask, Groq Cloud API, Mem0 + Qdrant vectors, vanilla JS frontend.

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

## Current Phase: P6 Makeover

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
| Tests | pytest (211 tests, 22+ suites) |

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
