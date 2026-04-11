"""Run live provider contract canaries for chat, memory extraction, and embeddings.

This script is intentionally non-mocked and uses real configured providers.
It writes a JSON artifact for ops tracking and returns non-zero in strict mode
when one or more probes fail.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from companion_ai.core import config as core_config
from companion_ai.llm import extract_profile_facts, generate_model_response, get_embedding


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: str, payload: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def _probe_chat() -> dict:
    started = time.perf_counter()
    prompt = "Canary contract check: reply with token CANARY_OK and one short sentence."
    try:
        text = (
            generate_model_response(
                prompt,
                "You are a contract canary assistant. Keep output short and deterministic.",
                core_config.PRIMARY_MODEL,
            )
            or ''
        ).strip()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        upper = text.upper()
        offline = text.lower().startswith("i'm offline") or 'llm client unavailable' in text.lower()
        errored = 'internal error' in text.lower() or 'trouble connecting' in text.lower()
        ok = bool(text) and not offline and not errored
        return {
            'name': 'chat',
            'ok': ok,
            'elapsed_ms': elapsed_ms,
            'response_preview': text[:220],
            'contains_canary_token': 'CANARY_OK' in upper,
            'offline': offline,
            'errored': errored,
        }
    except Exception as e:
        return {
            'name': 'chat',
            'ok': False,
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
            'error': str(e),
        }


def _probe_memory_extraction() -> dict:
    started = time.perf_counter()
    user_msg = "My name is Canary Bob and I live in Lisbon. I prefer tea over coffee."
    ai_msg = "Noted."
    try:
        facts = extract_profile_facts(user_msg, ai_msg) or {}
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        serialized = json.dumps(facts, ensure_ascii=True).lower()
        has_expected_signal = any(token in serialized for token in ('lisbon', 'tea', 'canary', 'bob'))
        ok = isinstance(facts, dict) and bool(facts) and has_expected_signal
        return {
            'name': 'memory_extraction',
            'ok': ok,
            'elapsed_ms': elapsed_ms,
            'fact_count': len(facts) if isinstance(facts, dict) else 0,
            'has_expected_signal': has_expected_signal,
            'facts_preview': list(facts.keys())[:10] if isinstance(facts, dict) else [],
        }
    except Exception as e:
        return {
            'name': 'memory_extraction',
            'ok': False,
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
            'error': str(e),
        }


def _probe_embedding() -> dict:
    started = time.perf_counter()
    try:
        vec = get_embedding("provider contract canary embedding probe")
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        valid_vec = isinstance(vec, list) and len(vec) > 0
        has_non_zero = bool(valid_vec and any(abs(float(v)) > 0.0 for v in vec[:64]))
        ok = valid_vec and has_non_zero
        return {
            'name': 'embedding',
            'ok': ok,
            'elapsed_ms': elapsed_ms,
            'vector_size': len(vec) if isinstance(vec, list) else 0,
            'has_non_zero': has_non_zero,
        }
    except Exception as e:
        return {
            'name': 'embedding',
            'ok': False,
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
            'error': str(e),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description='Run live provider contract canaries')
    parser.add_argument(
        '--output',
        default=os.path.join('data', 'benchmarks', 'provider_contract_canary_latest.json'),
        help='Path to write canary artifact JSON',
    )
    parser.add_argument('--skip-memory', action='store_true', help='Skip memory extraction probe')
    parser.add_argument('--skip-embedding', action='store_true', help='Skip embedding probe')
    parser.add_argument('--strict', dest='strict', action='store_true', default=True, help='Exit non-zero on failed probe(s)')
    parser.add_argument('--no-strict', dest='strict', action='store_false', help='Always exit zero (report-only mode)')
    args = parser.parse_args()

    started_at = _utc_now_iso()
    started_all = time.perf_counter()
    probes = [_probe_chat()]
    if not args.skip_memory:
        probes.append(_probe_memory_extraction())
    if not args.skip_embedding:
        probes.append(_probe_embedding())

    failed = [probe.get('name') for probe in probes if not probe.get('ok')]
    completed_at = _utc_now_iso()

    payload = {
        'started_at': started_at,
        'completed_at': completed_at,
        'elapsed_ms': round((time.perf_counter() - started_all) * 1000, 1),
        'strict': bool(args.strict),
        'status': 'ok' if not failed else 'degraded',
        'failed_probes': failed,
        'runtime': {
            'chat_provider_effective': core_config.get_effective_local_chat_provider(),
            'memory_provider_effective': core_config.get_effective_memory_processing_provider(),
            'embedding_provider': core_config.EMBEDDING_PROVIDER,
            'primary_model': core_config.PRIMARY_MODEL,
            'memory_processing_model': core_config.MEMORY_PROCESSING_MODEL,
            'embedding_model': core_config.EMBEDDING_MODEL,
        },
        'probes': probes,
    }

    _write_json(args.output, payload)

    print('Provider contract canary')
    print(f"- status: {payload['status']}")
    print(f"- failed_probes: {failed or []}")
    print(f"- output: {args.output}")

    if args.strict and failed:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
