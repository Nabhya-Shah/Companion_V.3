#!/usr/bin/env python3
"""Lightweight regression benchmark for routing/tool/memory/retrieval behavior.

Exit codes:
- 0: all benchmark suites pass
- 1: one or more suites failed or exceeded threshold
"""

from __future__ import annotations

import subprocess
import sys
import time
from dataclasses import dataclass


@dataclass
class Suite:
    name: str
    pytest_args: list[str]
    max_seconds: float


SUITES = [
    Suite(
        name="routing_and_orchestrator",
        pytest_args=[
            "tests/test_model_selection.py",
            "tests/test_orchestrator.py::TestOrchestratorToolChoiceFallback",
        ],
        max_seconds=60.0,
    ),
    Suite(
        name="tool_policy_and_approval",
        pytest_args=[
            "tests/test_tools.py",
            "tests/test_approval.py",
            "tests/test_feature_permissions.py",
        ],
        max_seconds=90.0,
    ),
    Suite(
        name="memory_queue_and_retrieval_events",
        pytest_args=[
            "tests/test_memory_write_queue.py",
            "tests/test_retrieval_observability.py",
            "tests/test_retrieval_stage_events.py",
        ],
        max_seconds=90.0,
    ),
]


def run_suite(suite: Suite) -> tuple[bool, float, int]:
    cmd = [sys.executable, "-m", "pytest", "-q", *suite.pytest_args]
    started = time.perf_counter()
    proc = subprocess.run(cmd)
    elapsed = time.perf_counter() - started

    ok = proc.returncode == 0 and elapsed <= suite.max_seconds
    return ok, elapsed, proc.returncode


def main() -> int:
    failed = False

    print("== Companion Agent Regression Benchmark ==")
    for suite in SUITES:
        print(f"\n[run] {suite.name}")
        print(f"      max_seconds={suite.max_seconds:.1f}")
        ok, elapsed, rc = run_suite(suite)
        status = "PASS" if ok else "FAIL"
        print(f"[result] {suite.name}: {status} | return_code={rc} | elapsed={elapsed:.2f}s")
        if not ok:
            if rc == 0 and elapsed > suite.max_seconds:
                print(f"         threshold exceeded: elapsed {elapsed:.2f}s > {suite.max_seconds:.2f}s")
            failed = True

    if failed:
        print("\nBenchmark status: FAILED")
        return 1

    print("\nBenchmark status: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
