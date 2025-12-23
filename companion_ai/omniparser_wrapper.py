"""
OmniParser Integration for Computer Use

This module provides UI element detection with bounding boxes
using Microsoft's OmniParser (V2).

Usage:
    from companion_ai.omniparser_wrapper import parse_screen
    
    # Returns list of UI elements with coordinates
    elements, labeled_image = parse_screen()
"""

import sys
import os
import base64
import io
import logging
from typing import List, Dict, Tuple, Optional
from PIL import Image

logger = logging.getLogger(__name__)

# Add OmniParser to path
OMNIPARSER_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "OmniParser")
if OMNIPARSER_PATH not in sys.path:
    sys.path.insert(0, OMNIPARSER_PATH)

# Lazy load OmniParser to avoid import errors on startup
_omniparser = None

def _get_omniparser():
    """Lazy-load OmniParser with required models."""
    global _omniparser
    
    if _omniparser is not None:
        return _omniparser
    
    try:
        from util.omniparser import Omniparser
        
        config = {
            'som_model_path': os.path.join(OMNIPARSER_PATH, 'weights', 'icon_detect', 'model.pt'),
            'caption_model_name': 'florence2',
            'caption_model_path': os.path.join(OMNIPARSER_PATH, 'weights', 'icon_caption_florence'),
            'BOX_TRESHOLD': 0.05,
        }
        
        _omniparser = Omniparser(config)
        logger.info("OmniParser initialized successfully!")
        return _omniparser
        
    except Exception as e:
        logger.error(f"Failed to load OmniParser: {e}")
        return None


def screenshot_to_base64() -> str:
    """Take a screenshot and return as base64 string."""
    import pyautogui
    
    screenshot = pyautogui.screenshot()
    buffer = io.BytesIO()
    screenshot.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode()


def parse_screen() -> Tuple[List[Dict], Optional[Image.Image]]:
    """
    Parse the current screen and detect all UI elements.
    
    Returns:
        elements: List of detected UI elements with:
            - id: Numeric ID (for referencing)
            - label: Description of the element
            - type: icon/text/button
            - coordinates: [x1, y1, x2, y2] normalized (0-1)
        labeled_image: PIL Image with bounding boxes drawn
    """
    parser = _get_omniparser()
    
    if parser is None:
        logger.warning("OmniParser not available, falling back to empty result")
        return [], None
    
    try:
        # Take screenshot
        image_base64 = screenshot_to_base64()
        
        # Parse with OmniParser
        labeled_img_base64, parsed_content = parser.parse(image_base64)
        
        # Decode labeled image
        labeled_image = None
        if labeled_img_base64:
            labeled_image = Image.open(io.BytesIO(base64.b64decode(labeled_img_base64)))
        
        # Parse the content list into structured elements
        elements = []
        if isinstance(parsed_content, list):
            for i, item in enumerate(parsed_content):
                elements.append({
                    'id': i,
                    'label': str(item.get('content', item) if isinstance(item, dict) else item),
                    'coordinates': item.get('coordinates', []) if isinstance(item, dict) else None,
                })
        
        logger.info(f"Parsed {len(elements)} UI elements")
        return elements, labeled_image
        
    except Exception as e:
        logger.error(f"OmniParser failed: {e}")
        return [], None


def format_elements_for_llm(elements: List[Dict]) -> str:
    """Format parsed elements into a text description for the mini-overseer."""
    if not elements:
        return "No UI elements detected on screen."
    
    lines = ["Detected UI elements on screen:"]
    for el in elements:
        coords = el.get('coordinates', 'unknown position')
        lines.append(f"  [{el['id']}] {el['label']}")
    
    return "\n".join(lines)


# Export for easy use
__all__ = ['parse_screen', 'format_elements_for_llm']
