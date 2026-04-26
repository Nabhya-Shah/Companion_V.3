"""Run a 10-minute authenticated UI hardening session.

This script drives the real web UI and repeatedly tests:
1) normal chat behavior
2) memory write + recall
3) tool-style responses (time/calc/planning)
4) vision prompt handling
5) brain/document search behavior

Artifacts are written under data/benchmarks/.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import time
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright


BASE_URL = os.getenv("UI_TEST_BASE_URL", "http://127.0.0.1:5000")
API_TOKEN = os.getenv("UI_TEST_API_TOKEN", "dev-ui-token")
DURATION_SECONDS = int(os.getenv("UI_TEST_DURATION_SECONDS", "600"))
IDLE_BETWEEN_PROMPTS_MS = int(os.getenv("UI_TEST_IDLE_MS", "3000"))


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _auth_headers() -> dict[str, str]:
    if API_TOKEN:
        return {"X-API-TOKEN": API_TOKEN}
    return {}


def _wait_ready(timeout_s: int = 45) -> None:
    start = time.time()
    last = ""
    while time.time() - start < timeout_s:
        try:
            res = requests.get(f"{BASE_URL}/api/health", headers=_auth_headers(), timeout=4)
            if res.status_code == 200:
                return
            last = f"HTTP {res.status_code}: {res.text[:120]}"
        except Exception as e:  # pragma: no cover - environment dependent
            last = str(e)
        time.sleep(1)
    raise RuntimeError(f"Web server not ready: {last}")


def _ensure_probe_doc() -> str:
    probe_path = Path("BRAIN") / "notes" / "hardening_probe.md"
    probe_path.parent.mkdir(parents=True, exist_ok=True)
    line = "HARDENING_SENTINEL_42: browser-memory-tools-probe"
    content = (
        "# Hardening Probe Note\n\n"
        "This note is used by automated UI hardening runs.\n"
        f"{line}\n"
    )
    probe_path.write_text(content, encoding="utf-8")
    return line


def _approve_all_pending(page) -> int:
    approved = 0
    while True:
        btns = page.locator('.approval-overlay .approval-btn.approve')
        if btns.count() <= 0:
            break
        btn = btns.first
        btn.scroll_into_view_if_needed()
        btn.evaluate("el => el.click()")
        approved += 1
        page.wait_for_timeout(250)
    return approved


def _send_prompt(page, prompt: str, timeout_s: int = 180) -> dict[str, Any]:
    ai_before = page.locator('#chatPane .message.ai').count()
    started = time.time()

    page.fill('#userInput', prompt)
    # Some layouts hide #sendBtn; use layered fallbacks for send action.
    sent = False
    try:
        btn = page.locator('#sendBtn')
        if btn.count() > 0:
            btn.first.click(timeout=4000, force=True)
            sent = True
    except Exception:
        pass

    if not sent:
        try:
            page.locator('#sendBtn').evaluate("el => el.click()")
            sent = True
        except Exception:
            pass

    if not sent:
        page.press('#userInput', 'Enter')

    approvals_clicked = 0
    while time.time() - started < timeout_s:
        approvals_clicked += _approve_all_pending(page)

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

    response = page.evaluate(
        """
        () => {
          const texts = Array.from(document.querySelectorAll('#chatPane .message.ai .message-text'));
          const last = texts[texts.length - 1];
          return (last?.innerText || '').trim();
        }
        """
    )

    return {
        "prompt": prompt,
        "response": response,
        "latency_s": round(time.time() - started, 2),
        "approvals_clicked": approvals_clicked,
    }


def _evaluate_case(case_name: str, response: str, sentinel_line: str) -> tuple[bool, str]:
    text = (response or "").strip()
    lower = text.lower()

    if not text:
        return False, "empty_response"

    if case_name == "baseline_greeting":
        return ("harden_ok" in lower), "missing_harden_ok_token" if "harden_ok" not in lower else "ok"

    if case_name in {"memory_recall_identity", "memory_recall_again"}:
        ok = ("orbit-77" in lower) and ("mango" in lower or case_name == "memory_recall_again")
        return ok, "memory_fact_not_found" if not ok else "ok"

    if case_name == "tool_calculate":
        return ("3293" in lower), "expected_3293_not_found" if "3293" not in lower else "ok"

    if case_name == "plan_multi_step":
        return ("orbit-77" in lower), "plan_missing_memory_recall" if "orbit-77" not in lower else "ok"

    if case_name == "brain_search":
        ok = sentinel_line.lower() in lower or "hardening_sentinel_42" in lower
        return ok, "brain_search_missing_sentinel" if not ok else "ok"

    # Non-strict checks for other exploratory prompts.
    return True, "ok"


def run() -> Path:
    _wait_ready()
    sentinel_line = _ensure_probe_doc()

    run_id = f"live_ui_10min_hardening_{_stamp()}"
    out_dir = Path("data") / "benchmarks" / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    test_cases = [
        {
            "name": "baseline_greeting",
            "prompt": "Hardening check: reply with token HARDEN_OK and one short sentence.",
        },
        {
            "name": "memory_write_identity",
            "prompt": "Remember this exactly for later: my codename is ORBIT-77 and my favorite snack is mango chips.",
        },
        {
            "name": "memory_recall_identity",
            "prompt": "What codename and favorite snack did I tell you to remember? Reply in one line.",
        },
        {
            "name": "tool_time",
            "prompt": "What time is it right now? Include timezone if possible.",
        },
        {
            "name": "tool_calculate",
            "prompt": "Calculate 37 * 89. Give the numeric result clearly.",
        },
        {
            "name": "plan_multi_step",
            "prompt": "Do two things: tell me current time, then remind me of my codename.",
        },
        {
            "name": "vision_ui",
            "prompt": "Look at the current screen and list 3 concrete UI elements you can see.",
        },
        {
            "name": "brain_search",
            "prompt": "Search my documents for HARDENING_SENTINEL_42 and quote the matching line.",
        },
        {
            "name": "memory_recall_again",
            "prompt": "Final memory check: what is my codename?",
        },
    ]

    report: dict[str, Any] = {
        "run_id": run_id,
        "base_url": BASE_URL,
        "duration_target_s": DURATION_SECONDS,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sentinel_line": sentinel_line,
        "cases": [],
        "summary": {},
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
        page.wait_for_selector('#userInput', timeout=30000)
        page.screenshot(path=str(out_dir / 'ui_start.png'), full_page=True)

        start = time.time()
        turn = 0
        while time.time() - start < DURATION_SECONDS:
            case = test_cases[turn % len(test_cases)]
            result = _send_prompt(page, case["prompt"], timeout_s=210)

            passed, reason = _evaluate_case(case["name"], result["response"], sentinel_line)
            result.update(
                {
                    "case": case["name"],
                    "pass": passed,
                    "reason": reason,
                    "elapsed_s": round(time.time() - start, 2),
                    "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
                }
            )
            report["cases"].append(result)

            if (turn + 1) % 3 == 0:
                page.screenshot(path=str(out_dir / f"turn_{turn + 1}.png"), full_page=True)

            turn += 1
            if IDLE_BETWEEN_PROMPTS_MS > 0:
                page.wait_for_timeout(IDLE_BETWEEN_PROMPTS_MS)

        page.screenshot(path=str(out_dir / 'ui_end.png'), full_page=True)
        browser.close()

    total = len(report["cases"])
    passed = sum(1 for x in report["cases"] if x.get("pass"))
    failed = total - passed
    report["summary"] = {
        "total_turns": total,
        "passed_turns": passed,
        "failed_turns": failed,
        "pass_rate": round((passed / total), 3) if total else 0.0,
        "actual_duration_s": round(time.time() - start, 2),
    }
    report["finished_at"] = dt.datetime.now(dt.timezone.utc).isoformat()

    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report_path


if __name__ == "__main__":
    path = run()
    print(path)