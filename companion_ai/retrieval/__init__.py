"""Retrieval connector contracts and shared models."""

from .connectors import (
    RetrievalConnectorCapability,
    RetrievalConnectorRecord,
    RetrievalConnectorRequest,
    build_retrieval_path,
)

__all__ = [
    "RetrievalConnectorCapability",
    "RetrievalConnectorRecord",
    "RetrievalConnectorRequest",
    "build_retrieval_path",
]
