# companion_ai/llm/token_tracker.py
"""Global token-usage accounting for all LLM calls (Groq + Ollama)."""

import logging

logger = logging.getLogger(__name__)

# ============================================================================
# TOKEN LOGGING
# ============================================================================
_token_stats = {
    'total_input': 0,
    'total_output': 0,
    'requests': 0,
    'by_model': {}
}

# Track tokens for the most recent request/interaction
_last_request_tokens = {
    'input': 0,
    'output': 0,
    'total': 0,
    'models': [],
    'steps': []  # Per-step breakdown: [{name, model, input, output, ms}]
}


def reset_last_request_tokens():
    """Reset the token counter for the current request."""
    global _last_request_tokens
    _last_request_tokens = {
        'input': 0,
        'output': 0,
        'total': 0,
        'models': [],
        'source': 'unknown',  # 'groq', 'local', or 'mixed'
        'steps': []  # Per-step breakdown
    }


def get_last_token_usage() -> dict:
    """Get token usage for the last request."""
    return _last_request_tokens.copy()


def log_tokens_step(step_name: str, model: str, input_tokens: int, output_tokens: int, duration_ms: int = 0):
    """Log a single pipeline step with timing.

    Args:
        step_name: e.g., 'orchestrator', 'memory_loop', 'tool_loop', 'synthesis'
        model: Model used for this step
        input_tokens: Input tokens for this step
        output_tokens: Output tokens for this step
        duration_ms: Time taken in milliseconds
    """
    step = {
        'name': step_name,
        'model': model,
        'input': input_tokens,
        'output': output_tokens,
        'total': input_tokens + output_tokens,
        'ms': duration_ms
    }
    _last_request_tokens['steps'].append(step)

    # Also update totals via standard log_tokens
    log_tokens(model, input_tokens, output_tokens, step_name)


def log_tokens(model: str, input_tokens: int, output_tokens: int, context: str = ""):
    """Log token usage for a request."""
    from companion_ai.core import config as core_config

    # Update global stats
    _token_stats['total_input'] += input_tokens
    _token_stats['total_output'] += output_tokens
    _token_stats['requests'] += 1

    if model not in _token_stats['by_model']:
        _token_stats['by_model'][model] = {'input': 0, 'output': 0, 'count': 0}
    _token_stats['by_model'][model]['input'] += input_tokens
    _token_stats['by_model'][model]['output'] += output_tokens
    _token_stats['by_model'][model]['count'] += 1

    # Update last request stats
    _last_request_tokens['input'] += input_tokens
    _last_request_tokens['output'] += output_tokens
    _last_request_tokens['total'] += (input_tokens + output_tokens)
    if model not in _last_request_tokens['models']:
        _last_request_tokens['models'].append(model)

    # Determine source:
    # - Ollama models: have ":" but no "/" (e.g. "qwen2.5:32b")
    # - vLLM models: start with "Qwen/" or contain LOCAL_HEAVY_MODEL pattern
    # - Groq/cloud: contain "llama-" or "gpt-" or other cloud patterns
    is_local = model and (
        (":" in model and "/" not in model) or  # Ollama format
        model.startswith("Qwen/") or  # vLLM Qwen models
        model == core_config.LOCAL_HEAVY_MODEL  # Exact match to configured local model
    )
    current_source = _last_request_tokens.get('source', 'unknown')

    if current_source == 'unknown':
        _last_request_tokens['source'] = 'local' if is_local else 'groq'
    elif (current_source == 'groq' and is_local) or (current_source == 'local' and not is_local):
        _last_request_tokens['source'] = 'mixed'

    total = input_tokens + output_tokens
    logger.info(f"TOKENS [{model}] in={input_tokens} out={output_tokens} total={total} | {context}")

    # Record to daily budget tracker
    try:
        from companion_ai.services.token_budget import record_tokens
        record_tokens(model, total)
    except Exception as e:
        logger.debug(f"Token budget recording failed: {e}")


def get_token_stats() -> dict:
    """Get current token statistics."""
    return _token_stats.copy()


def reset_token_stats():
    """Reset token statistics."""
    global _token_stats
    _token_stats = {'total_input': 0, 'total_output': 0, 'requests': 0, 'by_model': {}}
