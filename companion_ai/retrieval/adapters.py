"""Connector adapter registry for external retrieval sources.

Insert A2 keeps local retrieval as primary and treats connector results as
additive context when enabled.
"""

from __future__ import annotations

from dataclasses import asdict
import json
import logging
import os
import time
from pathlib import Path
from typing import Protocol

from companion_ai.core import config as core_config
from companion_ai.retrieval.connectors import (
    RetrievalConnectorCapability,
    RetrievalConnectorRecord,
    RetrievalConnectorRequest,
    build_retrieval_path,
)

logger = logging.getLogger(__name__)


class RetrievalConnector(Protocol):
    connector_id: str
    connector_type: str

    def is_enabled(self) -> bool:
        ...

    def search(self, request: RetrievalConnectorRequest) -> list[RetrievalConnectorRecord]:
        ...

    def capability(self) -> RetrievalConnectorCapability:
        ...


class FileStubConnector:
    connector_id = "file_stub"
    connector_type = "file"

    def __init__(self) -> None:
        self.stub_path = Path(os.getenv("RETRIEVAL_FILE_STUB_PATH", os.path.join("data", "retrieval_stub.json")))

    def is_enabled(self) -> bool:
        return self.stub_path.exists() and self.stub_path.is_file()

    def search(self, request: RetrievalConnectorRequest) -> list[RetrievalConnectorRecord]:
        started = time.perf_counter()
        try:
            payload = json.loads(self.stub_path.read_text(encoding="utf-8"))
            items = payload if isinstance(payload, list) else payload.get("results", [])
            records: list[RetrievalConnectorRecord] = []
            for idx, item in enumerate(items[: request.limit]):
                if not isinstance(item, dict):
                    continue
                text = (item.get("text") or "").strip()
                if not text:
                    continue
                records.append(
                    RetrievalConnectorRecord(
                        connector_id=self.connector_id,
                        connector_type=self.connector_type,
                        source_id=str(item.get("id") or f"stub-{idx}"),
                        source_type=str(item.get("source_type") or "external_stub"),
                        text=text,
                        score=float(item.get("score") or 0.25),
                        confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        retrieval_path=build_retrieval_path("connector", self.connector_id, str(item.get("path") or "root")),
                        metadata={"provider": "file_stub"},
                    )
                )
            return records
        except Exception as exc:
            logger.warning("FileStubConnector search failed: %s", exc)
            return []

    def capability(self) -> RetrievalConnectorCapability:
        return RetrievalConnectorCapability(
            connector_id=self.connector_id,
            connector_type=self.connector_type,
            enabled=self.is_enabled(),
            requires_auth=False,
            description="Reads optional additive retrieval results from a local JSON stub file.",
        )


class HttpMockConnector:
    connector_id = "http_mock"
    connector_type = "http"

    def __init__(self) -> None:
        self.base_url = (os.getenv("RETRIEVAL_HTTP_MOCK_URL", "") or "").strip()

    def is_enabled(self) -> bool:
        return bool(self.base_url)

    def search(self, request: RetrievalConnectorRequest) -> list[RetrievalConnectorRecord]:
        if not self.base_url:
            return []

        started = time.perf_counter()
        timeout = max(core_config.RETRIEVAL_CONNECTOR_TIMEOUT_MS, 100) / 1000.0
        try:
            import requests

            response = requests.get(
                self.base_url,
                params={"q": request.query, "limit": request.limit, "workspace_id": request.workspace_id},
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json() if response.content else {}
            items = payload if isinstance(payload, list) else payload.get("results", [])

            records: list[RetrievalConnectorRecord] = []
            for idx, item in enumerate(items[: request.limit]):
                if not isinstance(item, dict):
                    continue
                text = (item.get("text") or "").strip()
                if not text:
                    continue
                records.append(
                    RetrievalConnectorRecord(
                        connector_id=self.connector_id,
                        connector_type=self.connector_type,
                        source_id=str(item.get("id") or f"http-{idx}"),
                        source_type=str(item.get("source_type") or "external_http"),
                        text=text,
                        score=float(item.get("score") or 0.25),
                        confidence=float(item["confidence"]) if item.get("confidence") is not None else None,
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        retrieval_path=build_retrieval_path("connector", self.connector_id, str(item.get("path") or "root")),
                        metadata={"provider": "http_mock", "status_code": response.status_code},
                    )
                )
            return records
        except Exception as exc:
            logger.warning("HttpMockConnector search failed: %s", exc)
            return []

    def capability(self) -> RetrievalConnectorCapability:
        return RetrievalConnectorCapability(
            connector_id=self.connector_id,
            connector_type=self.connector_type,
            enabled=self.is_enabled(),
            requires_auth=False,
            description="Queries an optional external HTTP retrieval service.",
        )


def _all_connectors() -> list[RetrievalConnector]:
    return [FileStubConnector(), HttpMockConnector()]


def get_enabled_connectors() -> list[RetrievalConnector]:
    """Return enabled connectors after feature and allowlist filtering."""
    if not core_config.RETRIEVAL_CONNECTORS_ENABLED:
        return []

    # Web-mode feature gate: retrieval connectors are workspace-permission scoped.
    try:
        from flask import has_request_context
        if has_request_context():
            from companion_ai.web import state as web_state
            workspace_id = web_state._resolve_workspace_key()
            perms = web_state.get_workspace_permissions(workspace_id)
            if not perms.get("retrieval_connectors", False):
                return []
    except Exception:
        # Non-web callers (CLI/tests) do not require request-scoped permission checks.
        pass

    allowlist = core_config.get_retrieval_connector_allowlist()
    connectors = []
    for connector in _all_connectors():
        if allowlist is not None and connector.connector_id not in allowlist:
            continue
        if connector.is_enabled():
            connectors.append(connector)
    return connectors


def get_connector_capabilities() -> list[dict]:
    """Return capabilities for diagnostics endpoints."""
    allowlist = core_config.get_retrieval_connector_allowlist()
    out: list[dict] = []
    for connector in _all_connectors():
        enabled = connector.is_enabled() and core_config.RETRIEVAL_CONNECTORS_ENABLED
        if allowlist is not None and connector.connector_id not in allowlist:
            enabled = False
        cap = connector.capability()
        cap.enabled = enabled
        out.append(asdict(cap))
    return out


def search_connectors(request: RetrievalConnectorRequest) -> tuple[list[dict], dict]:
    """Query enabled connectors and return normalized records plus diagnostics."""
    records: list[dict] = []
    connector_counts: dict[str, int] = {}
    connector_ms: dict[str, int] = {}
    connector_paths: dict[str, list[str]] = {}
    source_allowlist = core_config.get_retrieval_connector_source_allowlist()
    timeout_budget_ms = max(core_config.RETRIEVAL_CONNECTOR_TIMEOUT_MS, 100)

    for connector in get_enabled_connectors():
        started = time.perf_counter()
        try:
            hits = connector.search(request)
        except Exception as exc:
            logger.warning("Connector %s failed: %s", connector.connector_id, exc)
            hits = []

        connector_ms[connector.connector_id] = int((time.perf_counter() - started) * 1000)
        if connector_ms[connector.connector_id] > timeout_budget_ms:
            logger.warning(
                "Connector %s exceeded timeout budget (%sms > %sms); dropping connector hits",
                connector.connector_id,
                connector_ms[connector.connector_id],
                timeout_budget_ms,
            )
            hits = []

        connector_counts[connector.connector_id] = 0
        connector_paths[connector.connector_id] = []

        for hit in hits[: request.limit]:
            if source_allowlist is not None and hit.source_type not in source_allowlist:
                continue
            d = asdict(hit)
            d["source"] = f"connector:{hit.connector_id}"
            d["surfacing_reason"] = "External connector match"
            d["score_breakdown"] = {
                "connector_score": hit.score,
                "connector_id": hit.connector_id,
            }
            records.append(d)
            connector_counts[connector.connector_id] += 1
            if hit.retrieval_path:
                connector_paths[connector.connector_id].append(hit.retrieval_path)

    diagnostics = {
        "connector_counts": connector_counts,
        "connector_ms": connector_ms,
        "connector_paths": {
            key: list(dict.fromkeys(paths))[:3]
            for key, paths in connector_paths.items()
            if paths
        },
        "enabled_count": len(get_enabled_connectors()),
    }
    return records, diagnostics
