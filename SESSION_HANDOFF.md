# Companion AI - Session Handoff Document
> **Created:** December 16, 2025
> **Purpose:** Transfer complete context to new AI session

---

## 🏗️ Current Architecture (V5)

### Model Routing Strategy
```
User Request → Intent Detection
    ↓
├─ HEAVY TOOLS (local, free)
│   ├─ File/Brain ops → qwen2.5:32b
│   ├─ Vision → llava:13b
│   └─ Browser/Computer → qwen2.5:32b
│
├─ LIGHT TOOLS (cloud, fast)
│   └─ Search, time, scheduling → Groq llama-3.1-8b-instant
│
└─ SYNTHESIS (cloud, smart)
    └─ Final response → Groq openai/gpt-oss-120b
```

### Installed Local Models (Ollama)
| Model | Size | Purpose |
|-------|------|---------|
| qwen2.5:32b | 19GB | Heavy tool execution |
| llava:13b | 8GB | Vision/screen analysis |
| llama3.1:latest | 4.9GB | Fast summarization |

---

## 📁 Key Files & Modules

### Core Configuration
| File | Purpose |
|------|---------|
| `companion_ai/core/config.py` | Model constants, LIGHT_TOOLS/HEAVY_TOOLS sets, get_tool_model() |
| `companion_ai/core/context_builder.py` | System prompt builder with capabilities + brain context |
| `companion_ai/core/prompts.py` | Static persona prompt (cached) |
| `.env` | API keys, LOCAL_VISION_MODEL=llava:13b |

### Main Logic
| File | Purpose |
|------|---------|
| `companion_ai/llm_interface.py` | Hybrid routing, tool execution, summarization |
| `companion_ai/tools.py` | Tool definitions and execute_function_call() |
| `companion_ai/conversation_manager.py` | Session handling, memory integration |
| `companion_ai/job_manager.py` | SQLite job queue for background tasks |

### Tool Modules
| File | Purpose |
|------|---------|
| `companion_ai/browser_agent.py` | Playwright browser automation |
| `companion_ai/computer_agent.py` | PyAutoGUI + vision for desktop control |
| `companion_ai/vision_manager.py` | Screen capture + local llava:13b analysis |
| `companion_ai/brain_manager.py` | Read/write persistent notes to data/companion_brain/ |

### Memory Systems
| File | Purpose |
|------|---------|
| `companion_ai/memory.py` | Core SQLite-based conversation memory |
| `companion_ai/memory_v2.py` | Mem0 integration for semantic memory |
| `companion_ai/memory_graph.py` | NetworkX knowledge graph (320 entities, 358 rels) |
| `companion_ai/memory_ai.py` | AI-powered memory operations |

### Data Directories
```
data/
├─ companion_ai.db      # SQLite: conversations, jobs, metrics
├─ companion_brain/     # AI's persistent notes
│  ├─ memories/         # personality.md, user_context.md
│  ├─ system/           # core_rules.md (protected)
│  └─ training/skills/  # Learned skills from trainer
├─ knowledge_graph.pkl  # Serialized NetworkX graph
└─ web_server.log       # Runtime logs
```

---

## ✅ Features Working

1. **Hybrid Model Routing** - Heavy tools use local Ollama, light use Groq
2. **Brain Tools** - read/write/list persistent notes
3. **Browser Automation** - Playwright-based goto/click/type/read
4. **Vision** - llava:13b screen analysis
5. **Token Budget** - Daily tracking with UI display
6. **Knowledge Graph** - 320 entities, auto-populates from conversations
7. **Smart Summarization** - Compresses tool results before 120B synthesis
8. **Capabilities Awareness** - System prompt tells 120B about its tools

---

## 🎯 Design Decisions Made

1. **Local for Heavy, Cloud for Light** - Saves Groq tokens, 32B is smart enough
2. **Intent-based routing** - Detects file/vision/browser keywords to pick model
3. **Model detection by format** - Ollama uses "model:tag" (colon), Groq uses dashes
4. **Summarization threshold** - Only summarize results >300 chars
5. **Vision default ON** - USE_LOCAL_VISION=1 in .env for llava:13b
6. **Brain context in prompt** - personality.md + user_context.md auto-included

---

## 🐛 Known Issues / Quirks

1. **Windows emoji encoding** - Some scripts fail on emoji in Windows console
2. **Knowledge graph UI** - Shows 0 in UI but data exists (320 entities)
3. **Vision fallback** - If Ollama down, falls back to Groq Maverick model
4. **Token tracking** - Shows 0 for local model usage (only tracks Groq)

---

## 📋 Backlog / Future Ideas

### High Priority
- [ ] Fix knowledge graph UI display
- [ ] Add escape key to stop generation
- [ ] Improved error messages in UI

### Medium Priority
- [ ] Voice mode (local Whisper)
- [ ] Multi-monitor awareness
- [ ] Hot-swap models per task

### Low Priority
- [ ] Gaming integration
- [ ] Discord bot integration

---

## 🔧 Quick Commands

```bash
# Start server
python web_companion.py

# Check local models
ollama list

# View knowledge graph stats
python -c "from companion_ai.memory_graph import get_graph_stats; print(get_graph_stats())"

# Run tests
python -m pytest tests/ -v

# Clear pycache
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
```

---

## 🧠 User Preferences (Observed)

- Prefers local models to save API costs
- Values speed over absolute quality for tools
- Likes detailed explanations when learning
- Uses "YOLO MODE" - trusts AI to run commands without asking
- Current hardware: RTX 5080 (16GB VRAM), 64GB RAM, Ryzen 9800X3D

---

## 📝 Files Cleaned This Session

Removed:
- `companion_ai/core/tool_router.py` (deprecated, just raises ImportError)
- All `__pycache__/` directories

Verified clean:
- No COMPOUND_MODEL references
- No minicpm references in companion_ai
- All core modules pass syntax check

---

## 🚀 To Resume Work

1. Read this document to understand architecture
2. Server: `python web_companion.py` (port 5000)
3. Test: "What files are in your brain?" (should list 4 files)
4. Test: "Look at my screen" (should describe in ~5 seconds)
5. Check logs: `data/web_server.log`

The codebase is clean and all major features are working!
