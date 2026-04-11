import importlib.util
from pathlib import Path


_SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'throughput_probe.py'
_SPEC = importlib.util.spec_from_file_location('throughput_probe_module', _SCRIPT_PATH)
throughput_probe = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(throughput_probe)


def test_evaluate_probe_thresholds_reports_failures():
    alerts = throughput_probe._evaluate_probe_thresholds(
        {
            'success_rate': 0.82,
            'latency_ms': {'p95_ms': 210.0},
        },
        min_success_rate=0.95,
        max_p95_ms=150.0,
    )

    assert any('success_rate_below_threshold' in item for item in alerts)
    assert any('p95_above_threshold' in item for item in alerts)


def test_run_profile_burst_aggregates_and_alerts(monkeypatch):
    calls = []

    def _fake_run_probe(*, base_url, endpoint, total_requests, concurrency, timeout_s):
        calls.append((total_requests, concurrency))
        return {
            'timestamp_utc': '2026-04-11T00:00:00+00:00',
            'target': {
                'base_url': base_url,
                'endpoint': endpoint,
                'url': f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}",
            },
            'request_plan': {
                'total_requests': total_requests,
                'concurrency': concurrency,
                'timeout_s': timeout_s,
            },
            'results': {
                'ok_count': max(0, total_requests - 1),
                'error_count': 1,
                'success_rate': round((max(0, total_requests - 1) / max(1, total_requests)), 4),
                'elapsed_s': 1.0,
                'throughput_rps': float(total_requests),
                'statuses': {'200': max(0, total_requests - 1), '500': 1},
                'latency_ms': {
                    'count': total_requests,
                    'min_ms': 10.0,
                    'max_ms': 300.0,
                    'avg_ms': 120.0,
                    'p50_ms': 100.0,
                    'p95_ms': 220.0,
                    'p99_ms': 280.0,
                },
                'sample_errors': ['http_error:500'],
            },
        }

    monkeypatch.setattr(throughput_probe, 'run_probe', _fake_run_probe)

    summary = throughput_probe.run_profile(
        profile='burst',
        base_url='http://127.0.0.1:5000',
        endpoint='/api/health',
        total_requests=40,
        concurrency=8,
        timeout_s=5.0,
        sustained_phases=2,
        burst_rounds=2,
        burst_requests=50,
        burst_concurrency=16,
        min_success_rate=0.99,
        max_p95_ms=150.0,
    )

    assert summary['profile'] == 'burst'
    assert len(summary['phases']) == 4
    assert len(calls) == 4
    assert summary['results']['ok_count'] > 0
    assert isinstance(summary.get('alerts'), list)
    assert summary['alerts']
