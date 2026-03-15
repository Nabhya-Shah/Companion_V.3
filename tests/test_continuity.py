import web_companion
from web_companion import app

from companion_ai.services import continuity


def test_continuity_create_and_latest():
    snapshot = continuity.create_snapshot(
        summary="Project continuity test",
        projects=["Companion roadmap"],
        blockers=["Pending memory review"],
        next_steps=["Review P8 tasks"],
        open_questions=["What to prioritize next?"],
        metadata={"source": "test"},
    )

    assert snapshot["summary"] == "Project continuity test"
    assert "Companion roadmap" in snapshot["projects"]

    latest = continuity.get_latest_snapshot()
    assert latest is not None
    assert latest["summary"]


def test_continuity_refresh_endpoint_requires_auth(monkeypatch):
    monkeypatch.setattr(web_companion.core_config, "API_AUTH_TOKEN", "secret")
    monkeypatch.setattr(
        "companion_ai.services.continuity.generate_continuity_if_due",
        lambda force=False: {"id": 1, "summary": "ok", "projects": []},
    )

    client = app.test_client()

    denied = client.post("/api/continuity/refresh", json={})
    assert denied.status_code == 401

    ok = client.post("/api/continuity/refresh", json={}, headers={"X-API-TOKEN": "secret"})
    assert ok.status_code == 200
    assert ok.get_json()["status"] == "success"


def test_continuity_list_endpoint(monkeypatch):
    monkeypatch.setattr(
        "companion_ai.services.continuity.get_latest_snapshot",
        lambda: {"id": 2, "summary": "latest continuity"},
    )
    monkeypatch.setattr(
        "companion_ai.services.continuity.list_snapshots",
        lambda limit=10: [{"id": 1, "summary": "older"}],
    )

    client = app.test_client()

    latest = client.get("/api/continuity?latest=true")
    assert latest.status_code == 200
    assert latest.get_json()["snapshot"]["summary"] == "latest continuity"

    listing = client.get("/api/continuity?latest=false&limit=5")
    assert listing.status_code == 200
    assert listing.get_json()["snapshots"][0]["summary"] == "older"
