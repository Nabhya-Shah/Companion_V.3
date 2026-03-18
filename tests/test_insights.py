from datetime import datetime

from companion_ai.services import insights
from companion_ai.web import create_app


def _use_temp_insights_db(tmp_path, monkeypatch):
    db_path = tmp_path / "insights_test.db"
    monkeypatch.setattr(insights, "DB_PATH", str(db_path))
    insights.init_db()
    return db_path


def test_create_and_list_insights(tmp_path, monkeypatch):
    _use_temp_insights_db(tmp_path, monkeypatch)

    created = insights.create_insight("Daily Companion Brief", "Top memory signals:\n- Loves coding")
    assert created["id"] > 0
    assert created["status"] == "unread"

    rows = insights.list_insights(limit=10)
    assert len(rows) == 1
    assert rows[0]["title"] == "Daily Companion Brief"
    assert insights.unread_count() == 1


def test_update_status(tmp_path, monkeypatch):
    _use_temp_insights_db(tmp_path, monkeypatch)

    row = insights.create_insight("Daily", "Body")
    ok = insights.update_status(row["id"], "read")
    assert ok is True
    assert insights.unread_count() == 0

    rows = insights.list_insights(limit=5)
    assert rows[0]["status"] == "read"


def test_generate_daily_if_due(tmp_path, monkeypatch):
    _use_temp_insights_db(tmp_path, monkeypatch)

    def fake_digest():
        return (
            "Daily Companion Brief",
            "Pending memory review: 1 fact(s) need approval/rejection.",
            {"pending_facts": 1},
        )

    monkeypatch.setattr(insights, "build_digest_text", fake_digest)

    first = insights.generate_daily_insight_if_due(now=datetime(2026, 3, 9, 8, 0, 0))
    second = insights.generate_daily_insight_if_due(now=datetime(2026, 3, 9, 20, 0, 0))

    assert first is not None
    assert second is None
    assert insights.unread_count() == 1


def test_generate_daily_if_due_dedupes_existing_same_day_digest(tmp_path, monkeypatch):
    _use_temp_insights_db(tmp_path, monkeypatch)

    def fake_digest():
        return (
            "Daily Companion Brief",
            "Top memory signals:",
            {"facts": 1},
        )

    monkeypatch.setattr(insights, "build_digest_text", fake_digest)

    pre = insights.create_insight(
        "Daily Companion Brief",
        "Top memory signals:",
        category="daily_digest",
        metadata={"facts": 1},
        digest_day="2026-03-09",
    )
    assert pre is not None

    generated = insights.generate_daily_insight_if_due(now=datetime(2026, 3, 9, 8, 0, 0), force=True)

    assert generated is None
    assert insights.unread_count() == 1


def test_chat_history_injects_offline_insights_once(tmp_path, monkeypatch):
    _use_temp_insights_db(tmp_path, monkeypatch)

    app = create_app()
    client = app.test_client()

    insights.create_insight("Daily Companion Brief", "You have 1 pending memory review item.")

    resp1 = client.get("/api/chat/history")
    data1 = resp1.get_json()
    ai_msgs_1 = [h.get("ai", "") for h in data1.get("history", []) if h.get("ai")]
    assert any("[Proactive] Daily Companion Brief" in msg for msg in ai_msgs_1)

    resp2 = client.get("/api/chat/history")
    data2 = resp2.get_json()
    ai_msgs_2 = [h.get("ai", "") for h in data2.get("history", []) if h.get("ai")]
    assert len(ai_msgs_2) == len(ai_msgs_1)


def test_insights_api_list_and_status_update(tmp_path, monkeypatch):
    _use_temp_insights_db(tmp_path, monkeypatch)

    app = create_app()
    client = app.test_client()

    created = insights.create_insight("Daily Companion Brief", "A useful reminder.")

    resp = client.get("/api/insights?unread=1")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["unread_count"] >= 1
    assert any(item["id"] == created["id"] for item in payload["insights"])

    resp2 = client.post(f"/api/insights/{created['id']}/status", json={"status": "read"})
    assert resp2.status_code == 200

    resp3 = client.get("/api/insights?unread=1")
    payload3 = resp3.get_json()
    assert all(item["id"] != created["id"] for item in payload3["insights"])
