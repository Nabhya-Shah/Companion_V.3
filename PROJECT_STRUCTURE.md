# Companion AI - Project Structure

**Last Updated:** November 10, 2025  
**Status:** Production-ready v0.3 - Knowledge Graph Integration Complete

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
│   ├── conversation_manager.py   # Orchestrates conversations
│   ├── llm_interface.py          # LLM calls & fact extraction
│   ├── memory.py                 # Memory storage & retrieval
│   ├── memory_ai.py             # Dedicated memory AI client
│   ├── memory_graph.py          # Knowledge graph system (NEW v0.3)
│   ├── tools.py                  # Tool calling system (10 tools)
│   ├── tts_manager.py           # Azure TTS integration
│   └── core/
│       ├── config.py             # Central configuration & model routing
│       ├── context_builder.py    # Context assembly & persona loading
│       ├── conversation_logger.py # Logging system
│       └── metrics.py            # Performance tracking
│
├── 🎨 Web Interface
│   ├── static/
│   │   ├── app.css              # Gemini-style UI design
│   │   └── app.js               # Frontend JavaScript
│   └── templates/
│       ├── index.html            # Main web template
│       └── graph.html            # Knowledge graph visualization (NEW v0.3)
│
├── 🧪 tests/ (Unit Tests - 11 files)
│   ├── conftest.py
│   ├── test_context_builder.py
│   ├── test_fact_parser.py
│   ├── test_logger.py
│   ├── test_memory_dedup.py
│   ├── test_memory_provenance.py
│   ├── test_model_selection.py
│   ├── test_models_endpoint.py
│   ├── test_routing_recent_endpoint.py
│   ├── test_search_and_sanitize.py
│   └── test_tools.py
│
├── 🔧 tools/ (Development Tools - 14 files)
│   ├── check_actual_memory.py    # View current memory contents
│   ├── check_db_schema.py        # Inspect database schema
│   ├── clean_memory_db.py        # Clean bad facts from DB
│   ├── list_azure_voices.py      # List available TTS voices
│   ├── reset_memory.py           # Wipe all memory (with backup)
│   ├── run_feature_tests.py      # Automated feature testing (NEW v0.3)
│   ├── send_debug_message.py     # Send test messages to web server (NEW v0.3)
│   ├── test_graph_integration.py # Test knowledge graph integration (NEW v0.3)
│   ├── test_knowledge_graph.py   # Test graph operations (NEW v0.3)
│   ├── test_tts.py               # Test TTS voices
│   ├── view_knowledge_graph.py   # Visualize knowledge graph in terminal (NEW v0.3)
│   ├── view_test_log.py          # View test logs (NEW v0.3)
│   └── watch_logs.py             # Watch web server logs in real-time (NEW v0.3)
│
├── 📜 scripts/ (Utility Scripts - 4 files)
│   ├── calibrate_mic.py          # Microphone calibration for STT
│   ├── check_env.py              # Verify .env configuration
│   ├── list_audio_devices.py     # List available audio devices
│   └── view_memory.py            # Quick memory viewer
│
├── 🎭 prompts/personas/
│   ├── companion.yaml            # Default personality (active)
│   └── aether.yaml               # Alternative persona
│
├── 💾 data/
│   ├── companion_ai.db           # SQLite memory database (active)
│   ├── knowledge_graph.pkl       # NetworkX knowledge graph (NEW v0.3)
│   ├── companion_ai_backup_*.db  # Latest backup
│   ├── logs/
│   │   ├── conv_YYYYMMDD.jsonl  # Daily conversation logs
│   │   └── metrics_state.json    # Performance metrics
│   └── chat_logs/                # (Empty - for new sessions)
│
├── ⚙️ Configuration
│   ├── .env                      # Your API keys (DO NOT COMMIT)
│   ├── .env.example              # Template for .env
│   ├── requirements.txt          # Python dependencies
│   ├── .gitignore               # Git ignore rules
│   └── .gitattributes           # Git line ending config
│
└── 📖 Documentation
    ├── README.md                 # Main project documentation
    ├── PROJECT_STRUCTURE.md      # This file - project organization
    ├── KNOWLEDGE_GRAPH.md        # Knowledge graph technical docs (NEW v0.3)
    ├── TOOL_SETUP_GUIDE.md       # Tool configuration guide
    └── HOW_TO_RUN_AND_TEST.md    # Testing and usage guide
```

---

## 🔑 Key Files Explained

### Entry Points

**`web_companion.py`** (400+ lines)
- Flask web server at http://127.0.0.1:5000
- Main interface with chat, memory sidebar, and settings
- API routes for chat, memory retrieval, and knowledge graph
- Knowledge graph visualization at `/graph`
- Graph API endpoints: `/api/graph`, `/api/graph/stats`, `/api/graph/search`

**`run_companion.py`**
- Launcher script with CLI arguments
- `--web` flag starts web interface
- Default starts CLI interface

**`chat_cli.py`**
- Simple command-line chat interface
- Alternative to web UI for terminal users

### Core AI Logic

**`companion_ai/llm_interface.py`** (700+ lines)
- LLM API calls to Groq/OpenRouter
- Fact extraction with strict filtering (no inferences!)
- Ensemble reasoning (3 candidate models)
- Tool calling integration
- Compound models support (built-in Groq tools)
- Token optimization (60-70% reduction via fresh context)

**`companion_ai/conversation_manager.py`**
- Orchestrates conversations
- Builds context with memory + history
- Coordinates LLM, tools, and logging

**`companion_ai/memory.py`**
- SQLite database operations
- Stores user profile facts, conversation summaries, AI insights
- Retrieval and search functionality
- Integrates with knowledge graph for entity-based memory

**`companion_ai/memory_graph.py`** (NEW v0.3 - 565 lines)
- Knowledge graph system using NetworkX
- Entity extraction with llama-3.1-8b-instant
- 12 entity types (person, place, concept, thing, etc.)
- 5 search modes (GRAPH_COMPLETION, KEYWORD, RELATIONSHIPS, TEMPORAL, IMPORTANT)
- Fuzzy deduplication (70% similarity threshold)
- Automatic relationship inference
- Pickle-based persistence at `data/knowledge_graph.pkl`

**`companion_ai/tools.py`** (761 lines)
- 10 registered tools for autonomous use
- Built-in: calculate, get_current_time, read_pdf, read_image_text, read_document
- Search: web_search (DuckDuckGo), wikipedia_lookup
- File ops: list_files, find_file
- Memory: memory_insight (enhanced with graph search)
- Removed: Custom weather/Brave search (now using Compound models)

**`companion_ai/core/config.py`** (400+ lines)
- Model routing and selection logic
- Feature flags (ensemble, auto-tools, compound models)
- Model capabilities registry
- Complexity classification
- Token optimization settings

**`companion_ai/core/context_builder.py`**
- Loads persona YAML files
- Assembles system prompts
- Builds conversation context

### Web Interface

**`static/app.js`** (290 lines)
- Frontend JavaScript for chat UI
- Auto-scroll to latest message
- Sidebar toggle for Memory/Settings
- API communication
- Graph visualization integration

**`templates/graph.html`** (NEW v0.3 - 450 lines)
- D3.js force-directed graph visualization
- Interactive node dragging and zooming
- Real-time entity/relationship display
- Color-coded by entity type
- Accessible at `/graph` endpoint

**`static/app.css`** (450 lines)
- Gemini-inspired design
- Dark theme with smooth animations
- Responsive layout

### Configuration

**`.env`** (Your actual secrets)
```env
GROQ_API_KEY=your_key_here
AZURE_SPEECH_KEY=your_key_here
AZURE_SPEECH_REGION=your_region_here
ENABLE_ENSEMBLE=1
ENABLE_COMPOUND_MODELS=1  # NEW v0.3 - Use Groq's built-in tools
```

**`.env.example`** (Template)
- Shows all available configuration options
- Copy to `.env` and fill in your values
- **v0.3**: Weather/Brave API keys removed (using Compound instead)

---

## 🎯 Feature Status

| Feature | Status | Notes |
|---------|--------|-------|
| Web Interface | ✅ Active | Primary interface at localhost:5000 |
| CLI Interface | ✅ Active | Alternative text-based interface |
| Model Routing | ✅ Active | Automatic model selection by complexity |
| Ensemble System | ✅ Active | 3 candidates (120B, 70B, Kimi) |
| Memory System | ✅ Active | Fresh DB with strict fact filtering |
| **Knowledge Graph** | ✅ **NEW v0.3** | NetworkX graph with 5 search modes |
| **Graph Visualization** | ✅ **NEW v0.3** | D3.js interactive graph at `/graph` |
| **Token Optimization** | ✅ **NEW v0.3** | 60-70% reduction (9-11K → 3-5K tokens) |
| **Compound Models** | ✅ **NEW v0.3** | Groq built-in weather/search/calculator |
| Fact Extraction | ✅ Fixed | Blocks all inferences, only explicit facts |
| TTS (Azure) | ⚠️ Ready | Voice: Jenny Neural, needs UI toggle |
| STT | ❌ Pending | To be tested with scripts/calibrate_mic.py |
| Auto-Tools | ✅ Active | 10 autonomous tools enabled |
| Prompt Caching | ✅ Active | Reduces API costs |

---

## 🗂️ Data Storage

### Database: `data/companion_ai.db`
- **user_profile**: User facts (name, age, preferences, etc.)
- **conversation_summaries**: Conversation history summaries
- **ai_insights**: AI observations and patterns
- **pending_profile_facts**: Facts awaiting approval
- **memory_consolidation**: Long-term memory consolidation

### Knowledge Graph: `data/knowledge_graph.pkl` (NEW v0.3)
- **NetworkX DiGraph**: Entity-relationship graph
- **Entities**: 12 types (person, place, concept, thing, organization, event, etc.)
- **Relationships**: Extracted from conversations with confidence scores
- **Attributes**: Timestamps, mentions, importance, entity-specific metadata
- **Growth**: ~5 entities per conversation, linear scaling

### Logs: `data/logs/`
- **conv_YYYYMMDD.jsonl**: Daily conversation logs (1 file per day)
- **metrics_state.json**: Performance metrics and stats

### Backups
- Automatic backups created before database resets
- Keep latest backup, delete old ones

---

## 🧪 Testing & Development

### Run Unit Tests
```bash
pytest -q
```

### Development Tools (in `tools/` folder)
```bash
# Check current memory
python tools/check_actual_memory.py

# View knowledge graph
python tools/view_knowledge_graph.py

# Test graph integration
python tools/test_knowledge_graph.py
python tools/test_graph_integration.py

# Run feature tests
python tools/run_feature_tests.py

# Send test messages to web server
python tools/send_debug_message.py "What's the weather in Seattle?"

# Watch web server logs in real-time
python tools/watch_logs.py

# Test TTS
python tools/test_tts.py

# Reset memory (with backup)
python tools/reset_memory.py
```

### Utility Scripts (in `scripts/` folder)
```bash
# Verify environment setup
python scripts/check_env.py
```

---

## 📊 Project Stats (v0.3)

- **Total Python Files:** ~65 (cleaned from 102)
- **Lines of Code:** ~9,000+ (core functionality)
- **Core Package:** 16 files in companion_ai/
- **Unit Tests:** 11 test files
- **Dev Tools:** 14 helper scripts
- **Utilities:** 1 utility script
- **v0.3 Additions:**
  - memory_graph.py (565 lines)
  - graph.html template (450 lines)
  - 6 new development tools
  - KNOWLEDGE_GRAPH.md documentation (500+ lines)

---

## 🚦 Roadmap

### ✅ Completed (v0.3)
- Knowledge graph system with NetworkX
- 5 search modes (GRAPH_COMPLETION, KEYWORD, RELATIONSHIPS, TEMPORAL, IMPORTANT)
- Interactive D3.js graph visualization
- Token optimization (60-70% reduction)
- Compound models integration (Groq built-in tools)
- Code cleanup (removed 159 lines, 12 outdated files)
- Comprehensive documentation (README, KNOWLEDGE_GRAPH)

### 🎯 Planned Features
1. **Semantic Entity Matching** - Embeddings-based similarity for better deduplication
2. **Graph Export** - Neo4j, GraphML, JSON-LD formats
3. **Graph Analytics** - Centrality, communities, path finding
4. **Automated Testing** - pytest suite for knowledge graph
5. **Real-time Updates** - WebSocket graph visualization
6. **TTS UI Toggle** - Frontend control for text-to-speech
7. **STT Integration** - Speech-to-text input
8. **Smart Home** - Final integration goal

---

## 📝 Notes

- **Primary Interface:** Use `web_companion.py` for best experience
- **Personas:** Switch between companion/aether in settings (Lilith removed)
- **Memory:** Clean slate with improved fact extraction (no inferences!)
- **Knowledge Graph:** View at `/graph`, access via `/api/graph` endpoints
- **Model:** Defaults to 120B model for best quality
- **Ensemble:** Triggers on complex queries for better responses
- **Compound Models:** Built-in Groq weather/search/calculator (no API keys needed)
- **Token Optimization:** 60-70% reduction via fresh context rebuilding

---

**Built with:** Python 3.x, Flask, SQLite, NetworkX, D3.js, Groq API, Azure Speech Services
