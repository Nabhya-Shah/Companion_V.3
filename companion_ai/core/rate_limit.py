import time
import functools
import logging
from typing import Dict, List

logger = logging.getLogger(__name__)

class RateLimiter:
    def __init__(self):
        self.calls: Dict[str, List[float]] = {}

    def is_allowed(self, key: str, max_calls: int, time_window: float) -> bool:
        now = time.time()
        if key not in self.calls:
            self.calls[key] = []
        
        # Remove old calls
        self.calls[key] = [t for t in self.calls[key] if now - t < time_window]
        
        if len(self.calls[key]) >= max_calls:
            return False
            
        self.calls[key].append(now)
        return True

_limiter = RateLimiter()

def rate_limit(calls: int = 10, period_seconds: int = 60):
    """
    Decorator to rate-limit function calls.
    Returns an error string if exceeded, preventing downstream API flood.
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = f"rl_{fn.__name__}"
            if not _limiter.is_allowed(key, calls, period_seconds):
                msg = f"Error: Rate limit exceeded for {fn.__name__}. Try again in {period_seconds}s."
                logger.warning(msg)
                return msg
            return fn(*args, **kwargs)
        return wrapper
    return decorator
