import asyncio
from datetime import datetime

from flask import Blueprint, jsonify, request
from companion_ai.services.workflows import get_manager
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
    manager = get_manager()
    try:
        results = asyncio.run(manager.execute_workflow(workflow_id))
        # Check if we should broadcast back any chat targeted steps
        chat_updates = []
        for res in results:
            if res.get("output_target") == "chat":
                chat_updates.append({
                    "ai": res.get("response", ""),
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {
                        "source": "workflow",
                        "workflow_id": workflow_id,
                        "step_id": res.get("step_id"),
                    },
                })

        if chat_updates:
            try:
                from companion_ai.web import state

                session_key, _, _, active_history, _ = state._get_active_session_state()
                active_history.extend(chat_updates)
                with state.history_condition:
                    state.history_version += 1
                    state.history_condition.notify_all()
                logger.info(f"Workflow {workflow_id} appended {len(chat_updates)} chat update(s) to session {session_key}")
            except Exception as broadcast_err:
                logger.warning(f"Workflow chat history update skipped: {broadcast_err}")
                
        return jsonify({"status": "success", "workflow_id": workflow_id, "results": results})
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:
        logger.error(f"Error running workflow {workflow_id}: {e}")
        return jsonify({"error": "Internal server error"}), 500