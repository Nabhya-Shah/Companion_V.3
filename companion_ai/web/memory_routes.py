# companion_ai/web/memory_routes.py
"""Memory blueprint — Mem0/SQLite memory CRUD, pending facts, quality sync."""

import logging
import json
import os
import re
import time
from datetime import datetime, timezone
from threading import Lock

from flask import Blueprint, request, jsonify

from companion_ai.core import config as core_config
from companion_ai.memory import sqlite_backend as sqlite_memory
from companion_ai.memory import write_queue
from companion_ai.memory.sqlite_backend import (
    get_all_profile_facts, upsert_profile_fact, delete_profile_fact,
    clear_all_memory, list_profile_facts_detailed, list_pending_profile_facts,
    approve_profile_fact, reject_profile_fact, get_latest_summary, get_latest_insights,
    bulk_sync_memory_quality_from_mem0, get_memory_quality_map,
    delete_memory_quality_entry, upsert_memory_quality_entry, list_memory_write_status,
)
from companion_ai.memory import mem0_backend as mem0
from companion_ai.runtime import ConversationSession
from companion_ai.web import state

logger = logging.getLogger(__name__)

memory_bp = Blueprint('memory', __name__)

_QUEUE_REPLAY_LOCK = Lock()
_QUEUE_REPLAY_COOLDOWN_SECONDS = 5.0
_QUEUE_REPLAY_MAX_ITEMS = 200
_queue_replay_last_monotonic_ts = 0.0
_queue_replay_last_completed_at = ''
_REVIEW_STATES = {'none', 'pending', 'conflict', 'resolved'}
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
_THROUGHPUT_BASELINE_PATH = os.path.join(_PROJECT_ROOT, 'data', 'benchmarks', 'throughput_probe_health.json')


def _bounded_positive_int(raw_value, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(raw_value)
    except Exception:
        parsed = default
    return max(minimum, min(parsed, maximum))


def _parse_iso_timestamp(raw_value: str | None) -> datetime | None:
    if not raw_value:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace('Z', '+00:00'))
    except Exception:
        return None


def _token_set(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", str(text).lower()) if len(token) >= 3}


def _jaccard_similarity(text_a: str, text_b: str) -> float:
    tokens_a = _token_set(text_a)
    tokens_b = _token_set(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    union = tokens_a | tokens_b
    if not union:
        return 0.0
    return len(tokens_a & tokens_b) / len(union)


def _compute_dedup_candidates(rows: list[dict], threshold: float = 0.72) -> None:
    for row in rows:
        row['dedup_candidates'] = []

    for idx in range(len(rows)):
        left = rows[idx]
        for jdx in range(idx + 1, len(rows)):
            right = rows[jdx]
            score = _jaccard_similarity(left.get('value', ''), right.get('value', ''))
            if score < threshold:
                continue

            left['dedup_candidates'].append({
                'key': right.get('key'),
                'value': right.get('value', ''),
                'similarity': round(score, 3),
            })
            right['dedup_candidates'].append({
                'key': left.get('key'),
                'value': left.get('value', ''),
                'similarity': round(score, 3),
            })

    for row in rows:
        candidates = sorted(
            row.get('dedup_candidates', []),
            key=lambda item: item.get('similarity', 0.0),
            reverse=True,
        )
        row['dedup_candidates'] = candidates[:3]
        row['dedup_candidate_count'] = len(candidates)


def _build_memory_review_rows(mem0_user_id: str, limit: int = 120) -> list[dict]:
    rows: list[dict] = []

    if core_config.USE_MEM0:
        try:
            mem0_memories = mem0.get_all_memories(user_id=mem0_user_id)
            bulk_sync_memory_quality_from_mem0(mem0_memories, user_scope=mem0_user_id)
            quality_map = get_memory_quality_map(mem0_user_id)

            for item in mem0_memories:
                memory_id = str(item.get('id') or '')
                value = item.get('memory', item.get('text', ''))
                if not memory_id or not value:
                    continue

                quality = quality_map.get(memory_id, {})
                confidence = quality.get('confidence', (item.get('metadata') or {}).get('confidence', 0.70))
                try:
                    confidence_value = float(confidence)
                except Exception:
                    confidence_value = 0.70

                rows.append({
                    'key': memory_id,
                    'value': str(value),
                    'source': str(quality.get('provenance_source', 'mem0')),
                    'confidence': max(0.0, min(1.0, confidence_value)),
                    'confidence_label': str(quality.get('confidence_label') or ('high' if confidence_value >= 0.80 else 'medium' if confidence_value >= 0.50 else 'low')),
                    'reaffirmations': int(quality.get('reaffirmations', (item.get('metadata') or {}).get('frequency', 0)) or 0),
                    'contradiction_state': str(quality.get('contradiction_state', 'none') or 'none').lower(),
                    'updated_at': quality.get('updated_at'),
                    'last_validated_ts': quality.get('last_validated_ts'),
                    'metadata': quality.get('metadata') if isinstance(quality.get('metadata'), dict) else (item.get('metadata') or {}),
                })
        except Exception as mem0_err:
            logger.warning(f"Memory review Mem0 path failed: {mem0_err}")

    if not rows:
        for fact in list_profile_facts_detailed():
            key = str(fact.get('key') or '')
            value = str(fact.get('value') or '')
            if not key or not value:
                continue

            confidence = fact.get('confidence', 0.70)
            try:
                confidence_value = float(confidence)
            except Exception:
                confidence_value = 0.70

            rows.append({
                'key': key,
                'value': value,
                'source': str(fact.get('source', 'sqlite_profile')),
                'confidence': max(0.0, min(1.0, confidence_value)),
                'confidence_label': str(fact.get('confidence_label') or ('high' if confidence_value >= 0.80 else 'medium' if confidence_value >= 0.50 else 'low')),
                'reaffirmations': int(fact.get('reaffirmations', 0) or 0),
                'contradiction_state': str(fact.get('contradiction_state', 'none') or 'none').lower(),
                'updated_at': fact.get('last_updated'),
                'last_validated_ts': fact.get('last_seen_ts'),
                'metadata': {
                    'first_seen_ts': fact.get('first_seen_ts'),
                    'last_seen_ts': fact.get('last_seen_ts'),
                    'evidence': fact.get('evidence'),
                },
            })

    for row in rows:
        state_value = row.get('contradiction_state', 'none')
        if state_value not in _REVIEW_STATES:
            row['contradiction_state'] = 'none'

    _compute_dedup_candidates(rows)

    for row in rows:
        state_value = row.get('contradiction_state', 'none')
        confidence_value = float(row.get('confidence', 0.70) or 0.70)
        dedup_count = int(row.get('dedup_candidate_count', 0) or 0)

        priority = 0.0
        if state_value == 'conflict':
            priority += 4.0
        elif state_value == 'pending':
            priority += 2.0
        priority += max(0.0, (0.70 - confidence_value) * 2.5)
        priority += min(2.0, dedup_count * 0.5)
        row['review_priority'] = round(priority, 3)

    rows.sort(
        key=lambda row: (
            row.get('review_priority', 0.0),
            row.get('updated_at') or row.get('last_validated_ts') or '',
        ),
        reverse=True,
    )
    return rows[:limit]


def _load_throughput_baseline() -> dict:
    if not os.path.exists(_THROUGHPUT_BASELINE_PATH):
        return {}
    try:
        with open(_THROUGHPUT_BASELINE_PATH, 'r', encoding='utf-8') as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _memory_readiness_snapshot() -> dict:
    """Return deterministic memory readiness diagnostics for local/dev operators."""
    mem0_enabled = bool(core_config.USE_MEM0)
    mem0_initialized = bool(getattr(mem0, '_memory_instance', None) is not None)

    runtime_descriptor = {}
    runtime_probe_failed = False
    try:
        runtime_descriptor = mem0.get_runtime_descriptor()
    except Exception:
        runtime_probe_failed = True
        runtime_descriptor = {}

    queue_depth = 0
    queue_oldest_created_at = None
    queue_probe_failed = False
    try:
        queue_rows = write_queue.list_queued_writes(limit=5000)
        queue_depth = len(queue_rows)
        if queue_rows:
            queue_oldest_created_at = queue_rows[-1].get('created_at')
    except Exception:
        queue_probe_failed = True

    write_probe_failed = False
    write_rows = []
    try:
        write_rows = list_memory_write_status(limit=500)
    except Exception:
        write_probe_failed = True

    write_total = len(write_rows)
    write_committed = sum(1 for row in write_rows if row.get('status') == 'accepted_committed')
    write_queued = sum(1 for row in write_rows if row.get('status') == 'accepted_queued')
    write_failed = sum(1 for row in write_rows if row.get('status') in {'failed', 'rejected'})

    queued_rate = (write_queued / write_total) if write_total else 0.0
    failure_rate = (write_failed / write_total) if write_total else 0.0

    baseline = _load_throughput_baseline()
    baseline_results = baseline.get('results') if isinstance(baseline.get('results'), dict) else {}
    baseline_latency = baseline_results.get('latency_ms') if isinstance(baseline_results.get('latency_ms'), dict) else {}

    reasons: list[str] = []
    if mem0_enabled and not mem0_initialized:
        reasons.append('mem0_not_initialized')
    if runtime_probe_failed:
        reasons.append('mem0_runtime_probe_failed')
    if queue_probe_failed:
        reasons.append('memory_write_queue_probe_failed')
    elif queue_depth >= 100:
        reasons.append('memory_write_queue_backlog')

    if write_probe_failed:
        reasons.append('memory_write_status_probe_failed')
    elif failure_rate >= 0.10:
        reasons.append('memory_write_failure_rate_high')

    if not write_probe_failed and queued_rate >= 0.25:
        reasons.append('memory_write_queued_ratio_high')

    recommendations: list[str] = []
    if not reasons:
        recommendations.append('Memory subsystem is healthy. Continue periodic migration-readiness and throughput checks.')
    else:
        if 'mem0_not_initialized' in reasons:
            recommendations.append('Initialize Mem0 backend and verify runtime descriptor model/provider alignment.')
        if 'memory_write_queue_backlog' in reasons:
            recommendations.append('Run bounded queue replay and monitor /api/memory/write-queue for sustained backlog.')
        if 'memory_write_failure_rate_high' in reasons or 'memory_write_queued_ratio_high' in reasons:
            recommendations.append('Investigate write reliability and consider dual-write migration planning if pressure persists.')
        if 'memory_write_queue_probe_failed' in reasons or 'memory_write_status_probe_failed' in reasons:
            recommendations.append('Fix memory diagnostics probe path before relying on readiness score for operations decisions.')

    return {
        'status': 'degraded' if reasons else 'ready',
        'reasons': reasons,
        'mem0': {
            'enabled': mem0_enabled,
            'initialized': mem0_initialized,
            'runtime': runtime_descriptor,
            'runtime_probe_failed': runtime_probe_failed,
        },
        'write_queue': {
            'depth': queue_depth,
            'oldest_created_at': queue_oldest_created_at,
            'probe_failed': queue_probe_failed,
        },
        'write_status': {
            'rows': write_total,
            'committed': write_committed,
            'queued': write_queued,
            'failed': write_failed,
            'queued_rate': round(queued_rate, 4),
            'failure_rate': round(failure_rate, 4),
            'probe_failed': write_probe_failed,
        },
        'baseline': {
            'throughput_probe_p95_ms': float(baseline_latency.get('p95_ms') or 0.0),
            'throughput_probe_rps': float(baseline_results.get('throughput_rps') or 0.0),
        },
        'recommendations': recommendations,
    }


@memory_bp.route('/api/memory')
def get_memory():
    try:
        detailed = request.args.get('detailed', 'false').lower() in ('1', 'true', 'yes')
        session_key, profile_key, mem0_user_id, _, _ = state._get_active_session_state()

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


@memory_bp.route('/api/memory/provenance/<key>', methods=['GET'])
def memory_provenance_detail(key: str):
    """Return drill-down provenance payload for one memory key."""
    try:
        _, profile_key, mem0_user_id, _, _ = state._get_active_session_state()
        trace_id = state.get_request_trace_id()

        def _confidence_label(value: float) -> str:
            if value >= 0.80:
                return 'high'
            if value >= 0.50:
                return 'medium'
            return 'low'

        if core_config.USE_MEM0:
            try:
                mem0_memories = mem0.get_all_memories(user_id=mem0_user_id)
                bulk_sync_memory_quality_from_mem0(mem0_memories, user_scope=mem0_user_id)
                quality_map = get_memory_quality_map(mem0_user_id)

                for item in mem0_memories:
                    memory_id = str(item.get('id') or '')
                    if memory_id != key:
                        continue

                    text = item.get('memory', item.get('text', ''))
                    metadata = item.get('metadata') or {}
                    quality = quality_map.get(memory_id, {})
                    confidence = quality.get('confidence', metadata.get('confidence', 0.70))
                    try:
                        confidence_value = float(confidence)
                    except Exception:
                        confidence_value = 0.70

                    payload = {
                        'key': memory_id,
                        'value': text,
                        'provenance': {
                            'source': quality.get('provenance_source', 'mem0'),
                            'confidence': confidence_value,
                            'confidence_label': quality.get('confidence_label') or _confidence_label(confidence_value),
                            'reaffirmations': int(quality.get('reaffirmations', metadata.get('frequency', 0)) or 0),
                            'contradiction_state': quality.get('contradiction_state', 'none'),
                            'updated_at': quality.get('updated_at'),
                            'last_validated_ts': quality.get('last_validated_ts'),
                            'metadata': quality.get('metadata') if isinstance(quality.get('metadata'), dict) else metadata,
                        },
                        'profile_id': profile_key,
                        'workspace_id': state._resolve_workspace_key(),
                        'trace_id': trace_id,
                    }
                    return jsonify(payload)
            except Exception as mem0_err:
                logger.warning(f"Memory provenance detail Mem0 path failed: {mem0_err}")

        detailed = list_profile_facts_detailed()
        for fact in detailed:
            fact_key = str(fact.get('key') or '')
            if fact_key != key:
                continue

            payload = {
                'key': fact_key,
                'value': fact.get('value', ''),
                'provenance': {
                    'source': fact.get('source', 'sqlite_profile'),
                    'confidence': fact.get('confidence', 0.70),
                    'confidence_label': fact.get('confidence_label', 'medium'),
                    'reaffirmations': fact.get('reaffirmations', 0),
                    'contradiction_state': 'none',
                    'updated_at': fact.get('last_updated'),
                    'last_validated_ts': fact.get('last_seen_ts'),
                    'metadata': {
                        'first_seen_ts': fact.get('first_seen_ts'),
                        'last_seen_ts': fact.get('last_seen_ts'),
                        'evidence': fact.get('evidence'),
                    },
                },
                'profile_id': profile_key,
                'workspace_id': state._resolve_workspace_key(),
                'trace_id': trace_id,
            }
            return jsonify(payload)

        return jsonify({
            'error': 'Memory fact not found',
            'key': key,
            'trace_id': trace_id,
        }), 404
    except Exception as e:
        logger.error(f"Memory provenance detail error: {e}")
        return jsonify({'error': str(e), 'trace_id': state.get_request_trace_id()}), 500


@memory_bp.route('/api/memory/write-queue', methods=['GET'])
def memory_write_queue_status():
    """Return durable memory write queue diagnostics for operators."""
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        raw_limit = request.args.get('limit', '25')
        limit = _bounded_positive_int(raw_limit, default=25, minimum=1, maximum=200)

        rows = write_queue.list_queued_writes(limit=limit)
        items = []
        for row in rows:
            payload = row.get('payload') if isinstance(row.get('payload'), dict) else {}
            payload_preview = json.dumps(payload, ensure_ascii=True)[:180] if payload else ''
            items.append({
                'request_id': str(row.get('request_id') or ''),
                'operation': str(row.get('operation') or ''),
                'user_scope': str(row.get('user_scope') or ''),
                'created_at': row.get('created_at'),
                'payload_preview': payload_preview,
            })

        return jsonify({
            'queued_count': len(rows),
            'items': items,
            'replay_state': {
                'cooldown_seconds': _QUEUE_REPLAY_COOLDOWN_SECONDS,
                'last_replay_at': _queue_replay_last_completed_at,
            },
            'trace_id': state.get_request_trace_id(),
        })
    except Exception as e:
        logger.error(f"Memory write queue status error: {e}")
        return jsonify({'error': str(e), 'trace_id': state.get_request_trace_id()}), 500


@memory_bp.route('/api/memory/readiness', methods=['GET'])
def memory_readiness_status():
    """Return deterministic memory readiness contract for local/dev health checks."""
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        snapshot = _memory_readiness_snapshot()
        snapshot['trace_id'] = state.get_request_trace_id()
        return jsonify(snapshot)
    except Exception as e:
        logger.error(f"Memory readiness error: {e}")
        return jsonify({'error': str(e), 'trace_id': state.get_request_trace_id()}), 500


@memory_bp.route('/api/memory/write-queue/replay', methods=['POST'])
def memory_write_queue_replay():
    """Replay durable queued writes with bounded controls."""
    global _queue_replay_last_monotonic_ts, _queue_replay_last_completed_at
    try:
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked

        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        data = request.get_json(silent=True) or {}
        raw_max_items = data.get('max_items', request.args.get('max_items', '50'))
        max_items = _bounded_positive_int(
            raw_max_items,
            default=50,
            minimum=1,
            maximum=_QUEUE_REPLAY_MAX_ITEMS,
        )

        now = time.monotonic()
        elapsed = now - float(_queue_replay_last_monotonic_ts or 0.0)
        if elapsed < _QUEUE_REPLAY_COOLDOWN_SECONDS:
            retry_after = max(0.0, _QUEUE_REPLAY_COOLDOWN_SECONDS - elapsed)
            return jsonify({
                'error': 'Replay cooldown active',
                'reason': 'replay_cooldown',
                'retry_after_seconds': round(retry_after, 2),
                'trace_id': state.get_request_trace_id(),
            }), 429

        if not _QUEUE_REPLAY_LOCK.acquire(blocking=False):
            return jsonify({
                'error': 'Replay already in progress',
                'reason': 'replay_in_progress',
                'trace_id': state.get_request_trace_id(),
            }), 409

        try:
            replay = mem0.replay_queued_writes(max_items=max_items)
            _queue_replay_last_monotonic_ts = time.monotonic()
            _queue_replay_last_completed_at = datetime.now(timezone.utc).isoformat()
        finally:
            _QUEUE_REPLAY_LOCK.release()

        queued_count = len(write_queue.list_queued_writes(limit=_QUEUE_REPLAY_MAX_ITEMS))
        return jsonify({
            'status': 'ok',
            'max_items': max_items,
            'replay': replay,
            'queued_count': queued_count,
            'trace_id': state.get_request_trace_id(),
        })
    except Exception as e:
        logger.error(f"Memory write queue replay error: {e}")
        return jsonify({'error': str(e), 'trace_id': state.get_request_trace_id()}), 500


@memory_bp.route('/api/memory/review', methods=['GET'])
def memory_review_queue():
    """Return prioritized contradiction/dedup review rows for operators."""
    try:
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked

        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        _, _, mem0_user_id, _, _ = state._get_active_session_state()
        include_all = request.args.get('include_all', 'false').lower() in {'1', 'true', 'yes'}
        limit = _bounded_positive_int(request.args.get('limit', '40'), default=40, minimum=1, maximum=200)

        rows = _build_memory_review_rows(mem0_user_id=mem0_user_id, limit=max(limit, 80))
        if not include_all:
            rows = [
                row for row in rows
                if row.get('contradiction_state') in {'pending', 'conflict'}
                or float(row.get('confidence', 0.70) or 0.70) < 0.55
                or int(row.get('dedup_candidate_count', 0) or 0) > 0
            ]

        rows = rows[:limit]
        summary = {
            'total_review_items': len(rows),
            'conflict_count': sum(1 for row in rows if row.get('contradiction_state') == 'conflict'),
            'pending_count': sum(1 for row in rows if row.get('contradiction_state') == 'pending'),
            'dedup_candidate_count': sum(1 for row in rows if int(row.get('dedup_candidate_count', 0) or 0) > 0),
            'low_confidence_count': sum(1 for row in rows if float(row.get('confidence', 0.70) or 0.70) < 0.55),
        }

        return jsonify({
            'items': rows,
            'summary': summary,
            'trace_id': state.get_request_trace_id(),
        })
    except Exception as e:
        logger.error(f"Memory review queue error: {e}")
        return jsonify({'error': str(e), 'trace_id': state.get_request_trace_id()}), 500


@memory_bp.route('/api/memory/review/<key>', methods=['POST'])
def memory_review_update(key: str):
    """Apply a quality-review action to one memory key."""
    try:
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked

        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        _, _, mem0_user_id, _, _ = state._get_active_session_state()
        rows = _build_memory_review_rows(mem0_user_id=mem0_user_id, limit=250)
        current = next((row for row in rows if str(row.get('key') or '') == str(key)), None)
        if not current:
            return jsonify({'error': 'Memory fact not found', 'key': key, 'trace_id': state.get_request_trace_id()}), 404

        payload = request.get_json(silent=True) or {}
        action = str(payload.get('action') or '').strip().lower()
        if action not in {'set_state', 'reaffirm', 'mark_duplicate'}:
            return jsonify({'error': "action must be one of: set_state, reaffirm, mark_duplicate"}), 400

        contradiction_state = str(current.get('contradiction_state', 'none') or 'none').lower()
        confidence = float(current.get('confidence', 0.70) or 0.70)
        reaffirmations = int(current.get('reaffirmations', 0) or 0)
        metadata = current.get('metadata') if isinstance(current.get('metadata'), dict) else {}
        metadata = dict(metadata)

        if action == 'set_state':
            next_state = str(payload.get('state') or '').strip().lower()
            if next_state not in _REVIEW_STATES:
                return jsonify({'error': f"state must be one of: {', '.join(sorted(_REVIEW_STATES))}"}), 400
            contradiction_state = next_state

        if action == 'reaffirm':
            step = payload.get('confidence_step', 0.05)
            try:
                step_value = float(step)
            except Exception:
                step_value = 0.05
            step_value = max(0.01, min(step_value, 0.20))
            confidence = min(1.0, confidence + step_value)
            reaffirmations += 1
            if contradiction_state == 'conflict':
                contradiction_state = 'pending'

        if action == 'mark_duplicate':
            duplicate_of = str(payload.get('duplicate_of') or '').strip()
            if not duplicate_of:
                return jsonify({'error': 'duplicate_of is required for mark_duplicate action'}), 400
            if duplicate_of == str(key):
                return jsonify({'error': 'duplicate_of cannot match key'}), 400
            contradiction_state = 'resolved'
            metadata['duplicate_of'] = duplicate_of
            metadata['review_action'] = 'mark_duplicate'

        ok = upsert_memory_quality_entry(
            memory_id=str(key),
            memory_text=str(current.get('value') or ''),
            user_scope=mem0_user_id,
            confidence=confidence,
            reaffirmations=reaffirmations,
            contradiction_state=contradiction_state,
            provenance_source=str(current.get('source') or 'mem0'),
            metadata=metadata,
        )
        if not ok:
            return jsonify({'error': 'Failed to update memory review state', 'trace_id': state.get_request_trace_id()}), 500

        updated = {
            'key': str(key),
            'confidence': confidence,
            'confidence_label': 'high' if confidence >= 0.80 else 'medium' if confidence >= 0.50 else 'low',
            'reaffirmations': reaffirmations,
            'contradiction_state': contradiction_state,
            'metadata': metadata,
        }
        return jsonify({'updated': updated, 'trace_id': state.get_request_trace_id()})
    except Exception as e:
        logger.error(f"Memory review update error: {e}")
        return jsonify({'error': str(e), 'trace_id': state.get_request_trace_id()}), 500


@memory_bp.route('/api/memory/migration-readiness', methods=['GET'])
def memory_migration_readiness():
    """Expose SQLite pressure and migration guidance signals for operators."""
    try:
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401

        queue_rows = write_queue.list_queued_writes(limit=5000)
        queue_depth = len(queue_rows)

        oldest_age_minutes = None
        if queue_rows:
            oldest_ts = _parse_iso_timestamp(queue_rows[-1].get('created_at'))
            if oldest_ts is not None:
                now = datetime.now(timezone.utc)
                if oldest_ts.tzinfo is None:
                    oldest_ts = oldest_ts.replace(tzinfo=timezone.utc)
                oldest_age_minutes = max(0.0, (now - oldest_ts).total_seconds() / 60.0)

        write_rows = list_memory_write_status(limit=500)
        total_writes = len(write_rows)
        queued_writes = sum(1 for row in write_rows if row.get('status') == 'accepted_queued')
        failed_writes = sum(1 for row in write_rows if row.get('status') in {'failed', 'rejected'})
        committed_writes = sum(1 for row in write_rows if row.get('status') == 'accepted_committed')

        queued_rate = (queued_writes / total_writes) if total_writes else 0.0
        failure_rate = (failed_writes / total_writes) if total_writes else 0.0

        baseline = _load_throughput_baseline()
        baseline_results = baseline.get('results') if isinstance(baseline.get('results'), dict) else {}
        baseline_latency = baseline_results.get('latency_ms') if isinstance(baseline_results.get('latency_ms'), dict) else {}
        baseline_p95_ms = float(baseline_latency.get('p95_ms') or 0.0)
        baseline_throughput_rps = float(baseline_results.get('throughput_rps') or 0.0)

        level = 'healthy'
        reasons: list[str] = []

        if queue_depth >= 500:
            reasons.append('queue_backlog_critical')
        elif queue_depth >= 150:
            reasons.append('queue_backlog_high')
        elif queue_depth >= 75:
            reasons.append('queue_backlog_watch')

        if failure_rate >= 0.15:
            reasons.append('write_failure_rate_critical')
        elif failure_rate >= 0.07:
            reasons.append('write_failure_rate_high')
        elif failure_rate >= 0.03:
            reasons.append('write_failure_rate_watch')

        if queued_rate >= 0.25:
            reasons.append('queued_write_ratio_high')
        elif queued_rate >= 0.15:
            reasons.append('queued_write_ratio_watch')

        if oldest_age_minutes is not None and oldest_age_minutes >= 60:
            reasons.append('queue_oldest_age_high')

        if 'queue_backlog_critical' in reasons or 'write_failure_rate_critical' in reasons:
            level = 'migrate_now'
        elif {'queue_backlog_high', 'write_failure_rate_high', 'queued_write_ratio_high', 'queue_oldest_age_high'} & set(reasons):
            level = 'plan_migration'
        elif reasons:
            level = 'watch'

        recommendations: list[str] = []
        if level == 'healthy':
            recommendations.append('Current SQLite path is healthy. Continue periodic throughput probes.')
        if level in {'watch', 'plan_migration', 'migrate_now'}:
            recommendations.append('Increase replay cadence and monitor /api/memory/write-queue for sustained backlog.')
        if level in {'plan_migration', 'migrate_now'}:
            recommendations.append('Prepare PostgreSQL + pgvector pilot lane and dual-write migration plan.')
            recommendations.append('Define cutover threshold on queue backlog and write failure rates before pilot execution.')
        if level == 'migrate_now':
            recommendations.append('Throttle non-critical memory writes until durable backend migration is active.')

        return jsonify({
            'level': level,
            'reasons': reasons,
            'metrics': {
                'queue_depth': queue_depth,
                'queue_oldest_age_minutes': round(oldest_age_minutes, 2) if oldest_age_minutes is not None else None,
                'write_log_rows': total_writes,
                'write_committed_count': committed_writes,
                'write_queued_count': queued_writes,
                'write_failed_count': failed_writes,
                'queued_rate': round(queued_rate, 4),
                'failure_rate': round(failure_rate, 4),
                'baseline_p95_ms': baseline_p95_ms,
                'baseline_throughput_rps': baseline_throughput_rps,
            },
            'thresholds': {
                'queue_backlog_watch': 75,
                'queue_backlog_high': 150,
                'queue_backlog_critical': 500,
                'failure_rate_watch': 0.03,
                'failure_rate_high': 0.07,
                'failure_rate_critical': 0.15,
                'queued_rate_watch': 0.15,
                'queued_rate_high': 0.25,
            },
            'recommendations': recommendations,
            'trace_id': state.get_request_trace_id(),
        })
    except Exception as e:
        logger.error(f"Memory migration readiness error: {e}")
        return jsonify({'error': str(e), 'trace_id': state.get_request_trace_id()}), 500


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
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked
        _, _, mem0_user_id, _, _ = state._get_active_session_state()
        token = request.headers.get('X-API-TOKEN') or request.cookies.get('api_token')
        if not core_config.require_auth(token):
            return jsonify({'error': 'Unauthorized'}), 401
        try:
            ok = approve_profile_fact(pid, user_id=mem0_user_id)
        except TypeError:
            ok = approve_profile_fact(pid)
        return jsonify({'approved': ok})
    except Exception as e:
        logger.error(f"Approve fact error: {e}")
        return jsonify({'error': str(e)}), 500


@memory_bp.route('/api/pending_facts/<int:pid>/reject', methods=['POST'])
def reject_fact(pid: int):
    try:
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked
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
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked
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
        _, _, mem0_user_id, _, _ = state._get_active_session_state()
        for raw_id in ids:
            try:
                pid = int(raw_id)
            except Exception:
                failed_ids.append(raw_id)
                continue
            if action == 'approve':
                try:
                    ok = approve_profile_fact(pid, user_id=mem0_user_id)
                except TypeError:
                    ok = approve_profile_fact(pid)
            else:
                ok = reject_profile_fact(pid)
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
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked
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
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked
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
        blocked = state.enforce_feature_permission('memory_write')
        if blocked:
            return blocked
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
