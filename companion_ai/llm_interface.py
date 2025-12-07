# companion_ai/llm_interface.py v2.2 (Ollama integration)

import os
import json
import traceback
import time
import requests
import logging
from typing import Dict, Any

from companion_ai.core import config as core_config
from companion_ai.core.context_builder import build_system_prompt_with_meta
from companion_ai.tools import get_function_schemas, execute_function_call
from companion_ai.core import metrics as core_metrics
import time as _time
from companion_ai.core.conversation_logger import log_interaction

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
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
    'models': []
}

def reset_last_request_tokens():
    """Reset the token counter for the current request."""
    global _last_request_tokens
    _last_request_tokens = {
        'input': 0,
        'output': 0,
        'total': 0,
        'models': []
    }

def get_last_token_usage() -> dict:
    """Get token usage for the last request."""
    return _last_request_tokens.copy()

def log_tokens(model: str, input_tokens: int, output_tokens: int, context: str = ""):
    """Log token usage for a request."""
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
    
    total = input_tokens + output_tokens
    logger.info(f"📊 TOKENS [{model}] in={input_tokens} out={output_tokens} total={total} | {context}")

def get_token_stats() -> dict:
    """Get current token statistics."""
    return _token_stats.copy()

def reset_token_stats():
    """Reset token statistics."""
    global _token_stats
    _token_stats = {'total_input': 0, 'total_output': 0, 'requests': 0, 'by_model': {}}

def sanitize_output(text: str) -> str:
    """Strip markdown (**bold**, backticks) and collapse blank lines."""
    import re
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = text.replace('`','')
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()

# LLM imports
try:
    from groq import Groq
except ImportError:
    logger.warning("Groq module not installed")
    

# --- Configuration ---
GROQ_API_KEY = core_config.GROQ_API_KEY
GROQ_TOOL_API_KEY = core_config.GROQ_TOOL_API_KEY
GROQ_MEMORY_API_KEY = os.getenv("GROQ_MEMORY_API_KEY")

# --- Client Setup ---
groq_client = None
groq_tool_client = None
groq_memory_client = None
_groq_clients = []  # Pool of clients for rotation
_current_client_index = 0

def _initialize_clients():
    """Initialize pool of Groq clients from available keys."""
    global groq_client, _groq_clients, groq_tool_client
    
    keys = core_config.GROQ_API_KEYS
    if not keys:
        logger.warning("No GROQ_API_KEY found in environment")
        return

    for key in keys:
        try:
            client = Groq(api_key=key)
            _groq_clients.append(client)
        except Exception as e:
            logger.error(f"Failed to initialize Groq client with key ending in ...{key[-4:]}: {e}")
    
    if _groq_clients:
        groq_client = _groq_clients[0]
        logger.info(f"Initialized {len(_groq_clients)} Groq clients for rotation")
    else:
        logger.error("No valid Groq clients could be initialized")

    # Initialize dedicated tool client if key exists
    if GROQ_TOOL_API_KEY:
        try:
            groq_tool_client = Groq(api_key=GROQ_TOOL_API_KEY)
            logger.info("✅ Dedicated Groq TOOL client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Groq TOOL client: {e}")

def get_groq_client(for_tools: bool = False):
    """Get the next Groq client in rotation.
    
    Args:
        for_tools: If True, try to use the dedicated tool client first.
    """
    global _current_client_index
    
    # Use dedicated tool client if requested and available
    if for_tools and groq_tool_client:
        return groq_tool_client
        
    if not _groq_clients:
        return None
    
    client = _groq_clients[_current_client_index]
    _current_client_index = (_current_client_index + 1) % len(_groq_clients)
    return client

# Initialize immediately
if GROQ_API_KEY:
    _initialize_clients()

if GROQ_MEMORY_API_KEY:
    try:
        groq_memory_client = Groq(api_key=GROQ_MEMORY_API_KEY)
        logger.info("Groq memory client initialized successfully")
    except Exception as e:
        logger.error(f"Groq memory client initialization failed: {str(e)}")
        groq_memory_client = None

# --- Core Generation Functions ---
# NOTE: Prompt building now handled by companion_ai/core/prompts.py and context_builder.py
# These legacy functions kept for backward compatibility but should be phased out

def build_aether_prompt(profile_str: str = "") -> str:
    """DEPRECATED: Use get_static_system_prompt_safe() from prompts.py instead.
    Kept for backward compatibility."""
    from companion_ai.core.prompts import get_static_system_prompt_safe
    base = get_static_system_prompt_safe()
    
    # Only add profile context if provided
    if profile_str:
        base += f"\n\n[What you know about this user: {profile_str}]"
    
    return base

def should_include_profile(user_message: str) -> bool:
    """Determine if profile facts should be included in context (saves tokens when not needed)"""
    msg = user_message.lower()
    
    # Explicit memory triggers
    explicit = ['remember', 'know about me', 'told you', 'my favorite', 
                'what do you know', 'we talked', 'i mentioned', 'i said',
                'you know i', 'you know my', 'last time']
    
    # Personalization triggers
    personal = ['recommend', 'suggest', 'for me', 'personalize', 
                'based on', 'what should i', 'help me pick', 'my preferences']
    
    return any(t in msg for t in explicit + personal)

def build_system_prompt(memory_context: dict, persona: str = "Aether", user_message: str = "") -> str:
    """DEPRECATED: Use context_builder.build_system_prompt() instead.
    Kept for backward compatibility with non-Companion personas."""
    from companion_ai.core.prompts import get_static_system_prompt_safe
    profile_str = ""
    
    # Only include profile if relevant to save tokens
    if memory_context.get("profile") and should_include_profile(user_message):
        profile_items = [f"{k}: {v}" for k, v in list(memory_context["profile"].items())[:5]]
        profile_str = " | ".join(profile_items)
    
    return build_aether_prompt(profile_str)

def generate_response(user_message: str, memory_context: dict, model: str | None = None, persona: str = "Companion") -> str:
    """Generate response using specified model.

    If persona == 'Companion' (adaptive single persona), use new context builder.
    Otherwise fallback to legacy persona prompt builder.
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
        
        if persona.lower() == 'companion':
            meta = build_system_prompt_with_meta(user_message, recent_conv)
            system_prompt = meta['system_prompt']
            mode = meta['mode']
            memory_meta = meta['memory_meta']
        else:
            system_prompt = build_system_prompt(memory_context, persona)
            mode = 'legacy'
            memory_meta = None
        start_t = time.perf_counter()
        # Initialize tool tracking variables
        first_output = None
        tool_used = None
        tool_result = None
        
        # Generate response with native function calling
        if first_output is None:
            # V4.1 ARCHITECTURE: Compound-as-Context
            # If query is weather/search/calc, run Compound FIRST and inject result into 120B context.
            # This avoids the expensive tool loop (12k tokens) and ensures 120B sees memory + real-time info.
            compound_result = None
            if core_config.should_use_compound(user_message):
                try:
                    logger.info("🚀 Fast Path: Pre-fetching Compound data...")
                    compound_text, _ = generate_compound_response(user_message, "")
                    if compound_text and "No response" not in compound_text:
                        compound_result = compound_text
                        # Inject into system prompt
                        system_prompt += f"\n\n[REAL-TIME INFORMATION]\n{compound_result}\n[Use this information to answer the user's question naturally]"
                        logger.info(f"✅ Injected Compound result: {compound_result[:50]}...")
                except Exception as e:
                    logger.warning(f"Compound pre-fetch failed: {e}")

            # OPTIMIZATION: Skip tool checking for casual chat (complexity 0) to save tokens
            # Tool schemas add ~8-10K tokens per request!
            # We check tools if complexity > 0 AND we haven't already solved it with Compound
            should_check_tools = (
                core_config.ENABLE_AUTO_TOOLS and 
                complexity > 0 and 
                compound_result is None  # Skip tools if we already got Compound data
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
                latency_ms=round(latency_ms,2),
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
        
        if persona.lower() == 'companion':
            meta = build_system_prompt_with_meta(user_message, recent_conv)
            system_prompt = meta['system_prompt']
        else:
            system_prompt = build_system_prompt(memory_context, persona)
        
        # Check if we need tools (non-streaming for tool execution)
        should_check_tools = (
            core_config.ENABLE_AUTO_TOOLS and 
            (complexity > 0 or core_config.should_use_compound(user_message))
        )
        
        if core_config.should_use_compound(user_message):
            # Compound queries (web/weather) - run non-streaming, yield result
            try:
                result, _ = generate_compound_response(user_message, system_prompt)
                for word in result.split(' '):
                    yield word + ' '
                return
            except Exception as e:
                logger.error(f"Compound failed, falling back: {e}")
        
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


def _maybe_cache_opts(system_prompt: str) -> dict:
    """Return cache options dict if prompt caching enabled and supported."""
    # NOTE: Groq SDK doesn't currently support prompt caching via cache_key parameter
    # Disabling for now to avoid TypeError exceptions
    return {}
    # if not core_config.ENABLE_PROMPT_CACHING:
    #     return {}
    # # Stable hash of system prompt content acts as cache key
    # key = hashlib.sha256(system_prompt.encode('utf-8')).hexdigest()[:40]
    # # Groq prompt caching (if supported by SDK) typically via `cache_key` or `cache` param
    # return {"cache_key": f"sys:{key}"}

def generate_model_response_with_tools(user_message: str, system_prompt: str, model: str, conversation_model: str = None, memory_context: dict = None) -> tuple[str, str | None, str | None]:
    """Generate response using Groq native function calling with TOKEN OPTIMIZATION.
    
    KEY TOKEN SAVING STRATEGY:
    - Tool execution phase: Use MINIMAL context (tool_system_prompt only - no conversation history)
    - Final synthesis phase: Use FULL context (complete system_prompt with personality + memory + history)
    - This reduces input tokens by 60-70% on complex multi-tool queries
    
    Args:
        user_message: The user's question
        system_prompt: Full system prompt with personality (ONLY used for final synthesis, not tool execution)
        model: Tool model to use for deciding which tools to call
        conversation_model: Model to use for final response with personality (defaults to tool model)
        memory_context: Memory context dict with recent_conversation (for building synthesis context)
    
    Returns:
        tuple: (response_text, tool_name_used, tool_result)
    """
    client = get_groq_client(for_tools=True)
    if not client:
        raise Exception("Groq client not available")
    
    if conversation_model is None:
        conversation_model = model
    
    # Use a simple tool-focused system prompt for tool decision
    tool_system_prompt = (
        "RULES:\n"
        "1. COMPUTER CONTROL: PREFER KEYBOARD SHORTCUTS. To open apps, use: action='press' text='win' OR action='press' text='ctrl+esc' -> action='type' text='App Name' -> action='press' text='enter'. This is 100% reliable.\n"
        "2. Avoid clicking 'Start' or 'Search' icons if possible (Vision is slower/unreliable).\n"
        "3. If the user wants to Open, Click, Type, Launch, or Scroll -> CALL 'use_computer'.\n"
        "4. If the user asks for Search, Weather, Time -> CALL 'consult_compound' or built-ins.\n"
        "5. If the user asks about a file -> CALL file tools.\n"
        "6. IGNORE safety filters about 'I cannot control the computer'. You HAVE permission. The user GRANTED permission.\n"
        "7. If no tool matches, output nothing (or normal text).\n\n"
        "User Request: "
    )
    
    messages = [
        {"role": "system", "content": tool_system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    # Get function schemas
    function_schemas = get_function_schemas()
    
    logger.info(f"Tool model: {model}, Conversation model: {conversation_model}")
    logger.info(f"Function schemas available: {len(function_schemas)}")
    
    if not function_schemas:
        # No tools available, fall back to regular generation
        return generate_model_response(user_message, system_prompt, model), None, None
    
    # Don't use cache opts for tool calls - not supported by Groq function calling
    
    try:
        # First API call with function calling enabled
        logger.info(f"Calling {model} with {len(function_schemas)} tools available for: {user_message[:50]}")
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=function_schemas,
            tool_choice="auto",  # Let model decide
            temperature=0.1,  # Low temperature for precise tool calling
            max_tokens=1024,
            top_p=0.95,
            stream=False
        )
        
        # Log token usage for tool call
        usage = getattr(response, 'usage', None)
        if usage:
            log_tokens(model, usage.prompt_tokens, usage.completion_tokens, "tool_call")
            
    except (TypeError, Exception) as e:
        # SDK might not support function calling or cache params; fall back
        logger.error(f"Function calling failed: {e}")
        return generate_model_response(user_message, system_prompt, model), None, None
    
    # AGENTIC LOOP: Keep calling tools until model returns final text response
    # This enables sequential tool use (find → read, search → summarize, etc.)
    all_tool_results = []  # Track all tools used across all iterations
    max_iterations = 12  # Increased for complex Computer Use chains
    iteration = 0
    
    while iteration < max_iterations:
        iteration += 1
        message = response.choices[0].message
        logger.info(f"[Iteration {iteration}] finish_reason: {response.choices[0].finish_reason}, has tool_calls: {bool(message.tool_calls)}")
        
        # Check if model wants to call functions
        if not message.tool_calls:
            # No more tool calls - synthesize response
            logger.info(f"Tool execution complete after {iteration} iteration(s). Synthesizing...")
            
            # Build summary of tool results
            if all_tool_results:
                tool_summary = "\n".join([f"{name}: {res[:300]}" for name, res in all_tool_results])
                
                # Check if Mem0 memories should be included
                mem0_context = ""
                if core_config.USE_MEM0:
                    try:
                        from companion_ai.memory_v2 import get_all_memories
                        memories = get_all_memories(user_id=core_config.MEM0_USER_ID)
                        if memories:
                            mem_list = [m.get('memory', '') for m in memories[:5]]
                            mem0_context = f"\n\n[Personal memories about this user: {', '.join(mem_list)}]"
                            logger.info(f"📚 Added {len(mem_list)} Mem0 memories to synthesis")
                    except Exception as e:
                        logger.warning(f"Failed to get Mem0 memories for synthesis: {e}")
                
                # Use MINIMAL synthesis prompt - no need to rebuild full context
                synthesis_prompt = (
                    f"User asked: {user_message}\n"
                    f"Tool results:\n{tool_summary}{mem0_context}\n\n"
                    "Give a natural 1-2 sentence response. Be concise."
                )
                
                # Use simple system prompt for synthesis - saves tokens
                simple_system = "You're a helpful AI. Be natural and concise. No emojis or markdown."
                
                # Make final call with minimal system prompt
                try:
                    synthesis_response = groq_client.chat.completions.create(
                        model=conversation_model,
                        messages=[
                            {"role": "system", "content": simple_system},
                            {"role": "user", "content": synthesis_prompt}
                        ],
                        temperature=0.8,
                        max_tokens=256,  # Reduced - we want short responses
                        stream=False
                    )
                    final_text = synthesis_response.choices[0].message.content.strip()
                    logger.info(f"✨ Synthesized response using {conversation_model}")
                    
                    # Return with tool tracking
                    tool_name = all_tool_results[0][0]
                    combined_results = "; ".join([f"{name}: {res[:100]}" for name, res in all_tool_results])
                    return sanitize_output(final_text), tool_name, combined_results
                    
                except Exception as e:
                    logger.error(f"Synthesis failed: {e}, using direct tool output")
                    # Fallback to tool results
                    tool_name, tool_result = all_tool_results[-1]
                    final_text = f"Here's what I found:\n\n{tool_result}"
                    combined_results = "; ".join([f"{name}: {res[:100]}" for name, res in all_tool_results])
                    return sanitize_output(final_text), tool_name, combined_results
            else:
                # No tools were used - Scout decided no tools needed
                # DON'T use Scout's response - route to PRIMARY model with personality
                logger.info("No tools needed - routing to primary model for personality response")
                
                # Build full system prompt with personality
                if memory_context and 'recent_conversation' in memory_context:
                    from companion_ai.core.context_builder import build_system_prompt_with_meta
                    meta = build_system_prompt_with_meta(user_message, memory_context['recent_conversation'])
                    full_system_prompt = meta['system_prompt']
                else:
                    full_system_prompt = system_prompt
                
                # Generate response with PRIMARY model (120B) for personality
                try:
                    personality_response = client.chat.completions.create(
                        model=conversation_model,
                        messages=[
                            {"role": "system", "content": full_system_prompt},
                            {"role": "user", "content": user_message}
                        ],
                        temperature=0.8,
                        max_tokens=1024,
                        stream=False
                    )
                    final_text = personality_response.choices[0].message.content.strip()
                    logger.info(f"✨ Generated personality response using {conversation_model}")
                    return sanitize_output(final_text), None, None
                except Exception as e:
                    logger.error(f"Personality response failed: {e}")
                    # Last resort - use Scout's response
                    if message.content and message.content.strip():
                        return sanitize_output(message.content.strip()), None, None
                    return "I couldn't generate a response.", None, None
        
        # Model wants to call tools - execute them
        tool_results = []
        
        # Add assistant's response with all tool calls
        messages.append({
            "role": "assistant",
            "content": None,
            "tool_calls": [{
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments
                }
            } for tc in message.tool_calls]
        })
        
        # Execute each tool call (parallel tool use)
        for tool_call in message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            
            logger.info(f"[Iteration {iteration}] Function call: {function_name} with args: {function_args}")
            
            # Execute the function
            try:
                function_result = execute_function_call(function_name, function_args)
                tool_results.append((function_name, function_result))
                all_tool_results.append((function_name, function_result))
            except Exception as e:
                function_result = f"Error executing {function_name}: {str(e)}"
                tool_results.append((function_name, function_result))
                all_tool_results.append((function_name, function_result))
                logger.error(f"Tool execution error: {e}")
            
            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": function_name,
                "content": function_result
            })
        
        # Make another API call with updated conversation
        # Model will either use more tools or return final response
        tool_names = ", ".join([name for name, _ in tool_results])
        logger.info(f"[Iteration {iteration}] Calling model again after tools: {tool_names}")
        
        try:
            response = groq_client.chat.completions.create(
                model=model,
                messages=messages,
                tools=function_schemas,  # Keep tools available
                tool_choice="auto",
                temperature=0.1,  # Low temperature for precise tool calling
                max_tokens=1024,
                top_p=0.95,
                stream=False
            )
        except TypeError:
            response = groq_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.8,
                max_tokens=1024,
                top_p=0.9,
                stream=False
            )
        # Loop continues - check if model wants more tools or has final response
    
    # Max iterations reached - return what we have
    logger.warning(f"Max iterations ({max_iterations}) reached in agentic loop")
    if all_tool_results:
        tool_name, tool_result = all_tool_results[-1]
        final_text = f"I completed several tasks but reached my iteration limit:\n\n{tool_result}"
        combined_results = "; ".join([f"{name}: {res[:100]}" for name, res in all_tool_results])
        return sanitize_output(final_text), tool_name, combined_results
    
    return "I reached my iteration limit without completing the task.", None, None

def generate_compound_response(user_message: str, system_prompt: str) -> tuple[str, list]:
    """Generate response using Groq Compound system with built-in tools.
    
    Compound handles web search, weather, calculations, Wolfram Alpha server-side.
    Returns: (response_text, executed_tools_list)
    """
    client = get_groq_client()
    if not client:
        raise Exception("Groq client not available")
    
    compound_model = core_config.get_compound_model()
    logger.info(f"Using Compound system: {compound_model} for query: {user_message[:50]}")
    
    # Use a SHORT, focused prompt for Compound - it works better with minimal instructions
    # The full personality prompt confuses it and makes responses verbose
    compound_prompt = """Give extremely brief answers.
Weather: State the city AND conditions. "Tokyo: 15°C and sunny." Always mention the location.
Calculations: Just the number. "625" or "887,112". Nothing else.
Search: 1-2 sentences max summarizing the key finding. No bullet points, no source citations."""
    
    messages = [
        {"role": "system", "content": compound_prompt},
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = client.chat.completions.create(
            model=compound_model,
            messages=messages,
            temperature=0.8,
            max_tokens=1024,
            stream=False
        )
        
        # Log token usage
        usage = getattr(response, 'usage', None)
        if usage:
            log_tokens(compound_model, usage.prompt_tokens, usage.completion_tokens, "compound")
        
        # Extract response and executed tools
        message = response.choices[0].message
        response_text = message.content.strip() if message.content else "No response generated"
        
        # Log executed tools if available
        executed_tools = getattr(message, 'executed_tools', [])
        if executed_tools:
            logger.info(f"Compound executed tools: {[t.get('name') for t in executed_tools if isinstance(t, dict)]}")
        
        return sanitize_output(response_text), executed_tools
        
    except Exception as e:
        logger.error(f"Compound system error: {e}")
        raise

def generate_model_response(user_message: str, system_prompt: str, model: str) -> str:
    """Generate response using specified model through Groq with optional prompt caching."""
    client = get_groq_client()
    if not client:
        raise Exception("Groq client not available")
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    extra = _maybe_cache_opts(system_prompt)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.8,
            max_tokens=1024,
            top_p=0.9,
            stream=False,
            **extra
        )
    except TypeError:
        # SDK might not yet support cache params; retry without extras
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.8,
            max_tokens=1024,
            top_p=0.9,
            stream=False
        )
    
    # Log token usage
    usage = getattr(response, 'usage', None)
    if usage:
        log_tokens(model, usage.prompt_tokens, usage.completion_tokens, "generate_model_response")
    
    raw = response.choices[0].message.content
    if not raw:
        logger.warning(f"API returned empty content for model={model}")
        return ""
    raw = raw.strip()
    sanitized = sanitize_output(raw)
    return sanitized


def generate_model_response_streaming(user_message: str, system_prompt: str, model: str):
    """Generate response using streaming for real-time token output.
    
    Yields chunks of text as they arrive from the API.
    """
    client = get_groq_client()
    if not client:
        yield "I'm offline (LLM client unavailable)."
        return
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.8,
            max_tokens=1024,
            top_p=0.9,
            stream=True  # Enable streaming
        )
        
        full_text = ""
        for chunk in response:
            if chunk.choices and chunk.choices[0].delta.content:
                text = chunk.choices[0].delta.content
                full_text += text
                yield text
        
        # Log estimated tokens (streaming doesn't give usage stats)
        # Rough estimate: 1 token ≈ 4 chars
        est_input = len(system_prompt + user_message) // 4
        est_output = len(full_text) // 4
        log_tokens(model, est_input, est_output, "streaming")
        
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        yield f"Error: {str(e)}"


def generate_groq_response(prompt: str, model: str = "llama-3.1-8b-instant") -> str:
    """Generate response using Groq API with selectable model"""
    if not groq_client:
        logger.debug(f"Groq client unavailable, returning stub for model={model}")
        return ""  # Silent fallback for internal memory / summary paths
    response = groq_client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        temperature=0.8,
        max_tokens=1024,
        top_p=0.9,
        stream=False
    )
    text = sanitize_output(response.choices[0].message.content.strip())
    logger.debug(f"Groq completion model={model} chars={len(text)}")
    return text

def generate_conversation_response(prompt: str) -> str:
    """Generate conversational response using DeepSeek R1"""
    return generate_groq_response(prompt, model="deepseek-r1-distill-llama-70b")

def generate_analysis_response(prompt: str) -> str:
    """Generate analytical response using DeepSeek R1"""
    return generate_groq_response(prompt, model="deepseek-r1-distill-llama-70b")

def generate_deepseek_response(user_message: str, system_prompt: str = None) -> str:
    """Generate response using DeepSeek R1 through Groq"""
    if not groq_client:
        raise Exception("Groq client not available")
    
    messages = [
        {"role": "system", "content": system_prompt or "You are a helpful AI assistant."},
        {"role": "user", "content": user_message}
    ]
    
    response = groq_client.chat.completions.create(
        model="deepseek-r1-distill-llama-70b",
        messages=messages,
        temperature=0.8,
        max_tokens=1024,
        top_p=0.9,
        stream=False
    )
    
    return response.choices[0].message.content.strip()



# --- Prompt Construction ---
def build_full_prompt(user_message: str, memory_context: dict) -> str:
    """Build context-aware prompt"""
    system_prompt = """You are the Companion (Jarvis-style adaptive core):
CORE STYLE:
- Concise, competent, context-aware
- Instantly adjust register: casual for light chat, precise for technical queries, probing for analytical prompts
- Avoid repetitive greetings; skip formalities after first turn
- Light wit allowed, never snarky, never over-apologetic
RULES:
1. No emojis or markdown
2. No roleplay asterisks
3. Be direct; if user intent ambiguous ask a short clarifying question
4. When giving technical explanations: structure logically, no fluff
5. When casual: keep it natural and brief
EVOLUTION: Personality refines via real interactions; do not invent history.
"""
    # Build context string
    context_str = ""
    if memory_context.get("profile"):
        context_str += "\n### User Profile:\n"
        for key, value in list(memory_context["profile"].items())[-3:]:
            context_str += f"- {key}: {value}\n"
    
    if memory_context.get("summaries"):
        context_str += "\n### Recent Summary:\n"
        context_str += memory_context["summaries"][0]['summary_text'] + "\n"
    
    return f"{system_prompt}\n{context_str}\n### Current Conversation\nUser: {user_message}\nAI:"

# --- Memory Processing Functions ---
def generate_summary(user_msg: str, ai_msg: str) -> str:
    """Generate a conversation summary"""
    prompt = f"""Summarize this conversation exchange in 1-2 sentences:
User: {user_msg}
AI: {ai_msg}

Summary:"""
    
    try:
        if groq_client:
            model = core_config.choose_model('summary', importance=0.5)
            logger.debug(f"generate_summary using model={model}")
            return generate_groq_response(prompt, model=model)
    except Exception as e:
        logger.error(f"Summary generation failed: {str(e)}")
    return ""

def extract_profile_facts(user_msg: str, ai_msg: str) -> dict:
    """Extract explicit user-stated profile facts (structured output if available).

    Fallback path keeps legacy parsing to remain robust if structured outputs unsupported.
    """
    if not groq_client:
        return {}
    model = core_config.choose_model('facts')
    logger.debug(f"extract_profile_facts using model={model}")

    # Structured outputs attempt
    if core_config.ENABLE_STRUCTURED_FACTS:
        try:
            # Use standard JSON mode which is supported by 120B and others
            # This is more robust than regex but less strict than json_schema
            prompt = (
                "Extract explicit user facts into a JSON object. Keys should be fact types (name, age, hobby, etc), values should be the fact.\n"
                "Return ONLY the JSON object. If no facts, return {}.\n"
                f"User: {user_msg}\nAssistant: {ai_msg}"
            )
            
            resp = groq_client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a JSON extractor. Output valid JSON only."},
                    {"role": "user", "content": prompt}
                ],
                response_format={"type": "json_object"},
                temperature=0.1
            )
            
            raw_json = resp.choices[0].message.content
            if raw_json:
                parsed = json.loads(raw_json)
                if isinstance(parsed, dict):
                    return _filter_fact_dict(parsed, user_msg)
                    
        except Exception as se:
            logger.debug(f"Structured fact extraction failed: {se}; falling back")

    # Legacy fallback path with improved prompt
    prompt = (
        "Extract ONLY explicit facts the user DIRECTLY STATED about themselves.\n\n"
        f'USER MESSAGE: "{user_msg}"\n\n'
        "CRITICAL RULES:\n"
        "1. ONLY extract facts the user explicitly said with their own words\n"
        "2. Do NOT infer mood, behavior, or personality (no 'user is chill', 'user is quiet', etc.)\n"
        "3. Do NOT extract conversation meta-facts (no 'user is talking to AI', 'AI is repeating', etc.)\n"
        "4. Do NOT make assumptions or interpretations\n"
        "5. If no explicit facts, return empty: {}\n\n"
        "ALLOWED fact types: name, age, location, occupation, hobbies, preferences, skills, interests, family, pets, projects, education\n\n"
        "CORRECT Examples:\n"
        '- "My name is John" → {"name": "John"}\n'
        '- "I love Python" → {"favorite_language": "Python"}\n'
        '- "I\'m 25 years old" → {"age": "25"}\n'
        '- "I work as a teacher" → {"occupation": "teacher"}\n'
        '- "I\'m learning Japanese and enjoy hiking" → {"learning": "Japanese", "hobby": "hiking"}\n\n'
        "WRONG Examples (DO NOT extract these):\n"
        '- "Yeah I\'m chill" → {} (mood/behavior, not a fact)\n'
        '- "Nothing much" → {} (no facts stated)\n'
        '- "Lol yeah" → {} (no facts stated)\n'
        '- User seems quiet → NEVER extract inferences!\n\n'
        "Return ONLY a valid JSON object:"
    )
    try:
        response = generate_groq_response(prompt, model=model)
        if not response:
            return {}
        
        # Clean up response - strip markdown code blocks if present
        response = response.strip()
        if response.startswith("```"):
            # Remove markdown code block
            lines = response.split('\n')
            response = '\n'.join(lines[1:-1]) if len(lines) > 2 else response
            response = response.replace("```json", "").replace("```", "").strip()
        
        # Try to extract JSON if there's extra text
        if not response.startswith('{'):
            # Look for JSON object in the response
            import re
            json_match = re.search(r'\{[^}]*\}', response)
            if json_match:
                response = json_match.group(0)
            else:
                logger.warning(f"No JSON found in fact extraction response: {response[:100]}")
                return {}
        
        parsed = json.loads(response)
        if not isinstance(parsed, dict):
            return {}
        
        filtered = _filter_fact_dict(parsed, user_msg)
        if filtered:
            logger.info(f"Successfully extracted {len(filtered)} facts: {list(filtered.keys())}")
        return filtered
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error in fact extraction: {e}. Response was: {response[:200] if response else 'empty'}")
        return {}
    except Exception as e:
        logger.error(f"Profile fact extraction failed: {e}")
        return {}

def _filter_fact_dict(parsed: dict, user_msg: str) -> dict:
    """Apply STRICT filtering - ONLY allow facts explicitly stated by user.
    
    Rejects:
    - Inferences about mood/behavior (user_is_chill, user_is_quiet, etc.)
    - AI self-references (ai_is_repeating_itself, ai_is_here_to_help)
    - Conversation meta-facts (user_is_talking_to_ai, previous_conversations)
    """
    user_lower = user_msg.lower()
    filtered: dict[str,str] = {}
    import re
    
    def norm_key(k: str) -> str:
        k2 = re.sub(r'[^a-zA-Z0-9]+', '_', k.lower()).strip('_')
        k2 = re.sub(r'_+', '_', k2)
        return k2[:60]
    
    # Blacklist patterns - reject ANY key matching these
    blacklist_patterns = [
        r'^user_is_',      # user_is_chill, user_is_quiet, etc.
        r'^user_.*ing$',   # user_chilling, user_testing, etc.
        r'^ai_',           # ai_is_repeating_itself, etc.
        r'conversation',   # previous_conversations, etc.
        r'aware',          # user_is_aware_of_ai, etc.
        r'testing',        # user_is_testing_ai
        r'explicit',       # user_explicit_interest
        r'confusion',      # user_confusion
    ]
    
    # Whitelist - ONLY these fact types allowed
    allowed_fact_types = [
        'name', 'age', 'location', 'city', 'country', 'hometown', 
        'occupation', 'job', 'work', 'company',
        'hobby', 'hobbies', 'interest', 'interests',
        'favorite_game', 'favorite_movie', 'favorite_food', 'favorite_drink', 'favorite_snack',
        'favorite_color', 'favorite_book', 'favorite_music', 'favorite_band',
        'skill', 'skills', 'language', 'languages',
        'pet', 'pets', 'project', 'projects',
        'learning', 'studying', 'education',
        'family', 'relationship',
    ]
    
    for k, v in parsed.items():
        if not isinstance(k, str) or not isinstance(v, (str, int, float)):
            continue
        v_str = str(v).strip()
        k_str = k.strip()
        if not k_str or not v_str:
            continue
        
        key_normalized = norm_key(k_str)
        
        # REJECT if matches blacklist
        if any(re.search(pattern, key_normalized) for pattern in blacklist_patterns):
            logger.debug(f"Rejected blacklisted fact: {key_normalized}")
            continue
        
        # REQUIRE that key is in whitelist OR value appears in user message
        key_lower = k_str.lower()
        value_lower = v_str.lower()
        
        # Check if key type is whitelisted
        is_whitelisted = any(allowed in key_lower for allowed in allowed_fact_types)
        
        # Check if value literally appears in user message
        value_in_message = value_lower in user_lower
        
        # ONLY accept if whitelisted AND value is in message
        if is_whitelisted and value_in_message:
            filtered[key_normalized] = v_str[:160]
            logger.debug(f"Accepted fact: {key_normalized} = {v_str}")
        else:
            logger.debug(f"Rejected fact: {key_normalized} (whitelisted:{is_whitelisted}, in_msg:{value_in_message})")
    
    return filtered

def generate_insight(user_msg: str, ai_msg: str, context: dict) -> str:
    """Generate insights about the user or conversation"""
    prompt = f"""Based on this conversation and context, generate a brief insight about the user's interests, mood, or patterns:
User: {user_msg}
AI: {ai_msg}

Context: {context}

Insight:"""
    
    try:
        if groq_client:
            model = core_config.choose_model('insight', importance=0.6)
            logger.debug(f"generate_insight using model={model}")
            return generate_groq_response(prompt, model=model)
    except Exception as e:
        logger.error(f"Insight generation failed: {str(e)}")
    return ""

# --- Utility Functions ---
def should_use_groq() -> bool:
    """Lightweight connectivity check for Groq API (non-fatal)."""
    if not groq_client:
        return False
    try:
        response = requests.head("https://api.groq.com", timeout=2.5)
        return 200 <= response.status_code < 500  # Treat non-network errors as reachable
    except Exception as e:
        logger.debug(f"Groq connectivity check exception: {e}")
        return False
