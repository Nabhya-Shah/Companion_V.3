# Companion AI - Project Structure

**Last Updated:** December 9, 2025  
**Status:** Production-ready V4 - Mem0 & Tool Planner Integration Complete

---

## 🎯 Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Copy .env.example to .env and add your API keys
cp .env.example .env

# 3. Run the web interface
python run_companion.py --web
```

---

## 📁 Project Structure

```
Companion_V.3/
│
├── 🚀 Main Entry Points
│   ├── web_companion.py          # Flask web interface (PRIMARY)
│   ├── run_companion.py          # Launcher script
│   └── chat_cli.py               # CLI interface (alternative)
│
├── 🤖 companion_ai/ (Core AI Package)
│   ├── __init__.py
│   ├── conversation_manager.py   # Orchestrates conversations (V4 Flow)
│   ├── llm_interface.py          # LLM calls, Tool Planner, & Synthesis
│   ├── memory_v2.py              # Mem0 (Qdrant) Integration (NEW V4)
│   ├── memory.py                 # Legacy SQLite memory (being phased out)
│   ├── memory_graph.py           # Knowledge graph system
│   ├── tools.py                  # Tool registry & JSON Schemas
│   ├── vision_manager.py         # Maverick Vision integration
│   ├── computer_agent.py         # Computer control (PyAutoGUI)
│   └── core/
│       ├── config.py             # Central configuration & model roles
│       ├── context_builder.py    # Dynamic context assembly (Mem0 + History)
│       ├── prompts.py            # Static persona management
│       ├── conversation_logger.py # Logging system
│       └── metrics.py            # Performance tracking
│
├── 🎨 Web Interface
│   ├── static/
│   │   ├── app.css              # UI design
│   │   ├── app.js               # Frontend JavaScript
│   │   ├── computer-control.js  # Computer control UI
│   │   └── toast.js             # Notifications
│   └── templates/
│       ├── index.html            # Main web template
│       └── graph.html            # Knowledge graph visualization
│
├── 🧪 tests/ (Unit Tests)
│   ├── conftest.py
│   ├── test_context_builder.py
│   ├── test_tools.py
│   └── ... (various unit tests)
│
├── 🔧 tools/ (Development Tools)
│   ├── check_schemas.py          # Verify tool schemas
│   ├── debug_mem0_search.py      # Test Mem0 retrieval
│   ├── memory_deep_dive.py       # Analyze memory contents
│   ├── test_computer_use_e2e.py  # Test computer control
│   ├── verify_vision.py          # Test Maverick vision
│   └── watch_logs.py             # Watch web server logs
│
├── 📜 scripts/
│   ├── check_env.py              # Verify .env configuration
│   └── safe_run_browser.ps1      # Browser automation helper
│
├── 🎭 prompts/personas/
│   ├── companion.yaml            # Default personality (active)
│
├── 💾 data/
│   ├── mem0_qdrant/              # Mem0 Vector Database (NEW V4)
│   ├── companion_ai.db           # SQLite memory database (Legacy)
│   ├── knowledge_graph.pkl       # NetworkX knowledge graph
│   ├── logs/                     # Conversation logs
│   └── training_examples.jsonl   # For future fine-tuning
│
├── ⚙️ Configuration
│   ├── .env                      # Your API keys (DO NOT COMMIT)
│   ├── requirements.txt          # Python dependencies
│   └── .gitignore               # Git ignore rules
│
└── 📖 Documentation
    ├── README.md                 # Main project documentation
    ├── PROJECT_STRUCTURE.md      # This file
    ├── V4_PLANNING.md            # V4 Architecture details
    └── KNOWLEDGE_GRAPH.md        # Knowledge graph docs
```

---

## 🔑 Key Files Explained

### Entry Points

**`web_companion.py`**
- Flask web server at http://127.0.0.1:5000
- Manages `ConversationSession` persistence
- Handles `/api/chat` requests and streams responses

### Core AI Logic (V4 Architecture)

**`companion_ai/llm_interface.py`**
- **Planner Pattern:** Uses 120B/8B to plan tool usage before synthesis.
- **Token Optimization:** Uses minimal context for tool planning, full context for final response.
- **Model Roles:**
    - **Primary:** `openai/gpt-oss-120b` (Personality & Synthesis)
    - **Tools:** `llama-3.1-8b-instant` (Fast execution)
    - **Vision:** `llama-4-maverick-17b` (Screen analysis)

**`companion_ai/memory_v2.py`** (NEW V4)
- **Mem0 Integration:** Wraps Qdrant vector database.
- **Auto-Retrieval:** Fetches relevant memories for every request.
- **Hybrid Storage:** Stores facts, preferences, and conversation history.

**`companion_ai/tools.py`**
- **Native Function Calling:** Defines JSON Schemas for Groq.
- **Capabilities:**
    - `memory_search`: Query Mem0.
    - `use_computer`: Control mouse/keyboard.
    - `look_at_screen`: Analyze screen content.
    - `read_pdf`/`read_image`: File processing.
    - `brain_*`: Self-modification (Experimental).

**`companion_ai/core/context_builder.py`**
- Assembles the system prompt dynamically:
    1. **Static Persona:** From `prompts.py` (Cached).
    2. **Dynamic Memory:** From `memory_v2.py` (Mem0).
    3. **Recent History:** Last 3 turns of conversation.

### Web Interface

**`static/app.js`**
- Handles chat UI, streaming responses, and tool output display.
- Manages "Computer Control" overlay.

---

## 🎯 Feature Status (V4)

| Feature | Status | Notes |
|---------|--------|-------|
| **Architecture** | ✅ **V4 Active** | 120B Planner + 8B Tools + Mem0 |
| **Memory** | ✅ **Mem0** | Vector DB (Qdrant) active |
| **Vision** | ✅ **Maverick** | `look_at_screen` tool enabled |
| **Computer Use** | ✅ **Active** | PyAutoGUI integration working |
| **Tool System** | ✅ **Native** | Groq JSON Schema function calling |
| **Web Interface** | ✅ **Active** | Streaming chat + Graph view |
| **Knowledge Graph** | ✅ **Active** | NetworkX integration |
| **Legacy Memory** | ⚠️ Phasing Out | SQLite still present but secondary |

---

## 🗂️ Data Storage

### Mem0: `data/mem0_qdrant/`
- **Vector Store:** Qdrant (Local)
- **Embeddings:** `sentence-transformers/all-MiniLM-L6-v2`
- **Content:** Long-term memories, facts, user preferences.

### Knowledge Graph: `data/knowledge_graph.pkl`
- **NetworkX DiGraph:** Entity-relationship graph.
- **Entities:** People, places, concepts.

### Logs: `data/logs/`
- **conv_YYYYMMDD.jsonl**: Daily conversation logs.

---

## 🧪 Testing & Development

### Run Unit Tests
```bash
pytest -q
```

### Development Tools (in `tools/`)
```bash
# Verify Mem0 integration
python tools/verify_memory_integration.py

# Test Computer Use
python tools/test_computer_use_e2e.py

# Watch logs
python tools/watch_logs.py
```

---

**Built with:** Python 3.x, Flask, Mem0 (Qdrant), Groq API (Llama 3/GPT-OSS), NetworkX
