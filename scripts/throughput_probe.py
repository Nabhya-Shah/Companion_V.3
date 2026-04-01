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
    parser.add_argument('--requests', type=int, default=50, help='Total number of requests')
    parser.add_argument('--concurrency', type=int, default=10, help='Number of concurrent workers')
    parser.add_argument('--timeout', type=float, default=5.0, help='Per-request timeout in seconds')
    parser.add_argument(
        '--output',
        default=os.path.join('data', 'benchmarks', 'throughput_probe_latest.json'),
        help='Path to write probe JSON output',
    )
    parser.add_argument('--min-success-rate', type=float, default=0.95, help='Fail if success rate is lower')
    parser.add_argument('--max-p95-ms', type=float, default=0.0, help='Fail if p95 latency exceeds this threshold (0 disables)')
    args = parser.parse_args()

    summary = run_probe(
        base_url=args.base_url,
        endpoint=args.endpoint,
        total_requests=max(1, int(args.requests)),
        concurrency=max(1, int(args.concurrency)),
        timeout_s=max(0.1, float(args.timeout)),
    )
    _write_json(args.output, summary)

    results = summary['results']
    p95 = float(results['latency_ms']['p95_ms'])
    success_rate = float(results['success_rate'])

    print('Throughput probe summary')
    print(f"- target: {summary['target']['url']}")
    print(f"- requests: {args.requests} (concurrency={args.concurrency})")
    print(f"- success_rate: {success_rate:.2%}")
    print(f"- throughput_rps: {results['throughput_rps']}")
    print(f"- latency p95: {p95} ms")
    print(f"- output: {args.output}")

    if success_rate < float(args.min_success_rate):
        print('Probe failed: success rate below threshold')
        return 1
    if float(args.max_p95_ms) > 0.0 and p95 > float(args.max_p95_ms):
        print('Probe failed: p95 latency above threshold')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
