#!/usr/bin/env python3
"""
Web-based Companion AI Interface
Modern, responsive web portal for better UX
"""

from flask import Flask, render_template, request, jsonify
import threading
import webbrowser
import time
import logging
from companion_ai.llm_interface import generate_response
from companion_ai.core import config as core_config
from companion_ai import memory as db
from companion_ai.tts_manager import tts_manager
from companion_ai.tools import run_tool, list_tools
from companion_ai.core import metrics

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Store conversation history
conversation_history = []

@app.route('/')
def index():
    """Main chat interface"""
    return render_template('index.html')

@app.route('/api/chat', methods=['POST'])
def chat():
    """Handle chat messages"""
    try:
        data = request.json or {}
        token = request.headers.get('X-API-TOKEN') or data.get('token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        user_message = data.get('message', '').strip()
        persona = data.get('persona', 'Companion')
        model = data.get('model', core_config.DEFAULT_CONVERSATION_MODEL)
        
        if not user_message:
            return jsonify({'error': 'Empty message'}), 400
        
        # Get memory context
        memory_context = {
            "profile": db.get_all_profile_facts(),
            "summaries": db.get_latest_summary(3),
            "insights": db.get_latest_insights(3)
        }
        
        # Tool invocation: message starting with !tool_name rest
        if user_message.startswith('!') and ' ' in user_message:
            first, rest = user_message[1:].split(' ', 1)
            tool_result = run_tool(first, rest)
            ai_response = f"[tool:{first}]\n{tool_result}"
        else:
            # Generate response via LLM
            ai_response = generate_response(user_message, memory_context, model, persona)
        
        # Store conversation
        from datetime import datetime
        conversation_entry = {
            "user": user_message,
            "ai": ai_response,
            "timestamp": datetime.now().isoformat(),
            "persona": persona
        }
        conversation_history.append(conversation_entry)
        
        # TTS if enabled
        if tts_manager.is_enabled:
            tts_manager.speak_text(ai_response, blocking=False)
        
        return jsonify({
            'response': ai_response,
            'timestamp': conversation_entry['timestamp']
        })
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/memory')
def get_memory():
    """Get memory data"""
    try:
        profile = db.get_all_profile_facts()
        summaries = db.get_latest_summary(10)
        insights = db.get_latest_insights(10)
        
        return jsonify({
            'profile': profile,
            'summaries': summaries,
            'insights': insights
        })
    except Exception as e:
        logger.error(f"Memory error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tools')
def tools():
    return jsonify({'tools': list_tools()})

@app.route('/api/memory/clear', methods=['POST'])
def clear_memory():
    """Clear all memory"""
    try:
        token = request.headers.get('X-API-TOKEN')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        db.clear_all_memory()
        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Clear memory error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tts/toggle', methods=['POST'])
def toggle_tts():
    """Toggle TTS on/off"""
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
    """Change TTS voice"""
    try:
        data = request.json
        token = request.headers.get('X-API-TOKEN') or data.get('token') if isinstance(data, dict) else None
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        voice_name = data.get('voice')
        
        voice_mapping = {
            "Phoebe Dragon HD": "en-US-Phoebe:DragonHDLatestNeural",
            "Ava Dragon HD": "en-US-Ava:DragonHDLatestNeural"
        }
        
        if voice_name in voice_mapping:
            success = tts_manager.set_voice(voice_mapping[voice_name])
            return jsonify({'success': success})
        else:
            return jsonify({'error': 'Invalid voice'}), 400
            
    except Exception as e:
        logger.error(f"Voice change error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/search')
def search():
    """Structured memory + optional web snippet search."""
    try:
        q = request.args.get('q', '').strip()
        if not q:
            return jsonify({'query': q, 'memory_hits': [], 'web_snippet': None})
        # Use memory.search_memory directly for structured hits
        hits = db.search_memory(q, limit=8)
        # Optional web snippet via tool (parsing WEB line)
        web_snippet = None
        tool_text = run_tool('search', q)
        for line in tool_text.splitlines():
            if line.startswith('WEB:'):
                web_snippet = line[4:].strip()
        # Convert hits to safe subset
        return jsonify({
            'query': q,
            'memory_hits': hits,
            'web_snippet': web_snippet
        })
    except Exception as e:
        logger.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/health')
def health():
    try:
        memstats = db.get_memory_stats()
        mstats = metrics.snapshot()
        return jsonify({'memory': memstats, 'metrics': mstats})
    except Exception as e:
        logger.error(f"Health error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/config')
def config_info():
    """Expose minimal safe config needed by front-end (e.g., auth requirement)."""
    return jsonify({'auth_required': bool(core_config.API_AUTH_TOKEN)})

def open_browser():
    """Open browser after a short delay"""
    time.sleep(1.5)
    webbrowser.open('http://localhost:5000')

def run_web(host: str = 'localhost', port: int = 5000, open_browser_flag: bool = True):
    """Start the web UI programmatically (used by unified launcher)."""
    print(f"🚀 Starting Companion AI Web Portal on http://{host}:{port}")
    if open_browser_flag:
        print("📱 Opening browser...")
        threading.Thread(target=open_browser, daemon=True).start()
    app.run(debug=False, host=host, port=port)

if __name__ == '__main__':
    run_web()