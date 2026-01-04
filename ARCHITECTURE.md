# Companion AI V6 Architecture

> **Design Philosophy**: 120B is the brain. Local loops are the hands.

---

## System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         USER INTERFACE                                │
│  ┌─────────────────────┐              ┌─────────────────────┐        │
│  │    Chat Panel       │              │  Background Tasks   │        │
│  │  (Main Interaction) │              │  (Left Slide-in)    │        │
│  └─────────────────────┘              └─────────────────────┘        │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │     Web Server        │
                    │   (Flask/Python)      │
                    └───────────┬───────────┘
                                │
        ┌───────────────────────▼───────────────────────┐
        │               120B ORCHESTRATOR               │
        │                  (Groq Cloud)                 │
        │                                               │
        │  • Understands user intent                    │
        │  • Decides: answer OR delegate                │
        │  • Synthesizes loop outputs                   │
        │  • Decides what to save to memory             │
        └───────────────────────┬───────────────────────┘
                                │
        ┌───────────┬───────────┼───────────┬───────────┐
        ▼           ▼           ▼           ▼           ▼
   ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐
   │ Memory  │ │ Vision  │ │  Tool   │ │Computer │ │  ...    │
   │  Loop   │ │  Loop   │ │  Loop   │ │  Loop   │ │ (More)  │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
        │           │           │           │
        └───────────┴───────────┴───────────┘
                    │
            ┌───────▼───────┐
            │ Ollama / vLLM │
            │  (Local GPU)  │
            └───────────────┘
```

---

## Folder Structure (V6 Reorganized)

```
companion_ai/
├── core/                         # Config & prompts
│   ├── config.py
│   ├── context_builder.py
│   └── conversation_logger.py
├── agents/                       # Agent implementations
│   ├── browser.py               # Chrome automation
│   ├── computer.py              # Computer use
│   └── vision.py                # Vision/screen analysis
├── integrations/                 # External integrations
│   └── loxone.py                # Loxone smart home
├── memory/                       # Memory backends
│   ├── sqlite_backend.py        # SQLite storage
│   ├── mem0_backend.py          # Mem0 vector memory
│   ├── knowledge_graph.py       # NetworkX graph
│   └── ai_processor.py          # Memory AI processing
├── services/                     # Background services
│   ├── tts.py                   # Text-to-speech
│   ├── jobs.py                  # Job queue manager
│   ├── persona.py               # Persona evolution
│   └── token_budget.py          # Token tracking
├── local_loops/                  # Loop implementations
│   ├── memory_loop.py
│   ├── vision_loop.py
│   ├── tool_loop.py
│   └── computer_loop.py
├── llm/                          # (Reserved for LLM split)
├── llm_interface.py              # LLM calls & routing
├── orchestrator.py               # 120B brain
├── conversation_manager.py       # Session management
└── tools.py                      # Tool definitions
```

---

## Core Components

### 1. 120B Orchestrator (The Brain)
- **Model**: Groq `openai/gpt-oss-120b`
- Parses user intent, decides routing, synthesizes outputs
- Only component that saves to memory

### 2. Local Loops (Ollama/vLLM)
Self-contained units with specialized models:
- **Memory Loop**: Extract/retrieve facts (Ollama qwen3:14b)
- **Vision Loop**: Analyze screen/images (LLaVA 7B)
- **Tool Loop**: Execute simple tools
- **Computer Loop**: Complex automation

### 3. Memory Management
- Only 120B decides what to persist
- Memory save happens AFTER loop output

### 4. Per-Step Token Tracking
- Each pipeline step shows tokens + timing
- Model labels: GROQ (purple) / LOCAL (green)

### 5. Memory System
- **Conflict Detection**: `pending_profile_facts` table with `conflict_with` column
- **Deduplication**: Hash-based + 70% similarity threshold for summaries/insights
- **Confidence Scoring**: High (≥0.80), Medium (≥0.50), Low (<0.50)
- **Reaffirmation**: Same fact restated → confidence boost + reaffirmation count
- **Staleness**: `get_stale_profile_facts()` surfaces old facts for reconfirmation
- **Config**: Set `ENABLE_FACT_APPROVAL=true` for manual approval workflow

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Orchestrator | Groq Cloud (120B) |
| Memory AI | Ollama (qwen3:14b) |
| Vision | Ollama (llava:7b) |
| Web Server | Flask + SSE |
| Memory Store | Mem0 + SQLite |
| Smart Home | Loxone Miniserver |
