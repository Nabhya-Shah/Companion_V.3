import companion_ai.tools.browser_tools as browser_tools


def test_browser_tool_reports_playwright_install_hint(monkeypatch):
    def fake_goto(_url):
        raise ModuleNotFoundError("No module named 'playwright'")

    monkeypatch.setattr('companion_ai.agents.browser.sync_goto', fake_goto)

    msg = browser_tools.tool_browser_goto('example.com')
    assert 'Playwright is not installed' in msg
    assert 'pip install playwright' in msg
    assert 'playwright install chromium' in msg


def test_browser_tool_reports_chrome_runtime_hint(monkeypatch):
    def fake_click(_selector, _text=None):
        raise RuntimeError('Could not launch Chrome with your profile')

    monkeypatch.setattr('companion_ai.agents.browser.sync_click', fake_click)

    msg = browser_tools.tool_browser_click('#submit')
    assert 'Chrome/Chromium runtime is unavailable' in msg
    assert 'CHROME_PATH' in msg


def test_browser_tool_normalizes_string_error_from_agent(monkeypatch):
    monkeypatch.setattr(
        'companion_ai.agents.browser.sync_goto',
        lambda _url: "Error navigating to example.com: No module named 'playwright'",
    )

    msg = browser_tools.tool_browser_goto('example.com')
    assert 'Playwright is not installed' in msg
