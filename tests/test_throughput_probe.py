import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / 'scripts' / 'throughput_probe.py'
SPEC = importlib.util.spec_from_file_location('throughput_probe', SCRIPT_PATH)
throughput_probe = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = throughput_probe
SPEC.loader.exec_module(throughput_probe)


class _FakeResponse:
    def __init__(self, code=200, payload=b'{}'):
        self._code = code
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self._payload

    def getcode(self):
        return self._code


def test_percentile_linear_interpolation():
    values = [1.0, 2.0, 3.0, 4.0]
    assert throughput_probe._percentile(values, 50) == 2.5
    assert throughput_probe._percentile(values, 95) > 3.0


def test_summarize_latencies_shape():
    summary = throughput_probe._summarize_latencies([10.0, 20.0, 30.0, 40.0])
    assert summary['count'] == 4
    assert summary['min_ms'] == 10.0
    assert summary['max_ms'] == 40.0
    assert summary['p50_ms'] == 25.0


def test_run_probe_success_path(monkeypatch):
    monkeypatch.setattr(
        throughput_probe.urllib.request,
        'urlopen',
        lambda req, timeout=5.0: _FakeResponse(code=200, payload=b'{}'),
    )

    result = throughput_probe.run_probe(
        base_url='http://127.0.0.1:5000',
        endpoint='/api/health',
        total_requests=8,
        concurrency=4,
        timeout_s=1.0,
    )

    assert result['results']['ok_count'] == 8
    assert result['results']['error_count'] == 0
    assert result['results']['statuses'].get('200') == 8
    assert result['results']['success_rate'] == 1.0
    assert result['results']['latency_ms']['count'] == 8
