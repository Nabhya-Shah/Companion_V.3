# COMPANION AI v2.0 - CONTEXT TRANSFER DOCUMENT

## PROJECT OVERVIEW
This is an advanced conversational AI companion with persistent memory, built for natural human-like interactions. The user has been developing this over multiple sessions and wants seamless continuity when working with AI assistants.

## CURRENT STATE (Latest Session Completed)

### ✅ MAJOR ACCOMPLISHMENTS
- **Removed Claude dependency** - Now uses DeepSeek R1 exclusively through Groq API
- **Enhanced memory system** - Relevance-based retrieval instead of chronological
- **Fixed memory behavior** - AI uses memory subtly, doesn't force past conversations
- **Created modern GUI** - gui_app.py with thinking toggle and dark theme
- **Standardized AI models** - All tasks use DeepSeek R1 for personality consistency
- **Improved memory threshold** - Lowered from 0.3 to 0.2 to capture more information
- **Fixed database issues** - Resolved ai_insights vs insights table naming conflicts

### 🏗️ ARCHITECTURE
```
Companion-V.2/
├── companion_ai/           # Core AI modules
│   ├── llm_interface.py   # DeepSeek R1 integration & response generation
│   ├── memory.py          # SQLite database operations & memory functions
│   ├── memory_ai.py       # AI-powered memory processing & analysis
│   └── __init__.py
├── data/                  # SQLite database storage
│   └── companion_ai.db    # Persistent memory (profile, summaries, insights)
├── gui_app.py            # Modern GUI (RECOMMENDED - latest)
├── gui.py                # Alternative text interface (older)
├── main.py               # Voice-enabled interface
├── calibrate_mic.py      # Audio calibration utilities
├── list_audio_devices.py # Audio device management
└── test_all_systems.py   # System testing
```

### 🧠 MEMORY SYSTEM DETAILS

**How Memory Works:**
1. **Storage Types:**
   - Profile Facts: Personal info (favorite_color=purple, occupation=developer)
   - Conversation Summaries: Important conversation highlights
   - AI Insights: Observations about user patterns/personality

2. **Retrieval Strategy:**
   - Extracts keywords from current message
   - Searches database for relevant memories containing those keywords
   - Falls back to high-importance recent memories if no matches
   - Gives AI 5 relevant summaries + 8 relevant insights + all profile facts

3. **Memory Behavior Rules:**
   - AI uses memory SUBTLY - informs personality, doesn't drive topics
   - NEVER brings up past conversations unless user explicitly asks
   - Only references memory when user says "remember when..." or similar
   - Acts like a friend who knows you well but doesn't constantly bring up old stories

### 🤖 AI CONFIGURATION

**Current Setup:**
- **Primary Model:** DeepSeek R1 (deepseek-r1-distill-llama-70b) via Groq
- **All Functions:** Use DeepSeek R1 for consistency (conversation, memory processing, analysis)
- **Temperature:** 0.8 (balanced creativity/consistency)
- **Max Tokens:** 1024
- **Memory Threshold:** 0.2 (stores more conversations than before)

**Personality Guidelines:**
- Curious and genuinely interested in learning about the user
- Supportive but not overly enthusiastic
- Slightly witty and can appreciate humor
- Technical when needed, casual when appropriate
- Honest about limitations and uncertainties
- Responds to what user is saying NOW, not what AI thinks they want to hear

### 🔧 TECHNICAL IMPLEMENTATION

**Key Functions:**
- `generate_response()` - Main conversation handler using DeepSeek R1
- `get_relevant_summaries()` - Keyword-based memory retrieval
- `get_relevant_insights()` - Context-aware insight retrieval
- `build_system_prompt()` - Constructs memory-informed prompts

**Database Schema:**
- `user_profile` - Key-value pairs with confidence scores
- `conversation_summaries` - Important conversation highlights
- `ai_insights` - AI-generated user observations
- All tables have relevance_score, timestamp, content_hash for deduplication

**GUI Features:**
- Modern dark theme tkinter interface
- "Show AI Thinking" toggle (shows/hides <think> tags from DeepSeek R1)
- Real-time threaded processing
- Ctrl+Enter to send messages
- Background memory storage

### 🎯 USER PREFERENCES & BEHAVIOR

**What the User Values:**
- Natural conversation flow without forced topics
- Memory that works in background, not showcased
- Technical competence and understanding
- Direct communication without unnecessary verbosity
- AI that responds to current context, not past conversations
- Consistent personality across all interactions

**User's Technical Background:**
- Python programmer (started with Scratch)
- AI/ML developer working on this companion project
- Prefers practical solutions over theoretical explanations
- Values efficiency and clean code
- Has experience with various AI models and APIs

**Conversation Style Preferences:**
- Concise and natural responses
- Technical when needed, casual when appropriate
- Thoughtful follow-up questions when genuinely curious
- No overexplaining or being too formal
- Genuine curiosity and engagement

### 🚧 KNOWN ISSUES & NEXT STEPS

**Ready for Implementation:**
- **Azure TTS Integration** - User has Azure services ready for voice synthesis
- **Memory Search Commands** - "What did I tell you about..." functionality
- **GUI Aesthetic Improvements** - Better visual design
- **Memory Importance Scoring** - Currently rating everything as 0.0 importance

**Potential Issues to Watch:**
- Memory importance scoring might be too conservative
- DeepSeek R1 thinking tags can be verbose (hence the toggle)
- Database connections need proper cleanup (currently handled)
- Error handling for API failures (currently implemented)

### 📋 DEVELOPMENT WORKFLOW

**User's Approach:**
- Iterative development with testing after each major change
- Prefers fixing easiest issues first, then moving to complex ones
- Values clean, organized code structure
- Wants comprehensive documentation for continuity
- Tests functionality thoroughly before moving to next feature

**Communication Style:**
- Direct and efficient
- Appreciates technical explanations
- Likes to understand the "why" behind implementations
- Prefers actionable solutions over general advice
- Values time efficiency in development

### 🔑 CRITICAL CONTEXT

**Memory Behavior is Key:**
The most important aspect is that the AI should use memory SUBTLY. Previous versions were too obvious about referencing past conversations. The current system provides rich memory context but instructs the AI to use it for personality calibration only, not topic driving.

**DeepSeek R1 Integration:**
All AI functions now use DeepSeek R1 for consistency. The thinking process is visible via <think> tags, which can be toggled in the GUI. This provides transparency into the AI's reasoning process.

**File Priority:**
- `gui_app.py` is the MAIN interface (newest, most features)
- `gui.py` is alternative/backup
- `main.py` is for voice features
- Focus development on gui_app.py for best user experience

### 🎯 IMMEDIATE CONTEXT FOR NEW SESSIONS

When user says "continue with what you were doing" or similar:
1. Check what was last being worked on
2. Assume they want to continue development/improvements
3. Focus on practical implementation over explanation
4. Test changes immediately after implementation
5. Be ready to tackle Azure TTS integration (they mentioned having services ready)

**User's Development Style:**
- Likes to see working code quickly
- Prefers incremental improvements
- Values testing and validation
- Wants clean, maintainable solutions
- Appreciates comprehensive documentation

This document should provide complete context for seamless continuation of the Companion AI development project.