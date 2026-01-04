# Companion AI

A personal AI companion with persistent memory, knowledge graph, and intelligent orchestration. The 120B model acts as the brain, delegating to specialized local loops for memory, vision, and computer control.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **120B Orchestrator** | Groq 120B acts as the brain - understands intent, delegates tasks, synthesizes responses |
| **Local Loops** | Specialized local models (Ollama) for memory, vision, tools, computer control |
| **Knowledge Graph** | NetworkX-based entity/relationship extraction with D3.js visualization |
| **Persistent Memory** | Only 120B decides what to save - no noise from casual chat |
| **Per-Step Token Tracking** | See tokens + timing for each pipeline step with model labels |
| **Background Tasks** | Complex tasks run async with live timeline updates |
| **Web UI** | Modern chat interface with task panel and memory visualization |
| **Smart Home** | Loxone integration with live state, dim/bright modes, 15s auto-refresh |

## 🧠 Memory System

| Feature | Description |
|---------|-------------|
| **Conflict Detection** | Detects when new facts contradict existing ones (e.g., name change) |
| **Deduplication** | Hash-based exact match + 70% similarity threshold |
| **Confidence Scoring** | Facts have confidence levels (high/medium/low) with reaffirmation |
| **Priority/Staleness** | Surfaces old facts for reaffirmation, applies confidence decay |

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/Nabzy-12/Companion_V.3.git
cd Companion_V.3
pip install -r requirements.txt

# Configure (.env file)
GROQ_API_KEY=your_key_here

# Run
python web_companion.py    # Web UI at localhost:5000
```

## 🏗️ Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

```
User → Web Server → 120B Orchestrator → Response
                         │
            ┌────────────┼────────────┐
            ▼            ▼            ▼
       Memory Loop  Vision Loop  Computer Loop
            │            │            │
            └────────────┴────────────┘
                         │
                   Ollama (Local)
```

**Key Principles:**
- 120B = The Brain (decides, synthesizes, saves to memory)
- Local Loops = The Hands (execute, never persist)
- Background tasks run async with notifications

## 📁 Project Structure

```
companion_ai/
├── core/                 # Config, prompts, logging
├── agents/               # Browser, computer, vision agents
├── memory/               # SQLite, Mem0, knowledge graph
├── services/             # TTS, jobs, persona, token budget
├── local_loops/          # Memory, vision, tool, computer loops
├── llm_interface.py      # LLM calls & routing
├── orchestrator.py       # 120B brain
└── conversation_manager.py

web_companion.py          # Flask server
templates/                # HTML templates
static/                   # JS, CSS
```

## 🔧 Configuration

### Environment Variables

```env
# Required
GROQ_API_KEY=your_groq_api_key

# Optional
GROQ_MEMORY_API_KEY=second_groq_key
USE_MEM0=true
USE_ORCHESTRATOR=true

# Loxone Smart Home (optional)
LOXONE_HOST=192.168.x.x
LOXONE_USER=your_username
LOXONE_PASSWORD=your_password
```

### Models

| Role | Model | Provider |
|------|-------|----------|
| Orchestrator | `openai/gpt-oss-120b` | Groq Cloud |
| Memory AI | `qwen3:14b` | Ollama (local) |
| Vision | `llava:7b` | Ollama (local) |

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/send` | POST | Streaming SSE response |
| `/api/memory` | GET | View stored memories |
| `/api/tokens/last` | GET | Per-step token breakdown |
| `/api/graph` | GET | Export knowledge graph |
| `/graph` | GET | Interactive visualization |
| `/api/health` | GET | System status |
| `/api/loxone/rooms` | GET | Smart home room states |
| `/api/loxone/light/<action>` | POST | Control lights (on/off/brightness) |

## 📝 License

MIT