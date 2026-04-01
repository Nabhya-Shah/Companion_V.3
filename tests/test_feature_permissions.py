from web_companion import app


def _deny_feature(monkeypatch, feature_name):
    import companion_ai.web.state as web_state

    def fake_get_workspace_permissions(workspace_id=None):
        return {
            "tools_execute": True,
            "memory_write": True,
            "workflows_run": True,
            "files_upload": True,
            feature_name: False,
        }

    monkeypatch.setattr(web_state, "get_workspace_permissions", fake_get_workspace_permissions)


def test_workflow_run_blocked_when_workflows_disabled(monkeypatch):
    _deny_feature(monkeypatch, "workflows_run")
    client = app.test_client()

    res = client.post("/api/workflows/sample/run")

    assert res.status_code == 403
    payload = res.get_json()
    assert payload["feature"] == "workflows_run"


def test_upload_blocked_when_files_upload_disabled(monkeypatch):
    _deny_feature(monkeypatch, "files_upload")
    client = app.test_client()

    res = client.post("/api/upload")

    assert res.status_code == 403
    payload = res.get_json()
    assert payload["feature"] == "files_upload"


def test_memory_write_blocked_when_memory_write_disabled(monkeypatch):
    _deny_feature(monkeypatch, "memory_write")
    client = app.test_client()

    res = client.put("/api/memory/fact/f1", json={"value": "new"})

    assert res.status_code == 403
    payload = res.get_json()
    assert payload["feature"] == "memory_write"


def test_tools_search_blocked_when_tools_execute_disabled(monkeypatch):
    _deny_feature(monkeypatch, "tools_execute")
    client = app.test_client()

    res = client.get("/api/search?q=hello")

    assert res.status_code == 403
    payload = res.get_json()
    assert payload["feature"] == "tools_execute"


def test_permissions_endpoint_get_and_post(monkeypatch):
    import companion_ai.web.state as web_state

    captured = {}
    monkeypatch.setattr(web_state.core_config, "API_AUTH_TOKEN", "secret")

    monkeypatch.setattr(
        web_state,
        "get_workspace_permissions",
        lambda workspace_id=None: {
            "tools_execute": True,
            "memory_write": True,
            "workflows_run": True,
            "files_upload": True,
        },
    )

    def fake_set_workspace_permissions(workspace_id, updates):
        captured["workspace_id"] = workspace_id
        captured["updates"] = updates
        return {
            "tools_execute": False,
            "memory_write": True,
            "workflows_run": True,
            "files_upload": True,
        }

    monkeypatch.setattr(web_state, "set_workspace_permissions", fake_set_workspace_permissions)

    client = app.test_client()
    get_res = client.get("/api/permissions?workspace_id=alpha", headers={"X-API-TOKEN": "secret"})
    assert get_res.status_code == 200
    assert get_res.get_json()["permissions"]["tools_execute"] is True

    post_res = client.post(
        "/api/permissions",
        json={"workspace_id": "alpha", "permissions": {"tools_execute": False}},
        headers={"X-API-TOKEN": "secret"},
    )
    assert post_res.status_code == 200
    assert captured["workspace_id"] == "alpha"
    assert captured["updates"]["tools_execute"] is False
