# Companion AI

A personal AI companion with persistent memory, knowledge graph, and intelligent orchestration. The 120B model acts as the brain, delegating to specialized local loops for memory, vision, and computer control.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **120B Orchestrator** | Groq 120B acts as the brain - understands intent, delegates tasks, synthesizes responses |
| **Local Loops** | Specialized local models (Docker vLLM) for memory, vision, tools, computer control |
| **Knowledge Graph** | NetworkX-based entity/relationship extraction with D3.js visualization |
| **Persistent Memory** | Only 120B decides what to save - no noise from casual chat |
| **Background Tasks** | Complex tasks run async with live timeline updates |
| **Web UI** | Modern chat interface with task panel and memory visualization |

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
                   Docker vLLM
                   (Local GPU)
```

**Key Principles:**
- 120B = The Brain (decides, synthesizes, saves to memory)
- Local Loops = The Hands (execute, never persist)
- Background tasks run async with notifications

## 📁 Project Structure

```
companion_ai/
├── core/
│   ├── config.py              # Model routing, configuration
│   ├── context_builder.py     # System prompt construction
│   └── conversation_logger.py # JSONL logging
├── llm_interface.py           # LLM calls, tool execution
├── conversation_manager.py    # Session management
├── memory.py                  # SQLite storage
├── memory_v2.py               # Mem0/Qdrant vector memory
├── memory_graph.py            # NetworkX knowledge graph
├── local_loops.py             # Local loop implementations (TODO)
└── tools.py                   # Tool definitions

web_companion.py               # Flask server
templates/
├── index.html                 # Chat UI
└── graph.html                 # Knowledge graph viz
static/
├── app.js                     # Frontend logic
└── app.css                    # Styling
```

## 🔧 Configuration

### Environment Variables

```env
# Required
GROQ_API_KEY=your_groq_api_key

# Optional (for dedicated memory API)
GROQ_MEMORY_API_KEY=second_groq_key
```

### Models

| Role | Model | Description |
|------|-------|-------------|
| Orchestrator | `openai/gpt-oss-120b` | Main brain - routing and synthesis |
| Memory Loop | Qwen 3B (local) | Fact extraction and retrieval |
| Vision Loop | LLaVA 13B (local) | Screen/image analysis |
| Computer Loop | Qwen 7B (local) | Complex computer automation |

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat/send` | POST | Streaming SSE response |
| `/api/memory` | GET | View stored memories |
| `/api/graph` | GET | Export knowledge graph |
| `/graph` | GET | Interactive visualization |
| `/api/health` | GET | System status |

## 🧠 How Memory Works

1. **120B receives message** → Decides if memory needed
2. **Delegates to Memory Loop** → Search or extract facts
3. **After response** → 120B decides what to save (not auto-save everything)
4. **Learning** → Even loop outputs can be saved if useful

## 📝 License

MIT

---

*Built with Groq, Docker vLLM, NetworkX, Flask, and D3.js*