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

from companion_ai.llm_interface import generate_response, get_token_stats, reset_token_stats, get_last_token_usage
from companion_ai.conversation_manager import ConversationSession
from companion_ai.core import config as core_config
from companion_ai.memory.sqlite_backend import (
    get_all_profile_facts, upsert_profile_fact, delete_profile_fact,
    clear_all_memory, list_profile_facts_detailed, list_pending_profile_facts,
    approve_profile_fact, reject_profile_fact, get_latest_summary, get_latest_insights,
    search_memory, get_memory_stats
)
from companion_ai.memory import mem0_backend as memory_v2
from companion_ai.services.tts import tts_manager
from companion_ai.agents.vision import vision_manager
from companion_ai.tools import run_tool, list_tools
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

@app.route('/')
def index():
    resp = make_response(render_template('index.html'))
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
        brain = get_brain()
        
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
        
        brain = get_brain()
        
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
            ai_response, memory_saved = conversation_session.process_message(f"{context_msg}\n\nUser: {user_message}", conversation_history)
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
            
            ai_response, memory_saved = conversation_session.process_message(user_message, conversation_history)
        
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
        conversation_history.append(entry)
        global history_version
        with history_condition:
            history_version += 1
            history_condition.notify_all()
        
        # Auto-process memory every 5 messages to store facts in database
        if len(conversation_history) % 5 == 0:
            try:
                logger.info(f"Auto-processing memory at {len(conversation_history)} messages")
                conversation_session.process_session_memory()
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
            'memory_saved': memory_saved
        })
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/chat/send', methods=['POST'])
def chat_streaming():
    """Streaming chat endpoint - sends response tokens as they arrive."""
    try:
        data = request.json or {}
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
                for chunk in conversation_session.process_message_streaming(user_message, conversation_history):
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
                conversation_history.append(entry)
                
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
    No auth required, returns both user message and AI response.
    Shares conversation_history with main chat endpoint.
    """
    try:
        data = request.json or {}
        user_message = data.get('message', '').strip()
        persona = data.get('persona', 'Companion')
        
        if not user_message:
            return jsonify({'error': 'Empty message'}), 400
        
        # Use conversation session with FULL conversation history
        ai_response, memory_saved = conversation_session.process_message(user_message, conversation_history)
        
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
        conversation_history.append(entry)
        global history_version
        with history_condition:
            history_version += 1
            history_condition.notify_all()
        
        # Auto-process memory every 5 messages to store facts in database
        if len(conversation_history) % 5 == 0:
            try:
                logger.info(f"Auto-processing memory at {len(conversation_history)} messages")
                conversation_session.process_session_memory()
            except Exception as mem_err:
                logger.warning(f"Memory processing error: {mem_err}")
        
        # Get token usage
        from companion_ai.llm_interface import get_last_token_usage
        token_usage = get_last_token_usage()
        
        return jsonify({
            'user': user_message,
            'ai': ai_response,
            'timestamp': entry['timestamp'],
            'history_length': len(conversation_history),
            'tokens': token_usage
        })
        
    except Exception as e:
        logger.error(f"Debug chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/debug/reset', methods=['POST'])
def debug_reset():
    """Clear conversation history and start a fresh ConversationSession (testing only)."""
    try:
        global conversation_history, conversation_session, history_version
        conversation_history.clear()
        conversation_session = ConversationSession()
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
        return jsonify({
            'history': conversation_history,
            'count': len(conversation_history)
        })
    except Exception as e:
        logger.error(f"Get history error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/stream')
def chat_history_stream():
    """Server-sent events stream pushing history updates AND job updates."""
    def event_stream():
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
                snapshot = list(conversation_history)
            
            if current_version != last_version:
                # Send history update
                payload = json.dumps({
                    'type': 'history',
                    'history': snapshot,
                    'count': len(snapshot)
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
                            payload = json.dumps({
                                'type': 'job_update',
                                'job': job
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

@app.route('/api/memory')
def get_memory():
    try:
        detailed = request.args.get('detailed', 'false').lower() in ('1','true','yes')
        
        # --- SWITCH TO MEM0 AS PRIMARY SOURCE ---
        if core_config.USE_MEM0:
            try:
                # Fetch all memories from Mem0
                mem0_memories = memory_v2.get_all_memories(user_id=core_config.MEM0_USER_ID)
                
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
                    
                    profile_detailed.append({
                        'key': m.get('id'),  # Use ID as key for deletion
                        'value': text,
                        'confidence': 1.0,   # Mem0 doesn't have confidence, assume high
                        'confidence_label': 'high',
                        'reaffirmations': meta.get('frequency', 0), # Use frequency if available
                        'source': 'mem0'
                    })
                
                # Sort by most recent (if created_at exists) or just reverse
                # Mem0 usually returns most relevant or recent. Let's just use as is.
                
                resp = {
                    'profile': {m['key']: m['value'] for m in profile_detailed}, # Simple dict
                    'profile_detailed': profile_detailed,
                    'summaries': [], # Mem0 handles summaries internally or we don't have them separate
                    'insights': []   # Same
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

@app.route('/api/tools')
def tools():
    return jsonify({'tools': list_tools()})

@app.route('/api/memory/clear', methods=['POST'])
def clear_memory():
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        
        # Clear SQLite memory
        clear_all_memory()
        
        # Clear Mem0 vector memory
        if core_config.USE_MEM0:
            try:
                memory_v2.clear_all_memories(user_id=core_config.MEM0_USER_ID)
                # Reset the Mem0 instance to force fresh start
                memory_v2._reset_memory()
                logger.info("Cleared Mem0 vector memory and reset instance")
            except Exception as mem0_err:
                logger.error(f"Failed to clear Mem0: {mem0_err}")
        
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

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'pdf', 'docx', 'txt'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload a file and optionally analyze it with vision."""
    import uuid
    
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400
    
    if not allowed_file(file.filename):
        return jsonify({'success': False, 'error': f'File type not allowed. Allowed: {", ".join(ALLOWED_EXTENSIONS)}'}), 400
    
    # Generate unique ID for file
    file_id = str(uuid.uuid4())[:8]
    ext = file.filename.rsplit('.', 1)[1].lower()
    safe_filename = f"{file_id}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_filename)
    
    # Save file
    file.save(file_path)
    file_size = os.path.getsize(file_path)
    
    if file_size > MAX_FILE_SIZE:
        os.remove(file_path)
        return jsonify({'success': False, 'error': 'File too large (max 10MB)'}), 400
    
    # Determine file type
    is_image = ext in {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    is_pdf = ext == 'pdf'
    is_doc = ext in {'docx', 'txt'}
    
    # Auto-analyze images with Maverick
    analysis = None
    if is_image:
        try:
            analysis = vision_manager.analyze_image_file(
                file_path, 
                prompt="DESCRIBE ONLY - don't solve or interpret. Just describe what you see: text, numbers, objects, layout. If there's math/text, transcribe it exactly. Let someone else solve it."
            )
            logger.info(f"Image analyzed: {file_id} - {analysis[:100]}...")
        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            analysis = None
    
    return jsonify({
        'success': True,
        'file_id': file_id,
        'filename': file.filename,
        'type': 'image' if is_image else 'pdf' if is_pdf else 'document' if is_doc else 'file',
        'size': file_size,
        'url': f'/api/upload/{file_id}',
        'analysis': analysis
    })

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


# --- Tasks API (V6 Architecture) ---

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """Get list of active background tasks. (Computer loop removed)"""
    return jsonify({'tasks': [], 'count': 0})


@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get detailed status of a specific task. (Computer loop removed)"""
    return jsonify({'error': 'Background tasks not available'}), 503


@app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """Cancel a running task. (Computer loop removed)"""
    return jsonify({'error': 'Background tasks not available'}), 503


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
    return jsonify({'auth_required': bool(core_config.API_AUTH_TOKEN)})

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
                # Fetch all memories from Mem0
                mem0_memories = memory_v2.get_all_memories(user_id=core_config.MEM0_USER_ID)
                
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

@app.route('/api/tts/config', methods=['POST'])
def config_tts():
    """Update TTS configuration"""
    print(">>> TTS CONFIG REQUEST RECEIVED")
    try:
        data = request.json
        print(f">>> TTS CONFIG DATA: {data}")
        if 'enabled' in data:
            tts_manager.is_enabled = data['enabled']
            logger.info(f"TTS enabled: {tts_manager.is_enabled}")
            
        if 'provider' in data:
            tts_manager.provider = data['provider']
            logger.info(f"TTS provider set to: {tts_manager.provider}")
            print(f">>> TTS PROVIDER SET TO: {tts_manager.provider}")
            
        if 'voice' in data:
            tts_manager.set_voice(data['voice'])
            
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"TTS Config error: {e}")
        return jsonify({'error': str(e)}), 500

def open_browser():
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')

def run_web(host: str = '0.0.0.0', port: int = 5000, open_browser_flag: bool = True):
    print(f"Starting Companion AI Web Portal on http://{host}:{port}")
    # Start background scheduler (decay + resurfacing)
    def _bg_scheduler():
        while True:
            try:
                mem.decay_profile_confidence()
                mem.touch_stale_facts(limit=2)
            except Exception as e:
                logger.debug(f"BG scheduler error: {e}")
            time.sleep(300)  # every 5 minutes
    threading.Thread(target=_bg_scheduler, daemon=True).start()
    if open_browser_flag:
        threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, host=host, port=port)

if __name__ == '__main__':
    run_web()
