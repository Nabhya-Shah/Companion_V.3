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
GROQ_VISION_API_KEY = os.getenv("GROQ_VISION_API_KEY", GROQ_API_KEY)  # Falls back to main key

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
# MODEL CONFIGURATION - Simplified 4-Model Architecture
# ============================================================================
PRIMARY_MODEL = "openai/gpt-oss-120b"  # Best model for everything
TOOLS_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # Native tool calling
VISION_MODEL = "meta-llama/llama-4-maverick-17b-128e-instruct"  # Vision tasks
COMPOUND_MODEL = "compound-beta"  # Web, weather, calculations

# Model capabilities reference (for documentation)
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
    "compound-beta": {
        "description": "Built-in web search, weather, calculations",
        "context_window": 128000,
        "compound": True,
    },
}

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
    elif task in ('web_search', 'weather', 'calculate', 'compound'):
        model = COMPOUND_MODEL
    else:
        # Everything else uses PRIMARY_MODEL (chat, summary, facts, insight, memory, reasoning)
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
ENABLE_COMPOUND = True
ENABLE_AUTO_TOOLS = True  # Auto-detect when tools are needed
ENABLE_STRUCTURED_FACTS = False  # Use structured outputs for fact extraction

# Model roles mapping (for legacy compatibility)
MODEL_ROLES = {
    "chat": PRIMARY_MODEL,
    "tools": TOOLS_MODEL,
    "vision": VISION_MODEL,
    "compound": COMPOUND_MODEL,
    "memory": PRIMARY_MODEL,
    "summary": PRIMARY_MODEL,
    "facts": PRIMARY_MODEL,
    "insight": PRIMARY_MODEL,
}

# ============================================================================
# COMPOUND DETECTION - What queries should use Groq Compound
# ============================================================================
# Be specific to avoid false positives on casual conversation
COMPOUND_TRIGGERS = [
    # Weather (specific phrases)
    "weather in", "weather like", "temperature in", "forecast for",
    "is it raining", "will it rain", "is it sunny",
    # Search (explicit requests)
    "search for", "look up", "google", "find information",
    # Calculations (explicit)
    "calculate", "compute", "what is", "how much is",
    # Current info (specific)
    "current time", "what time", "current date", "today's date",
    "latest news", "recent news",
]

def should_use_compound(query: str) -> bool:
    """Check if query should use Groq Compound for built-in tools."""
    query_lower = query.lower()
    return any(trigger in query_lower for trigger in COMPOUND_TRIGGERS)

def get_compound_model() -> str:
    """Get the Compound model name."""
    return COMPOUND_MODEL

# ============================================================================
# COMPLEXITY CLASSIFICATION - Simplified (no escalation)
# ============================================================================
# Tool trigger keywords - these should always check tools regardless of length
TOOL_TRIGGERS = [
    "time", "weather", "calculate", "search", "find", "look up",
    "what is", "who is", "where is", "wikipedia", "read", "file",
    "screen", "look at", "pdf", "document",
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
    casual_patterns = ["hi", "hello", "hey", "sup", "yo", "what's up", "how are you", "thanks", "ok", "yeah", "yep", "nope", "lol", "haha"]
    if any(query_lower.strip() == p or query_lower.startswith(p + " ") for p in casual_patterns):
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
