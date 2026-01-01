# companion_ai/agents/__init__.py
"""Agent subsystem - browser, computer, and vision agents.

Import submodules directly to avoid circular import issues:
    from companion_ai.agents.browser import BrowserAgent
    from companion_ai.agents.computer import computer_agent
    from companion_ai.agents.vision import vision_manager
"""

__all__ = ['browser', 'computer', 'vision']
