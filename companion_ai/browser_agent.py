"""
Browser Agent - Playwright-based browser automation.

Provides reliable DOM-based browser control:
- Faster than PyAutoGUI vision-based approach
- More reliable with CSS/XPath selectors
- Supports headless and headed modes
"""

import asyncio
import logging
import base64
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy import to avoid startup overhead
_browser = None
_context = None
_page = None
_playwright = None

# Path to store browser data (bookmarks, cookies, etc.)
import os
BROWSER_DATA_DIR = os.path.join(os.path.expanduser("~"), ".companion_browser")


async def _ensure_browser(headless: bool = False):
    """Ensure browser is launched and page is ready.
    
    1. Tries to connect to EXISTING Chrome on port 9222 (for full user profile).
    2. Falls back to persistent context at ~/.companion_browser.
    """
    global _browser, _context, _page, _playwright
    
    if _page:
        try:
            # Check if page is still valid
            await _page.title()
            return _page
        except:
            # Page was closed, need to recreate
            _page = None
            _context = None
    
    from playwright.async_api import async_playwright
    
    if not _playwright:
        try:
            _playwright = await async_playwright().start()
        except:
            pass # Might be already started in this process
    
    # ---------------------------------------------------------
    # STRATEGY 1: Connect to existing Chrome (Port 9222)
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # STRATEGY 1: Connect to existing Chrome (Port 9222)
    # ---------------------------------------------------------
    if not headless:
        for i in range(3): # Retry loop in case Chrome is just starting
            try:
                logger.info(f"Strategy 1 (Attempt {i+1}/3): Connecting to existing Chrome on http://localhost:9222 ...")
                browser = await _playwright.chromium.connect_over_cdp("http://localhost:9222", timeout=3000)
                
                if browser.contexts:
                    _context = browser.contexts[0]
                else:
                    _context = await browser.new_context()
                    
                if _context.pages:
                    _page = _context.pages[0]
                else:
                    _page = await _context.new_page()
                    
                logger.info("\u2705 SUCCESS: Connected to existing Chrome instance!")
                return _page
            except Exception as e:
                logger.info(f"Strategy 1 attempt {i+1} failed: {e}")
                if i < 2: await asyncio.sleep(1.5)
    
    logger.info("Strategy 1 failed after retries. proceed to fallback.")

    # ---------------------------------------------------------
    # STRATEGY 2: Launch User's REAL Chrome (if closed)
    # ---------------------------------------------------------
    # Try to launch the actual Chrome binary with the real user profile
    try:
        if not headless:
            import os
            local_app_data = os.environ.get('LOCALAPPDATA', '')
            real_user_data = os.path.join(local_app_data, r"Google\Chrome\User Data")
            chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            
            if os.path.exists(real_user_data) and os.path.exists(chrome_exe):
                logger.info("Strategy 2: Attempting to launch REAL Chrome profile...")
                
                # We try to launch it exposing the debugging port, so we can reconnect later
                _context = await _playwright.chromium.launch_persistent_context(
                    user_data_dir=real_user_data,
                    executable_path=chrome_exe,
                    headless=False,
                    viewport={"width": 1280, "height": 800},
                    args=[
                        "--remote-debugging-port=9222", # Enable it for next time!
                        "--disable-blink-features=AutomationControlled"
                    ]
                )
                
                if _context.pages:
                    _page = _context.pages[0]
                else:
                    _page = await _context.new_page()
                    
                logger.info("\u2705 SUCCESS: Launched REAL Chrome profile!")
                return _page
    except Exception as e:
        # This usually fails if Chrome is ALREADY OPEN (SingletonLock)
        logger.info(f"Strategy 2 failed (Profile likely locked/open): {e}")

    # ---------------------------------------------------------
    # STRATEGY 3: Launch dedicated persistent context (Fallback)
    # ---------------------------------------------------------
    # This saves cookies in ~/.companion_browser
    
    try:
        logger.info("Strategy 3: Launching isolated browser profile...")
        _context = await _playwright.chromium.launch_persistent_context(
            user_data_dir=BROWSER_DATA_DIR,
            headless=headless,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",  # Less detectable
            ]
        )
        
        # Get existing page or create new one
        if _context.pages:
            _page = _context.pages[0]
        else:
            _page = await _context.new_page()
        
        logger.info(f"Browser launched with persistent profile at {BROWSER_DATA_DIR}")
        return _page
    except Exception as e:
        logger.error(f"Failed to launch browser: {e}")
        raise


async def close_browser():
    """Close the browser and cleanup."""
    global _browser, _context, _page, _playwright
    
    if _context:
        await _context.close()
        _context = None
        _page = None
    if _browser:
        await _browser.close()
        _browser = None
    if _playwright:
        await _playwright.stop()
        _playwright = None
    logger.info("Browser closed")


async def goto(url: str, wait: bool = True) -> str:
    """Navigate to a URL.
    
    Args:
        url: URL to navigate to
        wait: Wait for page to load
        
    Returns:
        Page title or error message
    """
    try:
        page = await _ensure_browser()
        
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        await page.goto(url, wait_until='domcontentloaded' if wait else 'commit')
        title = await page.title()
        logger.info(f"Navigated to: {url} (title: {title})")
        return f"Navigated to {url}. Page title: {title}"
    except Exception as e:
        logger.error(f"Navigation failed: {e}")
        return f"Error navigating to {url}: {str(e)}"


async def click(selector: str, text: Optional[str] = None) -> str:
    """Click an element by selector or text.
    
    Args:
        selector: CSS selector or XPath
        text: Optional text to match (uses text selector)
        
    Returns:
        Success message or error
    """
    try:
        page = await _ensure_browser()
        
        if text:
            # Click by text content
            await page.click(f'text="{text}"', timeout=5000)
            logger.info(f"Clicked element with text: {text}")
            return f"Clicked element with text: {text}"
        else:
            await page.click(selector, timeout=5000)
            logger.info(f"Clicked element: {selector}")
            return f"Clicked element: {selector}"
    except Exception as e:
        logger.error(f"Click failed: {e}")
        return f"Error clicking: {str(e)}"


async def type_text(selector: str, text: str, clear: bool = True) -> str:
    """Type text into an input field.
    
    Args:
        selector: CSS selector for input
        text: Text to type
        clear: Clear field before typing
        
    Returns:
        Success message or error
    """
    try:
        page = await _ensure_browser()
        
        if clear:
            await page.fill(selector, text, timeout=5000)
        else:
            await page.type(selector, text, timeout=5000)
            
        logger.info(f"Typed '{text[:20]}...' into {selector}")
        return f"Typed text into {selector}"
    except Exception as e:
        logger.error(f"Type failed: {e}")
        return f"Error typing: {str(e)}"


async def get_text(selector: Optional[str] = None) -> str:
    """Get text content from page or element.
    
    Args:
        selector: Optional CSS selector (gets whole page if None)
        
    Returns:
        Text content (limited to 2000 chars)
    """
    try:
        page = await _ensure_browser()
        
        if selector:
            text = await page.locator(selector).text_content()
        else:
            text = await page.locator('body').inner_text()
        
        text = text.strip() if text else ""
        
        # Limit length to avoid token bloat
        if len(text) > 2000:
            text = text[:2000] + "... (truncated)"
            
        return text
    except Exception as e:
        logger.error(f"Get text failed: {e}")
        return f"Error getting text: {str(e)}"


async def screenshot(path: Optional[str] = None) -> str:
    """Take a screenshot.
    
    Args:
        path: Optional path to save (returns base64 if None)
        
    Returns:
        File path or base64 data
    """
    try:
        page = await _ensure_browser()
        
        if path:
            await page.screenshot(path=path)
            return f"Screenshot saved to: {path}"
        else:
            data = await page.screenshot()
            b64 = base64.b64encode(data).decode('utf-8')
            return f"data:image/png;base64,{b64[:100]}... (truncated)"
    except Exception as e:
        logger.error(f"Screenshot failed: {e}")
        return f"Error taking screenshot: {str(e)}"


async def wait_for(selector: str, timeout: int = 10000) -> str:
    """Wait for an element to appear.
    
    Args:
        selector: CSS selector
        timeout: Timeout in milliseconds
        
    Returns:
        Success message or error
    """
    try:
        page = await _ensure_browser()
        await page.wait_for_selector(selector, timeout=timeout)
        return f"Element found: {selector}"
    except Exception as e:
        logger.error(f"Wait failed: {e}")
        return f"Timeout waiting for: {selector}"


async def press_key(key: str) -> str:
    """Press a keyboard key.
    
    Args:
        key: Key name (Enter, Tab, Escape, etc.)
        
    Returns:
        Success message
    """
    try:
        page = await _ensure_browser()
        await page.keyboard.press(key)
        return f"Pressed key: {key}"
    except Exception as e:
        logger.error(f"Press key failed: {e}")
        return f"Error pressing key: {str(e)}"


# Synchronous wrappers for tool integration
# Synchronous wrappers for tool integration
# Using a dedicated background thread with persistent event loop
# This is CRITICAL for keeping the browser open and the Playwright objects valid across calls
_agent_loop = None
_loop_thread = None

def _start_loop_thread():
    """Worker thread that runs the persistent event loop."""
    global _agent_loop
    import asyncio
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _agent_loop = loop
    
    logger.info("Browser Agent background loop started")
    loop.run_forever()

def _ensure_monitor():
    """Ensure the background loop thread is running."""
    global _loop_thread, _agent_loop
    import threading
    import time
    
    if not _loop_thread or not _loop_thread.is_alive():
        _loop_thread = threading.Thread(target=_start_loop_thread, daemon=True)
        _loop_thread.start()
        
        # Wait for loop to be initialized
        start = time.time()
        while _agent_loop is None:
            if time.time() - start > 5:
                raise RuntimeError("Failed to start browser background loop")
            time.sleep(0.05)

def _run_async(coro):
    """Run async coroutine in the persistent background loop."""
    _ensure_monitor()
    import asyncio
    
    # Submit coroutine to the background loop
    future = asyncio.run_coroutine_threadsafe(coro, _agent_loop)
    return future.result()

def sync_goto(url: str) -> str:
    """Sync wrapper for goto."""
    return _run_async(goto(url))

def sync_click(selector: str, text: Optional[str] = None) -> str:
    """Sync wrapper for click."""
    return _run_async(click(selector, text))

def sync_type(selector: str, text: str) -> str:
    """Sync wrapper for type_text."""
    return _run_async(type_text(selector, text))

def sync_get_text(selector: Optional[str] = None) -> str:
    """Sync wrapper for get_text."""
    return _run_async(get_text(selector))

def sync_screenshot(path: Optional[str] = None) -> str:
    """Sync wrapper for screenshot."""
    return _run_async(screenshot(path))

def sync_press_key(key: str) -> str:
    """Sync wrapper for press_key."""
    return _run_async(press_key(key))

def sync_close() -> str:
    """Sync wrapper for close_browser."""
    _run_async(close_browser())
    return "Browser closed"


# Test function
if __name__ == "__main__":
    async def test():
        await goto("https://example.com")
        print(await get_text("h1"))
        await close_browser()
    
    asyncio.run(test())
