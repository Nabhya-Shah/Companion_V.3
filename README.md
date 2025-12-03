# Companion AI

A personal AI companion with persistent memory, knowledge graph, and intelligent multi-model routing. Built for natural conversation with automatic fact extraction and context awareness.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Knowledge Graph** | NetworkX-based entity/relationship extraction with D3.js visualization |
| **Persistent Memory** | SQLite storage for facts, summaries, and insights with confidence tracking |
| **4-Model Architecture** | PRIMARY (120B), TOOLS (Scout), VISION (Maverick), COMPOUND (web/weather) |
| **Tool Use** | Agentic loop with file reading, web search, calculations, and more |
| **Token Optimized** | 60-70% reduction via 3-turn limits and conditional profile loading |
| **Azure TTS** | Text-to-speech with Jenny Neural voice |
| **Web UI** | Clean chat interface with memory management and graph visualization |

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/Nabzy-12/Companion_V.3.git
cd Companion_V.3
pip install -r requirements.txt

# Configure (create .env file)
GROQ_API_KEY=your_key_here
GROQ_VISION_API_KEY=optional_vision_key  # Falls back to main key

# Azure TTS (optional)
AZURE_SPEECH_KEY=your_key
AZURE_SPEECH_REGION=your_region

# Run
python run_companion.py --web    # Web UI at localhost:5000
python chat_cli.py               # Terminal chat
pytest -q                        # Run tests
```

## 🏗️ Architecture

```
User Message
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  web_companion.py                                        │
│  • Auth check                                            │
│  • Vision trigger detection (!photo)                     │
│  • Route to ConversationSession                          │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  conversation_manager.py - ConversationSession           │
│  • Search memory for relevant context                    │
│  • Build recent_conversation (last 3 turns only)         │
│  • Call LLM interface                                    │
│  • Store exchange for later memory processing            │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  llm_interface.py                                        │
│  • Classify complexity (0=casual, 1=moderate, 2=complex) │
│  • Build system prompt (profile only if memory triggers) │
│  • Route: Compound → Tools → Direct chat                 │
│  • Agentic tool loop (up to 5 iterations)                │
└─────────────────────────────────────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────┐
│  EVERY 5 TURNS: Memory Processing (background)           │
│  • Importance analysis → skip low-value exchanges        │
│  • Generate summary                                      │
│  • Extract facts → SQLite                                │
│  • Generate insights → Knowledge graph                   │
└─────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
companion_ai/
├── core/
│   ├── config.py              # Model routing, complexity classification
│   ├── context_builder.py     # System prompt construction
│   └── conversation_logger.py # JSONL logging
├── llm_interface.py           # LLM calls, tool execution, streaming
├── conversation_manager.py    # Session management, memory integration
├── memory.py                  # SQLite: facts, summaries, insights
├── memory_graph.py            # NetworkX knowledge graph
├── memory_ai.py               # AI-powered memory extraction
├── tools.py                   # Tool definitions and execution
└── tts_manager.py             # ElevenLabs TTS integration

web_companion.py               # Flask server
run_companion.py               # CLI launcher
templates/
├── index.html                 # Chat UI
└── graph.html                 # Knowledge graph visualization
tools/                         # Dev utilities (6 scripts)
tests/                         # Pytest suite
```

## 🔧 Configuration

### Environment Variables

```env
# Required
GROQ_API_KEY=your_groq_api_key

# Recommended (avoids rate limits for memory processing)
GROQ_MEMORY_API_KEY=second_groq_key

# Optional
API_AUTH_TOKEN=secret           # Protect mutating endpoints
ELEVENLABS_API_KEY=key          # TTS support
```

### Models (4-Model Architecture)

| Role | Model | Used For |
|------|-------|----------|
| PRIMARY | `openai/gpt-oss-120b` | Main chat, reasoning, everything |
| TOOLS | `meta-llama/llama-4-scout-17b-16e-instruct` | Native function calling |
| VISION | `meta-llama/llama-4-maverick-17b-128e-instruct` | Image analysis |
| COMPOUND | `compound-beta` | Web search, weather, calculations |

## 📡 API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/chat` | POST | Send message, get response |
| `/api/chat/send` | POST | Streaming SSE response |
| `/api/memory` | GET | View stored facts/summaries |
| `/api/memory/facts` | DELETE | Delete specific facts |
| `/api/graph` | GET | Export knowledge graph JSON |
| `/api/graph/stats` | GET | Graph statistics |
| `/graph` | GET | Interactive graph visualization |
| `/api/health` | GET | System status |
| `/api/tts/toggle` | POST | Toggle Azure TTS |
| `/api/voice/change` | POST | Switch TTS voice |

## 🛠️ Development

```bash
# Run tests
pytest -q

# Watch logs in real-time
python tools/watch_logs.py

# Quick API test
python tools/send_debug_message.py "Hello!"

# View knowledge graph (CLI)
python tools/view_knowledge_graph.py

# Reset memory (careful!)
python tools/reset_memory.py
```

## 🧠 How Memory Works

1. **During Chat**: Keywords extracted, relevant memories searched
2. **Every 5 Turns**: Background processing kicks in
3. **Importance Check**: Skip low-value exchanges (saves API calls)
4. **Extraction**: Facts, summaries, insights pulled from conversation
5. **Storage**: SQLite for structured data, NetworkX for relationships
6. **Retrieval**: Next conversation searches both stores for context

### Token Optimization

- Only **last 3 turns** sent to LLM (not full history)
- Profile facts only included when message has memory triggers ("remember", "my name", etc.)
- Tool execution uses minimal system prompt, synthesis uses full personality
- Result: **3-5K input tokens** instead of 9-11K

## 📝 License

MIT

---

*Built with Groq, NetworkX, Flask, and D3.js*