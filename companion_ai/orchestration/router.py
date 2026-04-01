"""Orchestration engine router with detachable pilot boundary."""

from __future__ import annotations

import logging
from typing import Dict, Optional, Tuple

from companion_ai.core import config as core_config
from companion_ai.orchestration import main_engine, hermes_pilot_engine


logger = logging.getLogger(__name__)

_MAIN_ALIASES = {"", "main", "default", "orchestrator"}
_PILOT_ALIASES = {"hermes_pilot", "hermes", "pilot"}


def _requested_engine() -> str:
    return str(core_config.ORCHESTRATION_ENGINE or "main").strip().lower()


def _resolve_engine_name() -> str:
    requested = _requested_engine()
    if requested in _MAIN_ALIASES:
        return "main"

    if requested in _PILOT_ALIASES:
        if core_config.ENABLE_HERMES_PILOT:
            return "hermes_pilot"
        logger.warning(
            "ORCHESTRATION_ENGINE=%s requested but ENABLE_HERMES_PILOT is false; using main engine",
            requested,
        )
        return "main"

    logger.warning("Unknown ORCHESTRATION_ENGINE=%s; using main engine", requested)
    return "main"


def get_runtime_descriptor() -> Dict:
    """Expose routing mode so pilot state is observable in health diagnostics."""
    requested = _requested_engine()
    resolved = _resolve_engine_name()
    return {
        "requested_engine": requested,
        "active_engine": resolved,
        "pilot_enabled": bool(core_config.ENABLE_HERMES_PILOT),
        "pilot_strict": bool(core_config.HERMES_PILOT_STRICT),
        "pilot_endpoint": core_config.HERMES_PILOT_ENDPOINT or "",
        "pilot_remote_enabled": bool(core_config.HERMES_PILOT_ENDPOINT),
        "pilot_timeout_seconds": float(core_config.HERMES_PILOT_TIMEOUT_SECONDS or 20.0),
        "detachable": True,
    }


def process_message(user_message: str, context: Optional[Dict] = None) -> Tuple[str, Dict]:
    """Route message processing to the active orchestration engine.

    In non-strict mode, pilot failures gracefully fall back to the main engine.
    """
    active = _resolve_engine_name()

    if active == "hermes_pilot":
        try:
            return hermes_pilot_engine.process_message(user_message, context)
        except Exception as e:
            if core_config.HERMES_PILOT_STRICT:
                raise

            logger.error(
                "Hermes pilot failed; falling back to main engine (strict disabled): %s",
                e,
            )
            response, metadata = main_engine.process_message(user_message, context)
            fallback_meta = dict(metadata or {})
            fallback_meta["orchestration_engine"] = "main"
            fallback_meta["pilot_detachable"] = True
            fallback_meta["pilot_fallback_from"] = "hermes_pilot"
            fallback_meta["pilot_fallback_reason"] = str(e)[:240]
            return response, fallback_meta

    return main_engine.process_message(user_message, context)
