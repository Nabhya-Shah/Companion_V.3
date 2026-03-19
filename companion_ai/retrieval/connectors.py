"""Connector contracts for external retrieval sources.

Insert A1 introduces these contracts without changing retrieval behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RetrievalConnectorRequest:
    """Normalized retrieval request for connector adapters."""

    query: str
    limit: int = 5
    workspace_id: str = "default"
    user_id: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalConnectorRecord:
    """One connector retrieval record.

    Fields are chosen to align with staged retrieval observability payloads.
    """

    connector_id: str
    connector_type: str
    source_id: str
    source_type: str
    text: str
    score: float
    latency_ms: int
    confidence: float | None = None
    retrieval_path: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalConnectorCapability:
    """Capability metadata exposed by diagnostics endpoints."""

    connector_id: str
    connector_type: str
    enabled: bool
    requires_auth: bool = False
    description: str = ""


def build_retrieval_path(*parts: str) -> str:
    """Build a normalized retrieval path for traceability metadata."""
    cleaned = [p.strip(" /") for p in parts if p and p.strip()]
    if not cleaned:
        return ""
    return "/".join(cleaned)
