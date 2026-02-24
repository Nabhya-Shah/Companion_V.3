# companion_ai/web/chat_routes.py
"""Chat blueprint — streaming send, debug, history, SSE stream, stop."""

import json
import time
import logging
from datetime import datetime

from flask import Blueprint, request, jsonify, Response, stream_with_context

from companion_ai.core import config as core_config
from companion_ai.conversation_manager import ConversationSession
from companion_ai.services.tts import tts_manager
from companion_ai.services import jobs as job_manager_module
from companion_ai.web import state

logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__)


@chat_bp.route('/api/chat/send', methods=['POST'])
def chat_streaming():
    """Streaming chat endpoint - sends response tokens as they arrive."""
    try:
        data = request.json or {}
        session_key, profile_key, mem0_user_id, active_history, active_session = state._get_active_session_state(data)
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
                        yield f"data: {json.dumps({'meta': chunk['data']})}\n\n"
                    elif isinstance(chunk, dict) and chunk.get('type') == 'token_meta':
                        yield f"data: {json.dumps({'token_meta': chunk['data']})}\n\n"
                    else:
                        full_response += chunk
                        yield f"data: {json.dumps({'chunk': chunk})}\n\n"

                from companion_ai.llm_interface import get_last_token_usage
                token_usage = get_last_token_usage()
                memory_saved = core_config.USE_MEM0

                tts_enabled = data.get('tts_enabled', False)
                tts_available = tts_manager.is_enabled or getattr(tts_manager, 'provider', 'azure') == 'groq'
                if tts_enabled and tts_available and full_response.strip():
                    try:
                        logger.info(f"🔊 TTS: Speaking response with provider={getattr(tts_manager, 'provider', 'azure')}")
                        tts_manager.speak_text(full_response, blocking=False)
                    except Exception as tts_error:
                        logger.warning(f"TTS error: {tts_error}")

                yield f"data: {json.dumps({'done': True, 'full_response': full_response, 'tokens': token_usage, 'memory_saved': memory_saved})}\n\n"

                entry = {
                    'user': user_message,
                    'ai': full_response,
                    'timestamp': datetime.now().isoformat(),
                    'persona': 'Companion',
                    'tokens': token_usage,
                }
                active_history.append(entry)

                with state.history_condition:
                    state.history_version += 1
                    state.history_condition.notify_all()

            except Exception as e:
                logger.error(f"Streaming error: {e}")
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        return Response(generate(), mimetype='text/event-stream')

    except Exception as e:
        logger.error(f"Chat streaming error: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/debug/chat', methods=['POST'])
def debug_chat():
    """Debug endpoint for AI agent testing."""
    try:
        data = request.json or {}
        session_key, profile_key, mem0_user_id, active_history, active_session = state._get_active_session_state(data)
        user_message = data.get('message', '').strip()
        persona = data.get('persona', 'Companion')

        if not user_message:
            return jsonify({'error': 'Empty message'}), 400

        ai_response, memory_saved = active_session.process_message(
            user_message,
            active_history,
            memory_user_id=mem0_user_id,
        )

        if not ai_response or not ai_response.strip():
            logger.warning("Empty AI response in debug endpoint, using fallback")
            ai_response = "I'm here! Sorry, I got a bit stuck there. What were you saying?"

        if ai_response.startswith("Chat:") or ai_response.startswith("CHAT:"):
            ai_response = ai_response[5:].strip()

        entry = {
            'user': user_message,
            'ai': ai_response,
            'timestamp': datetime.now().isoformat(),
            'persona': persona,
            'source': 'debug_api'
        }
        active_history.append(entry)
        with state.history_condition:
            state.history_version += 1
            state.history_condition.notify_all()

        if len(active_history) % 5 == 0:
            try:
                logger.info(f"Auto-processing memory at {len(active_history)} debug messages (session={session_key})")
                active_session.process_session_memory()
            except Exception as mem_err:
                logger.warning(f"Memory processing error: {mem_err}")

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


@chat_bp.route('/api/debug/reset', methods=['POST'])
def debug_reset():
    """Clear conversation history and start a fresh ConversationSession."""
    try:
        data = request.get_json(silent=True) or {}
        session_key, _, _, active_history, _ = state._get_active_session_state(data)
        with state._session_lock:
            active_history.clear()
            state._session_managers[session_key] = ConversationSession()
        with state.history_condition:
            state.history_version += 1
            state.history_condition.notify_all()
        return jsonify({'reset': True, 'history_length': 0})
    except Exception as e:
        logger.error(f"Debug reset error: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/chat/history')
def get_chat_history():
    """Get conversation history for live updates."""
    try:
        _, _, _, active_history, _ = state._get_active_session_state()
        return jsonify({'history': active_history, 'count': len(active_history)})
    except Exception as e:
        logger.error(f"Get history error: {e}")
        return jsonify({'error': str(e)}), 500


@chat_bp.route('/api/chat/stream')
def chat_history_stream():
    """Server-sent events stream pushing history updates AND job updates."""
    session_key, _, _, _, _ = state._get_active_session_state()

    def event_stream():
        last_version = -1
        last_job_check = 0
        notified_jobs = set()
        try:
            existing = job_manager_module.get_active_jobs()
            for job in existing:
                if job.get('status') in ('COMPLETED', 'FAILED'):
                    notified_jobs.add(job.get('id'))
        except Exception as e:
            logger.error(f"Job stream init error: {e}")

        while True:
            with state.history_condition:
                if state.history_version == last_version:
                    state.history_condition.wait(timeout=1.0)

                current_version = state.history_version
                with state._session_lock:
                    snapshot = list(state._session_histories.get(session_key, []))

            if current_version != last_version:
                state.sse_sequence += 1
                state.sse_counters['history.updated'] = state.sse_counters.get('history.updated', 0) + 1
                state.sse_last_event_ts = datetime.now().isoformat()
                payload = json.dumps({
                    'type': 'history',
                    'event': 'history.updated',
                    'seq': state.sse_sequence,
                    'ts': datetime.now().isoformat(),
                    'payload': {'history': snapshot, 'count': len(snapshot)},
                    'history': snapshot,
                    'count': len(snapshot),
                })
                last_version = current_version
                yield f"data: {payload}\n\n"

            now = time.time()
            if now - last_job_check > 2.0:
                last_job_check = now
                try:
                    jobs = job_manager_module.get_active_jobs()
                    for job in jobs:
                        if job['status'] in ('COMPLETED', 'FAILED') and job['id'] not in notified_jobs:
                            state.sse_sequence += 1
                            state.sse_counters['job.updated'] = state.sse_counters.get('job.updated', 0) + 1
                            state.sse_last_event_ts = datetime.now().isoformat()
                            payload = json.dumps({
                                'type': 'job_update',
                                'event': 'job.updated',
                                'seq': state.sse_sequence,
                                'ts': datetime.now().isoformat(),
                                'payload': {'job': job},
                                'job': job,
                            })
                            yield f"data: {payload}\n\n"
                            notified_jobs.add(job['id'])
                except Exception as e:
                    logger.error(f"Job stream error: {e}")

            yield ": keep-alive\n\n"

    response = Response(stream_with_context(event_stream()), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


@chat_bp.route('/api/events/diagnostics', methods=['GET'])
def event_diagnostics():
    return jsonify({
        'history_version': state.history_version,
        'sse_sequence': state.sse_sequence,
        'counters': dict(state.sse_counters),
        'last_event_ts': state.sse_last_event_ts,
    })


@chat_bp.route('/api/chat/stop', methods=['POST'])
def stop_chat():
    """Stop chat generation and audio."""
    try:
        if tts_manager:
            tts_manager.stop_speech()
        return jsonify({'status': 'ok'})
    except Exception as e:
        logger.error(f"Stop error: {e}")
        return jsonify({'error': str(e)}), 500
