# companion_ai/services/__init__.py
"""Services subsystem - TTS, jobs, persona, token budget.

Import submodules as needed to avoid circular imports.
"""

# Lazy imports - use from companion_ai.services.tts import ... etc.
# Or import specific functions:
# from companion_ai.services.jobs import add_job, start_worker, stop_worker

__all__ = ['tts', 'jobs', 'persona', 'token_budget']
