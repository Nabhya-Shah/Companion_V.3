# Architecture Index

This file is now an index document.

For the full, current architecture and runtime truth, see PLAN.md.

## Current Architecture Summary

- Web-first Flask application with blueprint split under companion_ai/web.
- Orchestrator-first routing in companion_ai/orchestrator.py.
- Local specialist loops in companion_ai/local_loops for memory, tools, and vision.
- Hybrid memory and retrieval in companion_ai/memory (Mem0 + SQLite + brain index).
- Safety-gated tools and approvals in companion_ai/tools/registry.py.

## Why This Is an Index

This project had multiple overlapping architecture documents that drifted over time.
PLAN.md is now the canonical merged source to keep implementation and docs aligned.
