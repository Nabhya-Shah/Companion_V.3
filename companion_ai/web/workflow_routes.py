import asyncio
from datetime import datetime

from flask import Blueprint, jsonify, request
from companion_ai.services.workflows import get_manager
from companion_ai.web import state
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('workflows', __name__, url_prefix='/api/workflows')

@bp.route('', methods=['GET'])
def list_workflows():
    """List all available workflows."""
    manager = get_manager()
    manager.reload_workflows() # Pick up new ones automatically
    return jsonify({"workflows": manager.list_workflows()})

@bp.route('/<workflow_id>', methods=['GET'])
def get_workflow(workflow_id):
    """Get details for a specific workflow."""
    manager = get_manager()
    wf = manager.get_workflow(workflow_id)
    if not wf:
        return jsonify({"error": "Workflow not found"}), 404
        
    return jsonify({
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "steps": [{"id": s.id, "action": s.action, "text": s.text} for s in wf.steps]
    })

@bp.route('/<workflow_id>/run', methods=['POST'])
def run_workflow(workflow_id):
    """Execute a workflow and return the results."""
    blocked = state.enforce_feature_permission('workflows_run')
    if blocked:
        return blocked

    manager = get_manager()
    data = request.get_json(silent=True) or {}
    if hasattr(manager, 'can_run_workflow'):
        can_run, reason = manager.can_run_workflow(workflow_id, approval_token=data.get('approval_token'))
        if not can_run:
            code = 404 if reason == 'workflow_not_found' else 403
            return jsonify({'error': f"Workflow '{workflow_id}' denied", 'reason': reason}), code

    try:
        results = asyncio.run(manager.execute_workflow(workflow_id))
        # Check if we should broadcast back any chat targeted steps
        chat_updates = []
        chat_target_count = 0
        for res in results:
            if res.get("output_target") == "chat":
                chat_target_count += 1
                chat_updates.append({
                    "ai": res.get("response", ""),
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "source": "workflow",
                        "workflow_id": workflow_id,
                        "step_id": res.get("step_id"),
                    },
                })

        chat_appended_count = 0
        if chat_updates:
            try:
                session_key, _, _, active_history, _ = state._get_active_session_state()
                active_history.extend(chat_updates)
                chat_appended_count = len(chat_updates)
                with state.history_condition:
                    state.history_version += 1
                    state.history_condition.notify_all()
                logger.info(f"Workflow {workflow_id} appended {len(chat_updates)} chat update(s) to session {session_key}")
            except Exception as broadcast_err:
                logger.warning(f"Workflow chat history update skipped: {broadcast_err}")

        chat_delivered = chat_target_count > 0 and chat_appended_count == chat_target_count

        workspace_id = state._resolve_workspace_key(data)
        if hasattr(manager, 'record_workflow_outcome'):
            manager.record_workflow_outcome(
                workflow_id,
                results=results,
                status='COMPLETED',
                workspace_id=workspace_id,
                source='manual',
            )
                
        return jsonify({
            "status": "success",
            "workflow_id": workflow_id,
            "results": results,
            "chat_target_count": chat_target_count,
            "chat_appended_count": chat_appended_count,
            "chat_delivered": chat_delivered,
        })
    except ValueError as e:
        if hasattr(manager, 'record_workflow_outcome'):
            manager.record_workflow_outcome(
                workflow_id,
                results=[],
                status='FAILED',
                workspace_id=state._resolve_workspace_key(data),
                source='manual',
                error=str(e),
            )
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Error running workflow {workflow_id}: {e}")
        if hasattr(manager, 'record_workflow_outcome'):
            manager.record_workflow_outcome(
                workflow_id,
                results=[],
                status='FAILED',
                workspace_id=state._resolve_workspace_key(data),
                source='manual',
                error=str(e),
            )
        return jsonify({"error": "Internal server error"}), 500


@bp.route('/skills', methods=['GET'])
def list_skills():
    manager = get_manager()
    manager.reload_workflows()
    return jsonify({'skills': manager.list_skills()})


@bp.route('/skills/<workflow_id>/enable', methods=['POST'])
def enable_skill(workflow_id):
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    from companion_ai.core import config as core_config

    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    manager = get_manager()
    try:
        return jsonify(manager.set_skill_enabled(workflow_id, True))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404


@bp.route('/skills/<workflow_id>/disable', methods=['POST'])
def disable_skill(workflow_id):
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    from companion_ai.core import config as core_config

    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    manager = get_manager()
    try:
        return jsonify(manager.set_skill_enabled(workflow_id, False))
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404


@bp.route('/skills/<workflow_id>/approval-token', methods=['POST'])
def skill_approval_token(workflow_id):
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    from companion_ai.core import config as core_config

    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    manager = get_manager()
    try:
        approval_token = manager.issue_skill_approval_token(workflow_id)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 404

    return jsonify({'workflow_id': workflow_id, 'approval_token': approval_token})


@bp.route('/runs', methods=['GET'])
def workflow_runs():
    manager = get_manager()
    limit = int(request.args.get('limit') or 20)
    return jsonify({'runs': manager.list_recent_runs(limit=limit)})