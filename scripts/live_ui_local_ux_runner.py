"""Run a real UI interaction session and capture UX evidence artifacts.

This script automates the actual web UI (not API-only probes) and writes:
- screenshots from each phase
- JSON transcript with prompts and assistant responses
- runtime/computer-use panel snapshots

Usage:
    ./.venv/bin/python scripts/live_ui_local_ux_runner.py
"""
from __future__ import annotations

import json
import time
import datetime as dt
from pathlib import Path
from typing import Any

import requests
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


BASE_URL = "http://127.0.0.1:5000"
MODEL_CONTENDERS = [
    "huihui_ai/qwen3.5-abliterated:27b",
    "huihui_ai/gemma-4-abliterated:31b",
]
MODEL_COMPARE_PROMPT = (
    "Go to https://example.com and tell me the exact page title and exact H1 text. "
    "Then summarize the page purpose in one sentence."
)
VISION_PROMPT = (
    "Look at the current screen and list 3 concrete UI elements you can see right now."
)
COMPUTER_USE_PROMPT = (
    "Use computer control and press Enter once, then confirm what action happened."
)


def _now_stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _wait_web_ready(base_url: str, timeout_s: int = 30) -> None:
    start = time.time()
    last_err = None
    while time.time() - start < timeout_s:
        try:
            res = requests.get(f"{base_url}/api/health", timeout=3)
            if res.status_code == 200:
                return
            last_err = f"HTTP {res.status_code}"
        except Exception as exc:  # pragma: no cover - runtime dependent
            last_err = str(exc)
        time.sleep(1)
    raise RuntimeError(f"Web server not ready at {base_url}: {last_err}")


def _set_runtime_model(page, model_name: str) -> dict[str, Any]:
    page.click('button[data-panel="stats"]')
    refresh_btn = page.locator('#refreshLocalRuntimeBtn')
    refresh_btn.scroll_into_view_if_needed()
    refresh_btn.evaluate("el => el.click()")
    page.wait_for_selector('#localRuntimeSelect', timeout=15000)

    page.select_option('#localRuntimeSelect', 'ollama')
    page.select_option('#localProfileSelect', 'balanced')

    page.evaluate(
        """
        (modelName) => {
          const select = document.querySelector('#localHeavyModelSelect');
          if (!select) return;
          const exists = Array.from(select.options).some(o => o.value === modelName);
          if (!exists) {
            const opt = document.createElement('option');
            opt.value = modelName;
            opt.textContent = modelName;
            select.appendChild(opt);
          }
          select.value = modelName;
        }
        """,
        model_name,
    )

    save_btn = page.locator('#saveLocalRuntimeBtn')
    save_btn.scroll_into_view_if_needed()
    save_btn.evaluate("el => el.click()")
    page.wait_for_timeout(1200)

    snapshot = page.evaluate(
        """
        () => {
          return {
            summary: document.querySelector('#localRuntimeSummary')?.innerText || '',
            chips: document.querySelector('#localRuntimeChips')?.innerText || '',
            models_json: document.querySelector('#localRuntimeModels')?.innerText || '',
          };
        }
        """
    )
    return snapshot


def _send_and_capture(page, prompt: str, timeout_ms: int = 180000) -> dict[str, str]:
    ai_count_before = page.locator('#chatPane .message.ai').count()

    page.fill('#userInput', prompt)
    page.click('#sendBtn')

    page.wait_for_function(
        "(prev) => document.querySelectorAll('#chatPane .message.ai').length > prev",
        arg=ai_count_before,
        timeout=timeout_ms,
    )

    # For approval-required computer-use calls, an approval modal may appear.
    try:
        page.wait_for_selector('.approval-overlay .approval-btn.approve', timeout=6000)
        page.click('.approval-overlay .approval-btn.approve')
    except PlaywrightTimeoutError:
        pass

    page.wait_for_function(
        """
        () => {
          const all = document.querySelectorAll('#chatPane .message.ai .message-text');
          if (!all.length) return false;
          const last = all[all.length - 1];
          return !last.querySelector('.streaming-cursor');
        }
        """,
        timeout=timeout_ms,
    )

    result = page.evaluate(
        """
        () => {
          const msgs = Array.from(document.querySelectorAll('#chatPane .message.ai'));
          const last = msgs[msgs.length - 1];
          const text = last?.querySelector('.message-text')?.innerText?.trim() || '';
          const role = last?.querySelector('.message-role')?.innerText?.trim() || '';
          return { text, role };
        }
        """
    )
    return {
        'prompt': prompt,
        'response': result.get('text', ''),
        'role_meta': result.get('role', ''),
    }


def _capture_computer_use_panel(page) -> dict[str, str]:
    page.click('button[data-panel="stats"]')
    page.wait_for_selector('#computerUseActivityList', timeout=15000)
    refresh_btn = page.locator('#refreshComputerUseBtn')
    refresh_btn.scroll_into_view_if_needed()
    refresh_btn.evaluate("el => el.click()")
    page.wait_for_timeout(1200)

    activity = page.evaluate(
        """
        () => {
          const summary = document.querySelector('#computerUsePolicySummary')?.innerText || '';
          const firstRow = document.querySelector('#computerUseActivityList .queue-item-row')?.innerText || '';
          const viewBtn = document.querySelector('#computerUseActivityList .activity-view-btn');
          if (viewBtn) viewBtn.click();
          const artifactPreview = document.querySelector('#computerUseArtifactPreview')?.innerText || '';
          return { summary, firstRow, artifactPreview };
        }
        """
    )
    return {
        'policy_summary': activity.get('summary', ''),
        'first_activity_row': activity.get('firstRow', ''),
        'artifact_preview': activity.get('artifactPreview', ''),
    }


def run() -> Path:
    _wait_web_ready(BASE_URL)

    run_id = f"live_ui_local_ux_{_now_stamp()}"
    out_dir = Path('data') / 'benchmarks' / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        'run_id': run_id,
        'base_url': BASE_URL,
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'model_runs': [],
        'vision_run': {},
        'computer_use_run': {},
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 1200})
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=45000)
        page.wait_for_selector('#userInput', timeout=30000)

        page.screenshot(path=str(out_dir / 'ui_loaded.png'), full_page=True)

        for idx, contender in enumerate(MODEL_CONTENDERS, start=1):
            runtime_snapshot = _set_runtime_model(page, contender)
            model_chat = _send_and_capture(page, MODEL_COMPARE_PROMPT)
            page.screenshot(path=str(out_dir / f'model_{idx}_{contender.replace(":", "_")}.png'), full_page=True)
            report['model_runs'].append({
                'model': contender,
                'runtime_snapshot': runtime_snapshot,
                **model_chat,
            })

        # Vision run (real UI request)
        vision_chat = _send_and_capture(page, VISION_PROMPT)
        page.screenshot(path=str(out_dir / 'vision_run.png'), full_page=True)
        report['vision_run'] = vision_chat

        # Computer-use run (real UI request + approval UI if shown)
        computer_chat = _send_and_capture(page, COMPUTER_USE_PROMPT, timeout_ms=220000)
        panel_data = _capture_computer_use_panel(page)
        page.screenshot(path=str(out_dir / 'computer_use_panel.png'), full_page=True)
        report['computer_use_run'] = {
            **computer_chat,
            **panel_data,
        }

        browser.close()

    report['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    report_path = out_dir / 'ux_report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='utf-8')
    return report_path


if __name__ == '__main__':
    path = run()
    print(path)
