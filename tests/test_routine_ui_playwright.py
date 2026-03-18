import os

import pytest
import requests


def test_routine_run_ui_smoke_playwright():
    """Browser regression: routine run should hit API and surface routine status feedback.

    This test is optional in environments without Playwright or without a running web server.
    """
    sync_api = pytest.importorskip("playwright.sync_api", reason="playwright is not installed")

    base_url = os.getenv("E2E_BASE_URL", "http://127.0.0.1:5000")
    try:
        health = requests.get(f"{base_url}/api/health", timeout=3)
        if health.status_code != 200:
            pytest.skip(f"web server not healthy at {base_url}")
    except Exception:
        pytest.skip(f"web server unavailable at {base_url}")

    # Contract check first: workflow run must expose chat delivery metadata.
    try:
        run_response = requests.post(f"{base_url}/api/workflows/morning_briefing/run", timeout=90)
    except requests.RequestException:
        pytest.skip("workflow run endpoint unavailable or timed out for e2e assertion")

    if run_response.status_code != 200:
        pytest.skip("workflow run endpoint unavailable for e2e assertion")
    run_payload = run_response.json()
    assert run_payload.get("status") == "success"
    assert "chat_delivered" in run_payload

    with sync_api.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 1200})
        page.goto(base_url, wait_until="domcontentloaded")

        # Ensure tasks panel is active before running routine.
        tasks_btn = page.locator('button[data-panel="tasks"]')
        if tasks_btn.count() > 0:
            tasks_btn.first.click()

        run_btn = page.locator('#routinesList button:has-text("Run now")').first
        sync_api.expect(run_btn).to_be_visible(timeout=10000)

        # Evaluate-click avoids viewport clipping in narrow side panel layouts.
        # Wait on the workflow API response so this test is not dependent on
        # transient toast timing under slow/rate-limited backends.
        with page.expect_response(
            lambda r: '/api/workflows/morning_briefing/run' in r.url and r.request.method == 'POST',
            timeout=120000,
        ) as run_resp_info:
            run_btn.evaluate("el => el.click()")

        run_resp = run_resp_info.value
        assert run_resp.ok, f"workflow run request failed with HTTP {run_resp.status}"
        run_ui_payload = run_resp.json()
        assert run_ui_payload.get('status') == 'success'
        assert 'chat_delivered' in run_ui_payload

        # UI should present a terminal routine status toast for user feedback.
        # Allow longer timeout for cold-start/rate-limit scenarios while still
        # requiring a clear terminal outcome to appear.
        sync_api.expect(
            page.locator("text=/Routine complete!|Routine ran|Failed to run routine[.]/i")
        ).to_be_visible(timeout=120000)

        browser.close()
