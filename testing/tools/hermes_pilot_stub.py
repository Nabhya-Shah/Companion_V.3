"""Hermes pilot stub service for live local A/B testing.

This endpoint mimics a remote Hermes adapter contract and delegates processing
to the current in-repo orchestrator path.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from flask import Flask, jsonify, request

# Ensure project root is importable when running this script directly.
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from companion_ai.runtime import process_message


logger = logging.getLogger(__name__)
app = Flask(__name__)


@app.get("/health")
def health():
    return jsonify({"status": "ok", "service": "hermes_pilot_stub"})


@app.post("/orchestrate")
def orchestrate():
    payload = request.get_json(silent=True) or {}
    message = str(payload.get("message") or "").strip()
    context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    trace_id = str(payload.get("trace_id") or request.headers.get("X-Trace-ID") or "").strip()

    if trace_id:
        context = dict(context)
        context.setdefault("trace_id", trace_id)

    if not message:
        return jsonify({"error": "message required"}), 400

    try:
        response, metadata = process_message(message, context)
        meta = dict(metadata or {})
        if trace_id:
            meta.setdefault("trace_id", trace_id)
        return jsonify({"response": response, "metadata": meta})
    except Exception as e:
        logger.exception("Pilot stub failed")
        return jsonify({"error": str(e), "trace_id": trace_id}), 500


def main() -> None:
    parser = argparse.ArgumentParser(description="Run local Hermes pilot stub service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5055)
    args = parser.parse_args()

    app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
