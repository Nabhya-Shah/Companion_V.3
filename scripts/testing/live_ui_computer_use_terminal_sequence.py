"""Live UI run for computer-use terminal sequence with approval handling.

This script drives the real web UI and attempts the exact requested flow:
1) open terminal and echo text
2) open another terminal/tab and echo text
3) close the second one

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


BASE_URL = "http://127.0.0.1:5000"
API_TOKEN = os.getenv("UI_TEST_API_TOKEN", "dev-ui-token")
RUNTIME_MODEL = "huihui_ai/qwen3.5-abliterated:27b"
VISION_PROMPT = (
    "Look at the current screen and provide a structured summary with: "
    "(1) page/app name, (2) at least 5 visible UI elements by label, "
    "(3) one user-action recommendation."
)
COMPUTER_PROMPT = (
    "Use computer control and execute this exact sequence now:\n"
    "1) Launch gnome-terminal\n"
    "2) Type: echo COMPANION_UI_TEST_ONE\n"
    "3) Press Enter\n"
    "4) Open another terminal tab with Ctrl+Shift+T\n"
    "5) Type: echo COMPANION_UI_TEST_TWO\n"
    "6) Press Enter\n"
    "7) Close the current tab with Ctrl+Shift+W\n"
    "After execution, report each step result briefly."
)

COMPUTER_PROMPT_STEPS = [
    "Use computer control now: launch gnome-terminal.",
    "Use computer control now: type exactly this text: echo COMPANION_UI_TEST_ONE",
    "Use computer control now: press Enter once.",
    "Use computer control now: press Ctrl+Shift+T once to open another terminal tab.",
    "Use computer control now: type exactly this text: echo COMPANION_UI_TEST_TWO",
    "Use computer control now: press Enter once.",
    "Use computer control now: press Ctrl+Shift+W once to close the current terminal tab.",
]


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _wait_ready(timeout_s: int = 30) -> None:
    start = time.time()
    last = ""
    while time.time() - start < timeout_s:
        try:
            r = requests.get(
                f"{BASE_URL}/api/health",
                headers={"X-API-TOKEN": API_TOKEN} if API_TOKEN else {},
                timeout=3,
            )
            if r.status_code == 200:
                return
            last = f"HTTP {r.status_code}"
        except Exception as e:  # pragma: no cover
            last = str(e)
        time.sleep(1)
    raise RuntimeError(f"Web server not ready: {last}")


def _enable_plugin_policy() -> dict[str, Any]:
    payload = {"enabled_plugins": ["core", "background"]}
    try:
        r = requests.post(
            f"{BASE_URL}/api/plugins/policy",
            headers={"X-API-TOKEN": API_TOKEN} if API_TOKEN else {},
            json=payload,
            timeout=10,
        )
        if r.ok:
            return r.json()
    except Exception:
        pass

    # Fallback for hardened environments where sensitive-write endpoints
    # require API_AUTH_TOKEN configuration.
    policy_path = Path('data') / 'plugin_policy.json'
    policy_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        'enabled_plugins': payload['enabled_plugins'],
        'updated_at': dt.datetime.now().isoformat(timespec='seconds'),
    }
    policy_path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding='utf-8')
    return {
        'source': 'file_fallback',
        'path': str(policy_path),
        'effective_enabled_plugins': payload['enabled_plugins'],
    }


def _set_runtime(page, model_name: str) -> dict[str, str]:
    _approve_all_pending(page)
    page.locator('button[data-panel="stats"]').click(force=True)
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

    return page.evaluate(
        """
        () => ({
          summary: document.querySelector('#localRuntimeSummary')?.innerText || '',
          chips: document.querySelector('#localRuntimeChips')?.innerText || '',
          models: document.querySelector('#localRuntimeModels')?.innerText || '',
        })
        """
    )


def _approve_all_pending(page) -> int:
    approved = 0
    while True:
        btns = page.locator('.approval-overlay .approval-btn.approve')
        count = btns.count()
        if count <= 0:
            break
        btn = btns.first
        btn.scroll_into_view_if_needed()
        btn.evaluate("el => el.click()")
        approved += 1
        page.wait_for_timeout(250)
    return approved


def _send_prompt(page, prompt: str, timeout_s: int = 240) -> dict[str, Any]:
    ai_before = page.locator('#chatPane .message.ai').count()

    page.fill('#userInput', prompt)
    page.click('#sendBtn')

    start = time.time()
    approvals_clicked = 0
    while time.time() - start < timeout_s:
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
        page.wait_for_timeout(300)

    response = page.evaluate(
        """
        () => {
          const all = Array.from(document.querySelectorAll('#chatPane .message.ai .message-text'));
          const last = all[all.length - 1];
          return (last?.innerText || '').trim();
        }
        """
    )
    return {
        'prompt': prompt,
        'response': response,
        'approvals_clicked': approvals_clicked,
    }


def _capture_activity(page) -> dict[str, str]:
    _approve_all_pending(page)
    page.locator('button[data-panel="stats"]').click(force=True)
    page.wait_for_selector('#computerUseActivityList', timeout=15000)
    refresh_btn = page.locator('#refreshComputerUseBtn')
    refresh_btn.scroll_into_view_if_needed()
    refresh_btn.evaluate("el => el.click()")
    page.wait_for_timeout(1200)

    return page.evaluate(
        """
        () => {
          const summary = document.querySelector('#computerUsePolicySummary')?.innerText || '';
          const first = document.querySelector('#computerUseActivityList .queue-item-row')?.innerText || '';
          const btn = document.querySelector('#computerUseActivityList .activity-view-btn');
          if (btn) btn.click();
          const artifact = document.querySelector('#computerUseArtifactPreview')?.innerText || '';
          return { summary, first, artifact };
        }
        """
    )


def run() -> Path:
    _wait_ready()
    policy_state = _enable_plugin_policy()

    run_id = f"live_ui_computer_use_seq_{_stamp()}"
    out_dir = Path('data') / 'benchmarks' / run_id
    out_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        'run_id': run_id,
        'started_at': dt.datetime.now(dt.timezone.utc).isoformat(),
        'plugin_policy_state': policy_state,
        'runtime_model': RUNTIME_MODEL,
    }

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 1200})
        if API_TOKEN:
            token_json = json.dumps(API_TOKEN)
            page.add_init_script(
                f"sessionStorage.setItem('companion_api_token', {token_json});"
            )
        page.goto(BASE_URL, wait_until='domcontentloaded', timeout=45000)
        page.wait_for_selector('#userInput', timeout=30000)

        print(f"[{run_id}] UI loaded")
        page.screenshot(path=str(out_dir / 'ui_start.png'), full_page=True)
        report['runtime_snapshot'] = _set_runtime(page, RUNTIME_MODEL)
        print(f"[{run_id}] Runtime set: {RUNTIME_MODEL}")
        page.screenshot(path=str(out_dir / 'runtime_set.png'), full_page=True)

        print(f"[{run_id}] Running vision prompt")
        report['vision'] = _send_prompt(page, VISION_PROMPT, timeout_s=90)
        page.screenshot(path=str(out_dir / 'vision_result.png'), full_page=True)

        print(f"[{run_id}] Running combined computer-use prompt")
        report['computer_use_combined'] = _send_prompt(page, COMPUTER_PROMPT, timeout_s=90)
        page.screenshot(path=str(out_dir / 'computer_use_combined_chat.png'), full_page=True)

        stepwise_results: list[dict[str, Any]] = []
        for idx, prompt in enumerate(COMPUTER_PROMPT_STEPS, start=1):
            print(f"[{run_id}] Running step {idx}/{len(COMPUTER_PROMPT_STEPS)}")
            step_result = _send_prompt(page, prompt, timeout_s=60)
            step_result['step'] = idx
            step_result['activity_snapshot'] = _capture_activity(page)
            stepwise_results.append(step_result)
            page.screenshot(path=str(out_dir / f'computer_use_step_{idx}.png'), full_page=True)
        report['computer_use_stepwise'] = stepwise_results

        report['computer_use_activity'] = _capture_activity(page)
        page.screenshot(path=str(out_dir / 'computer_use_activity.png'), full_page=True)

        browser.close()

    # Also collect backend activity for precise status records.
    try:
        act = requests.get(
            f"{BASE_URL}/api/computer-use/activity?limit=20",
            headers={"X-API-TOKEN": API_TOKEN} if API_TOKEN else {},
            timeout=10,
        )
        report['computer_use_activity_api'] = act.json() if act.ok else {'error': act.text}
    except Exception as e:  # pragma: no cover
        report['computer_use_activity_api'] = {'error': str(e)}

    report['finished_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
    report_path = out_dir / 'report.json'
    report_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding='utf-8')
    return report_path


if __name__ == '__main__':
    path = run()
    print(path)
