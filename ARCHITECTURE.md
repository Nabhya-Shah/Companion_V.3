# Companion AI — Architecture

> **Design Philosophy**: The orchestrator is the brain. Local loops are the specialists. Memory is unified. Persona is the soul.

**Last Updated**: Phase 5 kickoff (post-Phase 4 completion)

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

The HTTP/SSE surface. Currently a monolithic Flask app (`web_companion.py`, ~2,400 lines) — **target: split into Flask Blueprints**.

| Blueprint (Target) | Responsibilities |
|---------------------|------------------|
| `chat` | `/api/chat/send`, streaming SSE, stop/cancel |
| `memory` | `/api/memory`, `/api/pending_facts`, review center |
| `knowledge` | `/api/brain/*`, `/api/upload/*`, file management |
| `control` | `/api/tasks`, `/api/schedules`, `/api/events` |
| `system` | `/api/health`, `/api/models`, `/api/routing` |
| `integrations` | `/api/loxone/*`, `/api/plugins/*` |
| `settings` | `/api/context`, workspace/profile switching |

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

**File**: `companion_ai/llm_interface.py` (~1,600 lines) — **target: split into `companion_ai/llm/`**

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
| **Persona** | `services/persona.py` | Personality evolution — key differentiator, grows over time |
| **Jobs/Scheduler** | `services/jobs.py` | Recurring automations, run-now, policy enforcement |
| **Token Budget** | `services/token_budget.py` | Per-step token tracking with model labels |
| **TTS** | `services/tts.py` | Text-to-speech (optional plugin, not actively developed) |

### Layer 7: Integrations

| Integration | File | Status |
|-------------|------|--------|
| **Loxone Smart Home** | `integrations/loxone.py` | Live — room control, state sync, voice commands |
| **Plugin System** | `services/jobs.py` + policy | Live — registry, gating, policy enforcement |
| **Browser Agent** | `agents/browser.py` | Shelved — built but unwired |
| **Vision Agent** | `agents/vision.py` | Shelved — built but unwired |

---

## File Structure (Current → Target)

### Current
```
companion_ai/
├── core/
│   ├── config.py              # All configuration
│   ├── context_builder.py     # Prompt context assembly
│   ├── conversation_logger.py # Chat logging
│   ├── metrics.py             # Telemetry
│   └── prompts.py             # System prompt templates
├── agents/
│   ├── browser.py             # [shelved] Chrome automation
│   └── vision.py              # [shelved] Computer vision
├── integrations/
│   └── loxone.py              # Loxone smart home
├── memory/
│   ├── sqlite_backend.py      # Fact store
│   ├── mem0_backend.py        # Vector memory
│   ├── knowledge_graph.py     # Entity graph
│   └── ai_processor.py        # Memory AI
├── services/
│   ├── tts.py                 # Text-to-speech
│   ├── jobs.py                # Job queue + scheduler
│   ├── persona.py             # Persona evolution
│   └── token_budget.py        # Token tracking
├── local_loops/
│   ├── base.py                # Loop base class + LoopResult
│   ├── memory_loop.py         # Memory specialist
│   ├── vision_loop.py         # Vision specialist
│   ├── tool_loop.py           # Tool specialist
│   └── registry.py            # Loop auto-registration
├── llm_interface.py           # [to split] LLM router (~1,600 lines)
├── orchestrator.py            # [to activate] Cloud brain (~560 lines)
├── conversation_manager.py    # Session coordinator
├── brain_index.py             # Embedding index
├── brain_manager.py           # Brain file management
└── tools.py                   # [to split] Tool definitions (~1,250 lines)

web_companion.py               # [to split] Flask monolith (~2,400 lines)
```

### Target (after Phase 5 cleanup)
```
companion_ai/
├── core/                      # Config, prompts, logging, metrics
├── agents/                    # [shelved] browser, vision
├── integrations/              # Loxone, future plugins
├── memory/                    # Unified knowledge backends
├── services/                  # Persona, jobs, token budget, TTS
├── local_loops/               # Active specialists (memory, tool, vision)
├── llm/                       # Split from llm_interface.py
│   ├── __init__.py
│   ├── groq_provider.py       # Groq cloud calls
│   ├── ollama_provider.py     # Ollama local calls
│   └── router.py              # Model selection + fallbacks
├── tools/                     # Split from tools.py
│   ├── __init__.py
│   ├── registry.py            # Tool registration + discovery
│   ├── time_tools.py          # Time/date tools
│   ├── memory_tools.py        # Memory search/save tools
│   ├── file_tools.py          # File operation tools
│   └── home_tools.py          # Smart home tools
├── orchestrator.py            # Active cloud brain
├── conversation_manager.py    # Session coordinator
├── brain_index.py             # → merge into memory/
└── brain_manager.py           # → merge into memory/

web/                           # Split from web_companion.py
├── __init__.py                # Flask app factory
├── chat.py                    # Chat blueprint
├── memory_routes.py           # Memory blueprint
├── knowledge.py               # Knowledge blueprint
├── control.py                 # Tasks/schedules blueprint
├── system.py                  # Health/models blueprint
├── integrations.py            # Loxone/plugins blueprint
└── settings.py                # Context/workspace blueprint
```

---

## Dead Code / Removal Targets

| Item | Location | Reason |
|------|----------|--------|
| `build_full_prompt()` | `llm_interface.py` | Replaced by `context_builder.py` |
| `should_use_groq()` | `llm_interface.py` | Always Groq now |
| `ENABLE_COMPOUND` / `ENABLE_ENSEMBLE` | `config.py` | Never used in current flow |
| `REASONING_MODEL` / `HEAVY_MODEL` / `FAST_MODEL` aliases | `config.py` | Vestigial aliases |
| Legacy `/api/chat` (non-streaming) | `web_companion.py` | Replaced by SSE `/api/chat/send` |
| `computer_loop.py` | `local_loops/` | Shelved — unwire but keep code |
| Compatibility shims | `memory_v2.py`, `memory_graph.py`, etc. | Remove after import consolidation |

---

## Design Principles

1. **Orchestrator-first**: Every message hits the orchestrator. No bypass paths.
2. **Local specialists**: Loops run autonomously but never persist — orchestrator controls state.
3. **Unified knowledge**: One "remember" / "recall" interface regardless of backend.
4. **Policy-driven safety**: Tools, plugins, and automations respect explicit policy controls.
5. **Persona as differentiator**: The companion's personality evolves over time — not just a chatbot.
6. **Observable by default**: Token tracking, job status, schedule outcomes — all visible to the user.
7. **Local-first**: No cloud dependency except Groq for primary chat. Memory, embeddings, and tools run locally.

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
