# companion_ai/web/media_routes.py
"""Media blueprint — TTS configuration, vision control, voice change."""

import logging

from flask import Blueprint, request, jsonify

from companion_ai.core import config as core_config
from companion_ai.services.tts import tts_manager
from companion_ai.agents.vision import vision_manager

logger = logging.getLogger(__name__)

media_bp = Blueprint('media', __name__)


# --- TTS Endpoints ---

@media_bp.route('/api/tts/toggle', methods=['POST'])
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


@media_bp.route('/api/tts/voices', methods=['GET'])
def get_voices():
    try:
        voices = tts_manager.get_available_voices()
        return jsonify({'voices': voices})
    except Exception as e:
        logger.error(f"Get voices error: {e}")
        return jsonify({'error': str(e)}), 500


@media_bp.route('/api/tts/config', methods=['GET', 'POST'])
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
            provider = data.get('provider')

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


@media_bp.route('/api/tts/config/legacy', methods=['POST'])
def config_tts():
    """Update TTS configuration (legacy endpoint)."""
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


# --- Vision Endpoints ---

@media_bp.route('/api/vision/toggle', methods=['POST'])
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


@media_bp.route('/api/vision/status', methods=['GET'])
def vision_status():
    return jsonify({
        'enabled': vision_manager.watcher_enabled,
        'log_count': len(vision_manager.visual_log),
        'last_update': vision_manager.visual_log[-1]['timestamp'] if vision_manager.visual_log else None,
    })


@media_bp.route('/api/vision/analyze', methods=['POST'])
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


# --- Voice Change ---

@media_bp.route('/api/voice/change', methods=['POST'])
def change_voice():
    """Legacy voice change endpoint."""
    try:
        data = request.json or {}
        token = request.headers.get('X-API-TOKEN') or data.get('token') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        voice_name = data.get('voice')
        mapping = {
            'Phoebe Dragon HD': 'en-US-Phoebe:DragonHDLatestNeural',
            'Ava Dragon HD': 'en-US-Ava:DragonHDLatestNeural',
        }
        target_voice = mapping.get(voice_name, voice_name)
        success = tts_manager.set_voice(target_voice)
        return jsonify({'success': success})
    except Exception as e:
        logger.error(f"Voice change error: {e}")
        return jsonify({'error': str(e)}), 500
