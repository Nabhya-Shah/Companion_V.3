"""
Simplified Configuration for Companion AI v0.3

4-Model Architecture:
- PRIMARY (120B): Main chat, reasoning, everything 
- TOOLS (Scout): Native function calling
- VISION (Maverick): Image analysis (separate API key)
- COMPOUND: Web search, weather, calculations
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================================
# API KEYS
# ============================================================================
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_TOOL_API_KEY = os.getenv("GROQ_TOOL_API_KEY")  # Dedicated key for tool planner
GROQ_VISION_API_KEY = os.getenv("GROQ_VISION_API_KEY", GROQ_API_KEY)  # Falls back to main key

# Key Rotation Support
# Load additional keys if present (GROQ_API_KEY_2, GROQ_API_KEY_3, etc.)
GROQ_API_KEYS = [GROQ_API_KEY] if GROQ_API_KEY else []
for i in range(2, 10):
    key = os.getenv(f"GROQ_API_KEY_{i}")
    if key:
        GROQ_API_KEYS.append(key)

# External service keys
SERPER_API_KEY = os.getenv("SERPER_API_KEY")  # For custom web search if needed

# Security
API_AUTH_TOKEN = os.getenv("API_AUTH_TOKEN")  # Protects write endpoints

def require_auth(token: str) -> bool:
    """Check if token is valid. Returns True if auth disabled or token matches."""
    if not API_AUTH_TOKEN:
        return True  # No auth configured = allow all
    return token == API_AUTH_TOKEN

# ============================================================================
# MODEL CONFIGURATION - V4 Architecture
# ============================================================================
# V4 Philosophy: 120B decides, fast models execute
# - PRIMARY: Main personality, synthesis, decisions
# - TOOLS: Native function calling (Scout for now, 8B planned)
# - VISION: Image analysis only
# - COMPOUND: Web/weather fast path

PRIMARY_MODEL = "openai/gpt-oss-120b"  # Decisions, synthesis, personality
TOOLS_MODEL = "llama-3.1-8b-instant"  # Planner: Uses cached prompt to decide tools
TOOLS_MODEL_FAST = "llama-3.1-8b-instant"  # Backup / Fast execution if needed
VISION_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"  # Vision tasks (Maverick)

# Feature flags
USE_FAST_TOOL_EXECUTOR = True
USE_LOCAL_TOOLS = os.getenv("USE_LOCAL_TOOLS", "1").strip().lower() in {"1", "true", "yes", "on"}  # Default ON to save Groq tokens
LOCAL_TOOLS_MODEL = os.getenv("LOCAL_TOOLS_MODEL", "llama3.2:latest")  # Fast local model for tool execution

# Model capabilities reference (for documentation)
# - 120B: 128k context, high intelligence, expensive
# - 8B: 8k context, fast, cheap, good for tools
# - Compound: Built-in tools (web/calc) - DISABLED in favor of native tools
MODEL_INFO = {
    "openai/gpt-oss-120b": {
        "description": "Primary model - handles all chat, reasoning, analysis",
        "context_window": 131072,
        "tool_use": False,  # Use Scout for tools
    },
    "meta-llama/llama-4-scout-17b-16e-instruct": {
        "description": "Native function calling with tools",
        "context_window": 131072,
        "tool_use": True,
    },
    "meta-llama/llama-4-maverick-17b-128e-instruct": {
        "description": "Vision model for image analysis",
        "context_window": 131072,
        "vision": True,
    },
    "llama-3.1-8b-instant": {
        "description": "Fast tool executor - 560 tps, cheap",
        "context_window": 131072,
        "tool_use": True,
    },
}


def get_tool_executor() -> str:
    """Get the appropriate model for tool execution.
    
    Returns:
        - Local Ollama model if USE_LOCAL_TOOLS=1 (saves Groq tokens!)
        - Groq 8B model otherwise
    """
    if USE_LOCAL_TOOLS:
        return LOCAL_TOOLS_MODEL  # Local Ollama - free!
    if USE_FAST_TOOL_EXECUTOR:
        return TOOLS_MODEL_FAST
    return TOOLS_MODEL


# ============================================================================
# SIMPLE MODEL SELECTION
# ============================================================================
def choose_model(task: str = 'chat', complexity: int = 1, importance: float = 0.5, return_reason: bool = False):
    """
    Simple model selection - returns PRIMARY_MODEL for almost everything.
    
    Args:
        task: Task type ('chat', 'tools', 'vision', 'summary', 'facts', 'insight')
        complexity: 0-2 (not used for escalation anymore)
        importance: 0-1 (not used for escalation anymore)
        return_reason: If True, return (model, routing_meta) tuple
    
    Returns:
        model name, or (model, routing_meta) if return_reason=True
    """
    # Simple task-based routing
    if task in ('tools', 'function_calling'):
        model = TOOLS_MODEL
    elif task in ('vision', 'image', 'screen'):
        model = VISION_MODEL
    # V5: compound/web_search now use PRIMARY_MODEL (120B has built-in search)
    else:
        # Everything else uses PRIMARY_MODEL (chat, summary, facts, insight, memory, reasoning, web_search)
        model = PRIMARY_MODEL
    
    if return_reason:
        routing_meta = {
            'task': task,
            'complexity': complexity,
            'model': model,
            'routing': 'simple_task_based'
        }
        return model, routing_meta
    
    return model


def get_model_for_task(task: str) -> str:
    """Get the appropriate model for a specific task type."""
    return choose_model(task=task)


# ============================================================================
# MEMORY CONFIGURATION
# ============================================================================
MEMORY_SEARCH_LIMIT = 10
MEMORY_RELEVANCE_THRESHOLD = 0.5
MEMORY_GRAPH_ENABLED = True
MEMORY_AUTO_EXTRACT = True
IMPORTANCE_MIN_STORE = 0.3  # Minimum importance score to store in memory

# Graph search modes
GRAPH_SEARCH_MODES = [
    "GRAPH_COMPLETION",
    "KEYWORD", 
    "RELATIONSHIPS",
    "TEMPORAL",
    "IMPORTANT",
]

# ============================================================================
# MEM0 CONFIGURATION
# ============================================================================
# Feature flag: Use Mem0 for memory instead of SQLite + NetworkX
USE_MEM0 = True  # Enabled for V4 testing

# Mem0 settings
MEM0_USER_ID = "default"  # Default user ID for single-user mode
MEM0_MAX_RELEVANT = 10  # Max auto-retrieved memories per request (Increased for better recall)
MEM0_MODEL = "llama-3.1-8b-instant"  # Fast model for memory operations

# ============================================================================
# CONTEXT BUILDING
# ============================================================================
MAX_CONTEXT_TOKENS = 8000
MAX_MEMORY_CONTEXT_TOKENS = 2000
MAX_GRAPH_CONTEXT_TOKENS = 1500
RECENT_TURNS_IN_CONTEXT = 10

# ============================================================================
# CONVERSATION SETTINGS
# ============================================================================
DEFAULT_TEMPERATURE = 0.7
MAX_RESPONSE_TOKENS = 4096
STREAM_RESPONSES = True

# ============================================================================
# TTS CONFIGURATION
# ============================================================================
TTS_ENABLED = os.getenv("TTS_ENABLED", "false").lower() == "true"
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-JennyNeural")
TTS_RATE = os.getenv("TTS_RATE", "+0%")

# ============================================================================
# LOGGING
# ============================================================================
LOG_CONVERSATIONS = True
LOG_METRICS = True
LOG_TOOL_CALLS = True
LOG_DIR = "data/logs"
METRICS_FILE = "data/logs/metrics_state.json"
PERSONA_DIR = "prompts/personas"  # Directory containing persona YAML files

# ============================================================================
# WEB SERVER
# ============================================================================
WEB_HOST = "127.0.0.1"
WEB_PORT = 5000
WEB_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# ============================================================================
# FEATURE FLAGS (Simplified)
# ============================================================================
ENABLE_KNOWLEDGE_GRAPH = True
ENABLE_FACT_EXTRACTION = True
ENABLE_TOOL_CALLING = True
ENABLE_VISION = True
ENABLE_COMPOUND = False  # Disabled: User prefers native tool calling
ENABLE_AUTO_TOOLS = True  # Auto-detect when tools are needed
ENABLE_STRUCTURED_FACTS = True  # Use structured outputs for fact extraction
ENABLE_GROQ_BUILTINS = True  # Allow 120B built-in tools (web/code/browse) alongside custom tools
ENABLE_COMPUTER_USE = True   # Enable ComputerAgent (PyAutoGUI + Vision)

# Model roles mapping (V4 architecture)
MODEL_ROLES = {
    "primary": PRIMARY_MODEL,      # Decisions, synthesis, personality  
    "chat": PRIMARY_MODEL,         # Casual conversation
    "tools": TOOLS_MODEL,          # Tool execution (Scout for now; Planner uses 120B)
    "tools_fast": TOOLS_MODEL_FAST,  # Future: pure execution
    "vision": VISION_MODEL,        # Image analysis
    "compound": "DISABLED",        # Explicitly disabled
    "memory": PRIMARY_MODEL,       # Memory operations
    "summary": PRIMARY_MODEL,      # Summarization
    "facts": PRIMARY_MODEL,        # Fact extraction
    "insight": PRIMARY_MODEL,      # Analysis/insight
}

# Feature flag: Use 8B for tool execution instead of Scout
# Set to True to enable V4 tool routing (120B decides, 8B executes)
# USE_FAST_TOOL_EXECUTOR = False  # REMOVED DUPLICATE DEFINITION

# V5: Compound disabled - 120B has built-in search

# ============================================================================
# COMPLEXITY CLASSIFICATION - Simplified (no escalation)
# ============================================================================
# Tool trigger keywords - these should always check tools regardless of length
TOOL_TRIGGERS = [
    "time", "weather", "calculate", "search", "find", "look up",
    "what is", "who is", "where is", "wikipedia", "read", "file",
    "screen", "look at", "pdf", "document",
    "open", "launch", "click", "type", "scroll", "press",
]

def needs_tools(query: str) -> bool:
    """Check if query likely needs tool access."""
    query_lower = query.lower()
    return any(trigger in query_lower for trigger in TOOL_TRIGGERS)

def classify_complexity(query: str) -> int:
    """
    Classify query complexity (0-2).
    This is simplified - no longer used for model escalation.
    0 = casual chat (no tools needed)
    1 = normal query (may need tools)
    2 = complex/analytical
    """
    query_lower = query.lower()
    
    # Tool triggers always get complexity >= 1 (so tools are checked)
    if needs_tools(query_lower):
        return 1
    
    # Casual indicators
    # Normalize punctuation for better matching
    clean_query = query_lower.replace(',', ' ').replace('.', ' ').replace('!', ' ').strip()
    casual_patterns = ["hi", "hello", "hey", "sup", "yo", "what's up", "how are you", "thanks", "ok", "yeah", "yep", "nope", "lol", "haha", "test", "testing"]
    
    # Check for exact matches or starts-with
    if any(clean_query == p or clean_query.startswith(p + " ") for p in casual_patterns):
        return 0
        
    # Check for "test message" specifically
    if "test message" in query_lower or "verify the server" in query_lower:
        return 0
        
    if len(query) < 20:
        return 0
    
    # Complex indicators
    complex_patterns = ["explain", "analyze", "compare", "evaluate", "synthesize", "critique", "implement", "design", "architecture", "algorithm"]
    if any(p in query_lower for p in complex_patterns):
        return 2
    
    return 1

# ============================================================================
# DEPRECATED - Kept for backward compatibility, will be removed
# ============================================================================
# These are no longer used but kept to prevent import errors
REASONING_MODEL = PRIMARY_MODEL  # Deprecated: use PRIMARY_MODEL
HEAVY_MODEL = PRIMARY_MODEL  # Deprecated: use PRIMARY_MODEL
MEMORY_DEEP_MODEL = PRIMARY_MODEL  # Deprecated: use PRIMARY_MODEL
FAST_MODEL = PRIMARY_MODEL  # Deprecated: use PRIMARY_MODEL

# Old feature flags - all disabled
ENABLE_ENSEMBLE = False
HEAVY_MEMORY = False
AGGRESSIVE_ESCALATION = False
ALWAYS_HEAVY_CHAT = False
ENABLE_ENSEMBLE_FOR_MEMORY = False
