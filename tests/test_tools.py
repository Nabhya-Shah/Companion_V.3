"""Tests for custom tools - V5 architecture."""
import pytest

from companion_ai.tools import (
    list_tools,
    run_tool,
    get_plugin_catalog,
    set_workspace_plugin_policy,
    evaluate_tool_policy,
    list_tool_runtime,
    execute_function_call,
)
from companion_ai.core import config as core_config
import companion_ai.tools as tools_module

def test_list_tools_contains_core():
    """Test that core tools are registered."""
    tools = list_tools()
    # V5 tools: brain_*, memory_search, use_computer, etc.
    assert 'get_current_time' in tools
    assert 'memory_search' in tools  # memory_insight removed, replaced with memory_search
    assert 'brain_read' in tools     # V5 brain tools
    assert 'brain_write' in tools
    assert 'brain_list' in tools
    assert 'wikipedia_lookup' in tools
    assert 'find_file' in tools
    assert 'list_files' in tools
    assert 'use_computer' in tools

def test_time_tool():
    """Test get_current_time tool works."""
    result = run_tool('get_current_time', '')
    # Should return current time info
    assert result is not None
    assert 'Unknown tool' not in result

def test_unknown_tool():
    """Test unknown tool returns error message."""
    result = run_tool('not_a_tool', 'x')
    assert 'Unknown tool' in result


def test_tool_allowlist_blocks_disallowed_tool(monkeypatch):
    """Disallowed tools should return explicit allowlist-denied message."""
    monkeypatch.setattr(core_config, 'TOOL_ALLOWLIST', 'get_current_time')
    blocked = run_tool('use_computer', 'open calculator')
    allowed = run_tool('get_current_time', '')

    assert 'blocked by safety allowlist policy' in blocked
    assert 'Unknown tool' not in allowed


def test_plugin_allowlist_blocks_plugin_tool(monkeypatch):
    """Plugin policy should block tools from disabled plugins."""
    monkeypatch.setattr(core_config, 'PLUGIN_ALLOWLIST', 'core')
    monkeypatch.setattr(core_config, 'PLUGIN_POLICY_PATH', '')
    blocked = run_tool('start_background_task', 'research task')
    allowed = run_tool('get_current_time', '')

    assert 'blocked by plugin policy' in blocked
    assert 'Unknown tool' not in allowed


def test_workspace_plugin_policy_overrides_env_allowlist(monkeypatch, tmp_path):
    """Workspace plugin policy should take precedence over env plugin allowlist."""
    policy_path = tmp_path / "plugin_policy.json"
    policy_path.write_text('{"enabled_plugins": ["background"]}', encoding='utf-8')

    monkeypatch.setattr(core_config, 'PLUGIN_ALLOWLIST', 'core')
    monkeypatch.setattr(core_config, 'PLUGIN_POLICY_PATH', str(policy_path))
    monkeypatch.setattr(tools_module, 'add_job', lambda description, tool_name, tool_args: 'job1234')

    result = run_tool('start_background_task', 'do thing')
    assert 'Started background task' in result


def test_restricted_sandbox_blocks_high_risk_tool(monkeypatch):
    """Restricted sandbox mode blocks computer/browser tools."""
    tools_module.set_execution_mode('restricted')
    try:
        blocked = run_tool('use_computer', 'open browser')
        assert 'blocked by sandbox mode' in blocked
    finally:
        tools_module.set_execution_mode('main')


def test_plugin_catalog_contains_rich_metadata():
    catalog = get_plugin_catalog()
    assert catalog
    core = next((row for row in catalog if row['name'] == 'core'), None)
    assert core is not None
    assert 'tool_count' in core
    assert isinstance(core.get('tools'), list)


def test_set_workspace_plugin_policy_rejects_unknown_plugin(monkeypatch, tmp_path):
    policy_path = tmp_path / 'plugin_policy.json'
    monkeypatch.setattr(core_config, 'PLUGIN_POLICY_PATH', str(policy_path))

    with pytest.raises(ValueError):
        set_workspace_plugin_policy(['not_real_plugin'])


def test_evaluate_tool_policy_reports_plugin_denied(monkeypatch):
    monkeypatch.setattr(core_config, 'PLUGIN_ALLOWLIST', 'core')
    monkeypatch.setattr(core_config, 'PLUGIN_POLICY_PATH', '')
    decision = evaluate_tool_policy('start_background_task')

    assert decision['allowed'] is False
    assert decision['reason'] == 'plugin_denied'


def test_evaluate_tool_policy_reports_allowlist_denied(monkeypatch):
    monkeypatch.setattr(core_config, 'PLUGIN_ALLOWLIST', '')
    monkeypatch.setattr(core_config, 'TOOL_ALLOWLIST', 'get_current_time')
    decision = evaluate_tool_policy('wikipedia_lookup')

    assert decision['allowed'] is False
    assert decision['reason'] == 'allowlist_denied'


def test_tool_runtime_catalog_includes_risk_and_approval():
    catalog = list_tool_runtime()
    assert catalog
    by_name = {row['name']: row for row in catalog}
    assert by_name['use_computer']['risk_tier'] == 'high'
    assert by_name['use_computer']['requires_approval'] is True
    assert by_name['get_current_time']['risk_tier'] == 'low'


def test_execute_function_call_accepts_approval_token(monkeypatch):
    """If a valid approval token is provided, execution should not block on waiting."""
    import companion_ai.tools.registry as registry

    monkeypatch.setattr(registry, 'consume_approval_token', lambda token, tool_name: True)

    def _should_not_wait(*args, **kwargs):
        raise AssertionError("_wait_for_approval should not be called when token is valid")

    monkeypatch.setattr(registry, '_wait_for_approval', _should_not_wait)

    result = execute_function_call(
        'use_computer',
        {
            'action': 'press',
            'text': 'enter',
            'approval_token': 'tok_123',
        },
    )

    assert isinstance(result, str)