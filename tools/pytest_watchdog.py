"""Run pytest with watchdog timeouts to catch hangs reliably.

Usage examples:
  python tools/pytest_watchdog.py
  python tools/pytest_watchdog.py --idle-timeout 120 --max-duration 1800 -- -q tests/test_tools.py

Exit codes:
  0: pytest passed
  1: pytest failed
  124: watchdog timeout (idle or max duration)
  2: internal watchdog error
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from typing import Optional


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run pytest with hang watchdog")
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=float(os.getenv("PYTEST_IDLE_TIMEOUT_SECONDS", "0")),
        help="Seconds without test output before aborting (<=0 disables idle timeout)",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        default=float(os.getenv("PYTEST_MAX_DURATION_SECONDS", "1800")),
        help="Maximum total runtime seconds before aborting",
    )
    parser.add_argument(
        "pytest_args",
        nargs=argparse.REMAINDER,
        help="Arguments passed to pytest (prefix with --)",
    )
    return parser.parse_args()


def _normalize_pytest_args(pytest_args: list[str]) -> list[str]:
    args = list(pytest_args)
    if args and args[0] == "--":
        args = args[1:]
    if not args:
        args = ["-q"]
    return args


def main() -> int:
    args = _parse_args()
    pytest_args = _normalize_pytest_args(args.pytest_args)

    cmd = [sys.executable, "-m", "pytest", *pytest_args]
    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    print(
        f"[watchdog] starting: {' '.join(cmd)} | idle_timeout={args.idle_timeout}s | max_duration={args.max_duration}s",
        flush=True,
    )

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env,
        )
    except Exception as exc:
        print(f"[watchdog] failed to start pytest: {exc}", flush=True)
        return 2

    last_output_ts = time.time()
    start_ts = last_output_ts
    stream_closed = threading.Event()

    def _reader() -> None:
        nonlocal last_output_ts
        assert proc.stdout is not None
        try:
            for chunk in iter(lambda: proc.stdout.read(1), ""):
                if not chunk:
                    break
                sys.stdout.write(chunk)
                sys.stdout.flush()
                last_output_ts = time.time()
        finally:
            stream_closed.set()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()

    timeout_reason: Optional[str] = None
    while True:
        rc = proc.poll()
        now = time.time()

        if rc is not None:
            stream_closed.wait(timeout=2)
            print(f"\n[watchdog] pytest exited with code {rc}", flush=True)
            return rc

        if args.idle_timeout > 0 and (now - last_output_ts > args.idle_timeout):
            timeout_reason = (
                f"no output for {now - last_output_ts:.1f}s (idle timeout {args.idle_timeout:.1f}s)"
            )
            break

        if now - start_ts > args.max_duration:
            timeout_reason = (
                f"total runtime {now - start_ts:.1f}s exceeded max duration {args.max_duration:.1f}s"
            )
            break

        time.sleep(1.0)

    print(f"\n[watchdog] TIMEOUT: {timeout_reason}", flush=True)
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)

    stream_closed.wait(timeout=2)
    print("[watchdog] pytest terminated by watchdog", flush=True)
    return 124


if __name__ == "__main__":
    raise SystemExit(main())
