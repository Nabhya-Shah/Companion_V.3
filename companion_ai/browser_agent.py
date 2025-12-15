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
_page = None
_playwright = None


async def _ensure_browser(headless: bool = False):
    """Ensure browser is launched and page is ready."""
    global _browser, _page, _playwright
    
    if _browser and _page:
        return _page
    
    from playwright.async_api import async_playwright
    
    _playwright = await async_playwright().start()
    _browser = await _playwright.chromium.launch(headless=headless)
    _page = await _browser.new_page()
    logger.info(f"Browser launched (headless={headless})")
    return _page


async def close_browser():
    """Close the browser and cleanup."""
    global _browser, _page, _playwright
    
    if _browser:
        await _browser.close()
        _browser = None
        _page = None
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
def sync_goto(url: str) -> str:
    """Sync wrapper for goto."""
    return asyncio.get_event_loop().run_until_complete(goto(url))

def sync_click(selector: str, text: Optional[str] = None) -> str:
    """Sync wrapper for click."""
    return asyncio.get_event_loop().run_until_complete(click(selector, text))

def sync_type(selector: str, text: str) -> str:
    """Sync wrapper for type_text."""
    return asyncio.get_event_loop().run_until_complete(type_text(selector, text))

def sync_get_text(selector: Optional[str] = None) -> str:
    """Sync wrapper for get_text."""
    return asyncio.get_event_loop().run_until_complete(get_text(selector))

def sync_screenshot(path: Optional[str] = None) -> str:
    """Sync wrapper for screenshot."""
    return asyncio.get_event_loop().run_until_complete(screenshot(path))

def sync_press_key(key: str) -> str:
    """Sync wrapper for press_key."""
    return asyncio.get_event_loop().run_until_complete(press_key(key))

def sync_close() -> str:
    """Sync wrapper for close_browser."""
    asyncio.get_event_loop().run_until_complete(close_browser())
    return "Browser closed"


# Test function
if __name__ == "__main__":
    async def test():
        await goto("https://example.com")
        print(await get_text("h1"))
        await close_browser()
    
    asyncio.run(test())
