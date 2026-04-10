# companion_ai/web/system_routes.py
"""System blueprint — index, graph, shutdown, health, config, models,
tokens, routing, jobs, tasks, schedules, loops, token-budget, brain auto-write."""

import os
import json
import glob
import uuid
import time
import signal
import logging
import threading
from datetime import datetime, date

from flask import Blueprint, request, jsonify, render_template, make_response

from companion_ai.llm_interface import (
    generate_response, get_token_stats, reset_token_stats, get_last_token_usage,
)
from companion_ai.conversation_manager import ConversationSession
from companion_ai.core import config as core_config
from companion_ai.core import metrics
from companion_ai.memory.sqlite_backend import get_memory_stats
from companion_ai.memory import mem0_backend as mem0
from companion_ai.memory import write_queue
from companion_ai.orchestration import get_runtime_descriptor as get_orchestration_runtime_descriptor
from companion_ai.local_llm import VLLMBackend, OllamaBackend
from companion_ai.tools import system_tools as system_tools_module
from companion_ai.services import jobs as job_manager_module
from companion_ai.web import state

logger = logging.getLogger(__name__)

system_bp = Blueprint('system', __name__)


# ==========================================================================
# Page routes
# ==========================================================================

@system_bp.route('/')
def index():
    resp = make_response(render_template('index.html'))
    if not request.cookies.get('companion_session_id'):
        resp.set_cookie('companion_session_id', uuid.uuid4().hex[:16], httponly=True, samesite='Lax')
    if not request.cookies.get('companion_profile_id'):
        resp.set_cookie('companion_profile_id', 'default', httponly=True, samesite='Lax')
    if not request.cookies.get('companion_workspace_id'):
        resp.set_cookie('companion_workspace_id', 'default', httponly=True, samesite='Lax')
    if core_config.API_AUTH_TOKEN:
        if not request.cookies.get('api_token'):
            resp.set_cookie('api_token', core_config.API_AUTH_TOKEN, httponly=True, samesite='Lax')
    return resp


@system_bp.route('/graph')
def graph():
    """Interactive knowledge graph visualization."""
    return render_template('graph.html')


# ==========================================================================
# Shutdown
# ==========================================================================

@system_bp.route('/api/shutdown', methods=['POST'])
def shutdown():
    """Gracefully shutdown the server and trigger persona evolution."""
    data = request.get_json(silent=True) or {}
    token = (request.headers.get('X-API-TOKEN') or data.get('token')
             or request.cookies.get('api_token'))
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    logger.info("Shutdown requested. Saving session log and triggering persona evolution...")

    # Save session log to brain folder
    try:
        from companion_ai.brain_manager import get_brain
        workspace_key = state._resolve_workspace_key(data)
        brain = get_brain(workspace_id=workspace_key)

        session_date = datetime.now().strftime("%Y-%m-%d")
        session_time = datetime.now().strftime("%H:%M")
        history = state.conversation_session.conversation_history
        msg_count = len(history)

        from companion_ai.llm_interface import get_token_stats as _gts
        token_stats = _gts()
        total_tokens = token_stats.get('total_input', 0) + token_stats.get('total_output', 0)
        request_count = token_stats.get('requests', 0)

        log_content = f"# Session Log - {session_date} {session_time}\n\n"
        log_content += f"**Messages:** {msg_count}\n"
        log_content += f"**Total Tokens:** {total_tokens:,} ({request_count} requests)\n\n"

        if token_stats.get('by_model'):
            log_content += "## Token Usage by Model\n\n"
            for model, usage in token_stats['by_model'].items():
                model_total = usage.get('input', 0) + usage.get('output', 0)
                log_content += f"- **{model}**: {model_total:,} tokens ({usage.get('count', 0)} calls)\n"
            log_content += "\n"

        if history:
            log_content += "## Conversation Highlights\n\n"
            for msg in history[-5:]:
                user_msg = msg.get('user', '')[:100]
                ai_msg = msg.get('ai', '')[:100]
                if user_msg:
                    log_content += f"- **User**: {user_msg}...\n" if len(msg.get('user', '')) > 100 else f"- **User**: {user_msg}\n"
                if ai_msg:
                    log_content += f"- **AI**: {ai_msg}...\n\n" if len(msg.get('ai', '')) > 100 else f"- **AI**: {ai_msg}\n\n"

        log_file = f"logs/session_{session_date}.md"
        brain.write(log_file, log_content + "---\n\n", append=True)
        logger.info(f"Session log saved: {log_file}")

    except Exception as e:
        logger.error(f"Failed to save session log: {e}")

    # Trigger Persona Evolution
    try:
        from companion_ai.services.persona import analyze_and_evolve as _persona_evolve
        history = state.conversation_session.conversation_history
        if history:
            _persona_evolve(history)
            logger.info("Persona evolution complete.")
        else:
            logger.info("No conversation history to analyze.")
    except Exception as e:
        logger.error(f"Persona evolution failed during shutdown: {e}")

    # Shutdown Flask
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        os.kill(os.getpid(), signal.SIGINT)
        return jsonify({'status': 'Shutting down via signal...'})

    func()
    job_manager_module.stop_worker()

    return jsonify({'status': 'Server shutting down...'})


# ==========================================================================
# Jobs / Tasks / Schedules
# ==========================================================================

@system_bp.route('/api/jobs/active', methods=['GET'])
def get_active_jobs():
    """Get active and recently completed jobs."""
    token = (request.headers.get('X-API-TOKEN') or request.args.get('token')
             or request.cookies.get('api_token'))
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401
    jobs = job_manager_module.get_active_jobs()
    return jsonify({'jobs': jobs})


@system_bp.route('/api/token-budget', methods=['GET'])
def token_budget():
    """Get current token budget status."""
    try:
        from companion_ai.services.token_budget import get_budget_status, should_auto_save
        status = get_budget_status()
        status['should_auto_save'] = should_auto_save()
        return jsonify(status)
    except Exception as e:
        logger.error(f"Token budget error: {e}")
        return jsonify({'error': str(e), 'used': 0, 'limit': 500000, 'percent': 0}), 500


@system_bp.route('/api/brain/auto-write', methods=['POST'])
def brain_auto_write():
    """Trigger brain auto-write (end of conversation summary)."""
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        from companion_ai.brain_manager import get_brain
        from companion_ai.llm_interface import generate_model_response

        workspace_key = state._resolve_workspace_key()
        brain = get_brain(workspace_id=workspace_key)

        history = state.conversation_session.conversation_history[-10:]
        if not history:
            return jsonify({'success': False, 'reason': 'No conversation history'})

        conv_text = "\n".join([
            f"{msg.get('role', 'user')}: {msg.get('content', '')[:200]}"
            for msg in history
        ])

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
            core_config.PRIMARY_MODEL,
        )

        today = str(date.today())
        brain.write(
            f"memories/daily/{today}.md",
            f"# Daily Summary - {today}\n\n{summary}",
            append=False,
        )

        logger.info(f"Brain auto-write complete: memories/daily/{today}.md")
        return jsonify({'success': True, 'file': f'memories/daily/{today}.md'})

    except Exception as e:
        logger.error(f"Brain auto-write error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/continuity', methods=['GET'])
def continuity_list_or_latest():
    """Get latest continuity snapshot or recent snapshot history."""
    try:
        from companion_ai.services.continuity import get_latest_snapshot, list_snapshots

        latest = request.args.get('latest', 'true').lower() in {'1', 'true', 'yes'}
        if latest:
            snapshot = get_latest_snapshot()
            return jsonify({'snapshot': snapshot})

        limit = int(request.args.get('limit') or 10)
        return jsonify({'snapshots': list_snapshots(limit=limit)})
    except Exception as e:
        logger.error(f"Continuity list error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/continuity/refresh', methods=['POST'])
def continuity_refresh():
    """Force-generate a new continuity snapshot."""
    try:
        data = request.get_json(silent=True) or {}
        token = (
            request.headers.get('X-API-TOKEN')
            or data.get('token')
            or request.cookies.get('api_token')
        )
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        from companion_ai.services.continuity import generate_continuity_if_due

        snapshot = generate_continuity_if_due(force=True)
        return jsonify({'status': 'success', 'snapshot': snapshot})
    except Exception as e:
        logger.error(f"Continuity refresh error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/tasks', methods=['GET'])
def get_tasks():
    """Get list of active background tasks."""
    tasks = job_manager_module.get_tasks_for_ui()
    return jsonify({'tasks': tasks, 'count': len(tasks)})


@system_bp.route('/api/tasks/<task_id>', methods=['GET'])
def get_task_status(task_id):
    """Get detailed status of a specific task."""
    timeline = job_manager_module.get_task_timeline(task_id)
    if not timeline:
        return jsonify({'error': 'Task not found'}), 404
    return jsonify({'status': 'success', 'data': {'id': task_id, 'timeline': timeline}})


@system_bp.route('/api/tasks/<task_id>/cancel', methods=['POST'])
def cancel_task(task_id):
    """Cancel a running task."""
    ok = job_manager_module.cancel_job(task_id)
    if not ok:
        return jsonify({'status': 'error', 'error': 'Task not found or not cancellable'}), 404
    return jsonify({'status': 'success'})


@system_bp.route('/api/schedules', methods=['GET', 'POST'])
def schedules():
    if request.method == 'GET':
        rows = job_manager_module.list_schedules()
        return jsonify({'schedules': rows, 'count': len(rows)})

    data = request.get_json(silent=True) or {}
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    description = (data.get('description') or '').strip()
    try:
        interval_minutes = state._parse_interval_minutes(data)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception:
        return jsonify({'error': 'Invalid interval/cadence value'}), 400
    tool_name = (data.get('tool_name') or 'start_background_task').strip()
    tool_args = data.get('tool_args') if isinstance(data.get('tool_args'), dict) else {}
    timezone = (data.get('timezone') or 'UTC').strip() or 'UTC'
    retry_limit = int(data.get('retry_limit') or 0)
    retry_backoff_minutes = int(data.get('retry_backoff_minutes') or 1)
    if not description or interval_minutes <= 0:
        return jsonify({'error': 'description and interval_minutes/cadence are required'}), 400
    if retry_limit < 0 or retry_backoff_minutes <= 0:
        return jsonify({'error': 'retry_limit must be >= 0 and retry_backoff_minutes must be > 0'}), 400

    schedule_id = job_manager_module.add_schedule(
        description,
        interval_minutes,
        tool_name,
        tool_args,
        timezone=timezone,
        retry_limit=retry_limit,
        retry_backoff_minutes=retry_backoff_minutes,
    )
    return jsonify({'id': schedule_id, 'status': 'created'})


@system_bp.route('/api/schedules/<schedule_id>/toggle', methods=['POST'])
def schedule_toggle(schedule_id):
    data = request.get_json(silent=True) or {}
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401
    enabled = bool(data.get('enabled', True))
    ok = job_manager_module.set_schedule_enabled(schedule_id, enabled)
    if not ok:
        return jsonify({'error': 'Schedule not found'}), 404
    return jsonify({'status': 'success', 'enabled': enabled})


@system_bp.route('/api/schedules/<schedule_id>/run', methods=['POST'])
def schedule_run_now(schedule_id):
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401
    result = job_manager_module.run_schedule_now(schedule_id)
    if not result.get('ok'):
        err = result.get('error') or 'Failed to run schedule'
        if err == 'Schedule not found':
            return jsonify({'error': err}), 404
        if result.get('reason') == 'policy_denied':
            return jsonify({'error': err}), 400
        return jsonify({'error': err}), 500
    return jsonify({'status': 'success', 'job_id': result.get('job_id')})


@system_bp.route('/api/schedules/<schedule_id>', methods=['PUT', 'DELETE'])
def schedule_modify(schedule_id):
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    if request.method == 'DELETE':
        ok = job_manager_module.delete_schedule(schedule_id)
        if not ok:
            return jsonify({'error': 'Schedule not found'}), 404
        return jsonify({'status': 'success', 'deleted': True})

    data = request.get_json(silent=True) or {}
    description = (data.get('description') or '').strip()
    try:
        interval_minutes = state._parse_interval_minutes(data)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception:
        return jsonify({'error': 'Invalid interval/cadence value'}), 400

    tool_name = (data.get('tool_name') or 'start_background_task').strip()
    tool_args = data.get('tool_args') if isinstance(data.get('tool_args'), dict) else {}
    timezone = (data.get('timezone') or 'UTC').strip() or 'UTC'
    retry_limit = int(data.get('retry_limit') or 0)
    retry_backoff_minutes = int(data.get('retry_backoff_minutes') or 1)

    if not description or interval_minutes <= 0:
        return jsonify({'error': 'description and interval_minutes/cadence are required'}), 400
    if retry_limit < 0 or retry_backoff_minutes <= 0:
        return jsonify({'error': 'retry_limit must be >= 0 and retry_backoff_minutes must be > 0'}), 400

    ok = job_manager_module.update_schedule(
        schedule_id,
        description,
        interval_minutes,
        tool_name,
        tool_args,
        timezone=timezone,
        retry_limit=retry_limit,
        retry_backoff_minutes=retry_backoff_minutes,
    )
    if not ok:
        return jsonify({'error': 'Schedule not found'}), 404
    return jsonify({'status': 'success', 'updated': True})


@system_bp.route('/api/insights', methods=['GET'])
def list_insights_api():
    """List proactive insights and unread count."""
    try:
        from companion_ai.services.insights import list_insights, unread_count

        unread_only = request.args.get('unread', '').strip().lower() in {'1', 'true', 'yes'}
        limit = int(request.args.get('limit', '20'))
        rows = list_insights(unread_only=unread_only, limit=max(limit, 1))
        return jsonify({'insights': rows, 'count': len(rows), 'unread_count': unread_count()})
    except Exception as e:
        logger.error(f"Insights list error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/insights/<int:insight_id>/status', methods=['POST'])
def update_insight_status_api(insight_id: int):
    """Update insight status: unread/read/dismissed."""
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    status = (data.get('status') or '').strip().lower()
    if status not in {'unread', 'read', 'dismissed'}:
        return jsonify({'error': "status must be one of: unread, read, dismissed"}), 400

    try:
        from companion_ai.services.insights import update_status

        ok = update_status(insight_id, status)
        if not ok:
            return jsonify({'error': 'Insight not found'}), 404
        return jsonify({'status': 'success', 'id': insight_id, 'state': status})
    except Exception as e:
        logger.error(f"Insights status error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/insights/generate', methods=['POST'])
def generate_insight_now_api():
    """Force-generate a proactive insight digest now (debug/admin)."""
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        from companion_ai.services.insights import generate_daily_insight_if_due

        created = generate_daily_insight_if_due(force=True)
        if not created:
            return jsonify({'status': 'noop', 'reason': 'No digest content available'})
        return jsonify({'status': 'created', 'insight': created})
    except Exception as e:
        logger.error(f"Insights generate error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/loops/capabilities', methods=['GET'])
def get_loop_capabilities():
    """Get capabilities of all local loops (for debugging)."""
    try:
        from companion_ai.local_loops import get_capabilities_summary, list_loops
        return jsonify({
            'summary': get_capabilities_summary(),
            'loops': list_loops(),
        })
    except Exception as e:
        logger.error(f"Error getting loop capabilities: {e}")
        return jsonify({'error': str(e)}), 500


# ==========================================================================
# Health / Config / Models / Tokens
# ==========================================================================

def _readiness_snapshot() -> dict:
    worker = getattr(job_manager_module, '_worker_thread', None)
    worker_alive = bool(worker and worker.is_alive())

    mem0_enabled = bool(core_config.USE_MEM0)
    mem0_initialized = bool(getattr(mem0, '_memory_instance', None) is not None)

    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    brain_root = os.path.join(project_root, 'BRAIN')
    data_root = os.path.join(project_root, 'data')

    queue_depth = 0
    queue_oldest_created_at = None
    queue_probe_failed = False
    try:
        queued_rows = write_queue.list_queued_writes(limit=5000)
        queue_depth = len(queued_rows)
        if queued_rows:
            queue_oldest_created_at = queued_rows[-1].get('created_at')
    except Exception:
        queue_probe_failed = True

    local_runtime = _local_runtime_snapshot()

    snapshot = {
        'status': 'ready',
        'api_auth_configured': bool(core_config.API_AUTH_TOKEN),
        'jobs_worker_alive': worker_alive,
        'mem0_enabled': mem0_enabled,
        'mem0_initialized': mem0_initialized,
        'brain_dir_exists': os.path.isdir(brain_root),
        'data_dir_exists': os.path.isdir(data_root),
        'memory_write_queue_depth': queue_depth,
        'memory_write_queue_oldest_created_at': queue_oldest_created_at,
        'orchestration': get_orchestration_runtime_descriptor(),
        'local_runtime': local_runtime,
    }

    degraded_reasons = []
    if not worker_alive:
        degraded_reasons.append('jobs_worker_down')
    if mem0_enabled and not mem0_initialized:
        degraded_reasons.append('mem0_not_initialized')
    if not snapshot['data_dir_exists']:
        degraded_reasons.append('data_dir_missing')
    if queue_probe_failed:
        degraded_reasons.append('memory_write_queue_probe_failed')
    elif queue_depth > 100:
        degraded_reasons.append('memory_write_queue_backlog')
    if (not local_runtime.get('selected_runtime_available', True)
            and not local_runtime.get('cloud_fallback_enabled', True)):
        degraded_reasons.append('local_runtime_unavailable_no_fallback')

    if degraded_reasons:
        snapshot['status'] = 'degraded'
        snapshot['reasons'] = degraded_reasons

    return snapshot


def _local_runtime_snapshot() -> dict:
    cfg = core_config.get_local_model_runtime_config()
    runtime = (cfg.get('runtime') or 'hybrid').lower()

    vllm_available = False
    ollama_available = False
    try:
        vllm_available = bool(VLLMBackend().is_available())
    except Exception:
        vllm_available = False
    try:
        ollama_available = bool(OllamaBackend().is_available())
    except Exception:
        ollama_available = False

    if runtime == 'vllm':
        selected_available = vllm_available
    elif runtime == 'ollama':
        selected_available = ollama_available
    else:
        selected_available = vllm_available or ollama_available

    available_backends = []
    if vllm_available:
        available_backends.append('vllm')
    if ollama_available:
        available_backends.append('ollama')

    return {
        'runtime': runtime,
        'profile': cfg.get('profile'),
        'chat_provider': cfg.get('chat_provider'),
        'min_vram_gb': cfg.get('min_vram_gb'),
        'cloud_fallback_enabled': bool(cfg.get('allow_cloud_fallback', True)),
        'vllm_available': vllm_available,
        'ollama_available': ollama_available,
        'selected_runtime_available': selected_available,
        'available_backends': available_backends,
        'memory_provider_effective': cfg.get('memory_provider_effective'),
        'memory_provider_configured': cfg.get('memory_provider_configured'),
    }


def _read_recent_jsonl(path: str, limit: int) -> list[dict]:
    rows: list[dict] = []
    if not path or not os.path.exists(path):
        return rows
    try:
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    rows.append(obj)
        if limit <= 0:
            return rows
        return rows[-limit:]
    except Exception:
        return []

@system_bp.route('/api/health')
def health():
    try:
        memstats = get_memory_stats()
        mstats = metrics.snapshot()
        caps = core_config.model_capability_summary() if getattr(core_config, 'ENABLE_CAPABILITY_ROUTER', False) else None
        trace_id = state.get_request_trace_id()
        return jsonify({
            'memory': memstats,
            'metrics': mstats,
            'models': caps,
            'tools': (mstats or {}).get('tools') if isinstance(mstats, dict) else None,
            'readiness': _readiness_snapshot(),
            'trace_id': trace_id,
        })
    except Exception as e:
        logger.error(f"Health error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/tokens')
def token_stats():
    """Get token usage statistics."""
    try:
        stats = get_token_stats()
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Token stats error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/tokens/reset', methods=['POST'])
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


@system_bp.route('/api/tokens/last')
def last_request_tokens():
    """Get token usage breakdown for the last request."""
    try:
        usage = get_last_token_usage()
        return jsonify({
            'total_input': usage.get('input', 0),
            'total_output': usage.get('output', 0),
            'total': usage.get('total', 0),
            'source': usage.get('source', 'unknown'),
            'steps': usage.get('steps', []),
        })
    except Exception as e:
        logger.error(f"Last token error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/config')
def config_info():
    tool_allowlist = sorted(core_config.get_tool_allowlist() or [])
    retrieval_connectors = core_config.get_retrieval_connector_config()
    remote_action_caps = []
    try:
        from companion_ai.tools.remote_actions import list_capabilities as _list_remote_action_capabilities

        remote_action_caps = _list_remote_action_capabilities()
    except Exception:
        remote_action_caps = []
    try:
        from companion_ai.retrieval.adapters import get_connector_capabilities
        retrieval_connectors['capabilities'] = get_connector_capabilities()
    except Exception:
        retrieval_connectors['capabilities'] = []
    return jsonify({
        'auth_required': bool(core_config.API_AUTH_TOKEN),
        'tool_allowlist_enabled': bool(tool_allowlist),
        'tool_allowlist': tool_allowlist,
        'local_models': core_config.get_local_model_runtime_config(),
        'retrieval_connectors': retrieval_connectors,
        'remote_actions': {
            'enabled': bool(core_config.REMOTE_ACTIONS_ENABLED),
            'capability_allowlist': sorted(core_config.get_remote_action_capability_allowlist() or []),
            'capability_allowlist_enabled': bool(core_config.get_remote_action_capability_allowlist()),
            'approval_ttl_seconds': int(core_config.REMOTE_ACTION_APPROVAL_TTL_SECONDS),
            'capabilities': remote_action_caps,
        },
    })


@system_bp.route('/api/local-model/runtime', methods=['GET', 'POST'])
def local_model_runtime():
    """Read or update runtime local model profile/runtime overrides."""
    if request.method == 'GET':
        return jsonify({
            'local_models': core_config.get_local_model_runtime_config(),
            'readiness': _local_runtime_snapshot(),
        })

    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    try:
        if bool(data.get('clear_overrides')):
            cfg = core_config.clear_local_model_runtime_overrides()
        else:
            profile = data.get('profile') if 'profile' in data else None
            runtime = data.get('runtime') if 'runtime' in data else None
            cfg = core_config.set_local_model_runtime_overrides(profile=profile, runtime=runtime)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Local model runtime update error: {e}")
        return jsonify({'error': str(e)}), 500

    return jsonify({
        'status': 'updated',
        'local_models': cfg,
        'readiness': _local_runtime_snapshot(),
    })


@system_bp.route('/api/computer-use/activity', methods=['GET'])
def computer_use_activity():
    """Return recent computer-use activity records with artifact references."""
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    limit_raw = request.args.get('limit', '30')
    try:
        limit = max(1, min(int(limit_raw), 200))
    except Exception:
        limit = 30

    rows = _read_recent_jsonl(system_tools_module.COMPUTER_USE_AUDIT_PATH, limit)
    rows.reverse()  # newest first
    return jsonify({
        'count': len(rows),
        'limit': limit,
        'retention_days': int(core_config.COMPUTER_USE_ARTIFACT_RETENTION_DAYS),
        'items': rows,
    })


@system_bp.route('/api/computer-use/artifacts/<attempt_id>', methods=['GET'])
def computer_use_artifact(attempt_id: str):
    """Return artifact envelope for a computer-use attempt."""
    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    safe_attempt_id = ''.join(ch for ch in str(attempt_id or '') if ch.isalnum() or ch in {'-', '_'})
    if not safe_attempt_id:
        return jsonify({'error': 'Invalid attempt id'}), 400

    artifact_path = system_tools_module.get_computer_use_artifact_path(safe_attempt_id)
    if not os.path.exists(artifact_path):
        return jsonify({'error': 'Artifact not found'}), 404

    try:
        with open(artifact_path, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return jsonify({'error': 'Invalid artifact payload'}), 500
        return jsonify(payload)
    except Exception as e:
        logger.error(f"Computer-use artifact read error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/permissions', methods=['GET', 'POST'])
def workspace_permissions():
    """Read or update workspace feature permissions."""
    if request.method == 'GET':
        workspace_id = state._resolve_workspace_key()
        return jsonify({
            'workspace_id': workspace_id,
            'permissions': state.get_workspace_permissions(workspace_id),
        })

    token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
    if not core_config.require_auth(token):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json(silent=True) or {}
    workspace_id = state._resolve_workspace_key(data)
    updates = data.get('permissions')
    if not isinstance(updates, dict):
        return jsonify({'error': 'permissions must be an object'}), 400

    try:
        updated = state.set_workspace_permissions(workspace_id, updates)
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        logger.error(f"Permission update error: {e}")
        return jsonify({'error': str(e)}), 500

    return jsonify({'workspace_id': workspace_id, 'permissions': updated})


@system_bp.route('/api/models')
def models_info():
    """Return structured model configuration metadata."""
    try:
        connector_config = core_config.get_retrieval_connector_config()
        remote_action_caps = []
        try:
            from companion_ai.retrieval.adapters import get_connector_capabilities
            connector_config['capabilities'] = get_connector_capabilities()
        except Exception:
            connector_config['capabilities'] = []
        try:
            from companion_ai.tools.remote_actions import list_capabilities as _list_remote_action_capabilities

            remote_action_caps = _list_remote_action_capabilities()
        except Exception:
            remote_action_caps = []

        data = {
            'models': {
                'PRIMARY_MODEL': core_config.PRIMARY_MODEL,
                'TOOLS_MODEL': core_config.TOOLS_MODEL,
                'VISION_MODEL': core_config.VISION_MODEL,
                'MEMORY_PROCESSING_MODEL': core_config.MEMORY_PROCESSING_MODEL,
                'MEMORY_FAST_MODEL': core_config.MEMORY_FAST_MODEL,
                'MEMORY_LOCAL_MODEL': core_config.MEMORY_LOCAL_MODEL,
                'EMBEDDING_MODEL': core_config.EMBEDDING_MODEL,
            },
            'model_info': core_config.MODEL_INFO,
            'flags': {
                'knowledge_graph': core_config.ENABLE_KNOWLEDGE_GRAPH,
                'fact_extraction': core_config.ENABLE_FACT_EXTRACTION,
                'tool_calling': core_config.ENABLE_TOOL_CALLING,
                'vision': core_config.ENABLE_VISION,
                'auto_tools': core_config.ENABLE_AUTO_TOOLS,
                'memory_extract_prefer_fast': core_config.MEMORY_EXTRACT_PREFER_FAST,
            },
            'roles': {
                'SMART_PRIMARY_MODEL': core_config.PRIMARY_MODEL,
                'MEMORY_PROCESSING_MODEL': core_config.MEMORY_PROCESSING_MODEL,
                'EMBEDDING_MODEL': core_config.EMBEDDING_MODEL,
            },
            'ensemble': {
                'enabled': False,
                'mode': None,
                'candidates': None,
            },
            'local_runtime': core_config.get_local_model_runtime_config(),
            'connectors': connector_config,
            'remote_actions': {
                'enabled': bool(core_config.REMOTE_ACTIONS_ENABLED),
                'capability_allowlist': sorted(core_config.get_remote_action_capability_allowlist() or []),
                'capability_allowlist_enabled': bool(core_config.get_remote_action_capability_allowlist()),
                'approval_ttl_seconds': int(core_config.REMOTE_ACTION_APPROVAL_TTL_SECONDS),
                'capabilities': remote_action_caps,
            },
        }
        return jsonify(data)
    except Exception as e:
        logger.error(f"Models info error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/routing/recent')
def routing_recent():
    """Return recent routing / ensemble decisions."""
    try:
        n = request.args.get('n', '15')
        try:
            n_int = max(1, min(int(n), 100))
        except Exception:
            n_int = 15
        log_dir = core_config.LOG_DIR
        patterns = sorted(glob.glob(os.path.join(log_dir, 'conv_*.jsonl')))[-2:]
        records: list[dict] = []
        for path in reversed(patterns):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    for line in reversed(f.readlines()[-500:]):
                        try:
                            obj = json.loads(line)
                            if 'routing' in obj:
                                rec = {
                                    'ts': obj.get('ts'),
                                    'model': obj.get('model'),
                                    'complexity': obj.get('complexity'),
                                    'latency_ms': obj.get('latency_ms'),
                                    'routing': obj.get('routing'),
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


# ==========================================================================
# Knowledge Graph API
# ==========================================================================

@system_bp.route('/api/graph')
def get_graph():
    """Return knowledge graph data as JSON for visualization."""
    response = None
    try:
        if core_config.USE_MEM0:
            try:
                _, _, mem0_user_id, _, _ = state._get_active_session_state()
                mem0_memories = mem0.get_all_memories(user_id=mem0_user_id)
                from companion_ai.memory.knowledge_graph import build_semantic_graph_from_memories
                graph_data = build_semantic_graph_from_memories(mem0_memories, threshold=0.6)
                response = jsonify(graph_data)
            except Exception as mem0_err:
                logger.error(f"Failed to build graph from Mem0: {mem0_err}")

        if not response:
            from companion_ai.memory.knowledge_graph import export_graph
            graph_json = export_graph()
            response = make_response(graph_json, 200)
            response.headers['Content-Type'] = 'application/json'

    except ImportError:
        return jsonify({'error': 'Knowledge graph not available. Install networkx.'}), 503
    except Exception as e:
        logger.error(f"Graph export error: {e}")
        return jsonify({'error': str(e)}), 500

    if response:
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


@system_bp.route('/api/graph/stats')
def get_graph_stats():
    """Return knowledge graph statistics."""
    try:
        from companion_ai.memory.knowledge_graph import get_graph_stats as _kg_stats
        stats = _kg_stats()
        return jsonify(stats)
    except ImportError:
        return jsonify({'error': 'Knowledge graph not available. Install networkx.'}), 503
    except Exception as e:
        logger.error(f"Graph stats error: {e}")
        return jsonify({'error': str(e)}), 500


@system_bp.route('/api/graph/search')
def search_graph_api():
    """Search the knowledge graph."""
    try:
        from companion_ai.memory.knowledge_graph import search_graph
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
