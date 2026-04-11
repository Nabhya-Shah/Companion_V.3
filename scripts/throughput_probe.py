"""Lightweight HTTP throughput probe for Companion endpoints.

Usage examples:
  .venv/bin/python scripts/throughput_probe.py --base-url http://127.0.0.1:5000 --endpoint /api/health
  .venv/bin/python scripts/throughput_probe.py --requests 100 --concurrency 20 --output data/benchmarks/health_probe.json
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])

    ordered = sorted(values)
    p = max(0.0, min(100.0, float(percentile))) / 100.0
    idx = p * (len(ordered) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(ordered) - 1)
    frac = idx - lower
    return float(ordered[lower] + (ordered[upper] - ordered[lower]) * frac)


def _summarize_latencies(latencies_ms: list[float]) -> dict:
    if not latencies_ms:
        return {
            'count': 0,
            'min_ms': 0.0,
            'max_ms': 0.0,
            'avg_ms': 0.0,
            'p50_ms': 0.0,
            'p95_ms': 0.0,
            'p99_ms': 0.0,
        }

    return {
        'count': len(latencies_ms),
        'min_ms': round(min(latencies_ms), 2),
        'max_ms': round(max(latencies_ms), 2),
        'avg_ms': round(sum(latencies_ms) / len(latencies_ms), 2),
        'p50_ms': round(_percentile(latencies_ms, 50), 2),
        'p95_ms': round(_percentile(latencies_ms, 95), 2),
        'p99_ms': round(_percentile(latencies_ms, 99), 2),
    }


def run_probe(
    *,
    base_url: str,
    endpoint: str,
    total_requests: int,
    concurrency: int,
    timeout_s: float,
) -> dict:
    url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"

    def _request_once() -> dict:
        started = time.perf_counter()
        req = urllib.request.Request(url, method='GET')
        try:
            with urllib.request.urlopen(req, timeout=timeout_s) as resp:
                _ = resp.read()
                status = int(resp.getcode())
                latency_ms = (time.perf_counter() - started) * 1000.0
                return {'status': status, 'latency_ms': latency_ms, 'error': ''}
        except urllib.error.HTTPError as e:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return {'status': int(e.code), 'latency_ms': latency_ms, 'error': f'http_error:{e.code}'}
        except Exception as e:
            latency_ms = (time.perf_counter() - started) * 1000.0
            return {'status': 0, 'latency_ms': latency_ms, 'error': str(e)}

    started_all = time.perf_counter()
    statuses: dict[str, int] = {}
    failures: list[str] = []
    latencies_ms: list[float] = []
    ok_count = 0

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futures = [pool.submit(_request_once) for _ in range(max(1, total_requests))]
        for fut in as_completed(futures):
            result = fut.result()
            status = int(result.get('status') or 0)
            statuses[str(status)] = statuses.get(str(status), 0) + 1
            latencies_ms.append(float(result.get('latency_ms') or 0.0))
            if 200 <= status < 400:
                ok_count += 1
            else:
                failures.append(str(result.get('error') or f'status:{status}'))

    elapsed_s = max(0.001, time.perf_counter() - started_all)
    total = max(1, total_requests)
    success_rate = ok_count / total

    summary = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'target': {
            'base_url': base_url,
            'endpoint': endpoint,
            'url': url,
        },
        'request_plan': {
            'total_requests': total_requests,
            'concurrency': concurrency,
            'timeout_s': timeout_s,
        },
        'results': {
            'ok_count': ok_count,
            'error_count': total - ok_count,
            'success_rate': round(success_rate, 4),
            'elapsed_s': round(elapsed_s, 3),
            'throughput_rps': round(total / elapsed_s, 2),
            'statuses': statuses,
            'latency_ms': _summarize_latencies(latencies_ms),
            'sample_errors': failures[:10],
        },
    }
    return summary


def _evaluate_probe_thresholds(results: dict, min_success_rate: float, max_p95_ms: float) -> list[str]:
    alerts: list[str] = []
    success_rate = float(results.get('success_rate') or 0.0)
    latency = results.get('latency_ms') if isinstance(results.get('latency_ms'), dict) else {}
    p95 = float(
        latency.get('p95_ms')
        or latency.get('p95_max_ms')
        or 0.0
    )

    if success_rate < float(min_success_rate):
        alerts.append(f'success_rate_below_threshold:{success_rate:.4f}<{float(min_success_rate):.4f}')
    if float(max_p95_ms) > 0.0 and p95 > float(max_p95_ms):
        alerts.append(f'p95_above_threshold:{p95:.2f}>{float(max_p95_ms):.2f}')
    return alerts


def _aggregate_profile_results(phases: list[dict]) -> dict:
    total_requests = 0
    ok_count = 0
    elapsed_s = 0.0
    statuses: dict[str, int] = {}
    p95_values: list[float] = []
    p99_values: list[float] = []
    sample_errors: list[str] = []

    for phase in phases:
        request_plan = phase.get('request_plan') if isinstance(phase.get('request_plan'), dict) else {}
        results = phase.get('results') if isinstance(phase.get('results'), dict) else {}
        latency = results.get('latency_ms') if isinstance(results.get('latency_ms'), dict) else {}

        total_requests += int(request_plan.get('total_requests') or 0)
        ok_count += int(results.get('ok_count') or 0)
        elapsed_s += float(results.get('elapsed_s') or 0.0)

        phase_statuses = results.get('statuses') if isinstance(results.get('statuses'), dict) else {}
        for code, count in phase_statuses.items():
            statuses[str(code)] = statuses.get(str(code), 0) + int(count or 0)

        p95_values.append(float(latency.get('p95_ms') or 0.0))
        p99_values.append(float(latency.get('p99_ms') or 0.0))

        phase_errors = results.get('sample_errors') if isinstance(results.get('sample_errors'), list) else []
        for err in phase_errors:
            if len(sample_errors) >= 10:
                break
            sample_errors.append(str(err))

    total_requests = max(1, total_requests)
    elapsed_s = max(0.001, elapsed_s)
    error_count = max(0, total_requests - ok_count)
    success_rate = ok_count / total_requests

    return {
        'ok_count': ok_count,
        'error_count': error_count,
        'success_rate': round(success_rate, 4),
        'elapsed_s': round(elapsed_s, 3),
        'throughput_rps': round(total_requests / elapsed_s, 2),
        'statuses': statuses,
        'latency_ms': {
            'p95_max_ms': round(max(p95_values) if p95_values else 0.0, 2),
            'p95_avg_ms': round((sum(p95_values) / len(p95_values)) if p95_values else 0.0, 2),
            'p99_max_ms': round(max(p99_values) if p99_values else 0.0, 2),
        },
        'sample_errors': sample_errors,
    }


def run_profile(
    *,
    profile: str,
    base_url: str,
    endpoint: str,
    total_requests: int,
    concurrency: int,
    timeout_s: float,
    sustained_phases: int,
    burst_rounds: int,
    burst_requests: int,
    burst_concurrency: int,
    min_success_rate: float,
    max_p95_ms: float,
) -> dict:
    profile_name = str(profile or 'single').strip().lower()
    phase_plan: list[dict] = []

    if profile_name == 'sustained':
        for idx in range(max(1, int(sustained_phases))):
            phase_plan.append({
                'name': f'sustained_{idx + 1}',
                'requests': max(1, int(total_requests)),
                'concurrency': max(1, int(concurrency)),
            })
    elif profile_name == 'burst':
        base_requests = max(1, int(total_requests) // 2)
        base_concurrency = max(1, int(concurrency) // 2)
        spike_requests = max(1, int(burst_requests))
        spike_concurrency = max(1, int(burst_concurrency))
        for idx in range(max(1, int(burst_rounds))):
            phase_plan.append({
                'name': f'burst_{idx + 1}_baseline',
                'requests': base_requests,
                'concurrency': base_concurrency,
            })
            phase_plan.append({
                'name': f'burst_{idx + 1}_spike',
                'requests': spike_requests,
                'concurrency': spike_concurrency,
            })
    else:
        phase_plan.append({
            'name': 'single',
            'requests': max(1, int(total_requests)),
            'concurrency': max(1, int(concurrency)),
        })
        profile_name = 'single'

    phases: list[dict] = []
    all_alerts: list[str] = []
    for phase in phase_plan:
        summary = run_probe(
            base_url=base_url,
            endpoint=endpoint,
            total_requests=int(phase['requests']),
            concurrency=int(phase['concurrency']),
            timeout_s=timeout_s,
        )
        results = summary.get('results') if isinstance(summary.get('results'), dict) else {}
        phase_alerts = _evaluate_probe_thresholds(results, min_success_rate=min_success_rate, max_p95_ms=max_p95_ms)
        for alert in phase_alerts:
            all_alerts.append(f"{phase['name']}:{alert}")

        phases.append({
            'name': phase['name'],
            'request_plan': summary.get('request_plan'),
            'results': results,
            'alerts': phase_alerts,
        })

    if profile_name == 'single':
        request_plan = phases[0]['request_plan'] if phases else {
            'total_requests': total_requests,
            'concurrency': concurrency,
            'timeout_s': timeout_s,
        }
        aggregate_results = phases[0]['results'] if phases else {}
    else:
        request_plan = {
            'profile': profile_name,
            'phase_count': len(phases),
            'total_requests_planned': sum(int((phase.get('request_plan') or {}).get('total_requests') or 0) for phase in phases),
            'timeout_s': timeout_s,
        }
        aggregate_results = _aggregate_profile_results(phases)

    return {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'target': {
            'base_url': base_url,
            'endpoint': endpoint,
            'url': f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}",
        },
        'profile': profile_name,
        'request_plan': request_plan,
        'results': aggregate_results,
        'phases': phases,
        'alerts': all_alerts,
    }


def _write_json(path: str, payload: dict) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a lightweight HTTP throughput probe')
    parser.add_argument('--base-url', default='http://127.0.0.1:5000', help='Base URL to probe')
    parser.add_argument('--endpoint', default='/api/health', help='Endpoint path to probe')
    parser.add_argument(
        '--profile',
        choices=['single', 'sustained', 'burst'],
        default='single',
        help='Probe profile: single request batch, repeated sustained phases, or burst baseline/spike rounds',
    )
    parser.add_argument('--requests', type=int, default=50, help='Total number of requests')
    parser.add_argument('--concurrency', type=int, default=10, help='Number of concurrent workers')
    parser.add_argument('--sustained-phases', type=int, default=3, help='Number of repeated phases for sustained profile')
    parser.add_argument('--burst-rounds', type=int, default=3, help='Number of baseline/spike rounds for burst profile')
    parser.add_argument('--burst-requests', type=int, default=80, help='Requests per burst spike phase')
    parser.add_argument('--burst-concurrency', type=int, default=20, help='Concurrency for burst spike phase')
    parser.add_argument('--timeout', type=float, default=5.0, help='Per-request timeout in seconds')
    parser.add_argument(
        '--output',
        default=os.path.join('data', 'benchmarks', 'throughput_probe_latest.json'),
        help='Path to write probe JSON output',
    )
    parser.add_argument('--min-success-rate', type=float, default=0.95, help='Fail if success rate is lower')
    parser.add_argument('--max-p95-ms', type=float, default=0.0, help='Fail if p95 latency exceeds this threshold (0 disables)')
    args = parser.parse_args()

    summary = run_profile(
        profile=str(args.profile),
        base_url=args.base_url,
        endpoint=args.endpoint,
        total_requests=max(1, int(args.requests)),
        concurrency=max(1, int(args.concurrency)),
        timeout_s=max(0.1, float(args.timeout)),
        sustained_phases=max(1, int(args.sustained_phases)),
        burst_rounds=max(1, int(args.burst_rounds)),
        burst_requests=max(1, int(args.burst_requests)),
        burst_concurrency=max(1, int(args.burst_concurrency)),
        min_success_rate=float(args.min_success_rate),
        max_p95_ms=float(args.max_p95_ms),
    )
    _write_json(args.output, summary)

    results = summary['results']
    latency = results.get('latency_ms') if isinstance(results.get('latency_ms'), dict) else {}
    p95 = float(latency.get('p95_ms') or latency.get('p95_max_ms') or 0.0)
    success_rate = float(results['success_rate'])
    alerts = summary.get('alerts') if isinstance(summary.get('alerts'), list) else []

    print('Throughput probe summary')
    print(f"- target: {summary['target']['url']}")
    print(f"- profile: {summary.get('profile')}")
    print(f"- requests: {args.requests} (concurrency={args.concurrency})")
    print(f"- success_rate: {success_rate:.2%}")
    print(f"- throughput_rps: {results['throughput_rps']}")
    print(f"- latency p95: {p95} ms")
    print(f"- alerts: {alerts or []}")
    print(f"- output: {args.output}")

    if alerts:
        print('Probe failed: one or more threshold alerts triggered')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
