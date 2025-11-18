#!/usr/bin/env python3
"""Quick conversational evaluation harness for Companion AI.

Runs scripted multi-turn scenarios against the debug chat endpoint,
logs responses, and emits lightweight metrics so we can compare prompt
changes (e.g., baseline vs. new personality dial).
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import requests

Scenario = Dict[str, Any]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run scripted chat evaluations")
    parser.add_argument(
        "--scenarios",
        default="tools/eval_scenarios.json",
        help="Path to JSON file containing evaluation scenarios",
    )
    parser.add_argument(
        "--label",
        default="baseline",
        help="Label to associate with this run (e.g., baseline, new_prompt)",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:5000",
        help="Base URL for the running Companion server",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=45.0,
        help="HTTP timeout for each request",
    )
    return parser.parse_args()


def load_scenarios(path: str) -> List[Scenario]:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def reset_session(base_url: str, timeout: float) -> None:
    resp = requests.post(f"{base_url}/api/debug/reset", timeout=timeout)
    resp.raise_for_status()


def send_message(base_url: str, message: str, timeout: float) -> Dict[str, Any]:
    resp = requests.post(
        f"{base_url}/api/debug/chat",
        json={"message": message},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def response_metrics(text: str) -> Dict[str, Any]:
    words = [w for w in re.split(r"\s+", text.strip()) if w]
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "avg_words_per_sentence": round(len(words) / len(sentences), 2) if sentences else 0.0,
        "contains_question": "?" in text,
        "contains_metaphor": any(token in text.lower() for token in ["like", "as if", "feels like"]),
    }


def ensure_report_dir() -> Path:
    report_dir = Path("data/eval_reports")
    report_dir.mkdir(parents=True, exist_ok=True)
    return report_dir


def run_scenarios(args: argparse.Namespace, scenarios: List[Scenario]) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    base_url = args.base_url.rstrip("/")

    for scenario in scenarios:
        reset_session(base_url, args.timeout)
        turns = scenario.get("turns", [])
        for idx, user_message in enumerate(turns):
            payload = send_message(base_url, user_message, args.timeout)
            metrics = response_metrics(payload.get("ai", ""))
            entry = {
                "label": args.label,
                "scenario": scenario.get("name", f"scenario_{idx}"),
                "description": scenario.get("description"),
                "turn_index": idx,
                "user": payload.get("user"),
                "ai": payload.get("ai"),
                "metrics": metrics,
                "history_length": payload.get("history_length"),
                "timestamp": payload.get("timestamp"),
            }
            entries.append(entry)
    return {
        "label": args.label,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "scenarios": scenarios,
        "entries": entries,
    }


def summarize(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    summary: Dict[str, Any] = {}
    by_scenario: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        by_scenario.setdefault(entry["scenario"], []).append(entry)

    for scenario, scen_entries in by_scenario.items():
        words = [e["metrics"]["word_count"] for e in scen_entries]
        sentences = [e["metrics"]["sentence_count"] for e in scen_entries]
        question_ratio = sum(1 for e in scen_entries if e["metrics"]["contains_question"]) / max(len(scen_entries), 1)
        summary[scenario] = {
            "avg_words": round(statistics.mean(words), 2) if words else 0.0,
            "avg_sentences": round(statistics.mean(sentences), 2) if sentences else 0.0,
            "question_ratio": round(question_ratio, 2),
        }
    return summary


def save_report(report: Dict[str, Any], summary: Dict[str, Any], label: str) -> Path:
    report_dir = ensure_report_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = report_dir / f"{timestamp}_{label}.jsonl"
    with open(out_path, "w", encoding="utf-8") as fh:
        for entry in report["entries"]:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    # Also save summary alongside for quick glance
    summary_path = report_dir / f"{timestamp}_{label}_summary.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)
    return summary_path


def main() -> None:
    args = parse_args()
    scenarios = load_scenarios(args.scenarios)
    report = run_scenarios(args, scenarios)
    summary = summarize(report["entries"])
    summary_path = save_report(report, summary, args.label)

    print(f"Saved detailed run to {summary_path.parent}")
    print("Summary metrics:")
    for scenario, stats in summary.items():
        print(f"  {scenario}: avg_words={stats['avg_words']} avg_sentences={stats['avg_sentences']} question_ratio={stats['question_ratio']}")


if __name__ == "__main__":
    main()
