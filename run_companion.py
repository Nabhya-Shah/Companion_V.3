"""Unified runner for Companion AI.

Supports task compatibility:
- python run_companion.py
- python run_companion.py --web
"""

from __future__ import annotations

import argparse

from web_companion import run_web


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Companion AI web server")
    parser.add_argument("--web", action="store_true", help="Run web mode (default behavior)")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=5000, help="Bind port (default: 5000)")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not auto-open browser window",
    )
    args = parser.parse_args()

    run_web(host=args.host, port=args.port, open_browser_flag=not args.no_browser)


if __name__ == "__main__":
    main()
