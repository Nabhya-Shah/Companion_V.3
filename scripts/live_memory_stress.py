"""Live memory stress runner for Companion web server.

Runs heavy chat workloads against /api/chat/send, collects latency/success data,
and validates memory persistence via /api/memory after optional server restarts.

Usage examples:
  .venv/bin/python scripts/live_memory_stress.py --mode exercise --prefix pilot-on --sessions 4 --turns 45 --output data/benchmarks/live_pilot_on_pre_restart.json
  .venv/bin/python scripts/live_memory_stress.py --mode verify --prefix pilot-on --sessions 4 --output data/benchmarks/live_pilot_on_post_restart.json
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time
from datetime import datetime, timezone
from typing import Any

import requests


def _safe_p95(values: list[float]) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    ordered = sorted(values)
    idx = int(round(0.95 * (len(ordered) - 1)))
    idx = max(0, min(idx, len(ordered) - 1))
    return float(ordered[idx])


def _parse_sse_response(body_text: str) -> dict[str, Any]:
    parsed = {
        "saw_done": False,
        "full_response": "",
        "error": "",
        "trace_id": "",
        "chunks": 0,
    }
    for raw_line in body_text.splitlines():
        line = raw_line.strip()
        if not line.startswith("data: "):
            continue
        try:
            payload = json.loads(line[6:])
        except Exception:
            continue

        if isinstance(payload, dict) and payload.get("chunk"):
            parsed["chunks"] += 1
        if isinstance(payload, dict) and payload.get("error"):
            parsed["error"] = str(payload.get("error"))
        if isinstance(payload, dict) and payload.get("done"):
            parsed["saw_done"] = True
            parsed["full_response"] = str(payload.get("full_response") or "")
            parsed["trace_id"] = str(payload.get("trace_id") or "")
    return parsed


def _chat_once(
    session: requests.Session,
    base_url: str,
    message: str,
    session_id: str,
    profile_id: str,
    timeout_s: float,
) -> dict[str, Any]:
    url = f"{base_url}/api/chat/send"
    payload = {
        "message": message,
        "session_id": session_id,
        "profile_id": profile_id,
        "tts_enabled": False,
    }

    started = time.perf_counter()
    try:
        response = session.post(url, json=payload, timeout=timeout_s)
        latency_ms = (time.perf_counter() - started) * 1000.0
    except Exception as e:
        return {
            "ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000.0, 2),
            "status_code": 0,
            "error": str(e),
            "response_text": "",
            "trace_id": "",
        }

    if response.status_code != 200:
        return {
            "ok": False,
            "latency_ms": round(latency_ms, 2),
            "status_code": int(response.status_code),
            "error": f"http_{response.status_code}: {response.text[:180]}",
            "response_text": "",
            "trace_id": "",
        }

    parsed = _parse_sse_response(response.text)
    ok = bool(parsed["saw_done"]) and not parsed["error"]
    return {
        "ok": ok,
        "latency_ms": round(latency_ms, 2),
        "status_code": int(response.status_code),
        "error": parsed["error"],
        "response_text": parsed["full_response"],
        "trace_id": parsed["trace_id"],
        "chunks": parsed["chunks"],
    }


def _memory_snapshot(
    session: requests.Session,
    base_url: str,
    session_id: str,
    profile_id: str,
    timeout_s: float,
) -> dict[str, Any]:
    url = f"{base_url}/api/memory"
    params = {
        "detailed": "1",
        "session_id": session_id,
        "profile_id": profile_id,
    }
    try:
        response = session.get(url, params=params, timeout=timeout_s)
        payload = response.json() if response.ok else {}
    except Exception as e:
        return {
            "ok": False,
            "error": str(e),
            "fact_count": 0,
            "has_name": False,
            "has_city": False,
        }

    detailed = payload.get("profile_detailed") if isinstance(payload, dict) else []
    detailed = detailed if isinstance(detailed, list) else []
    values = [str(item.get("value") or "") for item in detailed if isinstance(item, dict)]
    joined = "\n".join(values).lower()
    return {
        "ok": bool(response.ok),
        "error": "" if response.ok else f"http_{response.status_code}",
        "fact_count": len(detailed),
        "has_name": "stressuser" in joined,
        "has_city": "city" in joined,
    }


def _queue_snapshot(session: requests.Session, base_url: str, timeout_s: float) -> dict[str, Any]:
    try:
        q = session.get(f"{base_url}/api/memory/write-queue?limit=200", timeout=timeout_s)
        q_payload = q.json() if q.ok else {}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {
        "ok": bool(q.ok),
        "queued_count": int((q_payload or {}).get("queued_count", 0) or 0),
        "trace_id": str((q_payload or {}).get("trace_id") or ""),
    }


def _migration_snapshot(session: requests.Session, base_url: str, timeout_s: float) -> dict[str, Any]:
    try:
        r = session.get(f"{base_url}/api/memory/migration-readiness", timeout=timeout_s)
        payload = r.json() if r.ok else {}
    except Exception as e:
        return {"ok": False, "error": str(e)}

    return {
        "ok": bool(r.ok),
        "level": str((payload or {}).get("level") or "unknown"),
        "reasons": list((payload or {}).get("reasons") or []),
        "queue_depth": int(((payload or {}).get("metrics") or {}).get("queue_depth", 0) or 0),
        "failure_rate": float(((payload or {}).get("metrics") or {}).get("failure_rate", 0.0) or 0.0),
    }


def _build_messages(session_num: int, turns: int) -> list[str]:
    core = [
        f"My name is StressUser{session_num}.",
        f"I live in City{session_num}.",
        f"I work as systems engineer number {session_num}.",
        f"My favorite drink is tea{session_num}.",
        f"I wake up around {6 + (session_num % 3)}:30 most weekdays.",
    ]

    extra: list[str] = []
    index = 0
    while len(core) + len(extra) < turns:
        if index % 7 == 0:
            extra.append("What do you remember about me right now? Keep it short.")
        elif index % 9 == 0:
            extra.append(f"Actually I moved recently and now spend time in City{session_num}-{index} too.")
        elif index % 5 == 0:
            extra.append(f"I am planning a routine called DeepWork{session_num}-{index} for mornings.")
        else:
            extra.append(f"Note this preference update {index}: I like focus block length {20 + (index % 15)} minutes.")
        index += 1

    return (core + extra)[:turns]


def run_exercise(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    session = requests.Session()

    sessions_data: list[dict[str, Any]] = []
    latencies: list[float] = []
    total_requests = 0
    failed_requests = 0

    for s in range(1, args.sessions + 1):
        session_id = f"{args.prefix}-sess-{s}"
        profile_id = "stress"
        messages = _build_messages(s, args.turns)

        session_failures = 0
        session_traces: list[str] = []

        for message in messages:
            result = _chat_once(
                session,
                base_url,
                message,
                session_id,
                profile_id,
                timeout_s=args.timeout,
            )
            total_requests += 1
            latencies.append(float(result.get("latency_ms", 0.0) or 0.0))
            if not result.get("ok"):
                failed_requests += 1
                session_failures += 1
            if result.get("trace_id"):
                session_traces.append(str(result.get("trace_id")))

        memory = _memory_snapshot(session, base_url, session_id, profile_id, args.timeout)
        sessions_data.append(
            {
                "session_id": session_id,
                "profile_id": profile_id,
                "turns": len(messages),
                "failures": session_failures,
                "trace_ids_sample": session_traces[:8],
                "memory": memory,
            }
        )

    queue_data = _queue_snapshot(session, base_url, args.timeout)
    migration_data = _migration_snapshot(session, base_url, args.timeout)

    success_count = total_requests - failed_requests
    success_rate = (success_count / total_requests) if total_requests else 0.0
    latency_avg = statistics.mean(latencies) if latencies else 0.0

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "exercise",
        "label": args.label,
        "prefix": args.prefix,
        "base_url": base_url,
        "workload": {
            "sessions": args.sessions,
            "turns_per_session": args.turns,
            "requests_total": total_requests,
        },
        "results": {
            "requests_ok": success_count,
            "requests_failed": failed_requests,
            "success_rate": round(success_rate, 4),
            "latency_avg_ms": round(latency_avg, 2),
            "latency_p95_ms": round(_safe_p95(latencies), 2),
            "latency_max_ms": round(max(latencies), 2) if latencies else 0.0,
        },
        "sessions": sessions_data,
        "queue": queue_data,
        "migration_readiness": migration_data,
    }


def run_verify(args: argparse.Namespace) -> dict[str, Any]:
    base_url = args.base_url.rstrip("/")
    session = requests.Session()

    checks: list[dict[str, Any]] = []
    recall_hits = 0

    for s in range(1, args.sessions + 1):
        session_id = f"{args.prefix}-sess-{s}"
        profile_id = "stress"
        result = _chat_once(
            session,
            base_url,
            "What is my name and where do I live?",
            session_id,
            profile_id,
            timeout_s=args.timeout,
        )
        text = str(result.get("response_text") or "").lower()
        expected_name = f"stressuser{s}".lower()
        expected_city = f"city{s}".lower()
        has_recall = expected_name in text and "city" in text
        if has_recall:
            recall_hits += 1

        memory = _memory_snapshot(session, base_url, session_id, profile_id, args.timeout)
        checks.append(
            {
                "session_id": session_id,
                "chat_ok": bool(result.get("ok")),
                "chat_latency_ms": float(result.get("latency_ms", 0.0) or 0.0),
                "recall_text_hit": has_recall,
                "memory": memory,
            }
        )

    queue_data = _queue_snapshot(session, base_url, args.timeout)
    migration_data = _migration_snapshot(session, base_url, args.timeout)

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "verify",
        "label": args.label,
        "prefix": args.prefix,
        "base_url": base_url,
        "sessions": checks,
        "results": {
            "recall_hits": recall_hits,
            "recall_hit_rate": round((recall_hits / args.sessions) if args.sessions else 0.0, 4),
        },
        "queue": queue_data,
        "migration_readiness": migration_data,
    }


def _write_output(path: str, payload: dict[str, Any]) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live memory stress workload against Companion web")
    parser.add_argument("--mode", choices=["exercise", "verify"], required=True)
    parser.add_argument("--label", default="pilot", help="Label for report metadata")
    parser.add_argument("--prefix", required=True, help="Session prefix used for deterministic session ids")
    parser.add_argument("--sessions", type=int, default=4, help="Number of session ids to use")
    parser.add_argument("--turns", type=int, default=45, help="Turns per session in exercise mode")
    parser.add_argument("--base-url", default="http://127.0.0.1:5000", help="Companion base URL")
    parser.add_argument("--timeout", type=float, default=90.0, help="Per-request timeout seconds")
    parser.add_argument("--output", required=True, help="Output JSON report path")
    args = parser.parse_args()

    if args.mode == "exercise":
        report = run_exercise(args)
    else:
        report = run_verify(args)

    _write_output(args.output, report)

    print("Live memory stress run complete")
    print(f"- mode: {report.get('mode')}")
    print(f"- label: {report.get('label')}")
    print(f"- output: {args.output}")
    if report.get("mode") == "exercise":
        r = report.get("results", {})
        print(f"- success_rate: {r.get('success_rate')}")
        print(f"- latency_avg_ms: {r.get('latency_avg_ms')}")
        print(f"- latency_p95_ms: {r.get('latency_p95_ms')}")
    else:
        r = report.get("results", {})
        print(f"- recall_hit_rate: {r.get('recall_hit_rate')}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
