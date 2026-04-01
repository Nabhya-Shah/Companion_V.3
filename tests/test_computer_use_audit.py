import json
import sys
import types
import pytest

import companion_ai.tools.system_tools as system_tools
from companion_ai.tools import registry
from companion_ai.core import config as core_config


@pytest.fixture(autouse=True)
def _isolate_policy_and_approval_state(monkeypatch):
    monkeypatch.setattr(core_config, 'PLUGIN_POLICY_PATH', '')
    monkeypatch.setattr(core_config, 'PLUGIN_ALLOWLIST', '')
    monkeypatch.setattr(core_config, 'TOOL_ALLOWLIST', '')

    original_required = set(registry._APPROVAL_REQUIRED_TOOLS)
    registry._APPROVAL_REQUIRED_TOOLS.clear()
    registry._APPROVAL_REQUIRED_TOOLS.update(original_required | {'use_computer'})
    try:
        yield
    finally:
        registry._APPROVAL_REQUIRED_TOOLS.clear()
        registry._APPROVAL_REQUIRED_TOOLS.update(original_required)


def _read_jsonl(path):
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def test_computer_use_disabled_contract_and_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / 'computer_use_audit.jsonl'
    monkeypatch.setattr(system_tools, 'COMPUTER_USE_AUDIT_PATH', str(audit_path))
    monkeypatch.setattr(core_config, 'ENABLE_COMPUTER_USE', False)

    msg = system_tools.tool_use_computer('press', 'Enter')

    assert msg == 'Computer Use is disabled by policy (ENABLE_COMPUTER_USE=false).'
    rows = _read_jsonl(audit_path)
    assert len(rows) == 2
    assert rows[0]['status'] == 'requested'
    assert rows[1]['status'] == 'rejected'
    assert rows[1]['reason'] == 'feature_disabled'


def test_computer_use_invalid_action_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / 'computer_use_audit.jsonl'
    monkeypatch.setattr(system_tools, 'COMPUTER_USE_AUDIT_PATH', str(audit_path))
    monkeypatch.setattr(core_config, 'ENABLE_COMPUTER_USE', True)

    msg = system_tools.tool_use_computer('not_real_action', '')

    assert msg == 'Unknown action: not_real_action'
    rows = _read_jsonl(audit_path)
    assert len(rows) == 2
    assert rows[1]['status'] == 'rejected'
    assert rows[1]['reason'] == 'unknown_action'


def test_computer_use_runtime_unavailable_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / 'computer_use_audit.jsonl'
    monkeypatch.setattr(system_tools, 'COMPUTER_USE_AUDIT_PATH', str(audit_path))
    monkeypatch.setattr(core_config, 'ENABLE_COMPUTER_USE', True)
    monkeypatch.delitem(sys.modules, 'companion_ai.computer_agent', raising=False)

    msg = system_tools.tool_use_computer('press', 'Enter')

    assert msg == 'Computer Use runtime unavailable (computer_agent module not loaded).'
    rows = _read_jsonl(audit_path)
    assert len(rows) == 2
    assert rows[0]['status'] == 'requested'
    assert rows[1]['status'] == 'rejected'
    assert rows[1]['reason'] == 'runtime_unavailable'


def test_use_computer_approval_denied_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / 'computer_use_audit.jsonl'
    monkeypatch.setattr(system_tools, 'COMPUTER_USE_AUDIT_PATH', str(audit_path))
    monkeypatch.setattr(core_config, 'ENABLE_COMPUTER_USE', True)
    monkeypatch.setattr(registry, '_get_workspace_plugin_allowlist', lambda: None)
    monkeypatch.setattr(registry, '_wait_for_approval', lambda _name, _summary: False)

    msg = registry.execute_function_call('use_computer', {'action': 'press', 'text': 'Enter'})

    assert msg == "Tool 'use_computer' was denied or timed out waiting for approval."
    rows = _read_jsonl(audit_path)
    assert len(rows) == 2
    assert rows[0]['status'] == 'requested'
    assert rows[0]['action'] == 'press'
    assert rows[1]['status'] == 'rejected'
    assert rows[1]['reason'] == 'approval_denied'


def test_use_computer_allowlist_denied_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / 'computer_use_audit.jsonl'
    monkeypatch.setattr(system_tools, 'COMPUTER_USE_AUDIT_PATH', str(audit_path))
    monkeypatch.setattr(registry, '_get_workspace_plugin_allowlist', lambda: None)
    monkeypatch.setattr(core_config, 'TOOL_ALLOWLIST', 'get_current_time')

    msg = registry.execute_function_call('use_computer', {'action': 'press', 'text': 'Enter'})

    assert 'blocked by safety allowlist policy' in msg
    rows = _read_jsonl(audit_path)
    assert len(rows) == 2
    assert rows[0]['status'] == 'requested'
    assert rows[1]['status'] == 'rejected'
    assert rows[1]['reason'] == 'allowlist_denied'


def test_use_computer_approval_granted_audit(monkeypatch, tmp_path):
    audit_path = tmp_path / 'computer_use_audit.jsonl'
    monkeypatch.setattr(system_tools, 'COMPUTER_USE_AUDIT_PATH', str(audit_path))
    monkeypatch.setattr(core_config, 'ENABLE_COMPUTER_USE', True)
    monkeypatch.setattr(registry, '_get_workspace_plugin_allowlist', lambda: None)
    monkeypatch.setattr(registry, '_wait_for_approval', lambda _name, _summary: True)

    fake_agent = types.SimpleNamespace(
        mark_action=lambda: None,
        click_element=lambda text: f"clicked:{text}",
        type_text=lambda text, enter=True: f"typed:{text}:{enter}",
        press_key=lambda key: f"pressed:{key}",
        launch_app=lambda name: f"launched:{name}",
        scroll=lambda direction: f"scrolled:{direction}",
    )
    monkeypatch.setitem(sys.modules, 'companion_ai.computer_agent', types.SimpleNamespace(computer_agent=fake_agent))

    msg = registry.execute_function_call('use_computer', {'action': 'press', 'text': 'Enter'})

    assert msg == 'pressed:Enter'
    rows = _read_jsonl(audit_path)
    assert len(rows) == 2
    assert rows[0]['status'] == 'requested'
    assert rows[1]['status'] == 'completed'
