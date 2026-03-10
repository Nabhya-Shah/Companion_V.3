"""Benchmark OpenAI-compatible providers against Companion-specific tasks.

This script is intentionally standalone so provider experiments do not leak into
the production routing code before a decision is made.

Usage:
  python scripts/provider_benchmark.py --config scripts/provider_benchmark_candidates.example.yaml --dry-run
  python scripts/provider_benchmark.py --config scripts/provider_benchmark_candidates.yaml
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "benchmarks"

load_dotenv(ROOT / ".env")


@dataclass
class Candidate:
    name: str
    base_url: str
    model: str
    api_key_env: str
    headers: dict[str, str] = field(default_factory=dict)
    extra_body: dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    auth_header: str = "Authorization"
    auth_prefix: str = "Bearer "

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "").strip()

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def request_headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        headers.update(self.headers)
        if self.api_key:
            headers[self.auth_header] = f"{self.auth_prefix}{self.api_key}"
        return headers


def _extract_text_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "".join(parts)
    return ""


def _safe_json_loads(value: str) -> dict[str, Any] | list[Any] | None:
    try:
        loaded = json.loads(value)
    except Exception:
        return None
    if isinstance(loaded, (dict, list)):
        return loaded
    return None


def _json_request(candidate: Candidate, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    started_at = time.perf_counter()
    response = requests.post(
        candidate.chat_url,
        headers=candidate.request_headers(),
        json=payload,
        timeout=timeout_seconds,
    )
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)

    try:
        body = response.json()
    except Exception:
        body = {"raw_text": response.text}

    return {
        "status_code": response.status_code,
        "elapsed_ms": elapsed_ms,
        "body": body,
    }


def _stream_request(candidate: Candidate, payload: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    started_at = time.perf_counter()
    first_chunk_ms: float | None = None
    content_parts: list[str] = []
    tool_calls: list[dict[str, Any]] = []
    status_code = 0
    raw_lines: list[str] = []

    with requests.post(
        candidate.chat_url,
        headers=candidate.request_headers(),
        json=payload,
        timeout=timeout_seconds,
        stream=True,
    ) as response:
        status_code = response.status_code
        for raw_line in response.iter_lines(decode_unicode=True):
            if raw_line is None:
                continue
            line = raw_line.strip()
            if not line:
                continue
            raw_lines.append(line)
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except Exception:
                continue

            choices = event.get("choices") or []
            if not choices:
                continue
            delta = choices[0].get("delta") or {}
            delta_text = _extract_text_content(delta.get("content"))
            delta_tool_calls = delta.get("tool_calls") or []
            if (delta_text or delta_tool_calls) and first_chunk_ms is None:
                first_chunk_ms = round((time.perf_counter() - started_at) * 1000, 1)
            if delta_text:
                content_parts.append(delta_text)
            if delta_tool_calls:
                tool_calls.extend(delta_tool_calls)

    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
    return {
        "status_code": status_code,
        "elapsed_ms": elapsed_ms,
        "first_chunk_ms": first_chunk_ms,
        "content": "".join(content_parts),
        "tool_calls": tool_calls,
        "raw_lines": raw_lines,
    }


def _response_message(body: dict[str, Any]) -> dict[str, Any]:
    choices = body.get("choices") or []
    if not choices:
        return {}
    return choices[0].get("message") or {}


def _score_routing_case(result: dict[str, Any]) -> tuple[int, list[str]]:
    notes: list[str] = []
    parsed = result.get("parsed_json")
    if not isinstance(parsed, dict):
        return 0, ["response was not valid JSON"]

    required_keys = {"route", "needs_tools", "reason"}
    missing_keys = sorted(required_keys.difference(parsed.keys()))
    if missing_keys:
        return 5, [f"missing keys: {', '.join(missing_keys)}"]

    score = 10
    if parsed.get("route") == "tool":
        score += 10
    else:
        notes.append(f"unexpected route={parsed.get('route')!r}")

    if parsed.get("needs_tools") is True:
        score += 10
    else:
        notes.append(f"unexpected needs_tools={parsed.get('needs_tools')!r}")

    return score, notes


def _score_memory_case(result: dict[str, Any]) -> tuple[int, list[str]]:
    notes: list[str] = []
    parsed = result.get("parsed_json")
    if not isinstance(parsed, dict):
        return 0, ["response was not valid JSON"]

    facts = parsed.get("facts")
    if not isinstance(facts, list):
        return 5, ["facts key missing or not a list"]

    flattened = json.dumps(facts).lower()
    score = 10
    for keyword in ("vegetarian", "peanut", "berlin", "sister"):
        if keyword in flattened:
            score += 5
        else:
            notes.append(f"missing expected fact: {keyword}")
    return score, notes


def _score_persona_case(result: dict[str, Any]) -> tuple[int, list[str]]:
    text = (result.get("content") or "").strip()
    if not text:
        return 0, ["empty response"]

    score = 5
    notes: list[str] = []
    if 80 <= len(text) <= 700:
        score += 5
    else:
        notes.append(f"response length={len(text)}")
    lower_text = text.lower()
    if any(token in lower_text for token in ("step", "breathe", "pause", "small")):
        score += 5
    else:
        notes.append("did not include concrete calming guidance")
    return score, notes


def _score_tool_case(result: dict[str, Any]) -> tuple[int, list[str]]:
    tool_calls = result.get("tool_calls") or []
    if not tool_calls:
        return 0, ["no tool calls returned"]

    first_call = tool_calls[0]
    function_info = first_call.get("function") or {}
    function_name = function_info.get("name")
    if function_name == "get_current_time":
        return 30, []
    return 10, [f"unexpected first tool call: {function_name!r}"]


def _score_stream_case(result: dict[str, Any]) -> tuple[int, list[str]]:
    notes: list[str] = []
    first_chunk_ms = result.get("first_chunk_ms")
    content = (result.get("content") or "").strip()
    if first_chunk_ms is None:
        return 0, ["no streamed chunk received"]

    score = 5
    if first_chunk_ms <= 4000:
        score += 5
    else:
        notes.append(f"first chunk slow: {first_chunk_ms}ms")
    if content:
        score += 5
    else:
        notes.append("stream produced no text")
    return score, notes


def _build_cases() -> list[dict[str, Any]]:
    return [
        {
            "id": "routing_json",
            "weight": 30,
            "mode": "json",
            "payload": {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are the Companion routing brain. Return JSON only with keys "
                            "route, needs_tools, and reason."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "What time is it for me right now? I want the exact current time, "
                            "not a guess."
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            "scorer": _score_routing_case,
        },
        {
            "id": "tool_call_time",
            "weight": 30,
            "mode": "json",
            "payload": {
                "messages": [
                    {
                        "role": "system",
                        "content": "Use tools when they are necessary to answer correctly.",
                    },
                    {
                        "role": "user",
                        "content": "What time is it right now where I am?",
                    },
                ],
                "tools": [
                    {
                        "type": "function",
                        "function": {
                            "name": "get_current_time",
                            "description": "Get the current local time for the user.",
                            "parameters": {
                                "type": "object",
                                "properties": {},
                                "additionalProperties": False,
                            },
                        },
                    },
                    {
                        "type": "function",
                        "function": {
                            "name": "memory_search",
                            "description": "Search long-term memory for user information.",
                            "parameters": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                },
                                "required": ["query"],
                                "additionalProperties": False,
                            },
                        },
                    },
                ],
                "tool_choice": "auto",
                "temperature": 0,
            },
            "scorer": _score_tool_case,
        },
        {
            "id": "memory_fact_extraction",
            "weight": 30,
            "mode": "json",
            "payload": {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Extract stable user facts. Return JSON only with a top-level facts array. "
                            "Each fact should have category and value keys."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "Remember this about me: I'm vegetarian, allergic to peanuts, "
                            "I live in Berlin, and I share an apartment with my sister."
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            "scorer": _score_memory_case,
        },
        {
            "id": "streaming_persona",
            "weight": 15,
            "mode": "stream",
            "payload": {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a calm AI companion. Be warm but concise and practical."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "I'm overwhelmed and keep switching tasks. Give me a short grounded "
                            "response that helps me reset in the next five minutes."
                        ),
                    },
                ],
                "temperature": 0.4,
                "stream": True,
            },
            "scorer": _score_stream_case,
            "content_scorer": _score_persona_case,
        },
    ]


def _run_case(candidate: Candidate, case: dict[str, Any], timeout_seconds: int) -> dict[str, Any]:
    payload = dict(case["payload"])
    payload["model"] = candidate.model
    payload.update(candidate.extra_body)

    result: dict[str, Any] = {
        "case_id": case["id"],
        "weight": case["weight"],
        "success": False,
    }
    try:
        if case["mode"] == "stream":
            transport = _stream_request(candidate, payload, timeout_seconds)
            result.update(transport)
            if transport["status_code"] != 200:
                result["error"] = f"http {transport['status_code']}"
                return result
            score, notes = case["scorer"](result)
            persona_score, persona_notes = case["content_scorer"](result)
            combined_score = min(case["weight"], score + persona_score)
            result["score"] = combined_score
            result["notes"] = notes + persona_notes
            result["success"] = combined_score > 0
            return result

        transport = _json_request(candidate, payload, timeout_seconds)
        result.update(transport)
        if transport["status_code"] != 200:
            result["error"] = f"http {transport['status_code']}"
            result["response_preview"] = json.dumps(transport["body"])[:500]
            return result

        message = _response_message(transport["body"])
        content = _extract_text_content(message.get("content"))
        tool_calls = message.get("tool_calls") or []
        parsed_json = _safe_json_loads(content)
        result["content"] = content
        result["tool_calls"] = tool_calls
        result["parsed_json"] = parsed_json
        score, notes = case["scorer"](result)
        result["score"] = score
        result["notes"] = notes
        result["success"] = score > 0
        return result
    except Exception as err:
        result["error"] = str(err)
        return result


def _candidate_summary(candidate: Candidate, case_results: list[dict[str, Any]]) -> dict[str, Any]:
    total_score = sum(int(item.get("score", 0)) for item in case_results)
    max_score = sum(int(item.get("weight", 0)) for item in case_results)
    latencies = [float(item["elapsed_ms"]) for item in case_results if item.get("elapsed_ms") is not None]
    first_chunks = [float(item["first_chunk_ms"]) for item in case_results if item.get("first_chunk_ms") is not None]
    failures = [item["case_id"] for item in case_results if not item.get("success")]
    return {
        "name": candidate.name,
        "model": candidate.model,
        "base_url": candidate.base_url,
        "score": total_score,
        "max_score": max_score,
        "score_percent": round((total_score / max_score) * 100, 1) if max_score else 0.0,
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else None,
        "median_first_chunk_ms": round(statistics.median(first_chunks), 1) if first_chunks else None,
        "failures": failures,
        "cases": case_results,
    }


def _load_candidates(config_path: Path) -> list[Candidate]:
    with config_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    raw_candidates = raw.get("candidates") if isinstance(raw, dict) else raw
    if not isinstance(raw_candidates, list):
        raise ValueError("Benchmark config must be a list or a mapping with a 'candidates' key")

    candidates: list[Candidate] = []
    for entry in raw_candidates:
        if not isinstance(entry, dict):
            continue
        candidate = Candidate(
            name=str(entry["name"]),
            base_url=str(entry["base_url"]),
            model=str(entry["model"]),
            api_key_env=str(entry["api_key_env"]),
            headers=dict(entry.get("headers") or {}),
            extra_body=dict(entry.get("extra_body") or {}),
            enabled=bool(entry.get("enabled", True)),
            auth_header=str(entry.get("auth_header", "Authorization")),
            auth_prefix=str(entry.get("auth_prefix", "Bearer ")),
        )
        if candidate.enabled:
            candidates.append(candidate)
    return candidates


def _write_reports(output_dir: Path, report: dict[str, Any]) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    json_path = output_dir / f"provider_benchmark_{stamp}.json"
    markdown_path = output_dir / f"provider_benchmark_{stamp}.md"

    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)

    lines = [
        "# Provider Benchmark Report",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "| Candidate | Model | Score | Median latency | Median first chunk | Failed cases |",
        "|---|---|---:|---:|---:|---|",
    ]
    for candidate in report["candidates"]:
        lines.append(
            "| {name} | {model} | {score}/{max_score} ({score_percent}%) | {latency} ms | {first_chunk} ms | {failures} |".format(
                name=candidate["name"],
                model=candidate["model"],
                score=candidate["score"],
                max_score=candidate["max_score"],
                score_percent=candidate["score_percent"],
                latency=candidate["median_latency_ms"] if candidate["median_latency_ms"] is not None else "-",
                first_chunk=candidate["median_first_chunk_ms"] if candidate["median_first_chunk_ms"] is not None else "-",
                failures=", ".join(candidate["failures"]) if candidate["failures"] else "-",
            )
        )
        lines.append("")
        for case in candidate["cases"]:
            notes = "; ".join(case.get("notes") or []) or "-"
            lines.append(
                f"- {candidate['name']} / {case['case_id']}: score={case.get('score', 0)}/{case['weight']}, "
                f"latency={case.get('elapsed_ms', '-') } ms, notes={notes}"
            )
        lines.append("")

    with markdown_path.open("w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    return json_path, markdown_path


def _print_summary(report: dict[str, Any]) -> None:
    print("Provider benchmark summary")
    print("=" * 26)
    for candidate in report["candidates"]:
        failures = ", ".join(candidate["failures"]) if candidate["failures"] else "-"
        print(
            f"[{candidate['name']}] {candidate['score']}/{candidate['max_score']} "
            f"({candidate['score_percent']}%) | latency={candidate['median_latency_ms']}ms "
            f"| first_chunk={candidate['median_first_chunk_ms']}ms | failures={failures}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark candidate providers for Companion workloads")
    parser.add_argument("--config", required=True, help="YAML file describing candidate providers")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Directory for JSON/Markdown reports")
    parser.add_argument("--timeout", type=int, default=60, help="Per-request timeout in seconds")
    parser.add_argument("--dry-run", action="store_true", help="Validate config and print candidate availability without calling APIs")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    candidates = _load_candidates(config_path)

    if not candidates:
        print("No enabled candidates found in config.")
        return 1

    missing_keys = [candidate.name for candidate in candidates if not candidate.api_key]
    if args.dry_run:
        print("Dry run candidate status")
        print("=" * 24)
        for candidate in candidates:
            availability = "ready" if candidate.api_key else f"missing {candidate.api_key_env}"
            print(f"- {candidate.name}: model={candidate.model}, base_url={candidate.base_url}, {availability}")
        return 0

    if missing_keys:
        print("Missing API keys for:")
        for name in missing_keys:
            print(f"- {name}")
        return 1

    cases = _build_cases()
    candidate_reports: list[dict[str, Any]] = []
    for candidate in candidates:
        case_results = [_run_case(candidate, case, args.timeout) for case in cases]
        candidate_reports.append(_candidate_summary(candidate, case_results))

    candidate_reports.sort(key=lambda item: item["score"], reverse=True)
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "cases": [case["id"] for case in cases],
        "candidates": candidate_reports,
    }
    json_path, markdown_path = _write_reports(Path(args.output_dir), report)
    _print_summary(report)
    print(f"\nSaved JSON report to {json_path}")
    print(f"Saved Markdown report to {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())