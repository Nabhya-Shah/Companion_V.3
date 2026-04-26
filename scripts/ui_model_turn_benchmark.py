"""UI-driven A/B model benchmark with screenshot proof for every turn.

Runs the real web UI with Playwright, sends the same prompt for each turn,
and captures one screenshot per response for each model.

Outputs:
1) JSON report with per-turn raw data
2) Markdown summary with overall pick and screenshot evidence links
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import statistics
import time
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright


BASE_URL = os.getenv("UI_BENCH_BASE_URL", "http://127.0.0.1:5000")
API_TOKEN = os.getenv("UI_BENCH_API_TOKEN", "dev-ui-token")
TURNS_PER_MODEL = int(os.getenv("UI_BENCH_TURNS", "10"))
PROMPT = os.getenv(
    "UI_BENCH_PROMPT",
    "In exactly 2 short sentences, give one concrete reliability risk in this app UI and one concrete mitigation.",
)
MODELS = ["qwen3.6:35b", "gemma4:31b"]


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _sanitize_model(model: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "-", model)


def _headers() -> dict[str, str]:
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if API_TOKEN:
        headers["X-API-TOKEN"] = API_TOKEN
    return headers


def _wait_health(timeout_s: int = 60) -> None:
    start = time.time()
    last_error = ""
    while time.time() - start < timeout_s:
        try:
            res = requests.get(f"{BASE_URL}/api/health", headers=_headers(), timeout=5)
            if res.status_code == 200:
                return
            last_error = f"HTTP {res.status_code}: {res.text[:120]}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1)
    raise RuntimeError(f"UI server not ready: {last_error}")


def _set_runtime(model: str) -> None:
    payload = {
        "profile": "quality",
        "runtime": "ollama",
        "chat_provider": "local_primary",
        "local_heavy_model": model,
    }
    res = requests.post(
        f"{BASE_URL}/api/local-model/runtime",
        headers=_headers(),
        json=payload,
        timeout=30,
    )
    res.raise_for_status()


def _reset_debug_session() -> None:
    # Resets active conversation so each model run starts clean.
    res = requests.post(
        f"{BASE_URL}/api/debug/reset",
        headers=_headers(),
        json={},
        timeout=30,
    )
    res.raise_for_status()


def _approve_all_pending(page) -> int:
    approved = 0
    while True:
        buttons = page.locator(".approval-overlay .approval-btn.approve")
        if buttons.count() <= 0:
            break
        btn = buttons.first
        btn.scroll_into_view_if_needed()
        btn.evaluate("el => el.click()")
        approved += 1
        page.wait_for_timeout(200)
    return approved


def _response_sentence_count(text: str) -> int:
    # Rough sentence count for prompt adherence checks.
    parts = [p for p in re.split(r"[.!?]+", text.strip()) if p.strip()]
    return len(parts)


def _send_prompt_and_capture(page, prompt: str, screenshot_path: Path, timeout_s: int = 240) -> dict[str, Any]:
    ai_before = page.locator("#chatPane .message.ai").count()
    started = time.time()

    page.fill("#userInput", prompt)

    sent = False
    try:
        btn = page.locator("#sendBtn")
        if btn.count() > 0:
            btn.first.click(timeout=4000, force=True)
            sent = True
    except Exception:
        sent = False

    if not sent:
        try:
            page.locator("#sendBtn").evaluate("el => el.click()")
            sent = True
        except Exception:
            sent = False

    if not sent:
        page.press("#userInput", "Enter")

    approvals = 0
    while time.time() - started < timeout_s:
        approvals += _approve_all_pending(page)
        done = page.evaluate(
            """
            (prev) => {
              const nodes = document.querySelectorAll('#chatPane .message.ai .message-text');
              if (nodes.length <= prev) return false;
              const last = nodes[nodes.length - 1];
              return !last.querySelector('.streaming-cursor');
            }
            """,
            ai_before,
        )
        if done:
            break
        page.wait_for_timeout(350)

    response_text = page.evaluate(
        """
        () => {
          const nodes = Array.from(document.querySelectorAll('#chatPane .message.ai .message-text'));
          const last = nodes[nodes.length - 1];
          return (last?.innerText || '').trim();
        }
        """
    )

    page.evaluate(
        """
        () => {
          const pane = document.querySelector('#chatPane');
          if (pane) pane.scrollTop = pane.scrollHeight;
          window.scrollTo(0, document.body.scrollHeight);
        }
        """
    )

    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(screenshot_path), full_page=True)

    elapsed = round(time.time() - started, 2)
    text = str(response_text or "").strip()
    sentence_count = _response_sentence_count(text)

    return {
        "latency_s": elapsed,
        "response": text,
        "response_chars": len(text),
        "sentence_count": sentence_count,
        "adheres_two_sentence_prompt": sentence_count == 2,
        "approvals_clicked": approvals,
        "screenshot": str(screenshot_path),
    }


def _mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def _compute_model_metrics(turns: list[dict[str, Any]]) -> dict[str, Any]:
    latencies = [float(t.get("latency_s", 0.0) or 0.0) for t in turns]
    chars = [int(t.get("response_chars", 0) or 0) for t in turns]
    two_sentence = [bool(t.get("adheres_two_sentence_prompt", False)) for t in turns]
    non_empty = [bool((t.get("response") or "").strip()) for t in turns]

    return {
        "turn_count": len(turns),
        "avg_latency_s": round(_mean(latencies), 2),
        "median_latency_s": round(float(statistics.median(latencies)) if latencies else 0.0, 2),
        "avg_response_chars": round(_mean([float(v) for v in chars]), 1),
        "two_sentence_adherence_rate": round(sum(two_sentence) / len(two_sentence), 3) if two_sentence else 0.0,
        "non_empty_rate": round(sum(non_empty) / len(non_empty), 3) if non_empty else 0.0,
    }


def _pick_winner(metrics: dict[str, dict[str, Any]]) -> tuple[str, dict[str, Any]]:
    # Weighted pick: lower latency and stronger format adherence dominate.
    models = list(metrics.keys())
    if len(models) != 2:
        return models[0], {"reason": "single_model"}

    m1, m2 = models[0], models[1]
    a = metrics[m1]
    b = metrics[m2]

    max_latency = max(a["avg_latency_s"], b["avg_latency_s"], 0.001)

    def score(m: dict[str, Any]) -> float:
        latency_score = 1.0 - (float(m["avg_latency_s"]) / max_latency)
        adherence_score = float(m["two_sentence_adherence_rate"])
        non_empty_score = float(m["non_empty_rate"])
        return (0.55 * latency_score) + (0.30 * adherence_score) + (0.15 * non_empty_score)

    s1 = score(a)
    s2 = score(b)

    winner = m1 if s1 >= s2 else m2
    detail = {
        m1: round(s1, 4),
        m2: round(s2, 4),
        "winner": winner,
        "method": "0.55 latency + 0.30 two_sentence_adherence + 0.15 non_empty",
    }
    return winner, detail


def _write_markdown_report(report: dict[str, Any], out_path: Path) -> None:
    metrics = report["metrics"]
    winner = report["overall_pick"]
    score_detail = report["scoring_detail"]

    lines: list[str] = []
    lines.append("# UI Model A/B Overall Pick")
    lines.append("")
    lines.append(f"- Generated: {report['generated_at']}")
    lines.append(f"- Base URL: {report['base_url']}")
    lines.append(f"- Prompt used for every turn: {report['prompt']}")
    lines.append(f"- Turns per model: {report['turns_per_model']}")
    lines.append("")
    lines.append("## Summary Metrics")
    lines.append("")
    lines.append("| Model | Avg Latency (s) | Median Latency (s) | Two-Sentence Adherence | Non-Empty Rate | Avg Response Chars |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    for model, data in metrics.items():
        lines.append(
            f"| {model} | {data['avg_latency_s']} | {data['median_latency_s']} | "
            f"{data['two_sentence_adherence_rate']} | {data['non_empty_rate']} | {data['avg_response_chars']} |"
        )

    lines.append("")
    lines.append("## Overall Pick")
    lines.append("")
    lines.append(f"**Winner: {winner}**")
    lines.append("")
    lines.append("### Justification")
    lines.append("")
    lines.append("1. The winner had the better weighted score using latency plus instruction-adherence and response availability.")
    lines.append("2. Latency was weighted highest to reflect interactive UI experience quality.")
    lines.append("3. Instruction-following (exactly two sentences) and non-empty responses were used as reliability checks.")
    lines.append("")
    lines.append("### Scoring Detail")
    lines.append("")
    lines.append(f"- Method: {score_detail['method']}")
    for model, score in score_detail.items():
        if model in {"winner", "method"}:
            continue
        lines.append(f"- {model}: {score}")

    for model, turns in report["turns"].items():
        lines.append("")
        lines.append(f"## Evidence: {model}")
        lines.append("")
        for turn in turns:
            turn_no = turn["turn"]
            screenshot_rel = Path(turn["screenshot"]).as_posix()
            excerpt = (turn.get("response") or "").replace("\n", " ").strip()
            if len(excerpt) > 280:
                excerpt = excerpt[:277] + "..."

            lines.append(f"### Turn {turn_no}")
            lines.append("")
            lines.append(f"- Latency: {turn['latency_s']}s")
            lines.append(f"- Two-sentence adherence: {turn['adheres_two_sentence_prompt']}")
            lines.append(f"- Response excerpt: {excerpt}")
            lines.append(f"- Screenshot: ![Turn {turn_no} - {model}]({screenshot_rel})")
            lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def run() -> dict[str, Any]:
    _wait_health()

    out_dir = Path("data") / "benchmarks" / f"ui_model_turn_benchmark_{_stamp()}"
    screenshot_dir = out_dir / "screenshots"
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "prompt": PROMPT,
        "turns_per_model": TURNS_PER_MODEL,
        "turns": {},
        "metrics": {},
        "overall_pick": "",
        "scoring_detail": {},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200})

        if API_TOKEN:
            token_json = json.dumps(API_TOKEN)
            page.add_init_script(
                f"sessionStorage.setItem('companion_api_token', {token_json});"
                f"localStorage.setItem('companion_api_token', {token_json});"
            )

        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_selector("#userInput", timeout=30000)

        for model in MODELS:
            _set_runtime(model)
            _reset_debug_session()

            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_selector("#userInput", timeout=30000)
            page.wait_for_timeout(800)

            model_key = _sanitize_model(model)
            turns: list[dict[str, Any]] = []

            for turn_index in range(1, TURNS_PER_MODEL + 1):
                shot = screenshot_dir / f"{model_key}_turn_{turn_index:02d}.png"
                turn_data = _send_prompt_and_capture(page, PROMPT, shot)
                turn_data.update({"turn": turn_index, "model": model})
                turns.append(turn_data)
                page.wait_for_timeout(500)

            report["turns"][model] = turns
            report["metrics"][model] = _compute_model_metrics(turns)

        browser.close()

    winner, detail = _pick_winner(report["metrics"])
    report["overall_pick"] = winner
    report["scoring_detail"] = detail

    json_path = out_dir / "report.json"
    md_path = out_dir / "OVERALL_PICK.md"

    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True), encoding="utf-8")
    _write_markdown_report(report, md_path)

    return {
        "output_dir": str(out_dir),
        "json_report": str(json_path),
        "markdown_report": str(md_path),
        "winner": winner,
    }


if __name__ == "__main__":
    result = run()
    print(json.dumps(result, indent=2))
