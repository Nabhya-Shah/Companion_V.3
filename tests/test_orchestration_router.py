import pytest

from companion_ai.core import config as core_config
from companion_ai.orchestration import hermes_pilot_engine
from companion_ai.orchestration import main_engine
from companion_ai.orchestration import router


def test_router_uses_main_engine_by_default(monkeypatch):
    monkeypatch.setattr(core_config, "ORCHESTRATION_ENGINE", "main")
    monkeypatch.setattr(core_config, "ENABLE_HERMES_PILOT", False)

    monkeypatch.setattr(main_engine, "process_message", lambda user_message, context=None: ("ok", {"source": "main"}))
    monkeypatch.setattr(hermes_pilot_engine, "process_message", lambda *_: (_ for _ in ()).throw(AssertionError("pilot should not run")))

    response, meta = router.process_message("hello", {"trace_id": "t1"})

    assert response == "ok"
    assert meta["source"] == "main"


def test_router_pilot_request_falls_back_when_disabled(monkeypatch):
    monkeypatch.setattr(core_config, "ORCHESTRATION_ENGINE", "hermes_pilot")
    monkeypatch.setattr(core_config, "ENABLE_HERMES_PILOT", False)

    monkeypatch.setattr(main_engine, "process_message", lambda *_: ("main-lane", {"orchestration_engine": "main"}))
    monkeypatch.setattr(hermes_pilot_engine, "process_message", lambda *_: (_ for _ in ()).throw(AssertionError("pilot should be gated off")))

    response, meta = router.process_message("hello")

    assert response == "main-lane"
    assert meta["orchestration_engine"] == "main"


def test_hermes_pilot_engine_preserves_feature_parity_metadata(monkeypatch):
    monkeypatch.setattr(core_config, "HERMES_PILOT_ENDPOINT", "")
    monkeypatch.setattr(main_engine, "process_message", lambda *_: ("same-response", {"source": "loop_memory"}))

    response, meta = hermes_pilot_engine.process_message("what do you remember about me")

    assert response == "same-response"
    assert meta["source"] == "loop_memory"
    assert meta["orchestration_engine"] == "hermes_pilot"
    assert meta["pilot_detachable"] is True
    assert meta["pilot_feature_parity"] is True
    assert meta["pilot_endpoint"] == ""
    assert meta["pilot_mode"] == "mirror_main"


def test_hermes_pilot_engine_remote_adapter_success(monkeypatch):
    class _Resp:
        ok = True
        status_code = 200
        text = '{"response":"pilot ok"}'

        def json(self):
            return {
                "response": "pilot ok",
                "metadata": {
                    "source": "pilot_remote",
                    "loop_result": {"status": "success"},
                },
            }

    captured = {}

    def _fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["json"] = dict(json or {})
        captured["headers"] = dict(headers or {})
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(core_config, "HERMES_PILOT_ENDPOINT", "http://pilot.local/orchestrate")
    monkeypatch.setattr(core_config, "HERMES_PILOT_TIMEOUT_SECONDS", 12.5)
    monkeypatch.setattr(core_config, "HERMES_PILOT_API_TOKEN", "pilot-token")
    monkeypatch.setattr(hermes_pilot_engine.requests, "post", _fake_post)

    response, meta = hermes_pilot_engine.process_message("hello", {"trace_id": "trace-abc", "recent": "ctx"})

    assert response == "pilot ok"
    assert captured["url"] == "http://pilot.local/orchestrate"
    assert captured["json"]["message"] == "hello"
    assert captured["json"]["trace_id"] == "trace-abc"
    assert captured["headers"]["X-Trace-ID"] == "trace-abc"
    assert captured["headers"]["X-API-TOKEN"] == "pilot-token"
    assert captured["timeout"] == 12.5
    assert meta["orchestration_engine"] == "hermes_pilot"
    assert meta["pilot_mode"] == "remote_adapter"
    assert meta["pilot_endpoint"] == "http://pilot.local/orchestrate"
    assert meta["pilot_remote_status_code"] == 200
    assert meta["source"] == "pilot_remote"


def test_hermes_pilot_engine_remote_adapter_invalid_payload(monkeypatch):
    class _Resp:
        ok = True
        status_code = 200
        text = '{"status":"ok"}'

        def json(self):
            return {"status": "ok"}

    monkeypatch.setattr(core_config, "HERMES_PILOT_ENDPOINT", "http://pilot.local/orchestrate")
    monkeypatch.setattr(hermes_pilot_engine.requests, "post", lambda *args, **kwargs: _Resp())

    with pytest.raises(RuntimeError, match="pilot_missing_response_text"):
        hermes_pilot_engine.process_message("hello", {"trace_id": "t1"})


def test_router_non_strict_pilot_failure_falls_back_to_main(monkeypatch):
    monkeypatch.setattr(core_config, "ORCHESTRATION_ENGINE", "hermes_pilot")
    monkeypatch.setattr(core_config, "ENABLE_HERMES_PILOT", True)
    monkeypatch.setattr(core_config, "HERMES_PILOT_STRICT", False)

    monkeypatch.setattr(hermes_pilot_engine, "process_message", lambda *_: (_ for _ in ()).throw(RuntimeError("pilot unavailable")))
    monkeypatch.setattr(main_engine, "process_message", lambda *_: ("fallback-main", {"source": "main"}))

    response, meta = router.process_message("hi")

    assert response == "fallback-main"
    assert meta["source"] == "main"
    assert meta["orchestration_engine"] == "main"
    assert meta["pilot_fallback_from"] == "hermes_pilot"
    assert "pilot unavailable" in meta["pilot_fallback_reason"]


def test_router_strict_pilot_failure_raises(monkeypatch):
    monkeypatch.setattr(core_config, "ORCHESTRATION_ENGINE", "hermes_pilot")
    monkeypatch.setattr(core_config, "ENABLE_HERMES_PILOT", True)
    monkeypatch.setattr(core_config, "HERMES_PILOT_STRICT", True)

    monkeypatch.setattr(hermes_pilot_engine, "process_message", lambda *_: (_ for _ in ()).throw(RuntimeError("pilot hard failure")))

    with pytest.raises(RuntimeError, match="pilot hard failure"):
        router.process_message("hello")
