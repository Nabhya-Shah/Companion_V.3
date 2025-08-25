"""Conversation logging (single implementation).

Writes one JSON line per exchange under data/logs/conv_YYYYMMDD.jsonl.
Schema: { ts, user, ai, mode, model, success, error, system_prompt_hash, memory? }
"""
from __future__ import annotations
import os, json, datetime, hashlib
from threading import Lock
from typing import Optional, Dict, Any

from . import config
from . import metrics

_lock = Lock()

def _log_dir() -> str:
    os.makedirs(config.LOG_DIR, exist_ok=True)
    return config.LOG_DIR

def _log_path() -> str:
    date_str = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d')
    return os.path.join(_log_dir(), f"conv_{date_str}.jsonl")

def _hash_prompt(prompt: str) -> str:
    return hashlib.sha1(prompt.encode('utf-8')).hexdigest()[:10]

def log_interaction(user_message: str,
                    ai_message: str,
                    mode: str,
                    system_prompt: str,
                    memory_meta: Optional[Dict[str, Any]] = None,
                    model: str = '',
                    success: bool = True,
                    error: Optional[str] = None,
                    complexity: Optional[int] = None,
                    latency_ms: Optional[float] = None):
    record = {
        'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'user': user_message,
        'ai': ai_message,
        'mode': mode,
        'model': model,
        'success': success,
        'error': error,
        'system_prompt_hash': _hash_prompt(system_prompt),
    }
    if memory_meta:
        record['memory'] = memory_meta
    if complexity is not None:
        record['complexity'] = complexity
    if latency_ms is not None:
        record['latency_ms'] = latency_ms
    path = _log_path()
    line = json.dumps(record, ensure_ascii=False)
    with _lock:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    try:
        metrics.update(model, latency_ms if latency_ms is not None else None)
    except Exception:
        pass

__all__ = ["log_interaction"]