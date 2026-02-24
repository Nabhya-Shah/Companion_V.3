# companion_ai/llm/__init__.py
"""LLM subsystem — token tracking, Groq/Ollama providers, routing, memory extraction.

All public symbols are re-exported here so that ``from companion_ai.llm import X``
works for any X that used to live in ``companion_ai.llm_interface``.
"""

# --- Token tracking ---
from companion_ai.llm.token_tracker import (
    reset_last_request_tokens,
    get_last_token_usage,
    log_tokens_step,
    log_tokens,
    get_token_stats,
    reset_token_stats,
)

# --- Groq provider ---
from companion_ai.llm.groq_provider import (
    sanitize_output,
    get_groq_client,
    groq_client,
    groq_tool_client,
    groq_memory_client,
    generate_model_response_with_tools,
    generate_model_response,
    generate_model_response_streaming,
    generate_groq_response,
)

# --- Ollama provider ---
from companion_ai.llm.ollama_provider import (
    get_embedding,
    get_embeddings_batch,
    generate_local_response,
    OLLAMA_URL,
    OLLAMA_TEXT_MODEL,
    OLLAMA_VISION_MODEL,
    OLLAMA_EMBED_MODEL,
    OLLAMA_CODE_MODEL,
)

# --- Router (high-level) ---
from companion_ai.llm.router import (
    generate_response,
    generate_response_streaming,
)

# --- Memory extraction ---
from companion_ai.llm.memory_extraction import (
    generate_summary,
    extract_profile_facts,
    generate_insight,
)

__all__ = [
    # token_tracker
    "reset_last_request_tokens",
    "get_last_token_usage",
    "log_tokens_step",
    "log_tokens",
    "get_token_stats",
    "reset_token_stats",
    # groq_provider
    "sanitize_output",
    "get_groq_client",
    "groq_client",
    "groq_tool_client",
    "groq_memory_client",
    "generate_model_response_with_tools",
    "generate_model_response",
    "generate_model_response_streaming",
    "generate_groq_response",
    # ollama_provider
    "get_embedding",
    "get_embeddings_batch",
    "generate_local_response",
    "OLLAMA_URL",
    "OLLAMA_TEXT_MODEL",
    "OLLAMA_VISION_MODEL",
    "OLLAMA_EMBED_MODEL",
    "OLLAMA_CODE_MODEL",
    # router
    "generate_response",
    "generate_response_streaming",
    # memory_extraction
    "generate_summary",
    "extract_profile_facts",
    "generate_insight",
]
