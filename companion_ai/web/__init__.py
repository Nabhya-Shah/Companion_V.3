# companion_ai/web/__init__.py
"""Flask application factory and ``run_web`` entry-point.

Usage::

    from companion_ai.web import create_app, run_web
    app = create_app()      # used by tests / WSGI servers
    run_web()                # starts dev server with browser
"""

import os
import sys
import time
import logging
import threading
import webbrowser

from flask import Flask

from companion_ai.core import config as core_config
from companion_ai.services import jobs as job_manager_module
from companion_ai.memory import sqlite_backend as sqlite_memory

# ---------------------------------------------------------------------------
# Module-level singleton so repeated ``create_app()`` calls return the same
# Flask instance (mirrors the old single-module behaviour tests rely on).
# ---------------------------------------------------------------------------
_app_instance: Flask | None = None


def create_app() -> Flask:
    """Build and configure the Flask application, register all blueprints."""
    global _app_instance
    if _app_instance is not None:
        return _app_instance

    # ------------------------------------------------------------------
    # Logging  (runs once — identical to the old web_companion.py setup)
    # ------------------------------------------------------------------
    DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data')
    LOG_FILE = os.path.join(DATA_DIR, 'web_server.log')
    os.makedirs(DATA_DIR, exist_ok=True)

    if os.path.exists(LOG_FILE):
        try:
            os.remove(LOG_FILE)
        except OSError:
            pass

    console_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(console_formatter)

    file_handler = logging.FileHandler(LOG_FILE, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(file_formatter)

    logging.basicConfig(level=logging.DEBUG, handlers=[console_handler, file_handler], force=True)
    logger = logging.getLogger(__name__)

    sys.stdout.flush()
    sys.stderr.flush()

    logger.info("=" * 70)
    logger.info("COMPANION AI WEB SERVER STARTING")
    logger.info(f"Logs: {LOG_FILE}")
    logger.info("=" * 70)

    # ------------------------------------------------------------------
    # Background job worker
    # ------------------------------------------------------------------
    job_manager_module.start_worker()

    # ------------------------------------------------------------------
    # Flask app
    # ------------------------------------------------------------------
    # Templates and static live at project root, two levels up from this file
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    app = Flask(
        __name__,
        template_folder=os.path.join(project_root, 'templates'),
        static_folder=os.path.join(project_root, 'static'),
    )

    # ------------------------------------------------------------------
    # Security before_request hook
    # ------------------------------------------------------------------
    from companion_ai.web.state import enforce_api_security
    app.before_request(enforce_api_security)

    # ------------------------------------------------------------------
    # Register blueprints
    # ------------------------------------------------------------------
    from companion_ai.web.chat_routes import chat_bp
    from companion_ai.web.memory_routes import memory_bp
    from companion_ai.web.tools_routes import tools_bp
    from companion_ai.web.media_routes import media_bp
    from companion_ai.web.loxone_routes import loxone_bp
    from companion_ai.web.files_routes import files_bp
    from companion_ai.web.system_routes import system_bp

    app.register_blueprint(chat_bp)
    app.register_blueprint(memory_bp)
    app.register_blueprint(tools_bp)
    app.register_blueprint(media_bp)
    app.register_blueprint(loxone_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(system_bp)

    # ------------------------------------------------------------------
    # Background brain indexing
    # ------------------------------------------------------------------
    def _start_brain_indexing():
        try:
            from companion_ai.brain_index import start_background_indexing
            start_background_indexing()
        except Exception as e:
            logger.warning(f"Could not start brain indexing: {e}")

    threading.Thread(target=_start_brain_indexing, daemon=True).start()

    _app_instance = app
    return app


# -----------------------------------------------------------------------
# Convenience helpers (preserved from original web_companion.py)
# -----------------------------------------------------------------------

def _open_browser(port: int = 5000) -> None:
    time.sleep(1.5)
    webbrowser.open(f'http://localhost:{port}')


def run_web(
    host: str = core_config.WEB_HOST,
    port: int = core_config.WEB_PORT,
    open_browser_flag: bool = True,
) -> None:
    """Start the Flask dev server with optional browser launch."""
    app = create_app()
    print(f"Starting Companion AI Web Portal on http://{host}:{port}")

    # Background scheduler (decay + resurfacing)
    def _bg_scheduler():
        while True:
            try:
                sqlite_memory.decay_profile_confidence()
                sqlite_memory.touch_stale_facts(limit=2)
            except Exception as e:
                logging.getLogger(__name__).debug(f"BG scheduler error: {e}")
            time.sleep(300)

    threading.Thread(target=_bg_scheduler, daemon=True).start()

    if open_browser_flag:
        threading.Thread(target=_open_browser, args=(port,), daemon=True).start()

    app.run(debug=False, host=host, port=port)
