# Companion AI (Adaptive Companion – Phase 0 → 0.2)

An adaptive AI companion focused on high‑quality reasoning, authentic personality, transparent memory, and multi‑model orchestration. Now includes trio ensemble reasoning, skill‑gated autonomous tool use, confidence‑decaying memories, and observability endpoints.

## 🌟 Key Features

### 🧠 **Intelligent Memory System**
- **Persistent Memory**: Profile facts, summaries, insights (SQLite)
- **Confidence Lifecycle**: Confidence decay + resurfacing prompts to reaffirm facts
- **Structured Facts**: Each fact stores value, confidence, evidence, justification, reaffirmations
- **Pending Fact Approval** (flagged): Optional human approval queue before commit
- **Second-Pass Verification (Planned)**: Heavy model validation for low-confidence or conflicting facts
- **Session Logging**: JSONL conversation log with routing + ensemble metadata

### 💬 **Adaptive Persona Core**
- Unified adaptive persona (`Companion`) with contextual mode selection (heuristic now)
- Persona YAML definitions in `prompts/personas/` (e.g. `companion.yaml`, `aether.yaml`, `lilith.yaml`)
- Emotionally responsive but avoids fabricated shared history
- Avoids over-apologizing; adjusts tone by complexity & intent

### 🖥️ **Interfaces**
- **Web Portal** (`run_companion.py --web` / `run_web_with_warmup.py`)
- **Copilot-Style Desktop GUI** (`copilot_gui.py`)
- **CLI Chat** (`chat_cli.py`)
- **Memory Viewer & Utilities** (`scripts/view_memory.py`, `view_memory.py`)

### 🎤 **Azure TTS Integration**
- Dragon HD voices (Phoebe / Ava)
- Async playback; togglable via `/api/tts/toggle`
- Voice switching via `/api/voice/change`

### 🧮 **Autonomous Tool Use (Gated)**
- Model may emit `TOOL:name|input` directives
- Skill scoring (EMA) + cooldown gating prevents low-value/repeat tool calls
- Default tools: `time`, `calc`, `search` (memory + optional web)

### 🤖 **Multi-Model Routing & Ensemble**
- SMART Primary: `openai/gpt-oss-120b`
- HEAVY Reasoner: `deepseek-r1-distill-llama-70b`
- Heavy Alternates: `moonshotai/kimi-k2-0905`, smart fallback
- Fast Model: `llama-3.1-8b-instant`
- Complexity-driven escalation (0..3) + importance-aware upgrades
- Optional Trio Ensemble (`ENABLE_ENSEMBLE=1`) with `choose_refine` strategy:
   1. Generate candidates (smart + heavy + alt)
   2. Judge model scores & selects best
   3. Optional refinement pass with gap-focused improvement & token budget controls
- Rich routing metadata logged (chosen index, rationale, confidence, refinement stats)

### 📊 **Observability & Transparency**
- `/api/models` exposes roles, capabilities, flags, ensemble configuration
- `/api/health` returns memory stats, metrics snapshot
- JSONL logs in `data/logs/` with hash of system prompt & latency
- Tool usage metrics (success, gating decisions)

## 🚀 Quick Start

### Prerequisites
- Python 3.11+ (developed/tested on 3.13; 3.8+ may work but unverified)
- Groq API key (conversation) — can reuse for memory if desired
- Optional: Azure Speech Services (TTS)
- Optional experimental / ensemble flags

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/Companion_V.3.git
   cd Companion_V.3
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up environment variables** (create `.env`):
   ```env
   # Core
   GROQ_API_KEY=your_groq_api_key
   GROQ_MEMORY_API_KEY=optional_second_key
   API_AUTH_TOKEN=optional_web_write_token

   # Azure (optional TTS)
   AZURE_SPEECH_KEY=...
   AZURE_SPEECH_REGION=...

   # Feature Flags (0/1 or true/false)
   ENABLE_ENSEMBLE=1
   ENABLE_EXPERIMENTAL_MODELS=0
   ENABLE_COMPOUND_MODELS=0
   ENABLE_FACT_APPROVAL=1
   FACT_AUTO_APPROVE=1
   VERIFY_FACTS_SECOND_PASS=1
   ```

4. **Run the application**
   ```bash
   # Web Portal (basic)
   python run_companion.py --web

   # Web Portal with warmup (prompt cache & model probe)
   python run_web_with_warmup.py

   # Desktop GUI
   python copilot_gui.py

   # CLI Chat
   python chat_cli.py

   # Tests
   pytest -q
   ```

## 🎯 Usage

### GUI Interface
- **Send Messages**: Type and press Ctrl+Enter
- **Toggle Thinking**: Check "Show AI Thinking" to see reasoning process
- **Natural Conversation**: Just chat normally - memory works in the background

### Memory Commands
- `memory` - View your stored profile
- `stats` - See memory statistics
- `cleanup` - Run smart memory cleanup
- `clear` - Clear the screen

### Memory Behavior
- **Automatic Extraction**: Facts, summaries, insights stored when importance ≥ thresholds
- **Confidence Decay**: Old facts slowly lose confidence; resurfaced for reaffirmation
- **Reaffirmations**: Successful reaffirmation boosts confidence/time
- **Pending Review**: If approval enabled, new facts queue until accepted
- **Second-Pass (Planned)**: Low-confidence or conflicting facts re-queried with heavy model

## 🏗️ Architecture

```
Companion_V.3/
├── companion_ai/            # Core AI modules
│   ├── core/               # Config, context building, logging, metrics
│   ├── llm_interface.py    # Routing + ensemble + autonomous tools + generation
│   ├── memory.py           # SQLite memory store + lifecycle (decay/resurface)
│   ├── memory_ai.py        # Higher-level memory reasoning (future/placeholder)
│   ├── tools.py            # Tool registry + execution
│   ├── tts_manager.py      # Azure TTS integration
│   └── __init__.py
├── scripts/               # Utility helper scripts
│   ├── calibrate_mic.py
│   ├── list_audio_devices.py
│   └── view_memory.py
├── data/                  # Runtime data (DB, logs - ignored in git)
├── tests/                 # Test suite
├── run_companion.py       # Unified launcher
├── chat_cli.py            # Minimal terminal chat
├── copilot_gui.py         # Copilot-style GUI
├── gui_app.py / gui.py    # Legacy GUI variants
├── web_companion.py       # Web interface (WIP)
└── README.md
```

## 🧠 Memory System Details

### Storage Types
- **Profile Facts**: Key user attributes (confidence, evidence, justification)
- **Summaries**: Condensed conversation segments (importance-weighted)
- **Insights**: Behavioral / preference observations

### Retrieval Strategy
1. Keyword extraction
2. Simple relevance scan (SQLite LIKE / heuristics)
3. Importance + freshness weighting
4. Fallback to recent high-importance if sparse hits
5. (Future) Hybrid semantic + lexical retrieval

### Smart Features
- Deduplication (summaries, insights)
- Confidence decay + resurfacing
- Pending approval queue (optional)
- Tool-driven fact search (search tool)
- Planned: embedding similarity + heavy verification path

## 🔧 Configuration & Security

Never commit secrets: `.env`, `data/companion_ai.db`, exported memory files, or logs. `.gitignore` already excludes these; review before pushing if you add new sensitive assets.

### Memory Settings
- **Importance Threshold**: 0.2 (stores more conversations)
- **Summary Limit**: 5 most relevant summaries
- **Insight Limit**: 8 most relevant insights
- **Cleanup Frequency**: Automatic on low importance

### Routing & Models (Current)
- **Fast**: `llama-3.1-8b-instant`
- **Smart Primary**: `openai/gpt-oss-120b`
- **Heavy**: `deepseek-r1-distill-llama-70b`
- **Heavy Alternates**: `moonshotai/kimi-k2-0905`, smart fallback
- Complexity-based escalation (>=2 → heavy path / ensemble)

### Ensemble (Optional)
Environment variables:
```
ENABLE_ENSEMBLE=1
ENSEMBLE_MODE=choose_refine   # choose | combine | choose_refine | combine_refine | refine_only
ENSEMBLE_CANDIDATES=3         # 2 or 3 supported currently
ENSEMBLE_REFINE_EXPANSION=0.25
ENSEMBLE_REFINE_HARD_CAP=300
```

### Feature Flags Summary
| Flag | Purpose |
|------|---------|
| ENABLE_ENSEMBLE | Activate multi-model candidate generation + judge selection |
| ENABLE_FACT_APPROVAL | Manual approval queue for new profile facts |
| FACT_AUTO_APPROVE | Auto-approve high-confidence facts (>= threshold) |
| VERIFY_FACTS_SECOND_PASS | Plan: heavy model verification stage |
| ENABLE_AUTO_TOOLS | Allow TOOL: directives from model |
| ENABLE_PROMPT_CACHING | Provider prompt caching hints |
| ENABLE_EXPERIMENTAL_MODELS | Include experimental registry entries (qwen, kimi) |
| ENABLE_COMPOUND_MODELS | Future agentic compound models |

### Endpoints (Key)
| Endpoint | Description |
|----------|-------------|
| `POST /api/chat` | Chat interaction (optional `X-API-TOKEN`) |
| `GET /api/memory` | Dump recent stored memory artifacts |
| `GET /api/pending_facts` | List pending facts (if approval enabled) |
| `POST /api/pending_facts/<id>/approve|reject` | Fact moderation |
| `GET /api/models` | Model roles, flags, ensemble config, availability |
| `GET /api/health` | Memory stats + metrics snapshot |
| `POST /api/tts/toggle` | Toggle TTS engine |
| `POST /api/voice/change` | Switch Azure TTS voice |

Security note: Set `API_AUTH_TOKEN` to require token for mutating endpoints.

## 🚧 Roadmap (Rolling)
Delivered (Phase 0.2):
- Multi-model routing (fast / smart / heavy / alternates)
- Trio ensemble reasoning (choose_refine)
- Tool skill scoring + gating
- Confidence decay & resurfacing
- Structured fact storage (evidence, justification)
- `/api/models` transparency endpoint
- Logging with routing + ensemble metadata

In Progress / Planned:
- Second-pass fact verifier (heavy validation)
- Provenance UI (show evidence & confidence visually)
- Compound / agentic model stubs
- Embedding + hybrid retrieval layer
- Streaming responses & partial TTS
- Cost / latency dashboards
- Docker packaging & deployment guides

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📝 License

MIT License (see `LICENSE`).

## 🙏 Acknowledgments

- **DeepSeek** (R1 reasoning model)
- **Groq** (high-performance inference)
- **Azure** (speech services)
- Early testers & community feedback

---
Feel free to open issues for feature requests, routing anomalies, or memory governance improvements.