# companion_ai/llm/router.py
"""High-level LLM routing — generate_response + streaming wrapper.

Chooses the right model/provider based on complexity, then delegates to
groq_provider or ollama_provider for the actual API call.
"""

import time
import logging

from companion_ai.core import config as core_config
from companion_ai.core import metrics as core_metrics
from companion_ai.core.context_builder import build_system_prompt_with_meta
from companion_ai.core.conversation_logger import log_interaction

from companion_ai.llm.token_tracker import reset_last_request_tokens
from companion_ai.llm.groq_provider import (
    get_groq_client,
    groq_client,
    generate_model_response,
    generate_model_response_streaming,
    generate_model_response_with_tools,
    sanitize_output,
)

logger = logging.getLogger(__name__)

# --- Core Generation Functions ---
# NOTE: Prompt building now handled by companion_ai/core/prompts.py and context_builder.py


def generate_response(user_message: str, memory_context: dict, model: str | None = None, persona: str = "Companion") -> str:
    """Generate response using specified model.

    Uses adaptive single-persona context builder.
    """
    # Reset token counter for this new interaction
    reset_last_request_tokens()

    client = get_groq_client()
    if not client:
        return "I'm offline (LLM client unavailable)."
    try:
        complexity = core_config.classify_complexity(user_message)
        auto_model, routing_meta = core_config.choose_model('chat', complexity=complexity, return_reason=True)
        chosen_model = model or auto_model
        logger.info(f"Using model={chosen_model} persona={persona} complexity={complexity}")

        # Extract recent conversation from memory context if provided
        recent_conv = memory_context.get('recent_conversation', '')

        # Always use V4 context builder
        meta = build_system_prompt_with_meta(
            user_message,
            recent_conv,
            mem0_user_id=memory_context.get('mem0_user_id')
        )
        system_prompt = meta['system_prompt']
        mode = meta['mode']
        memory_meta = meta['memory_meta']

        start_t = time.perf_counter()
        # Initialize tool tracking variables
        first_output = None
        tool_used = None
        tool_result = None

        # Generate response with native function calling
        if first_output is None:
            # V5: Compound removed - 120B has built-in search capabilities

            # OPTIMIZATION: Skip tool checking for casual chat (complexity 0) to save tokens
            # Tool schemas add ~8-10K tokens per request!
            should_check_tools = (
                core_config.ENABLE_AUTO_TOOLS and
                complexity > 0
            )

            if first_output is None and should_check_tools:
                # Use dedicated tool model with parallel tool support
                tool_model = core_config.get_tool_executor()
                # IMPORTANT: Don't pass full conversation history to tool execution
                # Only use it for final synthesis to save massive tokens
                first_output, tool_used, tool_result = generate_model_response_with_tools(
                    user_message, system_prompt, tool_model, conversation_model=chosen_model,
                    memory_context=memory_context  # Pass for synthesis phase
                )
                if tool_used:
                    core_metrics.record_tool(tool_used, success=True, blocked=False, decision_type='native_function_call')
                final_output = first_output
            elif first_output is None:
                # Tools disabled - just generate normally
                logger.info("Tools skipped (casual chat), generating normal response")
                first_output = generate_model_response(user_message, system_prompt, chosen_model)
                final_output = first_output
                logger.info(f"Generated response length: {len(first_output) if first_output else 0}")
        else:
            final_output = first_output

        output = final_output
        latency_ms = (time.perf_counter() - start_t) * 1000.0
        try:
            log_interaction(
                user_message,
                output,
                mode,
                system_prompt,
                memory_meta,
                model=chosen_model,
                complexity=complexity,
                routing=routing_meta,
                latency_ms=round(latency_ms, 2),
                tool_used=tool_used,
                tool_result_len=len(tool_result) if tool_result else None,
                tool_blocked=True if (tool_used and '(Suppressed' in final_output) else False
            )
        except Exception as log_err:
            logger.debug(f"Logging failed: {log_err}")
        return output
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        return "Encountered an internal error generating a response."


def generate_response_streaming(user_message: str, memory_context: dict, model: str | None = None, persona: str = "Companion"):
    """Streaming version of generate_response.

    Yields chunks of text as they're generated.
    For tool calls, runs tools first (non-streaming) then streams final synthesis.
    """
    # Reset token counter for this new interaction
    reset_last_request_tokens()

    if not groq_client:
        yield "I'm offline (LLM client unavailable)."
        return

    try:
        complexity = core_config.classify_complexity(user_message)
        auto_model, _ = core_config.choose_model('chat', complexity=complexity, return_reason=True)
        chosen_model = model or auto_model

        recent_conv = memory_context.get('recent_conversation', '')

        # Always use V4 context builder
        meta = build_system_prompt_with_meta(
            user_message,
            recent_conv,
            mem0_user_id=memory_context.get('mem0_user_id')
        )
        system_prompt = meta['system_prompt']

        # Check if we need tools (non-streaming for tool execution)
        should_check_tools = (
            core_config.ENABLE_AUTO_TOOLS and
            complexity > 0
        )

        # V5: Compound streaming removed - 120B has built-in search

        if should_check_tools:
            # Tool query - run tools first, then stream synthesis
            tool_model = core_config.get_tool_executor()
            result, tool_used, tool_result = generate_model_response_with_tools(
                user_message, system_prompt, tool_model, conversation_model=chosen_model,
                memory_context=memory_context
            )
            if tool_used:
                # Already have final synthesized result from tool flow
                for word in result.split(' '):
                    yield word + ' '
                return

        # Simple query - stream directly
        for chunk in generate_model_response_streaming(user_message, system_prompt, chosen_model):
            yield chunk

    except Exception as e:
        logger.error(f"Streaming generation failed: {e}")
        yield "Encountered an error generating a response."
