#!/usr/bin/env python3
"""Web-based Companion AI Interface -- thin entry-point.

The real implementation now lives in ``companion_ai.web`` (Flask Blueprints).
This file exists purely for backwards compatibility so that:

    from web_companion import app      # all 18 test files
    from web_companion import run_web   # run_companion.py

continue to work unchanged.

It also re-exports module-level names that test files monkeypatch
(core_config, memory_v2, job_manager_module, ConversationSession).
"""

from companion_ai.web import create_app, run_web  # noqa: F401

# Re-export objects that existing tests monkeypatch via `web_companion.X`
from companion_ai.core import config as core_config  # noqa: F401
from companion_ai.memory import mem0_backend as memory_v2  # noqa: F401
from companion_ai.services import jobs as job_manager_module  # noqa: F401
from companion_ai.conversation_manager import ConversationSession  # noqa: F401

app = create_app()

if __name__ == "__main__":
    run_web()
