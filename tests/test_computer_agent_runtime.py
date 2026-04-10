import types

from companion_ai.computer_agent import ComputerAgent


def test_click_element_coordinates_uses_xdotool(monkeypatch):
    agent = ComputerAgent()
    monkeypatch.setattr(agent, '_run_xdotool', lambda args: (True, ''))

    out = agent.click_element('640,360')

    assert out == 'clicked:640,360'


def test_press_key_prefers_xdotool(monkeypatch):
    agent = ComputerAgent()
    monkeypatch.setattr(agent, '_run_xdotool', lambda args: (True, ''))

    out = agent.press_key('Enter')

    assert out == 'pressed:Enter'


def test_press_key_falls_back_to_browser(monkeypatch):
    agent = ComputerAgent()
    monkeypatch.setattr(agent, '_run_xdotool', lambda args: (False, 'xdotool_not_installed'))

    fake_browser = types.SimpleNamespace(sync_press_key=lambda key: 'Pressed key: Enter')
    import sys

    monkeypatch.setitem(sys.modules, 'companion_ai.agents.browser', fake_browser)
    out = agent.press_key('Enter')

    assert out == 'pressed:Enter'


def test_launch_app_url_uses_browser(monkeypatch):
    agent = ComputerAgent()
    fake_browser = types.SimpleNamespace(sync_goto=lambda url: f'Navigated to {url}')
    import sys

    monkeypatch.setitem(sys.modules, 'companion_ai.agents.browser', fake_browser)

    out = agent.launch_app('https://example.com')

    assert out == 'launched:https://example.com'


def test_url_detection_avoids_executable_like_values():
    agent = ComputerAgent()

    assert agent._looks_like_url('example.com') is True
    assert agent._looks_like_url('www.example.com') is True
    assert agent._looks_like_url('notepad.exe') is False
    assert agent._looks_like_url('/usr/bin/python3') is False
