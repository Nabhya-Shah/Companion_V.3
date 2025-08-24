# Companion AI (Adaptive Companion – Phase 0)

An advanced AI companion system with authentic personalities, emotional intelligence, and persistent memory. Features both modern web portal and desktop interfaces with voice integration.

## 🌟 Key Features

### 🧠 **Intelligent Memory System**
- **Persistent Memory**: Remembers conversations, preferences, and insights across sessions
- **Smart Storage**: Importance-weighted memory with automatic cleanup
- **Contextual Awareness**: Uses memory subtly to inform responses without being pushy
- **Session Logging**: Automatic conversation logs for review

### 💬 **Adaptive Single Persona**
- Unified adaptive persona (Companion) that shifts between informational and conversational modes.
- Mode selection currently heuristic (Phase 0) – future: semantic & emotional signals.
- Persona definition split into YAML fragments under `prompts/personas/`.
- **Emotional Intelligence**: Genuine emotions that respond to conversation context
- **Playful & Caring**: Mischievous personality with tsundere elements
- **Adaptive Responses**: Reads the room and matches your energy naturally
- **Evolving Bond**: Grows closer through shared experiences

### 🖥️ **Modern Copilot-Style Interface**
- **Clean Design**: GitHub Copilot-inspired dark theme
- **Quick Actions**: One-click conversation starters and tools
- **Responsive Layout**: Adapts to different window sizes
- **Keyboard Shortcuts**: Enter to send, Ctrl+N to clear, Escape to focus input

### 🎤 **Azure TTS Integration**
- **High-Quality Voices**: Phoebe and Ava Dragon HD Latest voices
- **Natural Speech**: Mood-based voice adjustments and natural pacing
- **Smart Text Processing**: Handles abbreviations and emotional delivery
- **Voice Controls**: Easy toggle and voice selection

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- Groq API key (free tier available)
- Optional: Azure Speech Services for voice features

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

3. **Set up environment variables**
   Copy `.env.example` to `.env` (DO NOT COMMIT `.env`) then fill values:
   ```env
   GROQ_API_KEY=your_groq_api_key
   GROQ_MEMORY_API_KEY=your_second_groq_key_optional
   AZURE_SPEECH_KEY=optional_azure_key
   AZURE_SPEECH_REGION=optional_region
   API_AUTH_TOKEN=optional_secret_for_web
   ```

4. **Run the application**
   ```bash
   # Web Portal (Recommended)
   python web_companion.py
   
   # Desktop GUI
   python copilot_gui.py
   
   # Memory Viewer Utility
   python scripts/view_memory.py
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
- **Automatic**: Stores important conversations and insights
- **Subtle**: Uses memory to inform personality, not drive topics
- **Contextual**: Retrieves relevant memories based on current conversation
- **Respectful**: Only references past conversations when you bring them up

## 🏗️ Architecture

```
Companion_V.3/
├── companion_ai/            # Core AI modules
│   ├── core/               # Config, context building, logging
│   ├── llm_interface.py    # Groq chat + persona logic
│   ├── memory.py           # SQLite memory store
│   ├── memory_ai.py        # (Optional) advanced memory ops
│   ├── tools.py            # Tool registry (time, calc, search stub)
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
- **Profile Facts**: Personal information and preferences
- **Conversation Summaries**: Important conversation highlights
- **Insights**: AI-generated observations about user patterns

### Retrieval Strategy
1. **Keyword Extraction**: Identifies relevant terms from current message
2. **Relevance Search**: Finds memories containing those keywords
3. **Importance Weighting**: Prioritizes high-relevance memories
4. **Fallback**: Uses recent high-importance memories if no matches

### Smart Features
- **Deduplication**: Prevents storing similar information multiple times
- **Aging**: Gradually reduces relevance of old, unused memories
- **Consolidation**: Merges similar memories to reduce redundancy
- **Cleanup**: Automatically removes very old, low-relevance data

## 🔧 Configuration & Security

Never commit secrets: `.env`, `data/companion_ai.db`, exported memory files, or logs. `.gitignore` already excludes these; review before pushing if you add new sensitive assets.

### Memory Settings
- **Importance Threshold**: 0.2 (stores more conversations)
- **Summary Limit**: 5 most relevant summaries
- **Insight Limit**: 8 most relevant insights
- **Cleanup Frequency**: Automatic on low importance

### AI Settings (Phase 0 Defaults)
- Conversation Model: `llama-3.1-8b-instant` (Groq)
- Memory Fast Model: same model (optionally separate key)
- Reasoning (reserved): `deepseek-r1-distill-llama-70b` (Groq, optional)
- Temperature: 0.8 (conversation), 0.3 (memory analysis)
- Max Tokens: 1024

## 🚧 Upcoming Features Roadmap
Phase 1: Tool abstraction (calc, memory_query) & unified agent core
Phase 2: Semantic embeddings + hybrid retrieval
Phase 3: Streaming tokens + partial TTS + barge-in
Phase 4: Vision (image caption & analysis)
Phase 5: Device control (permissioned tool calls) + audit logs
Phase 6: Observability (metrics/logs), Docker packaging

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📝 License

MIT License (see `LICENSE`).

## 🙏 Acknowledgments

- **DeepSeek** for the excellent R1 reasoning model
- **Groq** for fast, reliable API access
- **Azure** for speech services integration
- **Community** for feedback and suggestions