# Companion AI (Adaptive Companion – v0.3)

An adaptive AI companion with **knowledge graph memory**, high‑quality reasoning, transparent memory systems, and multi‑model orchestration. Features automatic entity extraction, 60-70% token optimization, interactive graph visualization, and trio ensemble reasoning.

## 🌟 Key Features

### 🕸️ **Knowledge Graph Memory System** ⭐ NEW
- **NetworkX Graph**: Automatic entity and relationship extraction from conversations
- **5 Search Modes**: 
  - `GRAPH_COMPLETION`: Entity + neighbors + relationships (1-hop traversal)
  - `KEYWORD`: Text matching across entity names and attributes
  - `RELATIONSHIPS`: Edge-focused queries
  - `TEMPORAL`: Date range filtering
  - `IMPORTANT`: Sorted by mentions, connections, and importance score
- **Automatic Growth**: Extracts entities during conversations using `llama-3.1-8b-instant`
- **Interactive Visualization**: D3.js force-directed graph at `/graph` endpoint
- **Smart Deduplication**: Fuzzy matching prevents duplicate entities
- **Multi-Modal Search**: `memory_insight` tool integrates graph, facts, summaries, and insights
- **Real-time Stats**: Track entity growth, relationships, and most connected nodes

### 🧠 **Intelligent Memory System**
- **Persistent Memory**: Profile facts, summaries, insights (SQLite)
- **Confidence Lifecycle**: Confidence decay + resurfacing prompts to reaffirm facts
- **Structured Facts**: Each fact stores value, confidence, evidence, justification, reaffirmations
- **Pending Fact Approval** (flagged): Optional human approval queue before commit
- **Second-Pass Verification (Active)**: Heavy model validates low-confidence facts before staging/commit
- **Provenance UI**: Web memory panel shows confidence tier, reaffirmations, timestamps, evidence (expandable)
- **Session Logging**: JSONL conversation log with routing + ensemble metadata

### 💬 **Adaptive Persona Core**
- Unified adaptive persona (`Companion`) with contextual mode selection (heuristic now)
- Persona YAML definitions in `prompts/personas/` (e.g. `companion.yaml`, `aether.yaml`, `lilith.yaml`)
- Emotionally responsive but avoids fabricated shared history
- Avoids over-apologizing; adjusts tone by complexity & intent

### � **Token Optimization** ⭐ NEW
- **60-70% Reduction**: Optimized from 9-11K to 3-5K input tokens
- **Fresh Context Rebuilding**: Synthesis phase rebuilds prompts with current conversation only
- **Minimal Tool Prompts**: Tool execution uses stripped-down system prompts
- **Verified on Production**: Confirmed via Groq dashboard metrics

### �🖥️ **Interfaces**
- **Web Portal** (`run_companion.py --web`)
- **Interactive Graph Visualization** (`/graph` - D3.js force-directed graph) ⭐ NEW
- **CLI Chat** (`chat_cli.py`)
- **Memory Viewer & Utilities** (`tools/view_knowledge_graph.py`) ⭐ NEW

### 🎤 **Azure TTS Integration**
- Dragon HD voices (Phoebe / Ava)
- Async playback; togglable via `/api/tts/toggle`
- Voice switching via `/api/voice/change`

### 🧮 **Autonomous Tool Use (Gated)**
- **Groq Compound Models** (weather, search, calculator built-in) ⭐ ENABLED
- Custom tools: `time`, `memory_insight`, `read_pdf`, `find_file`, `wikipedia_lookup`
- **Knowledge Graph Search**: Multi-modal `memory_insight` tool with 5 search modes
- Skill scoring (EMA) + cooldown gating prevents low-value/repeat tool calls

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
- `/api/routing/recent` streams recent routing & ensemble decisions
- `/api/health` returns memory stats, metrics snapshot
- **Knowledge Graph APIs** ⭐ NEW:
  - `/api/graph` - Full graph export (nodes + edges JSON)
  - `/api/graph/stats` - Entity counts, types, most connected nodes
  - `/api/graph/search?q=query&mode=GRAPH_COMPLETION` - Search with mode selection
- JSONL logs in `data/logs/` with hash of system prompt & latency
- Tool usage metrics (success, gating decisions)

## 📊 Knowledge Graph API Examples

### Get Graph Statistics
```bash
curl http://localhost:5000/api/graph/stats
```
**Response:**
```json
{
  "total_entities": 49,
  "total_relationships": 50,
  "avg_connections": 1.02,
  "entity_types": {
    "concept": 23,
    "person": 2,
    "place": 5,
    "organization": 4
  },
  "most_connected": [
    {"name": "User", "connections": 14},
    {"name": "Python", "connections": 7}
  ]
}
```

### Search Knowledge Graph
```bash
# Graph completion (entity + neighbors)
curl "http://localhost:5000/api/graph/search?q=Python&mode=GRAPH_COMPLETION&limit=10"

# Keyword search
curl "http://localhost:5000/api/graph/search?q=machine%20learning&mode=KEYWORD"

# Most important entities
curl "http://localhost:5000/api/graph/search?mode=IMPORTANT&limit=5"
```

### View Interactive Graph
Navigate to `http://localhost:5000/graph` to see the D3.js force-directed visualization:
- **Color-coded** by entity type (person, place, concept, etc.)
- **Node size** based on mentions + importance
- **Search & highlight** specific entities
- **Click to select** and see connections
- **Drag nodes** to rearrange layout
- **Hover** for entity attributes and details

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
   # Core (Required)
   GROQ_API_KEY=your_groq_api_key
   GROQ_MEMORY_API_KEY=optional_second_key
   
   # Web API Security (Optional)
   API_AUTH_TOKEN=optional_web_write_token

   # Azure TTS (Optional)
   AZURE_SPEECH_KEY=...
   AZURE_SPEECH_REGION=...

   # Feature Flags (0/1 or true/false)
   ENABLE_ENSEMBLE=1                  # Multi-model ensemble reasoning
   ENABLE_COMPOUND_MODELS=1           # Groq built-in tools (weather, search, calc) ⭐ RECOMMENDED
   ENABLE_EXPERIMENTAL_MODELS=0       # Experimental model registry
   ENABLE_FACT_APPROVAL=1             # Manual fact approval queue
   FACT_AUTO_APPROVE=1                # Auto-approve high-confidence facts
   VERIFY_FACTS_SECOND_PASS=1         # Heavy model verification
   
   # Ensemble Configuration
   ENSEMBLE_MODE=choose_refine        # choose | combine | choose_refine | refine_only
   ENSEMBLE_CANDIDATES=3              # Number of candidate models (2 or 3)
   ENSEMBLE_REFINE_EXPANSION=0.25     # Token budget expansion for refinement
   ENSEMBLE_REFINE_HARD_CAP=300       # Hard cap for refinement tokens
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

  5. **Run the conversational evaluation harness** (optional, for prompt tuning)
     ```bash
     # Ensure the web server is running on localhost:5000, then:
     python tools/run_prompt_eval.py --label current
     ```
     This script reads `tools/eval_scenarios.json`, resets the debug session between scenarios, and records
     full transcripts plus summary metrics in `data/eval_reports/<timestamp>_<label>*.json`. Run again with
     `--label new_prompt` after making prompt changes, then diff the summaries to spot regressions.

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
│   ├── llm_interface.py    # Routing + ensemble + token optimization + generation
│   ├── memory.py           # SQLite memory store + lifecycle (decay/resurface)
│   ├── memory_graph.py     # NetworkX knowledge graph (entities + relationships) ⭐ NEW
│   ├── memory_ai.py        # Higher-level memory reasoning
│   ├── conversation_manager.py  # Session management + graph integration
│   ├── tools.py            # Tool registry + execution (10 tools)
│   ├── tts_manager.py      # Azure TTS integration
│   └── __init__.py
├── tools/                  # Development & testing utilities ⭐ UPDATED
│   ├── send_debug_message.py    # API testing
│   ├── view_knowledge_graph.py  # CLI graph viewer ⭐ NEW
│   ├── run_feature_tests.py     # Comprehensive test suite ⭐ NEW
│   ├── watch_logs.py            # Real-time log monitoring
│   ├── check_actual_memory.py   # Memory inspection
│   └── ...
├── templates/              # Web UI templates
│   ├── index.html          # Chat interface
│   └── graph.html          # Interactive D3.js graph visualization ⭐ NEW
├── static/                 # Frontend assets (CSS, JS)
├── data/                   # Runtime data (DB, logs, graph - ignored in git)
│   ├── companion_ai.db     # SQLite memory database
│   ├── knowledge_graph.pkl # Pickled NetworkX graph ⭐ NEW
│   └── logs/               # JSONL conversation logs
├── tests/                  # Test suite (11 pytest tests)
├── prompts/personas/       # Persona YAML definitions
├── run_companion.py        # Unified launcher
├── chat_cli.py            # Minimal terminal chat
├── web_companion.py       # Flask web server
└── README.md
```

## 🧠 Memory System Details

### Storage Types
- **Knowledge Graph** ⭐ NEW: NetworkX DiGraph with entities and relationships
  - Automatic extraction from conversations (llama-3.1-8b-instant)
  - Entity types: person, place, concept, thing, organization, event, etc.
  - Relationship tracking with strength scores and context
  - Fuzzy deduplication (70% similarity threshold)
  - Persistent storage in `data/knowledge_graph.pkl`
- **Profile Facts**: Key user attributes (confidence, evidence, justification)
- **Summaries**: Condensed conversation segments (importance-weighted)
- **Insights**: Behavioral / preference observations

### Retrieval Strategy
1. **Knowledge Graph Search** (NEW): Multi-modal graph traversal with 5 search modes
2. Keyword extraction from query
3. Hybrid retrieval: Graph + Facts + Summaries + Insights
4. Importance + freshness + connection weighting
5. Fallback to recent high-importance if sparse hits

### Smart Features
- **Graph-Based Context**: Entity relationships enrich responses
- Deduplication (summaries, insights, entities)
- Confidence decay + resurfacing
- Pending approval queue (optional)
- Tool-driven fact search (`memory_insight` with graph integration)
- **Token Optimization**: 60-70% reduction via fresh context rebuilding

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
| VERIFY_FACTS_SECOND_PASS | Heavy model verification for low-confidence facts |
| ENABLE_AUTO_TOOLS | Allow TOOL: directives from model |
| ENABLE_PROMPT_CACHING | Provider prompt caching hints |
| ENABLE_EXPERIMENTAL_MODELS | Include experimental registry entries (qwen, kimi) |
| ENABLE_COMPOUND_MODELS | Future agentic compound models |

### Endpoints (Key)
| Endpoint | Description |
|----------|-------------|
| `POST /api/chat` | Chat interaction (optional `X-API-TOKEN`) |
| `POST /api/debug/chat` | Debug endpoint (no auth, returns full context) ⭐ NEW |
| `GET /api/memory` | Dump recent stored memory artifacts (`?detailed=1` for provenance) |
| `GET /api/graph` | Export full knowledge graph (nodes + edges JSON) ⭐ NEW |
| `GET /api/graph/stats` | Graph statistics (entity counts, most connected) ⭐ NEW |
| `GET /api/graph/search` | Search graph with mode parameter ⭐ NEW |
| `GET /graph` | Interactive D3.js graph visualization UI ⭐ NEW |
| `GET /api/routing/recent` | Recent routing & ensemble decisions tail |
| `GET /api/pending_facts` | List pending facts (if approval enabled) |
| `POST /api/pending_facts/<id>/approve\|reject` | Fact moderation |
| `GET /api/models` | Model roles, flags, ensemble config, availability |
| `GET /api/health` | Memory stats + metrics snapshot |
| `POST /api/tts/toggle` | Toggle TTS engine |
| `POST /api/voice/change` | Switch Azure TTS voice |

Security note: Set `API_AUTH_TOKEN` to require token for mutating endpoints.

## 🚧 Roadmap

### ✅ Completed (v0.3 - November 2025)
- **Knowledge Graph Memory System** with NetworkX
  - Automatic entity & relationship extraction
  - 5 search modes (GRAPH_COMPLETION, KEYWORD, RELATIONSHIPS, TEMPORAL, IMPORTANT)
  - Interactive D3.js visualization at `/graph`
  - Multi-modal `memory_insight` tool integration
  - Graph API endpoints (`/api/graph`, `/api/graph/stats`, `/api/graph/search`)
- **Token Optimization** (60-70% reduction: 9-11K → 3-5K tokens)
  - Fresh context rebuilding in synthesis phase
  - Minimal tool prompts during execution
  - Verified via Groq dashboard metrics
- **Compound Model Integration** (Groq built-in tools)
  - Weather, search, calculator built into LLM
  - Simplified tool management (removed 159 lines of custom code)
- **Code Cleanup** (12 files + 260 lines removed)
  - Removed unused Lilith persona (101 lines)
  - Removed redundant weather/search tools (159 lines)
  - Fixed broken task references
- Multi-model routing (fast / smart / heavy / alternates)
- Trio ensemble reasoning (choose_refine)
- Tool skill scoring + gating
- Confidence decay & resurfacing
- Structured fact storage (evidence, justification)
- Second-pass heavy fact verifier
- Provenance memory UI
- `/api/models` & `/api/routing/recent` transparency endpoints

### 🔜 Planned (Next Phase)
- **Semantic Entity Matching**: Embedding-based deduplication ("Python" = "python programming")
- **Graph Export**: Neo4j Cypher, GraphML, JSON-LD formats
- **Graph Analytics**: Centrality measures, community detection, path finding
- **Real-time Graph Updates**: WebSocket support for live visualization
- **Advanced Testing**: Comprehensive pytest suite for knowledge graph
- **Further Token Optimization**: <3K tokens for simple queries via prompt caching
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

- **NetworkX** (graph data structures and algorithms)
- **D3.js** (interactive graph visualization)
- **DeepSeek** (R1 reasoning model)
- **Groq** (high-performance inference + Compound models)
- **Azure** (speech services)
- Early testers & community feedback

---

**💡 Pro Tips:**
- Use `/graph` to visualize how your knowledge graph grows over time
- Try `memory_insight` tool with different search modes (GRAPH_COMPLETION, IMPORTANT)
- Check `/api/graph/stats` to see entity distribution and most connected concepts
- Enable `ENABLE_COMPOUND_MODELS=1` for built-in weather/search/calculator tools
- Monitor token usage via Groq dashboard - should see 3-5K input tokens (down from 9-11K)

For detailed knowledge graph documentation, see [KNOWLEDGE_GRAPH.md](KNOWLEDGE_GRAPH.md) (coming soon).

Feel free to open issues for feature requests, routing anomalies, or memory governance improvements.