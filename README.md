# Companion AI

A personal AI companion with an orchestrator brain, specialist local loops, persistent memory, knowledge graph, and evolving persona. The cloud orchestrator understands every message, delegates to local specialists when needed, and builds a growing model of who you are.

## ✨ Features

| Feature | Description |
|---------|-------------|
| **Orchestrator Brain** | Groq cloud model classifies every message and routes: answer, delegate, tool call, background task, or memory operation |
| **Local Specialists** | Ollama-powered loops for memory extraction, tool execution, and vision — autonomous but orchestrator-controlled |
| **Quick Tool Path** | Simple tool calls (time, weather) go through Groq directly for fast zero-shot execution |
| **Unified Knowledge** | Mem0 vector memory + SQLite fact store + brain document index + knowledge graph — one recall interface |
| **Memory Quality** | Conflict detection, dedup, confidence scoring, reaffirmation tracking, staleness decay |
| **Persona Evolution** | The companion's personality grows and adapts over time — not just a chatbot |
| **Streaming Chat** | SSE-based streaming responses with cancel support |
| **Scheduled Automations** | Recurring tasks with policy enforcement, retry tracking, and run-now controls |
| **Plugin & Tool Safety** | Policy-driven gating, allowlists, sandbox modes, and clear denial messages |
| **Smart Home** | Loxone integration with room control, state sync, voice commands |
| **Per-Step Token Tracking** | See tokens + timing for each pipeline step with GROQ/LOCAL model labels |
| **Session & Workspace Isolation** | Memory, brain paths, and settings scoped per session/profile/workspace |

## 🧠 Memory System

| Feature | Description |
|---------|-------------|
| **Conflict Detection** | Detects contradicting facts with full lifecycle (pending → review → resolved) |
| **Deduplication** | Hash-based exact match + 70% similarity threshold |
| **Confidence Scoring** | High (≥0.80), Medium (≥0.50), Low (<0.50) — low-confidence facts flagged for review |
| **Reaffirmation** | Repeated facts boost confidence + increment reaffirmation count |
| **Staleness** | Old facts surfaced for reconfirmation with configurable decay |

## 🚀 Quick Start

```bash
# Clone and install
git clone https://github.com/Nabzy-12/Companion_V.3.git
cd Companion_V.3
python -m venv .venv
.venv\\Scripts\\python.exe -m pip install --upgrade pip
.venv\\Scripts\\python.exe -m pip install -r requirements.txt

# Configure (.env file)
GROQ_API_KEY=your_key_here

# Run
.venv\\Scripts\\python.exe run_companion.py    # Web UI at localhost:5000
```

### Python Version Note (Important)

- Best compatibility today is Python 3.11 or 3.12.
- Python 3.14 may fail on some optional native packages (`lxml`, `pyaudio`, `zlib-state`) depending on your system build tools.
- If install fails on 3.14, create a Python 3.11 venv and reinstall.

### Windows One-Command Migration to Python 3.11

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_python311.ps1
```

What it does:
- Installs Python 3.11 with `winget` if missing
- Recreates `.venv` using Python 3.11
- Installs `requirements.txt`
- Falls back to a minimal Phase 1 dependency set if optional packages fail

## 🏗️ Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for full details.

```
User → Flask Web Layer → Orchestrator (Groq Cloud)
                              │
               ┌──────────────┼──────────────┐
               │              │              │
          Quick Tool     Local Loops    Unified Knowledge
          (Groq fast)    (Ollama)       System
                         │
                    ┌────┼────┐
                    │    │    │
                 Memory Tool Vision
                 Loop  Loop  Loop
```

**Key Principles:**
- **Orchestrator-first** — every message classified and routed
- **Local specialists** — loops run autonomously, orchestrator controls state
- **Unified knowledge** — one interface for memory, facts, and documents
- **Persona as soul** — personality evolves, not just a chat wrapper
- **Policy-driven safety** — tools, automations, and plugins respect explicit controls

## 📁 Project Structure

```
companion_ai/
├── core/                 # Config, prompts, logging, metrics
├── agents/               # Browser (shelved), vision (active)
├── integrations/         # Loxone smart home
├── memory/               # SQLite, Mem0, knowledge graph, AI processor
├── services/             # Persona, jobs/scheduler, workflows, insights, token budget, TTS
├── local_loops/          # Specialist loops (memory, tool, vision)
├── llm/                  # LLM router — Groq + Ollama providers
│   ├── groq_provider.py  # Groq cloud calls + tool calling
│   ├── ollama_provider.py # Ollama local calls + embeddings
│   ├── router.py         # High-level response routing
│   └── token_tracker.py  # Per-step token stats
├── tools/                # Tool registration + domain tools
│   ├── registry.py       # @tool decorator, plugin system, policy
│   ├── system_tools.py   # Time, memory search, screen
│   ├── brain_tools.py    # Brain search, read, write, list
│   ├── browser_tools.py  # Browser automation
│   ├── file_tools.py     # PDF, image, docx, file listing
│   └── research_tools.py # Wikipedia
├── web/                  # Flask Blueprints (7 route modules)
│   ├── __init__.py       # App factory (create_app)
│   ├── state.py          # Shared globals, security, scope helpers
│   ├── chat_routes.py    # SSE streaming chat
│   ├── memory_routes.py  # Memory CRUD + review
│   ├── files_routes.py   # Upload + brain files
│   ├── tools_routes.py   # Tools, plugins, context
│   ├── media_routes.py   # TTS + vision
│   ├── loxone_routes.py  # Smart home
│   └── system_routes.py  # Health, config, admin
├── orchestrator.py       # Cloud brain — intent classification & routing
├── conversation_manager.py # Session coordinator
├── brain_index.py        # Document embedding index
└── brain_manager.py      # Brain file management

web_companion.py          # Backwards-compat shim → companion_ai/web/
templates/                # HTML templates
static/                   # JS, CSS
tests/                    # 21 pytest suites, 219 tests
scripts/                  # Utility scripts
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
API_AUTH_TOKEN=
TOOL_ALLOWLIST=
PLUGIN_ALLOWLIST=
PLUGIN_POLICY_PATH=data/plugin_policy.json
SANDBOX_MODE=main

# Loxone Smart Home (optional)
LOXONE_HOST=192.168.x.x
LOXONE_USER=your_username
LOXONE_PASSWORD=your_password
```

### Models

| Role | Model | Provider |
|------|-------|----------|
| Primary chat / orchestrator | `openai/gpt-oss-120b` | Groq Cloud |
| Fast tool calling | `llama-3.1-8b-instant` | Groq Cloud |
| Vision | `meta-llama/llama-4-maverick-17b-128e-instruct` | Groq Cloud |
| Memory AI | `meta-llama/llama-4-scout-17b-16e-instruct` | Groq Cloud |
| Mem0 backend | `qwen3:14b` | Ollama (local) |
| Brain embeddings | `nomic-embed-text` | Ollama (local) |
| Vision (local) | `llava:7b` | Ollama (local) |

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

## 🛡️ Tool Safety Allowlist

- Set `TOOL_ALLOWLIST` in `.env` to restrict which tools can execute.
- Value format: comma-separated tool names (example: `get_current_time,memory_search,list_files`).
- Use `*` (or leave empty) to disable allowlist enforcement.
- Blocked calls return a clear denial message and are counted in tool telemetry.

## ✅ Smoke Test

Run the core daily-use endpoint smoke check against a running server:

```bash
.venv\\Scripts\\python.exe scripts/smoke_daily_use.py
```

With explicit token/base URL:

```bash
.venv\\Scripts\\python.exe scripts/smoke_daily_use.py --base-url http://127.0.0.1:5000 --token YOUR_TOKEN
```

## 🚦 Release Profile Check

Run a single command to validate Python compatibility, env, and smoke checks:

```bash
.venv\\Scripts\\python.exe scripts/release_profile_check.py
```

Require live LLM configuration:

```bash
.venv\\Scripts\\python.exe scripts/release_profile_check.py --require-llm
```

## 📝 License

MIT