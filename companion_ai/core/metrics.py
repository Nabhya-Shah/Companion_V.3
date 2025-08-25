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

def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    k = int(round((p/100.0)*(len(s)-1)))
    return s[k]

__all__ = ['update', 'snapshot']