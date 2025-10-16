# Companion AI - Project Structure

**Last Updated:** October 16, 2025  
**Status:** Production-ready, cleaned and organized

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
│   ├── tools.py                  # Tool calling system
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
│       └── index.html            # Main web template
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
├── 🔧 tools/ (Development Tools - 8 files)
│   ├── check_actual_memory.py    # View current memory contents
│   ├── check_db_schema.py        # Inspect database schema
│   ├── clean_memory_db.py        # Clean bad facts from DB
│   ├── reset_memory.py           # Wipe all memory (with backup)
│   ├── test_fact_extraction.py   # Test fact filtering
│   ├── test_features_verification.py # Verify all features work
│   ├── test_tts.py               # Test TTS voices
│   └── list_azure_voices.py      # List available TTS voices
│
├── 📜 scripts/ (Utility Scripts - 4 files)
│   ├── calibrate_mic.py          # Microphone calibration for STT
│   ├── check_env.py              # Verify .env configuration
│   ├── list_audio_devices.py     # List available audio devices
│   └── view_memory.py            # Quick memory viewer
│
├── 🎭 prompts/personas/
│   ├── companion.yaml            # Default personality (active)
│   ├── aether.yaml               # Alternative persona
│   └── lilith.yaml               # Alternative persona
│
├── 💾 data/
│   ├── companion_ai.db           # SQLite memory database (active)
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
    └── README.md                 # Main project documentation
```

---

## 🔑 Key Files Explained

### Entry Points

**`web_companion.py`** (346 lines)
- Flask web server at http://127.0.0.1:5000
- Main interface with chat, memory sidebar, and settings
- Handles API routes for chat and memory retrieval

**`run_companion.py`**
- Launcher script with CLI arguments
- `--web` flag starts web interface
- Default starts CLI interface

**`chat_cli.py`**
- Simple command-line chat interface
- Alternative to web UI for terminal users

### Core AI Logic

**`companion_ai/llm_interface.py`** (807 lines)
- LLM API calls to Groq/OpenRouter
- Fact extraction with strict filtering (no inferences!)
- Ensemble reasoning (3 candidate models)
- Tool calling integration

**`companion_ai/conversation_manager.py`**
- Orchestrates conversations
- Builds context with memory + history
- Coordinates LLM, tools, and logging

**`companion_ai/memory.py`**
- SQLite database operations
- Stores user profile facts, conversation summaries, AI insights
- Retrieval and search functionality

**`companion_ai/core/config.py`** (354 lines)
- Model routing and selection logic
- Feature flags (ensemble, auto-tools, etc.)
- Model capabilities registry
- Complexity classification

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
```

**`.env.example`** (Template)
- Shows all available configuration options
- Copy to `.env` and fill in your values

---

## 🎯 Feature Status

| Feature | Status | Notes |
|---------|--------|-------|
| Web Interface | ✅ Active | Primary interface at localhost:5000 |
| CLI Interface | ✅ Active | Alternative text-based interface |
| Model Routing | ✅ Active | Automatic model selection by complexity |
| Ensemble System | ✅ Active | 3 candidates (120B, 70B, Kimi) |
| Memory System | ✅ Active | Fresh DB with strict fact filtering |
| Fact Extraction | ✅ Fixed | Blocks all inferences, only explicit facts |
| TTS (Azure) | ⚠️ Ready | Voice: Jenny Neural, needs UI toggle |
| STT | ❌ Pending | To be tested with scripts/calibrate_mic.py |
| Auto-Tools | ✅ Active | Automatic tool calling enabled |
| Prompt Caching | ✅ Active | Reduces API costs |

---

## 🗂️ Data Storage

### Database: `data/companion_ai.db`
- **user_profile**: User facts (name, age, preferences, etc.)
- **conversation_summaries**: Conversation history summaries
- **ai_insights**: AI observations and patterns
- **pending_profile_facts**: Facts awaiting approval
- **memory_consolidation**: Long-term memory consolidation

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

# Test fact extraction
python tools/test_fact_extraction.py

# Verify all features
python tools/test_features_verification.py

# Test TTS
python tools/test_tts.py

# Reset memory (with backup)
python tools/reset_memory.py
```

### Utility Scripts (in `scripts/` folder)
```bash
# Verify environment setup
python scripts/check_env.py

# View memory contents
python scripts/view_memory.py

# List audio devices (for STT)
python scripts/list_audio_devices.py

# Calibrate microphone (for STT)
python scripts/calibrate_mic.py
```

---

## 📊 Project Stats

- **Total Python Files:** 74 (down from 102)
- **Lines of Code:** ~8,000+ (core functionality)
- **Core Package:** 15 files in companion_ai/
- **Unit Tests:** 11 test files
- **Dev Tools:** 8 helper scripts
- **Utilities:** 4 utility scripts

---

## 🚦 Next Steps

1. **Add TTS Toggle** - UI control for text-to-speech
2. **Test Memory** - Verify fact extraction with real conversations
3. **Test Conversation Quality** - 20-30 exchanges to evaluate
4. **Test STT** - Speech-to-text input testing
5. **Smart Home Integration** - Final goal after quality verified

---

## 📝 Notes

- **Primary Interface:** Use `web_companion.py` for best experience
- **Personas:** Switch between companion/aether/lilith in settings
- **Memory:** Clean slate with improved fact extraction (no inferences!)
- **Model:** Defaults to 120B model for best quality
- **Ensemble:** Triggers on complex queries for better responses

---

**Built with:** Python 3.x, Flask, SQLite, Groq API, Azure Speech Services
