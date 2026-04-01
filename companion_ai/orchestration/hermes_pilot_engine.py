"""Hermes pilot orchestration adapter.

Current pilot mode intentionally preserves feature parity by delegating request
execution to the main engine while exposing pilot metadata and endpoint intent.
This keeps the lane detachable while the external adapter matures.
"""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

import requests

from companion_ai.core import config as core_config
from companion_ai.orchestration import main_engine


ENGINE_NAME = "hermes_pilot"
_REMOTE_TEXT_KEYS = ("response", "content", "text", "answer", "message")
_REMOTE_META_KEYS = ("metadata", "meta")

logger = logging.getLogger(__name__)


def _candidate_payloads(payload: dict) -> list[dict]:
    candidates = [payload]
    for key in ("result", "data"):
        value = payload.get(key)
        if isinstance(value, dict):
            candidates.append(value)
    return candidates


def _extract_text(payload: dict) -> str:
    for candidate in _candidate_payloads(payload):
        for key in _REMOTE_TEXT_KEYS:
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _extract_metadata(payload: dict) -> dict:
    for candidate in _candidate_payloads(payload):
        for key in _REMOTE_META_KEYS:
            value = candidate.get(key)
            if isinstance(value, dict):
                return dict(value)
    return {}


def _normalize_metadata(base: dict, context: Optional[Dict], mode: str) -> dict:
    trace_id = str((context or {}).get("trace_id") or "").strip()
    normalized = dict(base or {})
    normalized["orchestration_engine"] = ENGINE_NAME
    normalized["pilot_detachable"] = True
    normalized["pilot_mode"] = mode
    normalized.setdefault("pilot_endpoint", core_config.HERMES_PILOT_ENDPOINT or "")
    normalized.setdefault("pilot_feature_parity", True)
    if trace_id:
        normalized.setdefault("trace_id", trace_id)
    return normalized


def _process_remote(user_message: str, context: Optional[Dict]) -> Tuple[str, Dict]:
    endpoint = core_config.HERMES_PILOT_ENDPOINT
    if not endpoint:
        raise RuntimeError("HERMES_PILOT_ENDPOINT is not configured")

    trace_id = str((context or {}).get("trace_id") or "").strip()
    timeout_s = max(1.0, float(core_config.HERMES_PILOT_TIMEOUT_SECONDS or 20.0))

    headers = {
        "Content-Type": "application/json",
    }
    if trace_id:
        headers["X-Trace-ID"] = trace_id
    if core_config.HERMES_PILOT_API_TOKEN:
        headers["X-API-TOKEN"] = core_config.HERMES_PILOT_API_TOKEN

    payload = {
        "message": user_message,
        "context": context or {},
        "trace_id": trace_id,
        "mode": "orchestration_pilot",
    }

    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=timeout_s,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"pilot_transport_error: {e}") from e

    if not response.ok:
        body_preview = (response.text or "")[:240]
        raise RuntimeError(f"pilot_http_{response.status_code}: {body_preview}")

    try:
        remote_payload = response.json()
    except ValueError as e:
        raise RuntimeError("pilot_non_json_response") from e

    if not isinstance(remote_payload, dict):
        raise RuntimeError("pilot_response_not_object")

    text = _extract_text(remote_payload)
    if not text:
        raise RuntimeError("pilot_missing_response_text")

    meta = _extract_metadata(remote_payload)
    meta.setdefault("source", "hermes_pilot_remote")
    meta["pilot_remote_status_code"] = int(response.status_code)
    return text, _normalize_metadata(meta, context, mode="remote_adapter")


def _process_mirror_main(user_message: str, context: Optional[Dict]) -> Tuple[str, Dict]:
    response, metadata = main_engine.process_message(user_message, context)
    return response, _normalize_metadata(dict(metadata or {}), context, mode="mirror_main")


def process_message(user_message: str, context: Optional[Dict] = None) -> Tuple[str, Dict]:
    """Execute message processing through pilot lane with parity-preserving fallback.

    Today, pilot mode mirrors the main engine output intentionally to maintain
    end-user feature parity while keeping detachability to one config switch.
    When HERMES_PILOT_ENDPOINT is configured, it uses the remote pilot adapter.
    """
    if not core_config.HERMES_PILOT_ENDPOINT:
        return _process_mirror_main(user_message, context)

    logger.info("Routing orchestration through Hermes pilot endpoint")
    return _process_remote(user_message, context)
