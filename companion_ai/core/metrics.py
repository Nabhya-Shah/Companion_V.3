"""Lightweight in-process metrics aggregation.

Persists rolling stats to data/logs/metrics_state.json so /health can report
without parsing full logs.
"""
from __future__ import annotations
import os, json, time, threading, statistics
from typing import Dict, Any

from . import config

_lock = threading.Lock()
_state: Dict[str, Any] = {
    'models': {},              # model -> {'count': int, 'latencies': [ms,...] (capped)}
    'total_interactions': 0,
    'last_update_ts': None,
    'tools': {
        'total_invocations': 0,
        'by_name': {},        # name -> count
        'blocked': 0,         # cooldown or rejection
        'failures': 0,
        'decision_types': {},  # e.g. model_directive, heuristic_override
        'skill': {            # basic EMA skill scoring per tool
            'by_name': {}     # name -> {'score': float, 'uses': int, 'successes': int}
        }
    }
}
_LATENCY_CAP = 200  # keep last 200 latencies per model
_STATE_FILE = os.path.join(config.LOG_DIR, 'metrics_state.json')

def _ensure_dir():
    os.makedirs(config.LOG_DIR, exist_ok=True)

def update(model: str, latency_ms: float | None):
    with _lock:
        _ensure_dir()
        entry = _state['models'].setdefault(model or 'unknown', {'count': 0, 'latencies': []})
        entry['count'] += 1
        if latency_ms is not None:
            lat_list = entry['latencies']
            lat_list.append(latency_ms)
            if len(lat_list) > _LATENCY_CAP:
                del lat_list[0:len(lat_list)-_LATENCY_CAP]
        _state['total_interactions'] += 1
        _state['last_update_ts'] = time.time()
        try:
            with open(_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(_state, f)
        except Exception:
            pass

def snapshot() -> Dict[str, Any]:
    with _lock:
        snap = json.loads(json.dumps(_state))  # deep copy via json roundtrip
    # enrich with per-model stats
    for m, data in snap.get('models', {}).items():
        lats = data.get('latencies', [])
        if lats:
            data['avg_latency_ms'] = round(statistics.fmean(lats), 2)
            data['p95_latency_ms'] = round(_pct(lats, 95), 2)
        else:
            data['avg_latency_ms'] = 0.0
            data['p95_latency_ms'] = 0.0
    return snap

def record_tool(name: str, success: bool = True, blocked: bool = False, decision_type: str = 'model_directive'):
    with _lock:
        t = _state['tools']
        if blocked:
            t['blocked'] += 1
        else:
            t['total_invocations'] += 1
            t['by_name'][name] = t['by_name'].get(name, 0) + 1
            if not success:
                t['failures'] += 1
        t['decision_types'][decision_type] = t['decision_types'].get(decision_type, 0) + 1
        # Update skill EMA (only when not blocked)
        if not blocked:
            s = t['skill']['by_name'].setdefault(name, {'score': 0.5, 'uses': 0, 'successes': 0})
            s['uses'] += 1
            if success:
                s['successes'] += 1
            obs = 1.0 if success else 0.0
            # EMA smoothing
            s['score'] = round(0.7 * s['score'] + 0.3 * obs, 4)
        _ensure_dir()
        try:
            with open(_STATE_FILE, 'w', encoding='utf-8') as f:
                json.dump(_state, f)
        except Exception:
            pass

def get_tool_skill(name: str) -> float:
    with _lock:
        return _state['tools']['skill']['by_name'].get(name, {}).get('score', 0.5)

def should_allow_tool(name: str, min_uses: int = 5, threshold: float = 0.3) -> bool:
    with _lock:
        entry = _state['tools']['skill']['by_name'].get(name)
        if not entry:
            return True  # no history -> allow
        # gate only after some observations
        if entry.get('uses', 0) < min_uses:
            return True
        return entry.get('score', 0.5) >= threshold

__all__ = ['update', 'snapshot', 'record_tool', 'get_tool_skill', 'should_allow_tool']

def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((p/100.0)*(len(s)-1)))
    return s[k]

__all__ = ['update', 'snapshot']