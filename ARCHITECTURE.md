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
            │  Docker vLLM  │
            │  (Local GPU)  │
            └───────────────┘
```

---

## Core Components

### 1. 120B Orchestrator (The Brain)
- **Model**: Groq `openai/gpt-oss-120b`
- Parses user intent, decides routing, synthesizes outputs
- Only component that saves to memory

### 2. Local Loops (Docker vLLM)
Self-contained units with multiple models working together:
- **Memory Loop**: Extract/retrieve facts
- **Vision Loop**: Analyze screen/images  
- **Tool Loop**: Execute simple tools
- **Computer Loop**: Complex automation with mini-overseer

### 3. Memory Management
- Only 120B decides what to persist
- Memory save happens AFTER loop output (learns from loops too)

### 4. Background Task Panel
- Left slide-in with expandable timeline view
- Live status updates, notifications on completion

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Orchestrator | Groq Cloud (120B) |
| Local Inference | Docker vLLM |
| Text Models | Qwen 3B/7B |
| Vision Models | LLaVA 13B / InternVL |
| Web Server | Flask + SSE |
| Memory Store | Mem0 + Qdrant |

---

See full architecture details in the design docs.
