# companion_ai/web/tools_routes.py
"""Tools blueprint — tool listing, plugins, policy, context, search."""

import uuid
import logging

from flask import Blueprint, request, jsonify, make_response

from companion_ai.core import config as core_config
from companion_ai.memory.sqlite_backend import search_memory
from companion_ai.tools import (
    run_tool,
    list_tools,
    list_plugins,
    get_plugin_catalog,
    get_plugin_policy_state,
    set_workspace_plugin_policy,
)
from companion_ai.web import state

logger = logging.getLogger(__name__)

tools_bp = Blueprint('tools', __name__)


@tools_bp.route('/api/tools')
def tools():
    return jsonify({'tools': list_tools()})


@tools_bp.route('/api/plugins')
def plugins():
    return jsonify({'plugins': list_plugins()})


@tools_bp.route('/api/plugins/catalog')
def plugins_catalog():
    return jsonify({'plugins': get_plugin_catalog()})


@tools_bp.route('/api/plugins/policy', methods=['GET', 'POST'])
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
        result = set_workspace_plugin_policy(enabled_plugins)
        return jsonify(result)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Plugin policy update error: {e}")
        return jsonify({'error': str(e)}), 500


@tools_bp.route('/api/context', methods=['GET'])
def api_context():
    """Return active scope context used for memory/brain selection."""
    payload = request.get_json(silent=True) or {}
    session_key = state._resolve_session_key(payload)
    profile_key = state._resolve_profile_key(payload)
    workspace_key = state._resolve_workspace_key(payload)
    mem0_user_id = state._mem0_user_id_for_scope(session_key, profile_key, workspace_key)
    return jsonify({
        'session_id': session_key,
        'profile_id': profile_key,
        'workspace_id': workspace_key,
        'mem0_user_id': mem0_user_id,
        'known_workspaces': state._list_known_workspaces(),
    })


@tools_bp.route('/api/context/switch', methods=['POST'])
def api_context_switch():
    payload = request.get_json(silent=True) or {}
    workspace_key = state._resolve_workspace_key(payload)
    profile_key = state._resolve_profile_key(payload)
    if bool(payload.get('new_session')):
        session_key = uuid.uuid4().hex[:16]
    else:
        session_key = state._resolve_session_key(payload)

    mem0_user_id = state._mem0_user_id_for_scope(session_key, profile_key, workspace_key)
    if bool(payload.get('migrate_legacy', False)):
        state._maybe_migrate_legacy_scope(mem0_user_id, profile_key, session_key)

    response_payload = {
        'session_id': session_key,
        'profile_id': profile_key,
        'workspace_id': workspace_key,
        'mem0_user_id': mem0_user_id,
        'known_workspaces': state._list_known_workspaces(),
        'switched': True,
    }
    resp = make_response(jsonify(response_payload))
    resp.set_cookie('companion_session_id', session_key, httponly=True, samesite='Lax')
    resp.set_cookie('companion_profile_id', profile_key, httponly=True, samesite='Lax')
    resp.set_cookie('companion_workspace_id', workspace_key, httponly=True, samesite='Lax')
    return resp


@tools_bp.route('/api/search')
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
