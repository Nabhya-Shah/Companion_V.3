from companion_ai.core.context_builder import _build_continuity_context


def test_build_continuity_context_includes_snapshot(monkeypatch):
    monkeypatch.setattr(
        "companion_ai.services.continuity.get_latest_snapshot",
        lambda: {
            "summary": "Project continuity summary",
            "projects": ["Companion roadmap"],
            "blockers": ["Pending review"],
            "next_steps": ["Close P8"],
            "open_questions": ["What is next?"],
        },
    )

    text = _build_continuity_context()
    assert "PROJECT CONTINUITY" in text
    assert "Project continuity summary" in text
    assert "Companion roadmap" in text
