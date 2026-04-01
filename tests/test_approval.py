"""Tests for Human-In-The-Loop tool approval system (P6-B)."""
import threading
import time
from companion_ai.tools import registry


def _reset_approval_state():
    """Clear all approval-related state between tests."""
    registry._APPROVAL_REQUIRED_TOOLS.clear()
    with registry._APPROVAL_LOCK:
        registry._PENDING_APPROVALS.clear()
        registry._APPROVAL_EVENTS.clear()


# -------------------------------------------------------------------
# Approval flag management
# -------------------------------------------------------------------

def test_mark_tool_requires_approval():
    _reset_approval_state()
    registry.mark_tool_requires_approval('browser_goto')
    assert registry.tool_requires_approval('browser_goto')
    assert 'browser_goto' in registry.list_approval_required_tools()
    _reset_approval_state()


def test_unmark_tool_requires_approval():
    _reset_approval_state()
    registry.mark_tool_requires_approval('browser_goto')
    registry.unmark_tool_requires_approval('browser_goto')
    assert not registry.tool_requires_approval('browser_goto')
    _reset_approval_state()


def test_list_approval_required_tools_sorted():
    _reset_approval_state()
    registry.mark_tool_requires_approval('use_computer')
    registry.mark_tool_requires_approval('browser_goto')
    result = registry.list_approval_required_tools()
    assert result == ['browser_goto', 'use_computer']
    _reset_approval_state()


# -------------------------------------------------------------------
# Approval request lifecycle
# -------------------------------------------------------------------

def test_resolve_approval_approved():
    _reset_approval_state()
    registry.mark_tool_requires_approval('get_current_time')

    result_holder = {'value': None}

    def background():
        result_holder['value'] = registry._wait_for_approval('get_current_time', 'no args', timeout=5.0)

    t = threading.Thread(target=background, daemon=True)
    t.start()

    # Wait for the approval request to appear
    for _ in range(50):
        pending = registry.get_pending_approvals()
        if pending:
            break
        time.sleep(0.05)

    pending = registry.get_pending_approvals()
    assert len(pending) == 1
    assert pending[0]['tool'] == 'get_current_time'
    assert pending[0]['status'] == 'pending'

    req_id = pending[0]['id']
    resolved = registry.resolve_approval(req_id, approved=True)
    assert resolved is not None
    assert resolved['status'] == 'approved'

    t.join(timeout=3)
    assert result_holder['value'] is True
    _reset_approval_state()


def test_resolve_approval_denied():
    _reset_approval_state()
    registry.mark_tool_requires_approval('get_current_time')

    result_holder = {'value': None}

    def background():
        result_holder['value'] = registry._wait_for_approval('get_current_time', 'no args', timeout=5.0)

    t = threading.Thread(target=background, daemon=True)
    t.start()

    for _ in range(50):
        pending = registry.get_pending_approvals()
        if pending:
            break
        time.sleep(0.05)

    req_id = registry.get_pending_approvals()[0]['id']
    registry.resolve_approval(req_id, approved=False)

    t.join(timeout=3)
    assert result_holder['value'] is False
    _reset_approval_state()


def test_resolve_approval_timeout():
    _reset_approval_state()
    registry.mark_tool_requires_approval('get_current_time')

    result_holder = {'value': None}

    def background():
        result_holder['value'] = registry._wait_for_approval('get_current_time', 'no args', timeout=0.3)

    t = threading.Thread(target=background, daemon=True)
    t.start()
    t.join(timeout=2)

    assert result_holder['value'] is False
    _reset_approval_state()


def test_resolve_nonexistent_approval():
    _reset_approval_state()
    assert registry.resolve_approval('nonexistent_id', approved=True) is None
    _reset_approval_state()


def test_get_pending_approvals_empty():
    _reset_approval_state()
    assert registry.get_pending_approvals() == []
    _reset_approval_state()


# -------------------------------------------------------------------
# run_tool integration with approval
# -------------------------------------------------------------------

def test_run_tool_blocks_until_approved(monkeypatch):
    _reset_approval_state()
    monkeypatch.setattr(registry, '_get_workspace_plugin_allowlist', lambda: None)
    registry.mark_tool_requires_approval('get_current_time')

    result_holder = {'value': None}

    def background():
        result_holder['value'] = registry.run_tool('get_current_time', '')

    t = threading.Thread(target=background, daemon=True)
    t.start()

    for _ in range(50):
        pending = registry.get_pending_approvals()
        if pending:
            break
        time.sleep(0.05)

    req_id = registry.get_pending_approvals()[0]['id']
    registry.resolve_approval(req_id, approved=True)

    t.join(timeout=5)
    # get_current_time should have run and returned a time string
    assert result_holder['value'] is not None
    assert 'denied' not in (result_holder['value'] or '').lower()
    _reset_approval_state()


def test_run_tool_denied_returns_message(monkeypatch):
    _reset_approval_state()
    monkeypatch.setattr(registry, '_get_workspace_plugin_allowlist', lambda: None)
    registry.mark_tool_requires_approval('get_current_time')

    result_holder = {'value': None}

    def background():
        result_holder['value'] = registry.run_tool('get_current_time', '')

    t = threading.Thread(target=background, daemon=True)
    t.start()

    for _ in range(50):
        pending = registry.get_pending_approvals()
        if pending:
            break
        time.sleep(0.05)

    req_id = registry.get_pending_approvals()[0]['id']
    registry.resolve_approval(req_id, approved=False)

    t.join(timeout=5)
    assert 'denied' in (result_holder['value'] or '').lower()
    _reset_approval_state()


def test_browser_goto_run_tool_blocks_until_approved(monkeypatch):
    _reset_approval_state()
    monkeypatch.setattr(registry, '_get_workspace_plugin_allowlist', lambda: None)
    monkeypatch.setitem(registry._TOOLS, 'browser_goto', lambda arg: f'navigated:{arg}')
    registry.mark_tool_requires_approval('browser_goto')

    result_holder = {'value': None}

    def background():
        result_holder['value'] = registry.run_tool('browser_goto', 'https://example.com')

    t = threading.Thread(target=background, daemon=True)
    t.start()

    for _ in range(50):
        pending = registry.get_pending_approvals()
        if pending:
            break
        time.sleep(0.05)

    pending = registry.get_pending_approvals()
    assert len(pending) == 1
    assert pending[0]['tool'] == 'browser_goto'
    assert pending[0]['status'] == 'pending'

    registry.resolve_approval(pending[0]['id'], approved=True)

    t.join(timeout=5)
    assert result_holder['value'] == 'navigated:https://example.com'
    _reset_approval_state()


def test_browser_goto_run_tool_denied(monkeypatch):
    _reset_approval_state()
    monkeypatch.setattr(registry, '_get_workspace_plugin_allowlist', lambda: None)
    monkeypatch.setitem(registry._TOOLS, 'browser_goto', lambda arg: f'navigated:{arg}')
    registry.mark_tool_requires_approval('browser_goto')

    result_holder = {'value': None}

    def background():
        result_holder['value'] = registry.run_tool('browser_goto', 'https://example.com')

    t = threading.Thread(target=background, daemon=True)
    t.start()

    for _ in range(50):
        pending = registry.get_pending_approvals()
        if pending:
            break
        time.sleep(0.05)

    pending = registry.get_pending_approvals()
    assert len(pending) == 1
    registry.resolve_approval(pending[0]['id'], approved=False)

    t.join(timeout=5)
    assert 'denied' in (result_holder['value'] or '').lower()
    _reset_approval_state()


def test_approval_timeout_shortened_under_pytest(monkeypatch):
    _reset_approval_state()
    monkeypatch.delenv('TOOL_APPROVAL_TIMEOUT_SECONDS', raising=False)

    # Under pytest, default timeout should be bounded to keep test runs responsive.
    assert registry._approval_timeout_seconds() <= 5.0


def test_approval_timeout_env_override(monkeypatch):
    _reset_approval_state()
    monkeypatch.setenv('TOOL_APPROVAL_TIMEOUT_SECONDS', '42')
    assert registry._approval_timeout_seconds() == 42.0


# -------------------------------------------------------------------
# API endpoint tests
# -------------------------------------------------------------------

def test_approvals_list_endpoint(monkeypatch):
    _reset_approval_state()
    from companion_ai.web import create_app
    app = create_app()
    client = app.test_client()

    resp = client.get('/api/approvals')
    assert resp.status_code == 200
    data = resp.get_json()
    assert 'approvals' in data
    assert data['approvals'] == []
    _reset_approval_state()


def test_approvals_resolve_endpoint_not_found(monkeypatch):
    _reset_approval_state()
    import web_companion
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    from companion_ai.web import create_app
    app = create_app()
    client = app.test_client()

    resp = client.post('/api/approvals/fake_id', json={'decision': 'approve'}, headers={'X-API-TOKEN': 'secret'})
    assert resp.status_code == 404
    _reset_approval_state()


def test_approvals_resolve_endpoint_bad_decision(monkeypatch):
    _reset_approval_state()
    import web_companion
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    from companion_ai.web import create_app
    app = create_app()
    client = app.test_client()

    resp = client.post('/api/approvals/fake_id', json={'decision': 'maybe'}, headers={'X-API-TOKEN': 'secret'})
    assert resp.status_code == 400
    _reset_approval_state()


def test_approval_config_endpoint(monkeypatch):
    _reset_approval_state()
    import web_companion
    monkeypatch.setattr(web_companion.core_config, 'API_AUTH_TOKEN', 'secret')
    from companion_ai.web import create_app
    app = create_app()
    client = app.test_client()

    # GET empty
    resp = client.get('/api/approvals/config', headers={'X-API-TOKEN': 'secret'})
    assert resp.status_code == 200
    assert resp.get_json()['requires_approval'] == []

    # POST add
    resp = client.post('/api/approvals/config', json={'tools': ['browser_goto'], 'action': 'add'}, headers={'X-API-TOKEN': 'secret'})
    assert resp.status_code == 200
    assert 'browser_goto' in resp.get_json()['requires_approval']

    # POST remove
    resp = client.post('/api/approvals/config', json={'tools': ['browser_goto'], 'action': 'remove'}, headers={'X-API-TOKEN': 'secret'})
    assert resp.status_code == 200
    assert resp.get_json()['requires_approval'] == []
    _reset_approval_state()
