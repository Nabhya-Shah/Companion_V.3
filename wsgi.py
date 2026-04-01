"""Production WSGI entrypoint for Companion V3."""

from companion_ai.web import create_app

app = create_app()
