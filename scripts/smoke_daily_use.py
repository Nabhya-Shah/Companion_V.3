"""Daily-use smoke test for core web endpoints.

Checks:
- /api/health
- /api/models
- /api/memory
- /api/chat/send

Usage:
  python scripts/smoke_daily_use.py
  python scripts/smoke_daily_use.py --base-url http://127.0.0.1:5000 --token YOUR_TOKEN
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import requests


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-API-TOKEN"] = token
    return headers


def _check_get(session: requests.Session, base_url: str, path: str, token: str | None) -> tuple[bool, str]:
    url = f"{base_url}{path}"
    try:
        response = session.get(url, headers=_headers(token), timeout=20)
        ok = response.status_code == 200
        details = f"{response.status_code}"
        if not ok:
            details += f" - {response.text[:180]}"
        return ok, details
    except Exception as err:
        return False, str(err)


def _check_chat(session: requests.Session, base_url: str, token: str | None) -> tuple[bool, str]:
    url = f"{base_url}/api/chat/send"
    payload: dict[str, Any] = {
        "message": "smoke test ping",
        "tts_enabled": False,
    }
    try:
        response = session.post(
            url,
            headers=_headers(token),
            data=json.dumps(payload),
            timeout=45,
        )
        if response.status_code != 200:
            return False, f"{response.status_code} - {response.text[:180]}"

        # /api/chat/send streams SSE lines; validate we got a chunk and done marker.
        saw_chunk = False
        saw_done = False
        full_response = ""
        for raw_line in response.text.splitlines():
            line = raw_line.strip()
            if not line.startswith("data: "):
                continue
            try:
                evt = json.loads(line[6:])
            except Exception:
                continue
            if isinstance(evt, dict) and evt.get("chunk"):
                saw_chunk = True
            if isinstance(evt, dict) and evt.get("done"):
                saw_done = True
                full_response = str(evt.get("full_response") or "").strip()

        if not saw_chunk and not full_response:
            return False, "200 - missing streamed chunk/full_response"
        if not saw_done:
            return False, "200 - missing done event"

        return True, "200"
    except Exception as err:
        return False, str(err)


def main() -> int:
    parser = argparse.ArgumentParser(description="Companion daily-use smoke checks")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Base URL for running web server")
    parser.add_argument("--token", default=os.getenv("API_AUTH_TOKEN", ""), help="API token for protected routes")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    token = args.token or None

    checks: list[tuple[str, bool, str]] = []
    session = requests.Session()

    for path in ("/api/health", "/api/models", "/api/memory"):
        ok, detail = _check_get(session, base_url, path, token)
        checks.append((path, ok, detail))

    chat_ok, chat_detail = _check_chat(session, base_url, token)
    checks.append(("/api/chat/send", chat_ok, chat_detail))

    print("Companion daily-use smoke results")
    print("=" * 34)
    failures = 0
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        print(f"[{status}] {name}: {detail}")
        if not ok:
            failures += 1

    if failures:
        print(f"\nSmoke check failed: {failures} endpoint(s) failed")
        return 1

    print("\nSmoke check passed: all endpoints healthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
