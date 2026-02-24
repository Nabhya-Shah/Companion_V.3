from web_companion import app
import web_companion


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
