# Companion AI — Architecture

> **Design Philosophy**: The orchestrator is the brain. Local loops are the specialists. Memory is unified. Persona is the soul.

**Last Updated**: Phase 6 complete + optimizations (2026-03-09)

---

## System Overview

Every user message flows through a single entry point — the **Orchestrator** — which classifies intent and routes to the appropriate handler. Local loops run specialist workloads on local models. A unified knowledge system provides memory, facts, and document context.

```
┌──────────────────────────────────────────────────────────────────────┐
│                          USER INTERFACE                               │
│  ┌───────────────────┐  ┌───────────────┐  ┌──────────────────┐     │
│  │   Chat (SSE)      │  │  Tasks Panel  │  │  Smart Home      │     │
│  │   Streaming UI    │  │  Schedules    │  │  Loxone Modal    │     │
│  └───────────────────┘  └───────────────┘  └──────────────────┘     │
└────────────────────────────────┬─────────────────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Layer 1: Web Layer    │
                    │   Flask Blueprints      │
                    │   (SSE, REST, Auth)     │
                    └────────────┬────────────┘
                                 │
        ┌────────────────────────▼────────────────────────┐
        │            Layer 2: ORCHESTRATOR                 │
        │             (Groq Cloud Primary)                │
        │                                                 │
        │  Every message → classify → route:              │
        │  ANSWER · DELEGATE · TOOL · BACKGROUND · MEMORY │
        └────────┬──────────┬──────────┬──────────────────┘
                 │          │          │
      ┌──────────▼┐  ┌─────▼────┐  ┌──▼───────────────┐
      │ Quick Tool │  │ Layer 4  │  │ Layer 5          │
      │ (Groq     │  │ Local    │  │ Unified Knowledge │
      │  zero-shot)│  │ Loops    │  │ System            │
      └───────────┘  │          │  └───────────────────┘
                     │ Memory   │
                     │ Tool     │
                     │ Vision   │
                     └──────────┘
                          │
                   ┌──────▼──────┐
                   │   Ollama    │
                   │   (Local)   │
                   └─────────────┘
```

### Routing Logic

| Decision    | Meaning                                            | Handler                   |
|-------------|----------------------------------------------------|---------------------------|
| **ANSWER**  | Orchestrator answers directly                      | Groq primary model        |
| **TOOL**    | Simple one-shot tool call (time, weather, etc.)    | Groq tools model (fast)   |
| **DELEGATE**| Complex specialist work                            | Local loop (Ollama)       |
| **BACKGROUND** | Long-running / async task                       | Job queue + local loop    |
| **MEMORY**  | Explicit memory operation (save, search, update)   | Unified knowledge system  |

---

## Layer Breakdown

### Layer 1: Web Layer

**Package**: `companion_ai/web/` (10 files, ~1,700 lines total)  
**Entry point**: `create_app()` factory in `companion_ai/web/__init__.py`  
**Backwards-compat shim**: `web_companion.py` (thin re-export, ~30 lines)

The HTTP/SSE surface is organised as Flask Blueprints with shared state in `state.py`.

| Blueprint | File | Responsibilities |
|-----------|------|------------------|
| `chat_bp` | `chat_routes.py` | `/api/chat/send` (SSE streaming + TTS), `/api/chat/history`, `/api/chat/stream`, `/api/chat/stop`, `/api/debug/*` |
| `memory_bp` | `memory_routes.py` | `/api/memory`, `/api/memory/clear`, `/api/memory/fact/*`, `/api/pending_facts`, `/api/pending_facts/bulk` |
| `files_bp` | `files_routes.py` | `/api/upload/*` (single, batch, list, extract, summarize, search), `/api/brain/*` (upload, batch, stats, files, delete, reindex, search) |
| `tools_bp` | `tools_routes.py` | `/api/tools`, `/api/plugins/*`, `/api/context`, `/api/context/switch`, `/api/search` |
| `media_bp` | `media_routes.py` | `/api/tts/*`, `/api/vision/*`, `/api/voice/change` |
| `loxone_bp` | `loxone_routes.py` | `/api/loxone/rooms`, `/api/loxone/health`, `/api/loxone/light/*` |
| `system_bp` | `system_routes.py` | `/`, `/graph`, `/api/shutdown`, `/api/jobs/*`, `/api/token-budget`, `/api/tasks/*`, `/api/schedules/*`, `/api/health`, `/api/tokens/*`, `/api/config`, `/api/models`, `/api/routing/*`, `/api/graph/*` |

### Layer 2: Orchestrator

**File**: `companion_ai/orchestrator.py` (~560 lines, built but currently dormant)

The cloud-powered brain that receives **every** user message. It:
1. Classifies intent (ANSWER / DELEGATE / TOOL / BACKGROUND / MEMORY)
2. Routes to the appropriate handler
3. Synthesizes specialist outputs into the final response
4. Decides what (if anything) to persist to memory

**Model**: Groq `openai/gpt-oss-120b` (primary)

**Key design rule**: The orchestrator never exposes its internal routing decision to the user. The user sees only the final natural-language response.

### Layer 3: LLM Interface

**Package**: `companion_ai/llm/` (5 submodules, ~1,300 lines total)  
**Backwards-compat shim**: `companion_ai/llm_interface.py` (thin re-export, ~60 lines)

Dual-provider router:
- **Groq Cloud** — primary chat, tool calling, vision
- **Ollama Local** — specialist loops, embeddings, memory AI

| Role | Model | Provider |
|------|-------|----------|
| Primary chat / orchestrator | `openai/gpt-oss-120b` | Groq |
| Fast tool calling | `llama-3.1-8b-instant` | Groq |
| Vision | `meta-llama/llama-4-maverick-17b-128e-instruct` | Groq |
| Memory AI (extraction) | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq |
| Mem0 backend | `qwen3:14b` | Ollama |
| Brain embeddings | `nomic-embed-text` | Ollama |
| Vision (local) | `llava:7b` | Ollama |
| Synthesis / compression | `llama3.1` | Ollama |

| Submodule | File | Responsibility |
|-----------|------|----------------|
| Token tracking | `token_tracker.py` | Per-step token stats, logging, reset |
| Groq provider | `groq_provider.py` | Client pool, tool calling, streaming, output sanitisation |
| Ollama provider | `ollama_provider.py` | Local model calls, embeddings |
| Router | `router.py` | High-level `generate_response` with complexity classification |
| Memory extraction | `memory/ai_processor.py` | Summary, profile facts, insight generation (re-exported via `llm/__init__.py`) |

### Layer 4: Local Loops (Specialists)

**Directory**: `companion_ai/local_loops/` (~1,400 lines across 4 files)

Self-contained processing units that run on local Ollama models. The orchestrator delegates to these when a task requires specialist reasoning.

| Loop | Purpose | Local Model |
|------|---------|-------------|
| **MemoryLoop** | Fact extraction, memory search, context enrichment | qwen3:14b |
| **ToolLoop** | Multi-step tool execution, result formatting | configurable |
| **VisionLoop** | Image analysis, screen description, OCR | llava:7b |

Each loop:
- Receives a structured task from the orchestrator
- Runs autonomously using its assigned local model
- Returns a `LoopResult` with output + metadata
- Never persists to memory directly (orchestrator decides)

**Shelved**: `ComputerLoop` and browser automation — unwired until needed.

### Layer 5: Unified Knowledge System

**Target**: Merge the current 5-layer memory stack into a coherent system.

**Current state** (to be unified):
- Mem0 vector memory (`memory/mem0_backend.py`)
- SQLite fact store (`memory/sqlite_backend.py`)
- Brain folder + index (`brain_index.py`, `brain_manager.py`)
- Knowledge graph (`memory/knowledge_graph.py`)
- AI processor (`memory/ai_processor.py`)

**Target architecture**:

| Component | Role |
|-----------|------|
| **Vector Memory** (Mem0) | Semantic search over stored memories |
| **Fact Store** (SQLite) | Structured profile facts with confidence scoring |
| **Document Index** (Brain) | Uploaded files + knowledge base with embeddings |
| **Knowledge Graph** | Entity-relationship extraction and traversal |

**Key changes**:
- Merge `pending_profile_facts` into the main confidence system (low-confidence = flagged for review, not a separate table)
- Unify brain folder + uploads + brain index into a single document pipeline
- Single entry point for "remember this" / "search for that" regardless of storage backend

**Memory quality features** (already built):
- Conflict detection with contradiction lifecycle
- Hash-based + similarity deduplication
- Confidence scoring (high ≥0.80, medium ≥0.50, low <0.50)
- Reaffirmation tracking
- Staleness detection for old facts

### Layer 6: Services

| Service | File | Purpose |
|---------|------|---------|
| **Persona** | `services/persona.py` | Personality evolution with `PersonaState` singleton, 3 trigger types (periodic/memory-event/session-end), incremental trait merging, rapport progression |
| **Jobs/Scheduler** | `services/jobs.py` | Recurring automations, run-now, policy enforcement, daemon-safe logging |
| **Workflows** | `services/workflows.py` | YAML workflow loader with change-aware reload (mtime+size signature), async execution, chat history updates, context-switch sync |
| **Proactive Insights** | `services/insights.py` | Daily digest generation, undelivered insight tracking, SSE delivery, offline catch-up via chat history injection |
| **Token Budget** | `services/token_budget.py` | Per-step token tracking with model labels |
| **TTS** | `services/tts.py` | Text-to-speech (optional plugin, not actively developed) |

### Layer 7: Integrations

| Integration | File | Status |
|-------------|------|--------|
| **Loxone Smart Home** | `integrations/loxone.py` | Live — room control, state sync, voice commands |
| **Plugin System** | `services/jobs.py` + policy | Live — registry, gating, policy enforcement |
| **Browser Agent** | `agents/browser.py` | Shelved — built but unwired |
| **Vision Agent** | `agents/vision.py` | Active — used by media_routes, files_routes |

---

## File Structure

```
companion_ai/
├── core/
│   ├── config.py              # All configuration + env vars
│   ├── context_builder.py     # Prompt context assembly
│   ├── conversation_logger.py # Chat logging
│   ├── metrics.py             # Telemetry
│   └── prompts.py             # System prompt templates
├── agents/
│   ├── browser.py             # [shelved] Chrome automation
│   └── vision.py              # Active — used by media_routes, files_routes
├── integrations/
│   └── loxone.py              # Loxone smart home
├── memory/
│   ├── sqlite_backend.py      # Fact store
│   ├── mem0_backend.py        # Vector memory (Mem0)
│   ├── knowledge_graph.py     # Entity graph
│   └── ai_processor.py        # Memory AI
├── services/
│   ├── tts.py                 # Text-to-speech
│   ├── jobs.py                # Job queue + scheduler
│   ├── workflows.py           # Workflow engine (YAML, change-aware reload)
│   ├── insights.py            # Proactive insights (daily digest, SSE delivery)
│   ├── persona.py             # Persona evolution
│   └── token_budget.py        # Token tracking
├── local_loops/
│   ├── base.py                # Loop base class + LoopResult
│   ├── memory_loop.py         # Memory specialist
│   ├── vision_loop.py         # Vision specialist
│   ├── tool_loop.py           # Tool specialist
│   └── registry.py            # Loop auto-registration
├── llm/                       # ✅ Split from llm_interface.py (P5-C)
│   ├── __init__.py            # Re-exports all public symbols
│   ├── token_tracker.py       # Per-step token stats
│   ├── groq_provider.py       # Groq cloud calls + tool calling
│   ├── ollama_provider.py     # Ollama local calls + embeddings
│   ├── router.py              # High-level response routing
│   └── (memory extraction re-exported from memory/ai_processor.py)
├── tools/                     # ✅ Split from tools.py (P5-C)
│   ├── __init__.py            # Re-exports full public API
│   ├── registry.py            # @tool decorator, plugin system, policy, dispatch
│   ├── system_tools.py        # Time, memory search, screen, computer
│   ├── brain_tools.py         # Brain search, read, write, list
│   ├── browser_tools.py       # Browser automation tools
│   ├── file_tools.py          # PDF, image, docx, file listing
│   └── research_tools.py      # Wikipedia
├── web/                       # ✅ Split from web_companion.py (P5-C)
│   ├── __init__.py            # App factory (create_app) + run_web
│   ├── state.py               # Shared globals, security, scope helpers
│   ├── chat_routes.py         # Chat blueprint (SSE streaming)
│   ├── memory_routes.py       # Memory blueprint
│   ├── files_routes.py        # Upload + brain file blueprint
│   ├── tools_routes.py        # Tools + plugins + context blueprint
│   ├── media_routes.py        # TTS + vision blueprint
│   ├── loxone_routes.py       # Smart home blueprint
│   └── system_routes.py       # System + admin blueprint
├── llm_interface.py           # Backwards-compat shim → llm/
├── orchestrator.py            # Cloud brain (USE_ORCHESTRATOR=true)
├── conversation_manager.py    # Session coordinator
├── brain_index.py             # Embedding index
└── brain_manager.py           # Brain file management

web_companion.py               # Backwards-compat shim → companion_ai/web/
templates/                     # HTML templates (index.html, graph.html)
static/                        # JS, CSS (app.js, app.css, toast.*)
tests/                         # 21 pytest suites, 120+ tests
scripts/                       # Utility scripts (smoke, setup, check_env)
prompts/personas/              # Persona YAML definitions
```

---

## Dead Code / Removal Status

| Item | Status | Notes |
|------|--------|-------|
| `build_full_prompt()` | ✅ Removed (P5-A) | Was in llm_interface.py |
| `should_use_groq()` | ✅ Removed (P5-A) | Always Groq now |
| `ENABLE_COMPOUND` / `ENABLE_ENSEMBLE` | ✅ Removed (P5-A) | Vestigial config flags |
| `REASONING_MODEL` / `HEAVY_MODEL` / `FAST_MODEL` aliases | ✅ Removed (P5-A) | Vestigial aliases |
| Legacy `/api/chat` (non-streaming) | ✅ Removed (P5-A) | Only SSE `/api/chat/send` remains |
| Compatibility shims (`memory_v2.py`, `memory_graph.py`, `persona_evolution.py`) | ✅ Deleted (P5-A) | 5 shim files removed, imports updated |
| `computer_loop.py` | ✅ Removed | Was shelved, file no longer exists |
| `llm_interface.py` monolith | ✅ Split → `llm/` (P5-C) | Thin re-export shim remains |
| `tools.py` monolith | ✅ Split → `tools/` (P5-C) | Old file deleted |
| `web_companion.py` monolith | ✅ Split → `web/` (P5-C) | Thin re-export shim remains |

---

## Design Principles

1. **Orchestrator-first**: Every message hits the orchestrator. No bypass paths.
2. **Local specialists**: Loops run autonomously but never persist — orchestrator controls state.
3. **Unified knowledge**: One "remember" / "recall" interface regardless of backend.
4. **Policy-driven safety**: Tools, plugins, and automations respect explicit policy controls.
5. **Persona as differentiator**: The companion's personality evolves over time — not just a chatbot.
6. **Observable by default**: Token tracking, job status, schedule outcomes — all visible to the user.
7. **Local-first**: No cloud dependency except Groq for primary chat. Memory, embeddings, and tools run locally.
8. **Lazy-load by default**: Frontend panels load data only when opened, not on bootstrap, to minimize startup token burn.
9. **Change-aware operations**: Backend services use file signatures to avoid unnecessary reloads and processing.

---

## Performance Optimizations

**Date**: 2026-03-09  
**Context**: Eliminated unexpected token burn from background systems and page loads.

| Optimization | Problem | Solution | Impact |
|--------------|---------|----------|--------|
| **Workflow Reload Spam** | `reload_workflows()` logged reload on every Tasks poll (~5s) even when files unchanged | Change-aware reload using `(filename, mtime_ns, size)` signature; early-exit if unchanged | Eliminated false reload logs; reduced filesystem overhead |
| **Automatic Migration Path** | Fresh sessions triggered Mem0 legacy migration on every `/api/memory` read | Moved migration trigger from read path to explicit `/api/context/switch` only | Eliminated unwanted token burn on memory queries |
| **Eager Frontend Loading** | Page bootstrap called `loadMemory()`, `loadRecentUploads()`, `loadProactiveInsights()` before panels opened | Removed eager calls; data loads deferred to `onPanelTabSwitch()` | Fresh page load no longer hits `/api/memory` or `/api/brain/files` |
| **Session-Scoped Mem0** | Memory operations could leak across sessions within same profile | Propagated `user_id` format `{base}::p:{profile}::s:{session}` throughout orchestrator and local loops | Proper session isolation for vector memory |

**Files Modified**:
- `companion_ai/services/workflows.py` — `_compute_signature()`, change-aware `reload_workflows()`
- `companion_ai/web/memory_routes.py` — removed `_maybe_migrate_legacy_scope()` from read path
- `static/app.js` — removed eager `loadMemory()` from DOMContentLoaded
- `static/memory.js` — removed terminal `loadRecentUploads()` and `loadProactiveInsights()` calls
- `companion_ai/orchestrator.py` — session-scoped context builder
- `companion_ai/local_loops/memory_loop.py` — user_id propagation

**Test Coverage**: All optimizations validated in test suite (219 tests passing).

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Primary LLM | Groq Cloud (`gpt-oss-120b`) |
| Fast Tools LLM | Groq Cloud (`llama-3.1-8b-instant`) |
| Vision LLM | Groq Cloud (`llama-4-maverick`) |
| Memory AI | Groq Cloud (`llama-4-scout`) |
| Local LLM | Ollama (`qwen3:14b`, `llama3.1`) |
| Embeddings | Ollama (`nomic-embed-text`) |
| Web Server | Flask + SSE |
| Memory Store | Mem0 + SQLite |
| Knowledge Index | ChromaDB / FAISS via brain_index |
| Smart Home | Loxone Miniserver |
| Frontend | Vanilla JS + D3.js (knowledge graph) |
