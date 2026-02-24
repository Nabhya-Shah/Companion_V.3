# companion_ai/web/loxone_routes.py
"""Loxone blueprint — smart home room statuses, health, light control."""

import logging

from flask import Blueprint, request, jsonify

logger = logging.getLogger(__name__)

loxone_bp = Blueprint('loxone', __name__)


@loxone_bp.route('/api/loxone/rooms', methods=['GET'])
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


@loxone_bp.route('/api/loxone/health', methods=['GET'])
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


@loxone_bp.route('/api/loxone/light/<action>', methods=['POST'])
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
