# companion_ai/web/memory_routes.py
"""Memory blueprint — Mem0/SQLite memory CRUD, pending facts, quality sync."""

import logging

from flask import Blueprint, request, jsonify

from companion_ai.core import config as core_config
from companion_ai.memory import sqlite_backend as sqlite_memory
from companion_ai.memory.sqlite_backend import (
    get_all_profile_facts, upsert_profile_fact, delete_profile_fact,
    clear_all_memory, list_profile_facts_detailed, list_pending_profile_facts,
    approve_profile_fact, reject_profile_fact, get_latest_summary, get_latest_insights,
    bulk_sync_memory_quality_from_mem0, get_memory_quality_map,
    delete_memory_quality_entry, upsert_memory_quality_entry,
)
from companion_ai.memory import mem0_backend as mem0
from companion_ai.conversation_manager import ConversationSession
from companion_ai.web import state

logger = logging.getLogger(__name__)

memory_bp = Blueprint('memory', __name__)


@memory_bp.route('/api/memory')
def get_memory():
    try:
        detailed = request.args.get('detailed', 'false').lower() in ('1', 'true', 'yes')
        session_key, profile_key, mem0_user_id, _, _ = state._get_active_session_state()
        state._maybe_migrate_legacy_scope(mem0_user_id, profile_key, session_key)

        # --- Mem0 as primary source ---
        if core_config.USE_MEM0:
            try:
                mem0_memories = mem0.get_all_memories(user_id=mem0_user_id)
                bulk_sync_memory_quality_from_mem0(mem0_memories, user_scope=mem0_user_id)
                quality_map = get_memory_quality_map(mem0_user_id)

                profile_detailed = []
                for m in mem0_memories:
                    text = m.get('memory', m.get('text', ''))
                    if not text:
                        continue
                    meta = m.get('metadata') or {}
                    quality = quality_map.get(m.get('id'), {})
                    confidence = quality.get('confidence', 0.70)
                    confidence_label = quality.get('confidence_label')
                    if not confidence_label:
                        confidence_label = 'high' if confidence >= 0.80 else 'medium' if confidence >= 0.50 else 'low'

                    profile_detailed.append({
                        'key': m.get('id'),
                        'value': text,
                        'confidence': confidence,
                        'confidence_label': confidence_label,
                        'reaffirmations': quality.get('reaffirmations', meta.get('frequency', 0)),
                        'source': quality.get('provenance_source', 'mem0'),
                        'contradiction_state': quality.get('contradiction_state', 'none'),
                    })

                resp = {
                    'profile': {m['key']: m['value'] for m in profile_detailed},
                    'profile_detailed': profile_detailed,
                    'summaries': [],
                    'insights': [],
                    'profile_id': profile_key,
                    'workspace_id': state._resolve_workspace_key(),
                }
                return jsonify(resp)

            except Exception as mem0_err:
                logger.error(f"Failed to fetch Mem0 memories: {mem0_err}")
                # Fallback to SQLite

        # --- SQLite fallback ---
        profile = get_all_profile_facts()
        summaries = get_latest_summary(10)
        insights = get_latest_insights(10)
        resp = {'profile': profile, 'summaries': summaries, 'insights': insights}
        if detailed:
            try:
                resp['profile_detailed'] = list_profile_facts_detailed()
            except Exception as inner:
                logger.warning(f"Detailed profile retrieval failed: {inner}")
        return jsonify(resp)
    except Exception as e:
        logger.error(f"Memory error: {e}")
        return jsonify({'error': str(e)}), 500


@memory_bp.route('/api/pending_facts')
def pending_facts():
    try:
        if not getattr(core_config, 'ENABLE_FACT_APPROVAL', False):
            return jsonify({'enabled': False, 'pending': []})
        pending = list_pending_profile_facts()
        return jsonify({'enabled': True, 'pending': pending})
    except Exception as e:
        logger.error(f"Pending facts error: {e}")
        return jsonify({'error': str(e)}), 500


@memory_bp.route('/api/pending_facts/<int:pid>/approve', methods=['POST'])
def approve_fact(pid: int):
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        ok = approve_profile_fact(pid)
        return jsonify({'approved': ok})
    except Exception as e:
        logger.error(f"Approve fact error: {e}")
        return jsonify({'error': str(e)}), 500


@memory_bp.route('/api/pending_facts/<int:pid>/reject', methods=['POST'])
def reject_fact(pid: int):
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        ok = reject_profile_fact(pid)
        return jsonify({'rejected': ok})
    except Exception as e:
        logger.error(f"Reject fact error: {e}")
        return jsonify({'error': str(e)}), 500


@memory_bp.route('/api/pending_facts/bulk', methods=['POST'])
def bulk_pending_facts_action():
    """Approve or reject multiple pending facts in one request."""
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        data = request.get_json(silent=True) or {}
        action = str(data.get('action') or '').strip().lower()
        ids = data.get('ids')
        if action not in {'approve', 'reject'}:
            return jsonify({'error': "action must be 'approve' or 'reject'"}), 400
        if not isinstance(ids, list) or not ids:
            return jsonify({'error': 'ids must be a non-empty list'}), 400

        ok_ids = []
        failed_ids = []
        for raw_id in ids:
            try:
                pid = int(raw_id)
            except Exception:
                failed_ids.append(raw_id)
                continue
            ok = approve_profile_fact(pid) if action == 'approve' else reject_profile_fact(pid)
            if ok:
                ok_ids.append(pid)
            else:
                failed_ids.append(pid)

        return jsonify({
            'action': action,
            'processed': len(ok_ids),
            'failed': failed_ids,
            'ok_ids': ok_ids,
        })
    except Exception as e:
        logger.error(f"Bulk pending facts error: {e}")
        return jsonify({'error': str(e)}), 500


@memory_bp.route('/api/memory/clear', methods=['POST'])
def clear_memory():
    try:
        data = request.get_json(silent=True) or {}
        _, _, mem0_user_id, active_history, active_session = state._get_active_session_state(data)
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        # Clear SQLite memory
        clear_all_memory()

        # Clear Mem0 vector memory
        if core_config.USE_MEM0:
            try:
                mem0.clear_all_memories(user_id=mem0_user_id)
                mem0._reset_memory()
                logger.info("Cleared Mem0 vector memory and reset instance")
            except Exception as mem0_err:
                logger.error(f"Failed to clear Mem0: {mem0_err}")

        # Clear active in-memory session state
        active_history.clear()
        with state._session_lock:
            for key, mgr in list(state._session_managers.items()):
                if mgr is active_session:
                    state._session_managers[key] = ConversationSession()
                    break

        # Clear Knowledge Graph
        try:
            from companion_ai.memory.knowledge_graph import clear_graph
            clear_graph()
            logger.info("Cleared Knowledge Graph")
        except Exception as kg_err:
            logger.error(f"Failed to clear Knowledge Graph: {kg_err}")

        return jsonify({'success': True})
    except Exception as e:
        logger.error(f"Clear memory error: {e}")
        return jsonify({'error': str(e)}), 500


@memory_bp.route('/api/memory/fact/<key>', methods=['DELETE'])
def delete_fact(key: str):
    local_logger = logging.getLogger(__name__)
    try:
        _, _, mem0_user_id, _, _ = state._get_active_session_state()
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        deleted = False

        if core_config.USE_MEM0:
            try:
                mem0_deleted = mem0.delete_memory(key)
                if mem0_deleted:
                    deleted = True
                    delete_memory_quality_entry(key, user_scope=mem0_user_id)
                    local_logger.info(f"Deleted Mem0 memory for key: {key}")
                else:
                    sqlite_deleted = delete_profile_fact(key)
                    if sqlite_deleted:
                        deleted = True
                        local_logger.info(f"Deleted SQLite memory for key: {key}")
            except Exception as mem0_err:
                local_logger.error(f"Failed to delete Mem0 fact: {mem0_err}")
        else:
            deleted = delete_profile_fact(key)

        return jsonify({'deleted': deleted, 'key': key})
    except Exception as e:
        local_logger.error(f"Delete fact error: {e}")
        return jsonify({'error': str(e)}), 500


@memory_bp.route('/api/memory/fact/<key>', methods=['PUT'])
def update_fact(key: str):
    """Update a memory fact by key."""
    local_logger = logging.getLogger(__name__)
    try:
        payload = request.get_json(silent=True) or {}
        _, _, mem0_user_id, _, _ = state._get_active_session_state(payload)
        token = request.headers.get('X-API-TOKEN') or payload.get('token') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        new_value = payload.get('value', '').strip()
        if not new_value:
            return jsonify({'error': 'Empty value not allowed'}), 400

        updated = False

        if core_config.USE_MEM0:
            try:
                updated = mem0.update_memory(key, new_value)
                if updated:
                    prior_quality = get_memory_quality_map(mem0_user_id).get(key, {})
                    upsert_memory_quality_entry(
                        memory_id=key,
                        memory_text=new_value,
                        user_scope=mem0_user_id,
                        confidence=prior_quality.get('confidence', 0.70),
                        reaffirmations=prior_quality.get('reaffirmations', 0),
                        contradiction_state=prior_quality.get('contradiction_state', 'none'),
                        provenance_source='mem0',
                        metadata=prior_quality.get('metadata') if isinstance(prior_quality, dict) else None,
                    )
                    local_logger.info(f"Updated Mem0 memory {key}: {new_value[:50]}...")
            except Exception as e:
                local_logger.error(f"Mem0 update error: {e}")
                try:
                    from companion_ai.memory.sqlite_backend import update_profile_fact
                    updated = update_profile_fact(key, new_value)
                except Exception:
                    pass

        return jsonify({'updated': updated, 'key': key, 'value': new_value})
    except Exception as e:
        local_logger.error(f"Update fact error: {e}")
        return jsonify({'error': str(e)}), 500
