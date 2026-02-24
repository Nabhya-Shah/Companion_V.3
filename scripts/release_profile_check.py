"""Release profile checker for local daily-use builds.

Checks:
- Python version compatibility
- Required env presence (soft/hard modes)
- Core endpoint smoke checks

Usage:
  python scripts/release_profile_check.py
  python scripts/release_profile_check.py --require-llm
"""

from __future__ import annotations

import argparse
import os
import sys
import subprocess
from pathlib import Path


def check_python() -> tuple[bool, str]:
    v = sys.version_info
    ok = (v.major, v.minor) in {(3, 11), (3, 12)}
    return ok, f"{v.major}.{v.minor}.{v.micro}"


def check_env(require_llm: bool) -> tuple[bool, str]:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if require_llm and not key:
        return False, "GROQ_API_KEY missing"
    return True, "ok"


def run_smoke() -> tuple[bool, str]:
    script = Path(__file__).parent / "smoke_daily_use.py"
    proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True)
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip()[-500:]


def main() -> int:
    parser = argparse.ArgumentParser(description="Companion release profile check")
    parser.add_argument("--require-llm", action="store_true", help="Fail if GROQ_API_KEY is missing")
    args = parser.parse_args()

    py_ok, py_msg = check_python()
    env_ok, env_msg = check_env(args.require_llm)
    smoke_ok, smoke_msg = run_smoke()

    print("Release profile check")
    print("=" * 24)
    print(f"[{'PASS' if py_ok else 'FAIL'}] python: {py_msg}")
    print(f"[{'PASS' if env_ok else 'FAIL'}] env: {env_msg}")
    print(f"[{'PASS' if smoke_ok else 'FAIL'}] smoke: {'ok' if smoke_ok else smoke_msg}")

    return 0 if (py_ok and env_ok and smoke_ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
