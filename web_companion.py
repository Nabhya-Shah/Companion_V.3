#!/usr/bin/env python3
"""
Web-based Companion AI Interface
"""

from flask import Flask, render_template, request, jsonify, make_response
import threading
import webbrowser
import time
import logging
from datetime import datetime

from companion_ai.llm_interface import generate_response
from companion_ai.conversation_manager import ConversationSession
from companion_ai.core import config as core_config
from companion_ai import memory as db
from companion_ai.tts_manager import tts_manager
from companion_ai.tools import run_tool, list_tools
from companion_ai.core import metrics
from companion_ai import memory as mem
import os, json, glob

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

conversation_history = []
conversation_session = ConversationSession()

@app.route('/')
def index():
    resp = make_response(render_template('index.html'))
    # If auth token configured, set it as httpOnly cookie for transparent reuse.
    if core_config.API_AUTH_TOKEN:
        # Only set if not already present to avoid rewriting each request
        if not request.cookies.get('api_token'):
            resp.set_cookie('api_token', core_config.API_AUTH_TOKEN, httponly=True, samesite='Lax')
    return resp

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
        else:
            # Use conversation session with FULL conversation history
            ai_response = conversation_session.process_message(user_message, conversation_history)
        
        # Guard against empty responses
        if not ai_response or not ai_response.strip():
            logger.warning("Empty AI response received, using fallback")
            ai_response = "I'm here! Sorry, I got a bit stuck there. What were you saying?"
        
        # Remove "Chat:" prefix if present (formatting artifact)
        if ai_response.startswith("Chat:") or ai_response.startswith("CHAT:"):
            ai_response = ai_response[5:].strip()
        
        entry = {
            'user': user_message,
            'ai': ai_response,
            'timestamp': datetime.now().isoformat(),
            'persona': persona
        }
        conversation_history.append(entry)
        
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
        return jsonify({'response': ai_response, 'timestamp': entry['timestamp']})
    except Exception as e:
        logger.error(f"Chat error: {e}")
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
        ai_response = conversation_session.process_message(user_message, conversation_history)
        
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
        
        # Auto-process memory every 5 messages to store facts in database
        if len(conversation_history) % 5 == 0:
            try:
                logger.info(f"Auto-processing memory at {len(conversation_history)} messages")
                conversation_session.process_session_memory()
            except Exception as mem_err:
                logger.warning(f"Memory processing error: {mem_err}")
        
        return jsonify({
            'user': user_message,
            'ai': ai_response,
            'timestamp': entry['timestamp'],
            'history_length': len(conversation_history)
        })
        
    except Exception as e:
        logger.error(f"Debug chat error: {e}")
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

@app.route('/api/memory')
def get_memory():
    try:
        detailed = request.args.get('detailed', 'false').lower() in ('1','true','yes')
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
        db.clear_all_memory()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Clear memory error: {e}")
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

@app.route('/api/voice/change', methods=['POST'])
def change_voice():
    try:
        data = request.json or {}
        token = request.headers.get('X-API-TOKEN') or data.get('token') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        voice_name = data.get('voice')
        mapping = {
            'Phoebe Dragon HD': 'en-US-Phoebe:DragonHDLatestNeural',
            'Ava Dragon HD': 'en-US-Ava:DragonHDLatestNeural'
        }
        if voice_name in mapping:
            success = tts_manager.set_voice(mapping[voice_name])
            return jsonify({'success': success})
        return jsonify({'error': 'Invalid voice'}), 400
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

@app.route('/api/config')
def config_info():
    return jsonify({'auth_required': bool(core_config.API_AUTH_TOKEN)})

@app.route('/api/models')
def models_info():
    """Return structured model + routing + ensemble configuration metadata.

    This endpoint is read-only and exposes only non-sensitive configuration
    needed by the UI for transparency / debugging. If an auth token is
    configured, it can be optionally supplied but isn't required (similar to
    /api/health). Adjust to enforce auth if later desired.
    """
    try:
        capability_summary = core_config.model_capability_summary()
        data = {
            'roles': {
                'SMART_PRIMARY_MODEL': getattr(core_config, 'SMART_PRIMARY_MODEL', None),
                'HEAVY_MODEL': getattr(core_config, 'HEAVY_MODEL', None),
                'HEAVY_ALTERNATES': getattr(core_config, 'HEAVY_ALTERNATES', []),
                'FAST_MODEL': getattr(core_config, 'FAST_MODEL', core_config.DEFAULT_CONVERSATION_MODEL),
            },
            'routing': {
                'aggressive_escalation': getattr(core_config, 'AGGRESSIVE_ESCALATION', False),
                'always_heavy_chat': getattr(core_config, 'ALWAYS_HEAVY_CHAT', False),
                'heavy_memory': getattr(core_config, 'HEAVY_MEMORY', False),
            },
            'ensemble': {
                'enabled': getattr(core_config, 'ENABLE_ENSEMBLE', False),
                'mode': getattr(core_config, 'ENSEMBLE_MODE', None),
                'candidates': getattr(core_config, 'ENSEMBLE_CANDIDATES', None),
                'refine': {
                    'expansion': getattr(core_config, 'ENSEMBLE_REFINE_EXPANSION', None),
                    'hard_cap': getattr(core_config, 'ENSEMBLE_REFINE_HARD_CAP', None),
                    'max_total_factor': getattr(core_config, 'ENSEMBLE_MAX_TOTAL_FACTOR', None)
                }
            },
            'capabilities': capability_summary,
            'available': sorted(list(getattr(core_config, 'KNOWN_AVAILABLE_MODELS', []))),
            'flags': {
                'experimental_models': getattr(core_config, 'ENABLE_EXPERIMENTAL_MODELS', False),
                'compound_models': getattr(core_config, 'ENABLE_COMPOUND_MODELS', False),
                'auto_tools': getattr(core_config, 'ENABLE_AUTO_TOOLS', False),
                'prompt_caching': getattr(core_config, 'ENABLE_PROMPT_CACHING', False),
                'fact_approval': getattr(core_config, 'ENABLE_FACT_APPROVAL', False),
                'verify_facts_second_pass': getattr(core_config, 'VERIFY_FACTS_SECOND_PASS', False),
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