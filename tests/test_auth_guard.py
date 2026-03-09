from web_companion import app
import web_companion
import io


def test_debug_endpoint_forbidden_without_api_token_config(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, "API_AUTH_TOKEN", None)

    client = app.test_client()
    res = client.post("/api/debug/reset", json={})

    assert res.status_code == 403


def test_debug_endpoint_requires_valid_token_when_configured(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, "API_AUTH_TOKEN", "secret")

    client = app.test_client()
    res = client.post("/api/debug/reset", json={})
    assert res.status_code == 401

    res_ok = client.post(
        "/api/debug/reset",
        json={},
        headers={"X-API-TOKEN": "secret"},
    )
    assert res_ok.status_code == 200
    assert res_ok.get_json().get("reset") is True


def test_brain_upload_allowed_on_localhost_without_api_token(monkeypatch, tmp_path):
    monkeypatch.setattr(web_companion.core_config, "API_AUTH_TOKEN", None)

    import companion_ai.web.files_routes as files_routes
    import companion_ai.brain_index as brain_index_module

    class _FakeBrainIndex:
        def index_file(self, _path):
            return 1

    monkeypatch.setattr(files_routes, '_brain_dir_for_workspace', lambda: str(tmp_path))
    monkeypatch.setattr(brain_index_module, 'get_brain_index', lambda: _FakeBrainIndex())

    client = app.test_client()
    res = client.post(
        '/api/brain/upload',
        data={'file': (io.BytesIO(b'hello'), 'note.txt')},
        content_type='multipart/form-data',
    )

    assert res.status_code == 200
    payload = res.get_json()
    assert payload['success'] is True
    assert payload['filename'] == 'note.txt'
