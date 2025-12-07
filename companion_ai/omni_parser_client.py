import requests
import base64
import logging
import time
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class OmniParserClient:
    """
    Client for interacting with a local Microsoft OmniParser inference server.
    Used for SOTA GUI element detection and parsing.
    """
    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url.rstrip('/')
        self.available = False
        self._check_connection()

    def _check_connection(self):
        """Check if the OmniParser server is running."""
        try:
            resp = requests.get(f"{self.base_url}/health", timeout=1)
            if resp.status_code == 200:
                self.available = True
                logger.info("✅ OmniParser server connected.")
            else:
                self.available = False
        except Exception:
            self.available = False
            logger.debug("OmniParser server not detected at startup (normal if not running).")

    def parse_screen(self, image_base64: str) -> Optional[Dict[str, Any]]:
        """
        Send a base64 screenshot to OmniParser and get structured UI elements.
        
        Expected Return Dict:
        {
            "som_image_base64": "...", # Image with Set-of-Mark labels
            "elements": [
                {"id": 1, "type": "button", "content": "Save", "bbox": [100, 100, 200, 150]}
                ...
            ]
        }
        """
        if not self.available:
            # Try one ping before failing
            self._check_connection()
            if not self.available:
                return None

        try:
            start_t = time.time()
            payload = {"base64_image": image_base64}
            
            response = requests.post(
                f"{self.base_url}/parse", 
                json=payload, 
                timeout=15  # GPU processing might take a few seconds
            )
            
            if response.status_code != 200:
                logger.error(f"OmniParser error {response.status_code}: {response.text}")
                return None
                
            data = response.json()
            logger.info(f"OmniParser success in {time.time()-start_t:.2f}s. Found {len(data.get('elements', []))} elements.")
            return data
            
        except Exception as e:
            logger.error(f"Failed to call OmniParser: {e}")
            self.available = False
            return None

# Global instance
omni_client = OmniParserClient()
