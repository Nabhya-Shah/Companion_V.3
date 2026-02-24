#!/usr/bin/env python3
"""
Web-based Companion AI Interface
"""

from flask import Flask, render_template, request, jsonify, make_response, Response, stream_with_context
import threading
import webbrowser
import time
import logging
from datetime import datetime
import os
import uuid
from typing import Dict, List, Tuple

from companion_ai.llm_interface import generate_response, get_token_stats, reset_token_stats, get_last_token_usage
from companion_ai.conversation_manager import ConversationSession
from companion_ai.core import config as core_config
from companion_ai.memory import sqlite_backend as sqlite_memory
from companion_ai.memory.sqlite_backend import (
    get_all_profile_facts, upsert_profile_fact, delete_profile_fact,
    clear_all_memory, list_profile_facts_detailed, list_pending_profile_facts,
    approve_profile_fact, reject_profile_fact, get_latest_summary, get_latest_insights,
    search_memory, get_memory_stats,
    bulk_sync_memory_quality_from_mem0, get_memory_quality_map,
    delete_memory_quality_entry, upsert_memory_quality_entry,
)
from companion_ai.memory import mem0_backend as memory_v2
from companion_ai.services.tts import tts_manager
from companion_ai.agents.vision import vision_manager
from companion_ai.tools import (
    run_tool,
    list_tools,
    list_plugins,
    get_plugin_catalog,
    get_plugin_policy_state,
    set_workspace_plugin_policy,
)
from companion_ai.core import metrics
from companion_ai.services import jobs as job_manager_module
import json, glob

# Configure logging with both console and file output
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
LOG_FILE = os.path.join(DATA_DIR, 'web_server.log')
os.makedirs(DATA_DIR, exist_ok=True)

# Clear log file on server restart (best-effort).
# On Windows, a log watcher may hold the file open; don't crash in that case.
if os.path.exists(LOG_FILE):
    try:
        os.remove(LOG_FILE)
    except OSError:
        pass

# Create formatters and handlers
console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Console handler (for terminal output)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(console_formatter)

# File handler (for persistent logs) - 'w' mode overwrites if file exists, UTF-8 encoding for emoji/arrows
# Use append mode to avoid Windows file-lock conflicts with log watchers.
file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
file_handler.setLevel(logging.DEBUG)
file_handler.setFormatter(file_formatter)

# Configure root logger with force=True to override any existing config
logging.basicConfig(level=logging.DEBUG, handlers=[console_handler, file_handler], force=True)
logger = logging.getLogger(__name__)

# Force flush after every log message
import sys
sys.stdout.flush()
sys.stderr.flush()

logger.info("=" * 70)
logger.info("🚀 COMPANION AI WEB SERVER STARTING")
logger.info(f"📝 Logs: {LOG_FILE}")
logger.info("=" * 70)

# Start background job worker
job_manager_module.start_worker()

app = Flask(__name__)

conversation_history = []
conversation_session = ConversationSession()
history_version = 0
history_condition = threading.Condition()
sse_sequence = 0
sse_counters = {'history.updated': 0, 'job.updated': 0}
sse_last_event_ts = None
_session_lock = threading.Lock()
_session_histories: Dict[str, List[dict]] = {}
_session_managers: Dict[str, ConversationSession] = {}
_scope_migration_done: set[str] = set()

_STRICT_TOKEN_PATH_PREFIXES = (
    '/api/debug',
    '/api/shutdown',
    '/api/memory/clear',
    '/api/brain/reindex',
    '/api/brain/upload',
    '/api/brain/auto-write',
    '/api/tokens/reset',
)


def _is_local_request() -> bool:
    """Allow localhost-only API access when no auth token is configured."""
    remote = (request.remote_addr or "").strip()
    return remote in {"127.0.0.1", "::1", "localhost"}


def _extract_api_token(payload: dict | None = None) -> str | None:
    return (
        request.headers.get('X-API-TOKEN')
        or request.args.get('token')
        or ((payload or {}).get('token') if isinstance(payload, dict) else None)
        or request.cookies.get('api_token')
    )


def _sanitize_scope_value(value: str | None, default: str) -> str:
    if not value:
        return default
    cleaned = ''.join(ch for ch in str(value) if ch.isalnum() or ch in ('-', '_'))
    return cleaned[:64] if cleaned else default


def _resolve_session_key(payload: dict | None = None) -> str:
    key = (
        request.headers.get('X-Session-ID')
        or request.args.get('session_id')
        or ((payload or {}).get('session_id') if isinstance(payload, dict) else None)
        or request.cookies.get('companion_session_id')
    )
    return _sanitize_scope_value(key, 'default')


def _resolve_profile_key(payload: dict | None = None) -> str:
    key = (
        request.headers.get('X-Profile-ID')
        or request.args.get('profile_id')
        or ((payload or {}).get('profile_id') if isinstance(payload, dict) else None)
        or request.cookies.get('companion_profile_id')
    )
    return _sanitize_scope_value(key, 'default')


def _resolve_workspace_key(payload: dict | None = None) -> str:
    key = (
        request.headers.get('X-Workspace-ID')
        or request.args.get('workspace_id')
        or ((payload or {}).get('workspace_id') if isinstance(payload, dict) else None)
        or request.cookies.get('companion_workspace_id')
    )
    return _sanitize_scope_value(key, 'default')


def _list_known_workspaces() -> list[str]:
    workspaces = {'default'}
    workspace_root = os.path.join(os.path.dirname(__file__), 'BRAIN', 'workspaces')
    try:
        if os.path.isdir(workspace_root):
            for name in os.listdir(workspace_root):
                full = os.path.join(workspace_root, name)
                if os.path.isdir(full):
                    workspaces.add(_sanitize_scope_value(name, 'default'))
    except Exception:
        pass
    return sorted(workspaces)


def _parse_interval_minutes(data: dict) -> int:
    raw_interval = data.get('interval_minutes')
    if raw_interval not in (None, ''):
        return int(raw_interval)
    cadence = str(data.get('cadence') or '').strip().lower()
    if not cadence:
        return 0
    units = {'m': 1, 'h': 60, 'd': 1440}
    suffix = cadence[-1:]
    if suffix not in units:
        raise ValueError("cadence must end with 'm', 'h', or 'd' (example: 15m)")
    value = int(cadence[:-1])
    return value * units[suffix]


def _mem0_user_id_for_scope(session_key: str, profile_key: str, workspace_key: str = 'default') -> str:
    base = core_config.MEM0_USER_ID or 'default'
    if workspace_key and workspace_key != 'default':
        return f"{base}::w:{workspace_key}::p:{profile_key}::s:{session_key}"
    return f"{base}::p:{profile_key}::s:{session_key}"


def _get_active_session_state(payload: dict | None = None) -> Tuple[str, str, str, List[dict], ConversationSession]:
    session_key = _resolve_session_key(payload)
    profile_key = _resolve_profile_key(payload)
    workspace_key = _resolve_workspace_key(payload)
    mem0_user_id = _mem0_user_id_for_scope(session_key, profile_key, workspace_key)

    with _session_lock:
        history = _session_histories.setdefault(session_key, [])
        manager = _session_managers.setdefault(session_key, ConversationSession())

    return session_key, profile_key, mem0_user_id, history, manager


def _maybe_migrate_legacy_scope(mem0_user_id: str, profile_key: str, session_key: str) -> None:
    """Best-effort one-time migration from legacy single-user Mem0 scope."""
    if not core_config.USE_MEM0:
        return

    # Avoid copying into the default scope itself.
    if profile_key == 'default' and session_key == 'default':
        return

    migration_key = f"{profile_key}:{session_key}"
    if migration_key in _scope_migration_done:
        return

    legacy_user_id = core_config.MEM0_USER_ID
    try:
        scoped = memory_v2.get_all_memories(user_id=mem0_user_id)
        if scoped:
            _scope_migration_done.add(migration_key)
            return

        result = memory_v2.migrate_legacy_memories(
            source_user_id=legacy_user_id,
            target_user_id=mem0_user_id,
            max_items=200,
        )
        logger.info(
            f"Legacy scope migration checked for {migration_key}: {result}"
        )
        _scope_migration_done.add(migration_key)
    except Exception as e:
        logger.warning(f"Legacy scope migration failed for {migration_key}: {e}")


@app.before_request
def enforce_api_security():
    """Security baseline:
    - If API_AUTH_TOKEN is set, all /api/* calls must provide it.
    - If no token is set, only localhost can access /api/*.
    """
    if not request.path.startswith('/api/'):
        return None

    payload = None
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        payload = request.get_json(silent=True) or {}

    token = _extract_api_token(payload)

    # Debug/admin paths always require an explicit token, even on localhost.
    if any(request.path.startswith(prefix) for prefix in _STRICT_TOKEN_PATH_PREFIXES):
        if not core_config.API_AUTH_TOKEN:
            return jsonify({'error': 'Forbidden: configure API_AUTH_TOKEN for debug/admin endpoints'}), 403
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        return None

    if core_config.API_AUTH_TOKEN:
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        return None

    if not _is_local_request():
        logger.warning(f"Blocked non-local API request without API_AUTH_TOKEN: {request.remote_addr} {request.path}")
        return jsonify({'error': 'Forbidden: local access only unless API_AUTH_TOKEN is configured'}), 403

    return None

@app.route('/')
def index():
    resp = make_response(render_template('index.html'))
    if not request.cookies.get('companion_session_id'):
        resp.set_cookie('companion_session_id', uuid.uuid4().hex[:16], httponly=True, samesite='Lax')
    if not request.cookies.get('companion_profile_id'):
        resp.set_cookie('companion_profile_id', 'default', httponly=True, samesite='Lax')
    if not request.cookies.get('companion_workspace_id'):
        resp.set_cookie('companion_workspace_id', 'default', httponly=True, samesite='Lax')
    # If auth token configured, set it as httpOnly cookie for transparent reuse.
    if core_config.API_AUTH_TOKEN:
        # Only set if not already present to avoid rewriting each request
        if not request.cookies.get('api_token'):
            resp.set_cookie('api_token', core_config.API_AUTH_TOKEN, httponly=True, samesite='Lax')
    return resp

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    """Gracefully shutdown the server and trigger persona evolution."""
    data = request.get_json(silent=True) or {}
    token = (request.headers.get('X-API-TOKEN') or data.get('token')
             or request.cookies.get('api_token'))
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401
        
    logger.info("🛑 Shutdown requested. Saving session log and triggering persona evolution...")
    
    # Save session log to brain folder
    try:
        from companion_ai.brain_manager import get_brain
        workspace_key = _resolve_workspace_key(data)
        brain = get_brain(workspace_id=workspace_key)
        
        # Build session summary
        session_date = datetime.now().strftime("%Y-%m-%d")
        session_time = datetime.now().strftime("%H:%M")
        
        # Get conversation summary
        history = conversation_session.conversation_history
        msg_count = len(history)
        
        # Get token stats
        from companion_ai.llm_interface import get_token_stats
        token_stats = get_token_stats()
        total_tokens = token_stats.get('total_input', 0) + token_stats.get('total_output', 0)
        request_count = token_stats.get('requests', 0)
        
        # Build log entry
        log_content = f"# Session Log - {session_date} {session_time}\n\n"
        log_content += f"**Messages:** {msg_count}\n"
        log_content += f"**Total Tokens:** {total_tokens:,} ({request_count} requests)\n\n"
        
        # Add model breakdown
        if token_stats.get('by_model'):
            log_content += "## Token Usage by Model\n\n"
            for model, usage in token_stats['by_model'].items():
                model_total = usage.get('input', 0) + usage.get('output', 0)
                log_content += f"- **{model}**: {model_total:,} tokens ({usage.get('count', 0)} calls)\n"
            log_content += "\n"
        
        if history:
            log_content += "## Conversation Highlights\n\n"
            # Just save last 5 exchanges as summary
            for msg in history[-5:]:
                user_msg = msg.get('user', '')[:100]
                ai_msg = msg.get('ai', '')[:100]
                if user_msg:
                    log_content += f"- **User**: {user_msg}...\n" if len(msg.get('user', '')) > 100 else f"- **User**: {user_msg}\n"
                if ai_msg:
                    log_content += f"- **AI**: {ai_msg}...\n\n" if len(msg.get('ai', '')) > 100 else f"- **AI**: {ai_msg}\n\n"
        
        # Write to logs folder
        log_file = f"logs/session_{session_date}.md"
        brain.write(log_file, log_content + "---\n\n", append=True)
        logger.info(f"📝 Session log saved: {log_file}")
        
    except Exception as e:
        logger.error(f"❌ Failed to save session log: {e}")
    
    # Trigger Persona Evolution (Synchronous to ensure completion)
    try:
        from companion_ai import persona_evolution
        history = conversation_session.conversation_history
        if history:
            persona_evolution.analyze_and_evolve(history)
            logger.info("✅ Persona evolution complete.")
        else:
            logger.info("ℹ️ No conversation history to analyze.")
    except Exception as e:
        logger.error(f"❌ Persona evolution failed during shutdown: {e}")

    # Shutdown Flask
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        # Fallback for production servers or if werkzeug shutdown not available
        import os, signal
        os.kill(os.getpid(), signal.SIGINT)
        return jsonify({'status': 'Shutting down via signal...'})
    
    func()
    
    # Stop job worker
    job_manager_module.stop_worker()
    
    return jsonify({'status': 'Server shutting down...'})

@app.route('/api/jobs/active', methods=['GET'])
def get_active_jobs():
    """Get active and recently completed jobs."""
    token = (request.headers.get('X-API-TOKEN') or request.args.get('token')
             or request.cookies.get('api_token'))
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401
    
    jobs = job_manager_module.get_active_jobs()
    return jsonify({'jobs': jobs})

@app.route('/api/token-budget', methods=['GET'])
def token_budget():
    """Get current token budget status."""
    try:
        from companion_ai.token_budget import get_budget_status, should_auto_save
        status = get_budget_status()
        status['should_auto_save'] = should_auto_save()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Token budget error: {e}")
        return jsonify({'error': str(e), 'used': 0, 'limit': 500000, 'percent': 0}), 500

@app.route('/api/brain/auto-write', methods=['POST'])
def brain_auto_write():
    """Trigger brain auto-write (end of conversation summary)."""
    try:
        token = (request.headers.get('X-API-TOKEN') or request.cookies.get('api_token'))
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        
        from companion_ai.brain_manager import get_brain
        from companion_ai.llm_interface import generate_model_response
        from datetime import date
        
        workspace_key = _resolve_workspace_key()
        brain = get_brain(workspace_id=workspace_key)
        
        # Get conversation history for summary
        history = conversation_session.conversation_history[-10:]  # Last 10 messages
        if not history:
            return jsonify({'success': False, 'reason': 'No conversation history'})
        
        # Build conversation text
        conv_text = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
            for msg in history
        ])
        
        # Generate summary using 120B (smart model)
        summary_prompt = f'''Analyze this conversation and extract:
1. Key topics discussed
2. Any user preferences learned
3. Skills/knowledge demonstrated

Conversation:
{conv_text}

Write a brief summary (max 200 words) for the AI's daily journal.'''
        
        summary = generate_model_response(
            summary_prompt, 
            "You are a summarizer. Be concise.", 
            core_config.PRIMARY_MODEL
        )
        
        # Write to brain folder (local model writes, saving tokens)
        today = str(date.today())
        brain.write(
            f"memories/daily/{today}.md", 
            f"# Daily Summary - {today}\n\n{summary}",
            append=False
        )
        
        logger.info(f"Brain auto-write complete: memories/daily/{today}.md")
        return jsonify({'success': True, 'file': f'memories/daily/{today}.md'})
        
    except Exception as e:
        logger.error(f"Brain auto-write error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/graph')
def graph():
    """Interactive knowledge graph visualization"""
    return render_template('graph.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.json or {}
        session_key, profile_key, mem0_user_id, active_history, active_session = _get_active_session_state(data)
        token = (request.headers.get('X-API-TOKEN') or data.get('token')
                 or request.cookies.get('api_token'))
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        user_message = data.get('message', '').strip()
        persona = data.get('persona', 'Companion')
        tts_enabled = data.get('tts_enabled', False)  # Get TTS preference from client
        # Allow automatic model selection (ensemble will trigger for complex queries)
        # Only use explicit model if provided by user
        model = data.get('model') if 'model' in data else None
        if not user_message:
            return jsonify({'error': 'Empty message'}), 400
        
        # Pass ALL conversation history to session (no limits!)
        # The AI has access to complete conversation + database memories
        if user_message.startswith('!') and ' ' in user_message:
            first, rest = user_message[1:].split(' ', 1)
            tool_result = run_tool(first, rest)
            ai_response = f"[tool:{first}]\n{tool_result}"
        elif user_message.lower().startswith(('look at', 'see this', 'what is on my screen', 'check screen')):
            # Trigger active vision analysis
            logger.info("Triggering active vision analysis from chat")
            vision_result = vision_manager.analyze_current_screen(user_message)
            # Feed the vision result back into the conversation as context
            context_msg = f"[SYSTEM: The user asked you to look at their screen. Here is what you see:\n{vision_result}]"
            # Now generate response based on this visual context
            ai_response, memory_saved = active_session.process_message(
                f"{context_msg}\n\nUser: {user_message}",
                active_history,
                memory_user_id=mem0_user_id,
            )
        else:
            # Use conversation session with FULL conversation history
            # Inject visual context if watcher is enabled
            if vision_manager.watcher_enabled and len(vision_manager.visual_log) > 0:
                # Add a subtle system note with recent visual context
                # We don't want to overwhelm the prompt, just give a hint
                latest = vision_manager.visual_log[-1]['description']
                # We can inject this into the message processing if we modify ConversationSession
                # For now, let's just append it to the user message invisibly? 
                # Better: The ConversationSession should handle context injection.
                # Let's keep it simple for now:
                pass 
            
            ai_response, memory_saved = active_session.process_message(
                user_message,
                active_history,
                memory_user_id=mem0_user_id,
            )
        
        # Guard against empty responses
        if not ai_response or not ai_response.strip():
            logger.warning("Empty AI response received, using fallback")
            ai_response = "I'm here! Sorry, I got a bit stuck there. What were you saying?"
        
        # Remove "Chat:" prefix if present (formatting artifact)
        if ai_response.startswith("Chat:") or ai_response.startswith("CHAT:"):
            ai_response = ai_response[5:].strip()
        
        # Get token usage for this specific request
        from companion_ai.llm_interface import get_last_token_usage
        token_usage = get_last_token_usage()
        
        entry = {
            'user': user_message,
            'ai': ai_response,
            'timestamp': datetime.now().isoformat(),
            'persona': persona,
            'tokens': token_usage
        }
        active_history.append(entry)
        global history_version
        with history_condition:
            history_version += 1
            history_condition.notify_all()
        
        # Auto-process memory every 5 messages to store facts in database
        if len(active_history) % 5 == 0:
            try:
                logger.info(f"Auto-processing memory at {len(active_history)} messages (session={session_key}, profile={profile_key})")
                active_session.process_session_memory()
            except Exception as mem_err:
                logger.warning(f"Memory processing error: {mem_err}")
        
        # TTS: Speak response if enabled by user
        if tts_enabled and tts_manager.is_enabled:
            try:
                tts_manager.speak_text(ai_response, blocking=False)
            except Exception as tts_error:
                logger.warning(f"TTS error: {tts_error}")
        
        return jsonify({
            'response': ai_response, 
            'response': ai_response, 
            'timestamp': entry['timestamp'],
            'tokens': token_usage,
            'memory_saved': memory_saved,
            'session_id': session_key,
            'profile_id': profile_key,
            'workspace_id': _resolve_workspace_key(data),
        })
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/send', methods=['POST'])
def chat_streaming():
    """Streaming chat endpoint - sends response tokens as they arrive."""
    try:
        data = request.json or {}
        session_key, profile_key, mem0_user_id, active_history, active_session = _get_active_session_state(data)
        token = (request.headers.get('X-API-TOKEN') or data.get('token')
                 or request.cookies.get('api_token'))
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        
        user_message = data.get('message', '').strip()
        if not user_message:
            return jsonify({'error': 'Empty message'}), 400
        
        def generate():
            """Generator for streaming response."""
            full_response = ""
            try:
                for chunk in active_session.process_message_streaming(
                    user_message,
                    active_history,
                    memory_user_id=mem0_user_id,
                ):
                    if isinstance(chunk, dict) and chunk.get('type') == 'meta':
                        # Send metadata event
                        yield f"data: {json.dumps({'meta': chunk['data']})}\n\n"
                    elif isinstance(chunk, dict) and chunk.get('type') == 'token_meta':
                        # Send token metadata event with token_steps
                        yield f"data: {json.dumps({'token_meta': chunk['data']})}\n\n"
                    else:
                        full_response += chunk
                        # Send chunk as SSE event
                        yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                
                # Get token usage
                from companion_ai.llm_interface import get_last_token_usage
                token_usage = get_last_token_usage()
                
                # Signal completion and update history
                memory_saved = core_config.USE_MEM0
                
                # Check if TTS enabled in request
                tts_enabled = data.get('tts_enabled', False)
                
                # TTS: Speak response if enabled
                # Allow Groq even if Azure is_enabled is False
                tts_available = tts_manager.is_enabled or getattr(tts_manager, 'provider', 'azure') == 'groq'
                if tts_enabled and tts_available and full_response.strip():
                    try:
                        logger.info(f"🔊 TTS: Speaking response with provider={getattr(tts_manager, 'provider', 'azure')}")
                        # Non-blocking speech
                        tts_manager.speak_text(full_response, blocking=False)
                    except Exception as tts_error:
                        logger.warning(f"TTS error: {tts_error}")

                yield f"data: {json.dumps({'done': True, 'full_response': full_response, 'tokens': token_usage, 'memory_saved': memory_saved})}\n\n"
                
                # Store in history (redundant? No, conversation_session does it, but web_companion updates its own list too?)
                # Wait, conversation_session.conversation_history IS the list web_companion uses?
                # web_companion.py line 75: conversation_session = ConversationSession()
                # conversation_session.conversation_history IS separate from web_companion.py's global conversation_history list (line 74).
                # Wait, line 74: conversation_history = []
                # Line 256: conversation_session.process_message(..., conversation_history)
                
                # Ah, conversation_session keeps its OWN history in self.conversation_history?
                # Let's check conversation_manager.py line 43: self.conversation_history = []
                # But process_message takes full_conversation_history as arg.
                
                # In web_companion, we maintain `conversation_history` global list.
                # conversation_session.process_message_streaming appends to ITS OWN self.conversation_history.
                # So we interpret `web_companion` as needing to update ITS global list too.
                
                entry = {
                    'user': user_message,
                    'ai': full_response,
                    'timestamp': datetime.now().isoformat(),
                    'persona': 'Companion',
                    'tokens': token_usage,
                    # We can't see 'final_metadata' here easily unless we extracted it from the stream loop
                    # But we can assume the frontend received it via 'meta' event.
                    # To store it in web_companion's history, we need to capture it.
                }
                # But wait, how do we get metadata here? 
                # We can store it in a local var during the loop.
                # BUT conversation_session.process_message_streaming ALREADY appended it to valid session history.
                # The issue is web_companion maintains a separate global `conversation_history` list (legacy?).
                
                # Let's skip adding metadata to web_companion's global list for now, 
                # OR capture it in the loop.
                active_history.append(entry)
                
                # Notify SSE listeners of history update
                global history_version
                with history_condition:
                    history_version += 1
                    history_condition.notify_all()
                    
            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
        
        return Response(generate(), mimetype='text/event-stream')
        
    except Exception as e:
        logger.error(f"Chat streaming error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/chat', methods=['POST'])
def debug_chat():
    """
    Debug endpoint for AI agent testing.
    Localhost/token-protected endpoint for AI agent testing.
    Shares conversation_history with main chat endpoint.
    """
    try:
        data = request.json or {}
        session_key, profile_key, mem0_user_id, active_history, active_session = _get_active_session_state(data)
        user_message = data.get('message', '').strip()
        persona = data.get('persona', 'Companion')
        
        if not user_message:
            return jsonify({'error': 'Empty message'}), 400
        
        # Use conversation session with FULL conversation history
        ai_response, memory_saved = active_session.process_message(
            user_message,
            active_history,
            memory_user_id=mem0_user_id,
        )
        
        # Guard against empty responses
        if not ai_response or not ai_response.strip():
            logger.warning("Empty AI response in debug endpoint, using fallback")
            ai_response = "I'm here! Sorry, I got a bit stuck there. What were you saying?"
        
        # Remove "Chat:" prefix if present (formatting artifact)
        if ai_response.startswith("Chat:") or ai_response.startswith("CHAT:"):
            ai_response = ai_response[5:].strip()
        
        # Add to shared conversation history
        entry = {
            'user': user_message,
            'ai': ai_response,
            'timestamp': datetime.now().isoformat(),
            'persona': persona,
            'source': 'debug_api'
        }
        active_history.append(entry)
        global history_version
        with history_condition:
            history_version += 1
            history_condition.notify_all()
        
        # Auto-process memory every 5 messages to store facts in database
        if len(active_history) % 5 == 0:
            try:
                logger.info(f"Auto-processing memory at {len(active_history)} debug messages (session={session_key})")
                active_session.process_session_memory()
            except Exception as mem_err:
                logger.warning(f"Memory processing error: {mem_err}")
        
        # Get token usage
        from companion_ai.llm_interface import get_last_token_usage
        token_usage = get_last_token_usage()
        
        return jsonify({
            'user': user_message,
            'ai': ai_response,
            'timestamp': entry['timestamp'],
            'history_length': len(active_history),
            'tokens': token_usage
        })
        
    except Exception as e:
        logger.error(f"Debug chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/reset', methods=['POST'])
def debug_reset():
    """Clear conversation history and start a fresh ConversationSession (testing only)."""
    try:
        global history_version
        data = request.get_json(silent=True) or {}
        session_key, _, _, active_history, _ = _get_active_session_state(data)
        with _session_lock:
            active_history.clear()
            _session_managers[session_key] = ConversationSession()
        with history_condition:
            history_version += 1
            history_condition.notify_all()
        return jsonify({'reset': True, 'history_length': 0})
    except Exception as e:
        logger.error(f"Debug reset error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/history')
def get_chat_history():
    """Get conversation history for live updates."""
    try:
        _, _, _, active_history, _ = _get_active_session_state()
        return jsonify({
            'history': active_history,
            'count': len(active_history)
        })
    except Exception as e:
        logger.error(f"Get history error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/stream')
def chat_history_stream():
    """Server-sent events stream pushing history updates AND job updates."""
    session_key, _, _, _, _ = _get_active_session_state()

    def event_stream():
        global sse_sequence, sse_last_event_ts
        last_version = -1
        last_job_check = 0
        # Avoid replaying old job completions on reconnect/startup
        notified_jobs = set()
        try:
            existing = job_manager_module.get_active_jobs()
            for job in existing:
                if job.get('status') in ('COMPLETED', 'FAILED'):
                    notified_jobs.add(job.get('id'))
        except Exception as e:
            logger.error(f"Job stream init error: {e}")
        
        while True:
            # 1. Check for Chat Updates
            with history_condition:
                # Wait for notification or timeout (reduced to 1s for job polling)
                if history_version == last_version:
                    history_condition.wait(timeout=1.0)
                
                current_version = history_version
                with _session_lock:
                    snapshot = list(_session_histories.get(session_key, []))
            
            if current_version != last_version:
                # Send history update
                sse_sequence += 1
                sse_counters['history.updated'] = sse_counters.get('history.updated', 0) + 1
                sse_last_event_ts = datetime.now().isoformat()
                payload = json.dumps({
                    'type': 'history',
                    'event': 'history.updated',
                    'seq': sse_sequence,
                    'ts': datetime.now().isoformat(),
                    'payload': {
                        'history': snapshot,
                        'count': len(snapshot),
                    },
                    'history': snapshot,
                    'count': len(snapshot),
                })
                last_version = current_version
                yield f"data: {payload}\n\n"
            
            # 2. Check for Job Updates (every 2 seconds approx)
            now = time.time()
            if now - last_job_check > 2.0:
                last_job_check = now
                try:
                    jobs = job_manager_module.get_active_jobs()
                    for job in jobs:
                        if job['status'] in ('COMPLETED', 'FAILED') and job['id'] not in notified_jobs:
                            # Send job update
                            sse_sequence += 1
                            sse_counters['job.updated'] = sse_counters.get('job.updated', 0) + 1
                            sse_last_event_ts = datetime.now().isoformat()
                            payload = json.dumps({
                                'type': 'job_update',
                                'event': 'job.updated',
                                'seq': sse_sequence,
                                'ts': datetime.now().isoformat(),
                                'payload': {
                                    'job': job,
                                },
                                'job': job,
                            })
                            yield f"data: {payload}\n\n"
                            notified_jobs.add(job['id'])
                except Exception as e:
                    logger.error(f"Job stream error: {e}")
            
            # Keep-alive
            yield ": keep-alive\n\n"

    response = Response(stream_with_context(event_stream()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@app.route('/api/events/diagnostics', methods=['GET'])
def event_diagnostics():
    return jsonify({
        'history_version': history_version,
        'sse_sequence': sse_sequence,
        'counters': dict(sse_counters),
        'last_event_ts': sse_last_event_ts,
    })

@app.route('/api/memory')
def get_memory():
    try:
        detailed = request.args.get('detailed', 'false').lower() in ('1','true','yes')
        session_key, profile_key, mem0_user_id, _, _ = _get_active_session_state()
        _maybe_migrate_legacy_scope(mem0_user_id, profile_key, session_key)
        
        # --- SWITCH TO MEM0 AS PRIMARY SOURCE ---
        if core_config.USE_MEM0:
            try:
                # Fetch all memories from Mem0
                mem0_memories = memory_v2.get_all_memories(user_id=mem0_user_id)
                bulk_sync_memory_quality_from_mem0(mem0_memories, user_scope=mem0_user_id)
                quality_map = get_memory_quality_map(mem0_user_id)
                
                # Convert to format expected by frontend
                # Frontend expects: { key, value, confidence_label, reaffirmations }
                # Mem0 returns: { id, memory, metadata, ... }
                
                profile_detailed = []
                for m in mem0_memories:
                    # Extract text
                    text = m.get('memory', m.get('text', ''))
                    if not text: continue
                    
                    # Extract metadata
                    meta = m.get('metadata') or {}
                    quality = quality_map.get(m.get('id'), {})
                    confidence = quality.get('confidence', 0.70)
                    confidence_label = quality.get('confidence_label')
                    if not confidence_label:
                        confidence_label = 'high' if confidence >= 0.80 else 'medium' if confidence >= 0.50 else 'low'
                    
                    profile_detailed.append({
                        'key': m.get('id'),  # Use ID as key for deletion
                        'value': text,
                        'confidence': confidence,
                        'confidence_label': confidence_label,
                        'reaffirmations': quality.get('reaffirmations', meta.get('frequency', 0)),
                        'source': quality.get('provenance_source', 'mem0'),
                        'contradiction_state': quality.get('contradiction_state', 'none'),
                    })
                
                # Sort by most recent (if created_at exists) or just reverse
                # Mem0 usually returns most relevant or recent. Let's just use as is.
                
                resp = {
                    'profile': {m['key']: m['value'] for m in profile_detailed}, # Simple dict
                    'profile_detailed': profile_detailed,
                    'summaries': [], # Mem0 handles summaries internally or we don't have them separate
                    'insights': [],   # Same
                    'profile_id': profile_key,
                    'workspace_id': _resolve_workspace_key(),
                }
                return jsonify(resp)
                
            except Exception as mem0_err:
                logger.error(f"Failed to fetch Mem0 memories: {mem0_err}")
                # Fallback to SQLite if Mem0 fails? Or just return error?
                # Let's fallback for safety but log it.
        
        # --- FALLBACK TO SQLITE (Legacy) ---
        profile = get_all_profile_facts()
        summaries = get_latest_summary(10)
        insights = get_latest_insights(10)
        resp = {'profile': profile, 'summaries': summaries, 'insights': insights}
        if detailed:
            try:
                resp['profile_detailed'] = list_profile_facts_detailed()
            except Exception as inner:
                logger.warning(f"Detailed profile retrieval failed: {inner}")
        return jsonify(resp)
    except Exception as e:
        logger.error(f"Memory error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pending_facts')
def pending_facts():
    try:
        from companion_ai.core import config as core_config
        if not getattr(core_config, 'ENABLE_FACT_APPROVAL', False):
            return jsonify({'enabled': False, 'pending': []})
        pending = list_pending_profile_facts()
        return jsonify({'enabled': True, 'pending': pending})
    except Exception as e:
        logger.error(f"Pending facts error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pending_facts/<int:pid>/approve', methods=['POST'])
def approve_fact(pid: int):
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        ok = approve_profile_fact(pid)
        return jsonify({'approved': ok})
    except Exception as e:
        logger.error(f"Approve fact error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/pending_facts/<int:pid>/reject', methods=['POST'])
def reject_fact(pid: int):
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        ok = reject_profile_fact(pid)
        return jsonify({'rejected': ok})
    except Exception as e:
        logger.error(f"Reject fact error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/pending_facts/bulk', methods=['POST'])
def bulk_pending_facts_action():
    """Approve or reject multiple pending facts in one request."""
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        data = request.get_json(silent=True) or {}
        action = str(data.get('action') or '').strip().lower()
        ids = data.get('ids')
        if action not in {'approve', 'reject'}:
            return jsonify({'error': "action must be 'approve' or 'reject'"}), 400
        if not isinstance(ids, list) or not ids:
            return jsonify({'error': 'ids must be a non-empty list'}), 400

        ok_ids = []
        failed_ids = []
        for raw_id in ids:
            try:
                pid = int(raw_id)
            except Exception:
                failed_ids.append(raw_id)
                continue

            ok = approve_profile_fact(pid) if action == 'approve' else reject_profile_fact(pid)
            if ok:
                ok_ids.append(pid)
            else:
                failed_ids.append(pid)

        return jsonify({
            'action': action,
            'processed': len(ok_ids),
            'failed': failed_ids,
            'ok_ids': ok_ids,
        })
    except Exception as e:
        logger.error(f"Bulk pending facts error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tools')
def tools():
    return jsonify({'tools': list_tools()})


@app.route('/api/plugins')
def plugins():
    return jsonify({'plugins': list_plugins()})


@app.route('/api/plugins/catalog')
def plugins_catalog():
    return jsonify({'plugins': get_plugin_catalog()})


@app.route('/api/plugins/policy', methods=['GET', 'POST'])
def plugin_policy():
    if request.method == 'GET':
        return jsonify(get_plugin_policy_state())

    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    enabled_plugins = data.get('enabled_plugins')
    if not isinstance(enabled_plugins, list):
        return jsonify({'error': 'enabled_plugins must be a list'}), 400

    try:
        state = set_workspace_plugin_policy(enabled_plugins)
        return jsonify(state)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Plugin policy update error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/context', methods=['GET'])
def api_context():
    """Return active scope context used for memory/brain selection."""
    payload = request.get_json(silent=True) or {}
    session_key = _resolve_session_key(payload)
    profile_key = _resolve_profile_key(payload)
    workspace_key = _resolve_workspace_key(payload)
    mem0_user_id = _mem0_user_id_for_scope(session_key, profile_key, workspace_key)
    return jsonify({
        'session_id': session_key,
        'profile_id': profile_key,
        'workspace_id': workspace_key,
        'mem0_user_id': mem0_user_id,
        'known_workspaces': _list_known_workspaces(),
    })


@app.route('/api/context/switch', methods=['POST'])
def api_context_switch():
    payload = request.get_json(silent=True) or {}
    workspace_key = _resolve_workspace_key(payload)
    profile_key = _resolve_profile_key(payload)
    if bool(payload.get('new_session')):
        session_key = uuid.uuid4().hex[:16]
    else:
        session_key = _resolve_session_key(payload)

    mem0_user_id = _mem0_user_id_for_scope(session_key, profile_key, workspace_key)
    if bool(payload.get('migrate_legacy', False)):
        _maybe_migrate_legacy_scope(mem0_user_id, profile_key, session_key)

    response_payload = {
        'session_id': session_key,
        'profile_id': profile_key,
        'workspace_id': workspace_key,
        'mem0_user_id': mem0_user_id,
        'known_workspaces': _list_known_workspaces(),
        'switched': True,
    }
    resp = make_response(jsonify(response_payload))
    resp.set_cookie('companion_session_id', session_key, httponly=True, samesite='Lax')
    resp.set_cookie('companion_profile_id', profile_key, httponly=True, samesite='Lax')
    resp.set_cookie('companion_workspace_id', workspace_key, httponly=True, samesite='Lax')
    return resp

@app.route('/api/memory/clear', methods=['POST'])
def clear_memory():
    try:
        data = request.get_json(silent=True) or {}
        _, _, mem0_user_id, active_history, active_session = _get_active_session_state(data)
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Clear SQLite memory
        clear_all_memory()
        
        # Clear Mem0 vector memory
        if core_config.USE_MEM0:
            try:
                memory_v2.clear_all_memories(user_id=mem0_user_id)
                # Reset the Mem0 instance to force fresh start
                memory_v2._reset_memory()
                logger.info("Cleared Mem0 vector memory and reset instance")
            except Exception as mem0_err:
                logger.error(f"Failed to clear Mem0: {mem0_err}")

        # Clear active in-memory session state
        active_history.clear()
        with _session_lock:
            for key, mgr in list(_session_managers.items()):
                if mgr is active_session:
                    _session_managers[key] = ConversationSession()
                    break
        
        # Clear Knowledge Graph
        try:
            from companion_ai.memory_graph import clear_graph
            clear_graph()
            logger.info("Cleared Knowledge Graph")
        except Exception as kg_err:
            logger.error(f"Failed to clear Knowledge Graph: {kg_err}")
        
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Clear memory error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/memory/fact/<key>', methods=['DELETE'])
def delete_fact(key: str):
    # Ensure logger is available
    local_logger = logging.getLogger(__name__)
    try:
        _, _, mem0_user_id, _, _ = _get_active_session_state()
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
            
        deleted = False
        
        # 1. Try deleting from Mem0 (Primary)
        if core_config.USE_MEM0:
            try:
                # Try deleting by ID (key is likely a UUID from Mem0)
                mem0_deleted = memory_v2.delete_memory(key)
                if mem0_deleted:
                    deleted = True
                    delete_memory_quality_entry(key, user_scope=mem0_user_id)
                    local_logger.info(f"Deleted Mem0 memory for key: {key}")
                else:
                    # Fallback: Try deleting from SQLite if ID not found in Mem0
                    # (This handles legacy facts or if key was actually a SQLite key)
                    sqlite_deleted = delete_profile_fact(key)
                    if sqlite_deleted:
                        deleted = True
                        local_logger.info(f"Deleted SQLite memory for key: {key}")
                        
            except Exception as mem0_err:
                local_logger.error(f"Failed to delete Mem0 fact: {mem0_err}")
        else:
            # 2. Fallback to SQLite only
            deleted = delete_profile_fact(key)
                
        return jsonify({'deleted': deleted, 'key': key})
    except Exception as e:
        local_logger.error(f"Delete fact error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/memory/fact/<key>', methods=['PUT'])
def update_fact(key: str):
    """Update a memory fact by key."""
    local_logger = logging.getLogger(__name__)
    try:
        payload = request.get_json(silent=True) or {}
        _, _, mem0_user_id, _, _ = _get_active_session_state(payload)
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        
        data = payload
        new_value = data.get('value', '').strip()
        
        if not new_value:
            return jsonify({'error': 'Empty value not allowed'}), 400
        
        updated = False
        
        if core_config.USE_MEM0:
            try:
                # Mem0 update_memory takes memory_id and new data
                updated = memory_v2.update_memory(key, new_value)
                if updated:
                    prior_quality = get_memory_quality_map(mem0_user_id).get(key, {})
                    upsert_memory_quality_entry(
                        memory_id=key,
                        memory_text=new_value,
                        user_scope=mem0_user_id,
                        confidence=prior_quality.get('confidence', 0.70),
                        reaffirmations=prior_quality.get('reaffirmations', 0),
                        contradiction_state=prior_quality.get('contradiction_state', 'none'),
                        provenance_source='mem0',
                        metadata=prior_quality.get('metadata') if isinstance(prior_quality, dict) else None,
                    )
                    local_logger.info(f"Updated Mem0 memory {key}: {new_value[:50]}...")
            except Exception as e:
                local_logger.error(f"Mem0 update error: {e}")
                # Try SQLite fallback
                try:
                    from companion_ai.memory.sqlite_backend import update_profile_fact
                    updated = update_profile_fact(key, new_value)
                except:
                    pass
        
        return jsonify({'updated': updated, 'key': key, 'value': new_value})
    except Exception as e:
        local_logger.error(f"Update fact error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts/toggle', methods=['POST'])
def toggle_tts():
    try:
        token = request.headers.get('X-API-TOKEN')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        tts_manager.is_enabled = not tts_manager.is_enabled
        return jsonify({'enabled': tts_manager.is_enabled})
    except Exception as e:
        logger.error(f"TTS toggle error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts/voices', methods=['GET'])
def get_voices():
    try:
        voices = tts_manager.get_available_voices()
        return jsonify({'voices': voices})
    except Exception as e:
        logger.error(f"Get voices error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts/config', methods=['GET', 'POST'])
def tts_config():
    try:
        if request.method == 'POST':
            data = request.json or {}
            token = request.headers.get('X-API-TOKEN') or data.get('token') or request.cookies.get('api_token')
            if not core_config.require_auth(token):
                return jsonify({'error': 'Unauthorized'}), 401
            
            voice = data.get('voice')
            rate = data.get('rate')
            pitch = data.get('pitch')
            provider = data.get('provider')  # 'azure' or 'groq'
            
            if provider:
                tts_manager.provider = provider
                logger.info(f"🔊 TTS provider set to: {provider}")
            if voice:
                tts_manager.set_voice(voice)
            if rate:
                tts_manager.set_speech_rate(rate)
            if pitch:
                tts_manager.set_speech_pitch(pitch)
                
            return jsonify(tts_manager.get_status())
        else:
            return jsonify(tts_manager.get_status())
    except Exception as e:
        logger.error(f"TTS config error: {e}")
        return jsonify({'error': str(e)}), 500

# --- Vision Endpoints ---

@app.route('/api/vision/toggle', methods=['POST'])
def toggle_vision():
    try:
        token = request.headers.get('X-API-TOKEN')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        
        if vision_manager.watcher_enabled:
            vision_manager.stop_watcher()
        else:
            vision_manager.start_watcher()
            
        return jsonify({'enabled': vision_manager.watcher_enabled})
    except Exception as e:
        logger.error(f"Vision toggle error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vision/status', methods=['GET'])
def vision_status():
    return jsonify({
        'enabled': vision_manager.watcher_enabled,
        'log_count': len(vision_manager.visual_log),
        'last_update': vision_manager.visual_log[-1]['timestamp'] if vision_manager.visual_log else None
    })

# --- Computer Control Endpoints REMOVED ---
# Endpoints removed as part of Agent-S cleanup.
# See companion_ai/agents/computer.py removal.


# --- Loxone Smart Home API ---

@app.route('/api/loxone/rooms', methods=['GET'])
def loxone_rooms():
    """Get all Loxone room statuses for control center UI."""
    import asyncio
    from companion_ai.integrations.loxone import get_room_statuses
    
    try:
        result = asyncio.run(get_room_statuses())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Loxone rooms error: {e}")
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/loxone/health', methods=['GET'])
def loxone_health():
    """Get Loxone health/configuration status for Smart Home modal."""
    import asyncio
    from companion_ai.integrations.loxone import get_health_status

    try:
        result = asyncio.run(get_health_status())
        return jsonify(result)
    except Exception as e:
        logger.error(f"Loxone health error: {e}")
        return jsonify({'success': False, 'configured': False, 'connected': False, 'message': str(e)})

@app.route('/api/loxone/light/<action>', methods=['POST'])
def loxone_light(action):
    """Control lights: action = 'on', 'off', or 'brightness'."""
    import asyncio
    from companion_ai.integrations.loxone import turn_on_lights, turn_off_lights, set_brightness
    
    data = request.get_json() or {}
    room = data.get('room')
    
    try:
        if action == 'on':
            result = asyncio.run(turn_on_lights(room))
        elif action == 'off':
            result = asyncio.run(turn_off_lights(room))
        elif action == 'brightness':
            brightness = data.get('brightness', 100)
            result = asyncio.run(set_brightness(room, brightness))
        else:
            return jsonify({'success': False, 'error': f'Unknown action: {action}'})
        
        return jsonify(result)
    except Exception as e:
        logger.error(f"Loxone light error: {e}")
        return jsonify({'success': False, 'error': str(e)})


# --- File Upload API ---

UPLOAD_DIR = os.path.join(DATA_DIR, 'uploads')
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'docx', 'txt', 'md'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _resolve_uploaded_file_path(file_id: str) -> str | None:
    for ext in ALLOWED_EXTENSIONS:
        candidate = os.path.join(UPLOAD_DIR, f"{file_id}.{ext}")
        if os.path.exists(candidate):
            return candidate
    return None


def _extract_text_from_uploaded_path(file_path: str, max_chars: int = 12000) -> tuple[str, bool]:
    ext = os.path.splitext(file_path)[1].lower()
    content = ''

    try:
        if ext in {'.txt', '.md'}:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        elif ext == '.pdf':
            try:
                import pypdf
                with open(file_path, 'rb') as f:
                    reader = pypdf.PdfReader(f)
                    pages = []
                    for page in reader.pages[:10]:
                        pages.append((page.extract_text() or '').strip())
                    content = '\n\n'.join([p for p in pages if p])
            except Exception:
                content = ''
        elif ext == '.docx':
            try:
                from docx import Document
                doc = Document(file_path)
                content = '\n'.join([p.text for p in doc.paragraphs if p.text.strip()])
            except Exception:
                content = ''
    except Exception:
        content = ''

    content = (content or '').strip()
    if not content:
        return '', False
    if len(content) > max_chars:
        return content[:max_chars], True
    return content, False


def _summarize_text_simple(text: str, max_chars: int = 600) -> str:
    if not text:
        return ''
    cleaned = ' '.join(text.replace('\r', ' ').replace('\n', ' ').split())
    if len(cleaned) <= max_chars:
        return cleaned

    sentence_candidates = cleaned.replace('?', '.').replace('!', '.').split('.')
    out = []
    total = 0
    for raw in sentence_candidates:
        sentence = raw.strip()
        if not sentence:
            continue
        addition = (sentence + '. ')
        if total + len(addition) > max_chars:
            break
        out.append(addition)
        total += len(addition)
        if len(out) >= 4:
            break
    if out:
        return ''.join(out).strip()
    return cleaned[:max_chars].rstrip() + '...'


def _save_uploaded_file(file, analyze_images: bool = True):
    import uuid

    if not file or not file.filename:
        return None, {'success': False, 'error': 'No file selected'}, 400
    if not allowed_file(file.filename):
        return None, {'success': False, 'error': f'File type not allowed. Allowed: {", ".join(sorted(ALLOWED_EXTENSIONS))}'}, 400

    file_id = str(uuid.uuid4())[:8]
    ext = file.filename.rsplit('.', 1)[1].lower()
    safe_filename = f"{file_id}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    file.save(file_path)
    file_size = os.path.getsize(file_path)
    if file_size > MAX_FILE_SIZE:
        os.remove(file_path)
        return None, {'success': False, 'error': 'File too large (max 10MB)'}, 400

    is_image = ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    is_pdf = ext == 'pdf'
    is_doc = ext in {'docx', 'txt'}

    analysis = None
    if analyze_images and is_image:
        try:
            analysis = vision_manager.analyze_image_file(
                file_path,
                prompt="DESCRIBE ONLY - don't solve or interpret. Just describe what you see: text, numbers, objects, layout. If there's math/text, transcribe it exactly. Let someone else solve it."
            )
            logger.info(f"Image analyzed: {file_id} - {analysis[:100]}...")
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")

    payload = {
        'success': True,
        'file_id': file_id,
        'filename': file.filename,
        'type': 'image' if is_image else 'pdf' if is_pdf else 'document' if is_doc else 'file',
        'size': file_size,
        'url': f'/api/upload/{file_id}',
        'analysis': analysis,
    }
    return payload, None, 200

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload a file and optionally analyze it with vision."""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400

    payload, err, status = _save_uploaded_file(request.files['file'], analyze_images=True)
    if err:
        return jsonify(err), status
    return jsonify(payload)


@app.route('/api/upload/batch', methods=['POST'])
def upload_files_batch():
    """Upload multiple files in one request."""
    files = request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]
    if not files:
        return jsonify({'success': False, 'error': 'No files provided'}), 400

    uploaded = []
    errors = []
    for file in files:
        payload, err, status = _save_uploaded_file(file, analyze_images=True)
        if payload:
            uploaded.append(payload)
        else:
            errors.append({
                'filename': getattr(file, 'filename', ''),
                'error': (err or {}).get('error', 'Upload failed'),
                'status': status,
            })

    status_code = 200 if uploaded else 400
    return jsonify({
        'success': bool(uploaded),
        'count': len(uploaded),
        'uploaded': uploaded,
        'errors': errors,
    }), status_code


@app.route('/api/upload/list', methods=['GET'])
def list_uploaded_files():
    """List recently uploaded files with basic metadata."""
    limit = max(1, min(int(request.args.get('limit', 50) or 50), 200))
    rows = []
    for name in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, name)
        if not os.path.isfile(path) or '.' not in name:
            continue
        file_id, ext = name.rsplit('.', 1)
        ext = ext.lower()
        if ext not in ALLOWED_EXTENSIONS:
            continue
        stat = os.stat(path)
        rows.append({
            'file_id': file_id,
            'filename': name,
            'ext': ext,
            'size': stat.st_size,
            'url': f'/api/upload/{file_id}',
            'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
        })
    rows.sort(key=lambda x: x['modified_at'], reverse=True)
    return jsonify({'files': rows[:limit], 'count': min(len(rows), limit)})

@app.route('/api/upload/<file_id>', methods=['GET'])
def get_uploaded_file(file_id):
    """Serve an uploaded file."""
    from flask import send_from_directory
    
    # Find file with any extension
    for ext in ALLOWED_EXTENSIONS:
        filename = f"{file_id}.{ext}"
        filepath = os.path.join(UPLOAD_DIR, filename)
        if os.path.exists(filepath):
            return send_from_directory(UPLOAD_DIR, filename)
    
    return jsonify({'error': 'File not found'}), 404


@app.route('/api/upload/extract', methods=['POST'])
def extract_uploaded_file_text():
    data = request.get_json(silent=True) or {}
    file_id = str(data.get('file_id') or '').strip()
    if not file_id:
        return jsonify({'error': 'file_id is required'}), 400

    max_chars = max(500, min(int(data.get('max_chars') or 12000), 50000))
    file_path = _resolve_uploaded_file_path(file_id)
    if not file_path:
        return jsonify({'error': 'File not found'}), 404

    text, truncated = _extract_text_from_uploaded_path(file_path, max_chars=max_chars)
    if not text:
        return jsonify({'error': 'No extractable text for this file type'}), 400

    return jsonify({
        'file_id': file_id,
        'filename': os.path.basename(file_path),
        'chars': len(text),
        'truncated': truncated,
        'text': text,
    })


@app.route('/api/upload/summarize', methods=['POST'])
def summarize_uploaded_file_text():
    data = request.get_json(silent=True) or {}
    file_id = str(data.get('file_id') or '').strip()
    if not file_id:
        return jsonify({'error': 'file_id is required'}), 400

    max_chars = max(120, min(int(data.get('max_chars') or 700), 3000))
    file_path = _resolve_uploaded_file_path(file_id)
    if not file_path:
        return jsonify({'error': 'File not found'}), 404

    text, _ = _extract_text_from_uploaded_path(file_path, max_chars=20000)
    if not text:
        return jsonify({'error': 'No extractable text for this file type'}), 400

    summary = _summarize_text_simple(text, max_chars=max_chars)
    return jsonify({
        'file_id': file_id,
        'filename': os.path.basename(file_path),
        'source_chars': len(text),
        'summary_chars': len(summary),
        'summary': summary,
    })


@app.route('/api/upload/search', methods=['GET'])
def search_uploaded_files():
    query = (request.args.get('q') or '').strip().lower()
    if not query:
        return jsonify({'error': 'q is required'}), 400

    limit = max(1, min(int(request.args.get('limit') or 20), 100))
    results = []

    for name in os.listdir(UPLOAD_DIR):
        path = os.path.join(UPLOAD_DIR, name)
        if not os.path.isfile(path) or '.' not in name:
            continue
        file_id, ext = name.rsplit('.', 1)
        ext = ext.lower()
        if ext not in {'txt', 'md', 'pdf', 'docx'}:
            continue

        text, _ = _extract_text_from_uploaded_path(path, max_chars=15000)
        if not text:
            continue
        low = text.lower()
        score = low.count(query)
        if score <= 0:
            continue

        idx = low.find(query)
        start = max(0, idx - 80)
        end = min(len(text), idx + len(query) + 140)
        snippet = text[start:end].replace('\n', ' ').strip()
        stat = os.stat(path)
        results.append({
            'file_id': file_id,
            'filename': name,
            'score': score,
            'snippet': snippet,
            'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
            'url': f'/api/upload/{file_id}',
        })

    results.sort(key=lambda x: (x['score'], x['modified_at']), reverse=True)
    return jsonify({'query': query, 'count': min(len(results), limit), 'results': results[:limit]})


# --- Brain Knowledge Base API ---

def _brain_dir_for_workspace() -> str:
    workspace_key = _resolve_workspace_key()
    base = os.path.join(os.path.dirname(__file__), 'BRAIN')
    if workspace_key and workspace_key != 'default':
        return os.path.join(base, 'workspaces', workspace_key)
    return base


def _resolve_brain_file_path(relative_path: str) -> str | None:
    safe_relative = str(relative_path or '').replace('\\', '/').lstrip('/').strip()
    if not safe_relative or '..' in safe_relative.split('/'):
        return None
    root = os.path.abspath(_brain_dir_for_workspace())
    candidate = os.path.abspath(os.path.join(root, safe_relative))
    if not candidate.startswith(root):
        return None
    return candidate

@app.route('/api/brain/upload', methods=['POST'])
def brain_upload():
    """Upload a file to the brain folder and index it."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    # Optional subfolder (defaults to 'documents')
    subfolder = request.form.get('folder', 'documents')
    
    # Create target directory
    target_dir = os.path.join(_brain_dir_for_workspace(), subfolder)
    os.makedirs(target_dir, exist_ok=True)
    
    try:
        from werkzeug.utils import secure_filename
        filename = secure_filename(file.filename)
        filepath = os.path.join(target_dir, filename)
        file.save(filepath)
        
        # Index the file
        from companion_ai.brain_index import get_brain_index
        index = get_brain_index()
        chunks = index.index_file(Path(filepath))
        
        logger.info(f"📄 Uploaded to brain: {filename} ({chunks} chunks indexed)")
        
        return jsonify({
            'success': True,
            'filename': filename,
            'path': f"{subfolder}/{filename}",
            'chunks_indexed': chunks
        })
    except Exception as e:
        logger.error(f"Brain upload error: {e}")
        return jsonify({'error': str(e)}), 500


def _save_brain_file(file, target_dir: str, subfolder: str, index):
    from pathlib import Path
    from werkzeug.utils import secure_filename

    filename = secure_filename(file.filename)
    if not filename:
        return None, {'filename': file.filename, 'error': 'Invalid filename'}

    filepath = os.path.join(target_dir, filename)
    if os.path.exists(filepath):
        base, ext = os.path.splitext(filename)
        suffix = datetime.now().strftime('%Y%m%d%H%M%S')
        filename = f"{base}_{suffix}{ext}"
        filepath = os.path.join(target_dir, filename)

    file.save(filepath)
    chunks = index.index_file(Path(filepath))
    logger.info(f"📄 Uploaded to brain: {filename} ({chunks} chunks indexed)")
    return {
        'success': True,
        'filename': filename,
        'path': f"{subfolder}/{filename}",
        'chunks_indexed': chunks,
    }, None


@app.route('/api/brain/upload/batch', methods=['POST'])
def brain_upload_batch():
    """Upload and index multiple files for the brain workspace."""
    files = request.files.getlist('files')
    if not files and 'file' in request.files:
        files = [request.files['file']]
    if not files:
        return jsonify({'error': 'No files provided'}), 400

    subfolder = request.form.get('folder', 'documents')
    target_dir = os.path.join(_brain_dir_for_workspace(), subfolder)
    os.makedirs(target_dir, exist_ok=True)

    try:
        from companion_ai.brain_index import get_brain_index
        index = get_brain_index()
        uploaded = []
        errors = []
        for file in files:
            if not file or not file.filename:
                errors.append({'filename': '', 'error': 'No file selected'})
                continue
            payload, err = _save_brain_file(file, target_dir, subfolder, index)
            if payload:
                uploaded.append(payload)
            elif err:
                errors.append(err)

        status_code = 200 if uploaded else 400
        return jsonify({
            'success': bool(uploaded),
            'count': len(uploaded),
            'uploaded': uploaded,
            'errors': errors,
        }), status_code
    except Exception as e:
        logger.error(f"Brain batch upload error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/stats', methods=['GET'])
def brain_stats():
    """Get brain index statistics."""
    try:
        from companion_ai.brain_index import get_brain_index
        index = get_brain_index()
        stats = index.get_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Brain stats error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/brain/files', methods=['GET'])
def brain_files_list():
    """List workspace brain files with index metadata."""
    try:
        from pathlib import Path
        root = _brain_dir_for_workspace()
        root_path = Path(root)
        if not root_path.exists():
            return jsonify({'files': [], 'count': 0})

        from companion_ai.brain_index import get_brain_index
        index = get_brain_index()
        stats = index.get_stats()
        chunk_map = {
            str(item.get('path', '')).replace('\\', '/'): int(item.get('chunks', 0))
            for item in (stats.get('files') or [])
            if item.get('path')
        }

        files = []
        for path in root_path.rglob('*'):
            if not path.is_file():
                continue
            rel = str(path.relative_to(root_path)).replace('\\', '/')
            stat = path.stat()
            files.append({
                'path': rel,
                'name': path.name,
                'size': stat.st_size,
                'modified_at': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                'chunks': chunk_map.get(rel, 0),
            })

        files.sort(key=lambda row: row['modified_at'], reverse=True)
        return jsonify({'files': files, 'count': len(files)})
    except Exception as e:
        logger.error(f"Brain files list error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/brain/file', methods=['DELETE'])
def brain_file_delete():
    """Delete one brain file and its indexed chunks."""
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    rel = data.get('path')
    if not rel:
        return jsonify({'error': 'path is required'}), 400

    abs_path = _resolve_brain_file_path(rel)
    if not abs_path:
        return jsonify({'error': 'Invalid path'}), 400
    if not os.path.exists(abs_path):
        return jsonify({'error': 'File not found'}), 404

    try:
        os.remove(abs_path)
        normalized = str(rel).replace('\\', '/').lstrip('/')
        from companion_ai.brain_index import get_brain_index
        index = get_brain_index()
        index.remove_file(normalized)
        return jsonify({'deleted': True, 'path': normalized})
    except Exception as e:
        logger.error(f"Brain file delete error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/reindex', methods=['POST'])
def brain_reindex():
    """Trigger full reindex of brain folder."""
    try:
        os.environ['BRAIN_DIR'] = _brain_dir_for_workspace()
        from companion_ai.brain_index import get_brain_index
        index = get_brain_index()
        results = index.index_all()
        return jsonify({
            'success': True,
            'files_indexed': len(results),
            'total_chunks': sum(results.values()),
            'files': results
        })
    except Exception as e:
        logger.error(f"Brain reindex error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/brain/search', methods=['GET'])
def brain_search_api():
    """Search brain documents via API."""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        from companion_ai.brain_index import get_brain_index
        index = get_brain_index()
        results = index.search(query, limit=10)
        return jsonify({'query': query, 'results': results})
    except Exception as e:
        logger.error(f"Brain search error: {e}")
        return jsonify({'error': str(e)}), 500


# Start background brain indexing on server start
def start_brain_indexing():
    """Start background indexing of brain folder."""
    try:
        from companion_ai.brain_index import start_background_indexing
        start_background_indexing()
    except Exception as e:
        logger.warning(f"Could not start brain indexing: {e}")

# Trigger indexing on import
threading.Thread(target=start_brain_indexing, daemon=True).start()


# --- Tasks API (V6 Architecture) ---

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """Get list of active background tasks."""
    tasks = job_manager_module.get_tasks_for_ui()
    return jsonify({'tasks': tasks, 'count': len(tasks)})


@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get detailed status of a specific task."""
    timeline = job_manager_module.get_task_timeline(task_id)
    if not timeline:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify({'status': 'success', 'data': {'id': task_id, 'timeline': timeline}})


@app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """Cancel a running task."""
    ok = job_manager_module.cancel_job(task_id)
    if not ok:
        return jsonify({'status': 'error', 'error': 'Task not found or not cancellable'}), 404
    return jsonify({'status': 'success'})


@app.route('/api/schedules', methods=['GET', 'POST'])
def schedules():
    if request.method == 'GET':
        rows = job_manager_module.list_schedules()
        return jsonify({'schedules': rows, 'count': len(rows)})

    data = request.get_json(silent=True) or {}
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    description = (data.get('description') or '').strip()
    try:
        interval_minutes = _parse_interval_minutes(data)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception:
        return jsonify({'error': 'Invalid interval/cadence value'}), 400
    tool_name = (data.get('tool_name') or 'start_background_task').strip()
    tool_args = data.get('tool_args') if isinstance(data.get('tool_args'), dict) else {}
    timezone = (data.get('timezone') or 'UTC').strip() or 'UTC'
    retry_limit = int(data.get('retry_limit') or 0)
    retry_backoff_minutes = int(data.get('retry_backoff_minutes') or 1)
    if not description or interval_minutes <= 0:
        return jsonify({'error': 'description and interval_minutes/cadence are required'}), 400
    if retry_limit < 0 or retry_backoff_minutes <= 0:
        return jsonify({'error': 'retry_limit must be >= 0 and retry_backoff_minutes must be > 0'}), 400

    schedule_id = job_manager_module.add_schedule(
        description,
        interval_minutes,
        tool_name,
        tool_args,
        timezone=timezone,
        retry_limit=retry_limit,
        retry_backoff_minutes=retry_backoff_minutes,
    )
    return jsonify({'id': schedule_id, 'status': 'created'})


@app.route('/api/schedules/<schedule_id>/toggle', methods=['POST'])
def schedule_toggle(schedule_id):
    data = request.get_json(silent=True) or {}
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    enabled = bool(data.get('enabled', True))
    ok = job_manager_module.set_schedule_enabled(schedule_id, enabled)
    if not ok:
        return jsonify({'error': 'Schedule not found'}), 404
    return jsonify({'status': 'success', 'enabled': enabled})


@app.route('/api/schedules/<schedule_id>/run', methods=['POST'])
def schedule_run_now(schedule_id):
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    result = job_manager_module.run_schedule_now(schedule_id)
    if not result.get('ok'):
        err = result.get('error') or 'Failed to run schedule'
        if err == 'Schedule not found':
            return jsonify({'error': err}), 404
        if result.get('reason') == 'policy_denied':
            return jsonify({'error': err}), 400
        return jsonify({'error': err}), 500
    return jsonify({'status': 'success', 'job_id': result.get('job_id')})


@app.route('/api/schedules/<schedule_id>', methods=['PUT', 'DELETE'])
def schedule_modify(schedule_id):
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    if request.method == 'DELETE':
        ok = job_manager_module.delete_schedule(schedule_id)
        if not ok:
            return jsonify({'error': 'Schedule not found'}), 404
        return jsonify({'status': 'success', 'deleted': True})

    data = request.get_json(silent=True) or {}
    description = (data.get('description') or '').strip()
    try:
        interval_minutes = _parse_interval_minutes(data)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception:
        return jsonify({'error': 'Invalid interval/cadence value'}), 400

    tool_name = (data.get('tool_name') or 'start_background_task').strip()
    tool_args = data.get('tool_args') if isinstance(data.get('tool_args'), dict) else {}
    timezone = (data.get('timezone') or 'UTC').strip() or 'UTC'
    retry_limit = int(data.get('retry_limit') or 0)
    retry_backoff_minutes = int(data.get('retry_backoff_minutes') or 1)

    if not description or interval_minutes <= 0:
        return jsonify({'error': 'description and interval_minutes/cadence are required'}), 400
    if retry_limit < 0 or retry_backoff_minutes <= 0:
        return jsonify({'error': 'retry_limit must be >= 0 and retry_backoff_minutes must be > 0'}), 400

    ok = job_manager_module.update_schedule(
        schedule_id,
        description,
        interval_minutes,
        tool_name,
        tool_args,
        timezone=timezone,
        retry_limit=retry_limit,
        retry_backoff_minutes=retry_backoff_minutes,
    )
    if not ok:
        return jsonify({'error': 'Schedule not found'}), 404
    return jsonify({'status': 'success', 'updated': True})


@app.route('/api/loops/capabilities', methods=['GET'])
def get_loop_capabilities():
    """Get capabilities of all local loops (for debugging)."""
    try:
        from companion_ai.local_loops import get_capabilities_summary, list_loops
        
        return jsonify({
            'summary': get_capabilities_summary(),
            'loops': list_loops()
        })
    except Exception as e:
        logger.error(f"Error getting loop capabilities: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/vision/analyze', methods=['POST'])
def vision_analyze():
    try:
        data = request.json or {}
        token = request.headers.get('X-API-TOKEN')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
            
        prompt = data.get('prompt', 'What is on the screen?')
        result = vision_manager.analyze_current_screen(prompt)
        return jsonify({'result': result})
    except Exception as e:
        logger.error(f"Vision analyze error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/voice/change', methods=['POST'])
def change_voice():
    # Legacy endpoint - redirect to new config
    try:
        data = request.json or {}
        token = request.headers.get('X-API-TOKEN') or data.get('token') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        voice_name = data.get('voice')
        # Try to map friendly names if needed, or just pass through
        mapping = {
            'Phoebe Dragon HD': 'en-US-Phoebe:DragonHDLatestNeural',
            'Ava Dragon HD': 'en-US-Ava:DragonHDLatestNeural'
        }
        target_voice = mapping.get(voice_name, voice_name)
        success = tts_manager.set_voice(target_voice)
        return jsonify({'success': success})
    except Exception as e:
        logger.error(f"Voice change error: {e}")
        return jsonify({'error': str(e)}), 500



@app.route('/api/search')
def search():
    try:
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify({'query': q, 'memory_hits': [], 'web_snippet': None})
        hits = search_memory(q, limit=8)
        web_snippet = None
        try:
            tool_text = run_tool('search', q)
            for line in tool_text.splitlines():
                if line.startswith('WEB:'):
                    web_snippet = line[4:].strip()
                    break
        except Exception as inner:
            logger.warning(f"Search tool error: {inner}")
        return jsonify({'query': q, 'memory_hits': hits, 'web_snippet': web_snippet})
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    try:
        memstats = get_memory_stats()
        mstats = metrics.snapshot()
        caps = core_config.model_capability_summary() if getattr(core_config, 'ENABLE_CAPABILITY_ROUTER', False) else None
        return jsonify({
            'memory': memstats,
            'metrics': mstats,
            'models': caps,
            'tools': (mstats or {}).get('tools') if isinstance(mstats, dict) else None
        })
    except Exception as e:
        logger.error(f"Health error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tokens')
def token_stats():
    """Get token usage statistics."""
    try:
        stats = get_token_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Token stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tokens/reset', methods=['POST'])
def reset_tokens():
    """Reset token usage statistics."""
    try:
        token = request.headers.get('X-API-TOKEN')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        reset_token_stats()
        return jsonify({'success': True, 'message': 'Token stats reset'})
    except Exception as e:
        logger.error(f"Token reset error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tokens/last')
def last_request_tokens():
    """Get token usage breakdown for the last request.
    
    Returns per-step breakdown showing:
    - Step name (orchestrator, memory_loop, tool_loop, etc.)
    - Model used
    - Input/output tokens
    - Duration in milliseconds
    """
    try:
        usage = get_last_token_usage()
        return jsonify({
            'total_input': usage.get('input', 0),
            'total_output': usage.get('output', 0),
            'total': usage.get('total', 0),
            'source': usage.get('source', 'unknown'),
            'steps': usage.get('steps', [])
        })
    except Exception as e:
        logger.error(f"Last token error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config')
def config_info():
    tool_allowlist = sorted(core_config.get_tool_allowlist() or [])
    return jsonify({
        'auth_required': bool(core_config.API_AUTH_TOKEN),
        'tool_allowlist_enabled': bool(tool_allowlist),
        'tool_allowlist': tool_allowlist,
    })

@app.route('/api/models')
def models_info():
    """Return structured model configuration metadata (simplified architecture).

    This endpoint is read-only and exposes only non-sensitive configuration
    needed by the UI for transparency / debugging.
    """
    try:
        data = {
            'models': {
                'PRIMARY_MODEL': core_config.PRIMARY_MODEL,
                'TOOLS_MODEL': core_config.TOOLS_MODEL,
                'VISION_MODEL': core_config.VISION_MODEL,
                # COMPOUND_MODEL removed - V5 cleanup
            },
            'model_info': core_config.MODEL_INFO,
            'flags': {
                'knowledge_graph': core_config.ENABLE_KNOWLEDGE_GRAPH,
                'fact_extraction': core_config.ENABLE_FACT_EXTRACTION,
                'tool_calling': core_config.ENABLE_TOOL_CALLING,
                'vision': core_config.ENABLE_VISION,
                'auto_tools': core_config.ENABLE_AUTO_TOOLS,
            },
            # Legacy fields for backward compatibility
            'roles': {
                'SMART_PRIMARY_MODEL': core_config.PRIMARY_MODEL,
                'HEAVY_MODEL': core_config.PRIMARY_MODEL,
                'HEAVY_ALTERNATES': [],
                'FAST_MODEL': core_config.PRIMARY_MODEL,
            },
            'ensemble': {
                'enabled': False,
                'mode': None,
                'candidates': None,
            }
        }
        return jsonify(data)
    except Exception as e:
        logger.error(f"Models info error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/routing/recent')
def routing_recent():
    """Return recent routing / ensemble decisions (last N records with routing info).

    Query params:
      n: max records (default 15, cap 100)
    """
    try:
        n = request.args.get('n', '15')
        try:
            n_int = max(1, min(int(n), 100))
        except Exception:
            n_int = 15
        # Collect today's and yesterday's log for tail safety
        log_dir = core_config.LOG_DIR
        patterns = sorted(glob.glob(os.path.join(log_dir, 'conv_*.jsonl')))[-2:]
        records: list[dict] = []
        for path in reversed(patterns):  # newest first
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in reversed(f.readlines()[-500:]):  # tail safety
                        try:
                            obj = json.loads(line)
                            if 'routing' in obj:
                                rec = {
                                    'ts': obj.get('ts'),
                                    'model': obj.get('model'),
                                    'complexity': obj.get('complexity'),
                                    'latency_ms': obj.get('latency_ms'),
                                    'routing': obj.get('routing')
                                }
                                records.append(rec)
                                if len(records) >= n_int:
                                    raise StopIteration
                        except json.JSONDecodeError:
                            continue
            except StopIteration:
                break
            except Exception as inner:
                logger.warning(f"Routing recent read error {path}: {inner}")
        return jsonify({'count': len(records), 'items': records[:n_int]})
    except Exception as e:
        logger.error(f"Routing recent error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/graph')
def get_graph():
    """
    Return knowledge graph data as JSON for visualization.
    
    Returns nodes and edges in a format suitable for D3.js or other graph libs.
    """
    # Prevent caching
    response = None
    try:
        # --- SWITCH TO MEM0 AS SOURCE ---
        if core_config.USE_MEM0:
            try:
                _, _, mem0_user_id, _, _ = _get_active_session_state()
                # Fetch all memories from Mem0
                mem0_memories = memory_v2.get_all_memories(user_id=mem0_user_id)
                
                # Use the new semantic graph builder
                from companion_ai.memory_graph import build_semantic_graph_from_memories
                graph_data = build_semantic_graph_from_memories(mem0_memories, threshold=0.6)
                
                response = jsonify(graph_data)
                
            except Exception as mem0_err:
                logger.error(f"Failed to build graph from Mem0: {mem0_err}")
                # Fallback to legacy graph

        if not response:
            from companion_ai.memory_graph import export_graph
            graph_json = export_graph()
            response = make_response(graph_json, 200)
            response.headers['Content-Type'] = 'application/json'
            
    except ImportError:
        return jsonify({'error': 'Knowledge graph not available. Install networkx.'}), 503
    except Exception as e:
        logger.error(f"Graph export error: {e}")
        return jsonify({'error': str(e)}), 500
        
    # Add cache control headers
    if response:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
    return response

@app.route('/api/graph/stats')
def get_graph_stats():
    """
    Return knowledge graph statistics.
    
    Returns entity counts, relationship counts, most connected nodes, etc.
    """
    try:
        from companion_ai.memory_graph import get_graph_stats
        stats = get_graph_stats()
        return jsonify(stats)
    except ImportError:
        return jsonify({'error': 'Knowledge graph not available. Install networkx.'}), 503
    except Exception as e:
        logger.error(f"Graph stats error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/graph/search')
def search_graph_api():
    """
    Search the knowledge graph.
    
    Query params:
      q: search query
      mode: search mode (GRAPH_COMPLETION, KEYWORD, RELATIONSHIPS, TEMPORAL, IMPORTANT)
      limit: max results (default 10)
    """
    try:
        from companion_ai.memory_graph import search_graph
        
        query = request.args.get('q', '')
        mode = request.args.get('mode', 'GRAPH_COMPLETION')
        limit = int(request.args.get('limit', '10'))
        
        results = search_graph(query, mode=mode, limit=limit)
        return jsonify({'query': query, 'mode': mode, 'count': len(results), 'results': results})
    except ImportError:
        return jsonify({'error': 'Knowledge graph not available. Install networkx.'}), 503
    except Exception as e:
        logger.error(f"Graph search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/stop', methods=['POST'])
def stop_chat():
    """Stop chat generation and audio"""
    print(">>> STOP CHAT REQUEST RECEIVED")
    try:
        # TODO: Stop LLM generation if possible
        if tts_manager:
            tts_manager.stop_speech()
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Stop error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts/config/legacy', methods=['POST'])
def config_tts():
    """Update TTS configuration"""
    try:
        data = request.json
        if 'enabled' in data:
            tts_manager.is_enabled = data['enabled']
            logger.info(f"TTS enabled: {tts_manager.is_enabled}")
            
        if 'provider' in data:
            tts_manager.provider = data['provider']
            logger.info(f"TTS provider set to: {tts_manager.provider}")
            
        if 'voice' in data:
            tts_manager.set_voice(data['voice'])
            
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"TTS Config error: {e}")
        return jsonify({'error': str(e)}), 500

def open_browser(port: int = 5000):
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{port}')

def run_web(host: str = core_config.WEB_HOST, port: int = core_config.WEB_PORT, open_browser_flag: bool = True):
    print(f"Starting Companion AI Web Portal on http://{host}:{port}")
    # Start background scheduler (decay + resurfacing)
    def _bg_scheduler():
        while True:
            try:
                sqlite_memory.decay_profile_confidence()
                sqlite_memory.touch_stale_facts(limit=2)
            except Exception as e:
                logger.debug(f"BG scheduler error: {e}")
            time.sleep(300)  # every 5 minutes
    threading.Thread(target=_bg_scheduler, daemon=True).start()
    if open_browser_flag:
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    app.run(debug=False, host=host, port=port)

if __name__ == '__main__':
    run_web()
