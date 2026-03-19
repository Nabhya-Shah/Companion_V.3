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
    list_tool_runtime,
    list_plugins,
    get_plugin_catalog,
    get_plugin_policy_state,
    set_workspace_plugin_policy,
    get_pending_approvals,
    resolve_approval,
    list_approval_required_tools,
    set_approval_required_tools,
    mark_tool_requires_approval,
    unmark_tool_requires_approval,
)
from companion_ai.tools.remote_actions import (
    list_capabilities as list_remote_action_capabilities,
    request_execution_token as request_remote_action_token,
    execute_simulated_action,
    RemoteActionRequest,
)
from companion_ai.web import state

logger = logging.getLogger(__name__)

tools_bp = Blueprint('tools', __name__)


@tools_bp.route('/api/tools')
def tools():
    return jsonify({'tools': list_tools()})


@tools_bp.route('/api/tools/catalog')
def tools_catalog():
    return jsonify({'tools': list_tool_runtime()})


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
        blocked = state.enforce_feature_permission('tools_execute')
        if blocked:
            return blocked
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


# ---------------------------------------------------------------------------
# Human-In-The-Loop Approval endpoints
# ---------------------------------------------------------------------------

@tools_bp.route('/api/approvals', methods=['GET'])
def pending_approvals():
    """List all pending tool approval requests."""
    return jsonify({'approvals': get_pending_approvals()})


@tools_bp.route('/api/approvals/<request_id>', methods=['POST'])
def resolve_approval_endpoint(request_id):
    """Approve or deny a pending tool execution request."""
    data = request.get_json(silent=True) or {}
    decision = data.get('decision', '').lower()
    if decision not in ('approve', 'deny'):
        return jsonify({'error': "decision must be 'approve' or 'deny'"}), 400

    result = resolve_approval(request_id, approved=(decision == 'approve'))
    if result is None:
        return jsonify({'error': 'Approval request not found or already resolved'}), 404

    return jsonify({
        'status': result.get('status'),
        'tool': result.get('tool'),
        'id': request_id,
        'approval_token': result.get('approval_token'),
    })


@tools_bp.route('/api/approvals/config', methods=['GET', 'POST'])
def approval_config():
    """View or update which tools require approval."""
    if request.method == 'GET':
        return jsonify({'requires_approval': list_approval_required_tools()})

    data = request.get_json(silent=True) or {}
    tools_list = data.get('tools')
    action = data.get('action', 'set')  # 'set', 'add', 'remove'

    if not isinstance(tools_list, list):
        return jsonify({'error': 'tools must be a list'}), 400

    if action == 'add':
        for t in tools_list:
            mark_tool_requires_approval(t)
    elif action == 'remove':
        for t in tools_list:
            unmark_tool_requires_approval(t)
    else:
        # Full replace
        set_approval_required_tools(tools_list)

    return jsonify({'requires_approval': list_approval_required_tools()})


@tools_bp.route('/api/remote-actions/capabilities', methods=['GET'])
def remote_action_capabilities():
    return jsonify({'capabilities': list_remote_action_capabilities()})


@tools_bp.route('/api/remote-actions/approve', methods=['POST'])
def remote_action_approve():
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    capability = str(data.get('capability') or '').strip()
    action = str(data.get('action') or '').strip()
    result = request_remote_action_token(capability, action)
    if not result.get('ok'):
        reason = result.get('reason')
        code = 400
        if reason in {'disabled', 'allowlist_denied', 'unsupported_capability'}:
            code = 403
        return jsonify({'error': result.get('error'), 'reason': reason}), code
    return jsonify(result)


@tools_bp.route('/api/remote-actions/simulate', methods=['POST'])
def remote_action_simulate():
    blocked = state.enforce_feature_permission('tools_execute')
    if blocked:
        return blocked

    data = request.get_json(silent=True) or {}
    req = RemoteActionRequest(
        capability=str(data.get('capability') or '').strip(),
        action=str(data.get('action') or '').strip(),
        target=str(data.get('target') or '').strip(),
        params=data.get('params') if isinstance(data.get('params'), dict) else {},
        approval_token=str(data.get('approval_token') or '').strip() or None,
    )
    envelope = execute_simulated_action(req)
    status = envelope.get('status')
    if status == 'completed':
        return jsonify(envelope)
    if status == 'rejected':
        reason = envelope.get('reason')
        code = 403 if reason in {'disabled', 'allowlist_denied'} else 400
        return jsonify(envelope), code
    return jsonify(envelope), 500
