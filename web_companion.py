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

from companion_ai.llm_interface import generate_response, get_token_stats, reset_token_stats
from companion_ai.conversation_manager import ConversationSession
from companion_ai.core import config as core_config
from companion_ai import memory as db
from companion_ai.tts_manager import tts_manager
from companion_ai.vision_manager import vision_manager
from companion_ai.tools import run_tool, list_tools
from companion_ai.core import metrics
from companion_ai import memory as mem
from companion_ai import memory_v2
from companion_ai import job_manager  # Import job manager
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
job_manager.start_worker()

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
        
    logger.info("🛑 Shutdown requested. Triggering persona evolution...")
    
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
    job_manager.stop_worker()
    
    return jsonify({'status': 'Server shutting down...'})

@app.route('/api/jobs/active', methods=['GET'])
def get_active_jobs():
    """Get active and recently completed jobs."""
    token = (request.headers.get('X-API-TOKEN') or request.args.get('token')
             or request.cookies.get('api_token'))
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401
    
    jobs = job_manager.get_active_jobs()
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
                    full_response += chunk
                    # Send chunk as SSE event
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                
                # Get token usage
                from companion_ai.llm_interface import get_last_token_usage
                token_usage = get_last_token_usage()
                
                # Signal completion and update history
                memory_saved = core_config.USE_MEM0
                yield f"data: {json.dumps({'done': True, 'full_response': full_response, 'tokens': token_usage, 'memory_saved': memory_saved})}\n\n"
                
                # Store in history
                entry = {
                    'user': user_message,
                    'ai': full_response,
                    'timestamp': datetime.now().isoformat(),
                    'persona': 'Companion',
                    'tokens': token_usage
                }
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
            existing = job_manager.get_active_jobs()
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
                    jobs = job_manager.get_active_jobs()
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
        profile = db.get_all_profile_facts()
        summaries = db.get_latest_summary(10)
        insights = db.get_latest_insights(10)
        resp = {'profile': profile, 'summaries': summaries, 'insights': insights}
        if detailed:
            try:
                resp['profile_detailed'] = db.list_profile_facts_detailed()
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
        pending = db.list_pending_profile_facts()
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
        ok = db.approve_profile_fact(pid)
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
        ok = db.reject_profile_fact(pid)
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
        db.clear_all_memory()
        
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
                    sqlite_deleted = db.delete_profile_fact(key)
                    if sqlite_deleted:
                        deleted = True
                        local_logger.info(f"Deleted SQLite memory for key: {key}")
                        
            except Exception as mem0_err:
                local_logger.error(f"Failed to delete Mem0 fact: {mem0_err}")
        else:
            # 2. Fallback to SQLite only
            deleted = db.delete_profile_fact(key)
                
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

# --- Computer Control Endpoints ---
@app.route('/api/computer/status', methods=['GET'])
def computer_status():
    """Return current computer control status for UI banner."""
    from companion_ai.computer_agent import computer_agent
    return jsonify({
        'active': computer_agent.is_recently_active(),
        'safe_mode': computer_agent.safe_mode,
        'screen': f"{computer_agent.screen_width}x{computer_agent.screen_height}"
    })

@app.route('/api/computer/stream')
def computer_status_stream():
    """Server-sent events stream pushing computer control status changes."""
    def event_stream():
        from companion_ai.computer_agent import computer_agent
        last_state = None
        while True:
            state = {
                'active': computer_agent.is_recently_active(),
                'safe_mode': computer_agent.safe_mode,
            }
            if state != last_state:
                payload = json.dumps({'type': 'computer_status', 'status': state})
                yield f"data: {payload}\n\n"
                last_state = state
            # Keep-alive + low CPU usage
            yield ": keep-alive\n\n"
            time.sleep(1.0)

    response = Response(stream_with_context(event_stream()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response

@app.route('/api/computer/stop', methods=['POST'])
def computer_stop():
    """Emergency stop for computer control."""
    from companion_ai.computer_agent import computer_agent
    computer_agent.safe_mode = True
    
    # Cancel all background jobs
    job_manager.cancel_all_jobs()
    
    logger.warning("Computer control STOPPED via API")
    return jsonify({'success': True, 'message': 'Computer control disabled and jobs cancelled'})


# --- Tasks API (V6 Architecture) ---

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    """Get list of active background tasks."""
    try:
        from companion_ai.local_loops import get_loop
        
        computer_loop = get_loop('computer')
        if computer_loop:
            tasks = computer_loop.get_active_tasks()
            return jsonify({'tasks': tasks, 'count': len(tasks)})
        else:
            return jsonify({'tasks': [], 'count': 0})
    except Exception as e:
        logger.error(f"Error getting tasks: {e}")
        return jsonify({'tasks': [], 'count': 0, 'error': str(e)})


@app.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get detailed status of a specific task with timeline."""
    try:
        from companion_ai.local_loops import get_loop
        import asyncio
        
        computer_loop = get_loop('computer')
        if not computer_loop:
            return jsonify({'error': 'Computer loop not available'}), 503
        
        # Run async in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                computer_loop.execute({'operation': 'status', 'task_id': task_id})
            )
            return jsonify(result.to_dict())
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """Cancel a running task."""
    try:
        from companion_ai.local_loops import get_loop
        import asyncio
        
        computer_loop = get_loop('computer')
        if not computer_loop:
            return jsonify({'error': 'Computer loop not available'}), 503
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                computer_loop.execute({'operation': 'cancel', 'task_id': task_id})
            )
            return jsonify(result.to_dict())
        finally:
            loop.close()
            
    except Exception as e:
        logger.error(f"Error canceling task {task_id}: {e}")
        return jsonify({'error': str(e)}), 500


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
        hits = db.search_memory(q, limit=8)
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
        memstats = db.get_memory_stats()
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

def open_browser():
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')

def run_web(host: str = 'localhost', port: int = 5000, open_browser_flag: bool = True):
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