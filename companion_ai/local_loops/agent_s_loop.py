"""
Agent-S Integration Loop for Computer Use

This module provides a reliable computer use loop using:
- Qwen2.5-VL for vision (seeing screen) and planning
- pyautogui for execution
- Vision verification between steps
- Detailed pipeline logging for debugging
"""

import asyncio
import logging
import io
import base64
import json
import re
import threading
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime

import pyautogui
import requests

logger = logging.getLogger(__name__)

# Try to import Agent-S components
try:
    from gui_agents.cli_app import UIAgent, WindowsACI, run_agent
    AGENT_S_AVAILABLE = True
    logger.info("Agent-S gui_agents components loaded")
except ImportError as e:
    logger.warning(f"Agent-S not fully available: {e}. Using fallback.")
    AGENT_S_AVAILABLE = False


class OllamaGrounder:
    """Grounding engine using Ollama Qwen3-VL to find UI elements."""
    
    def __init__(self, model: str = "gemma3:4b", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self.width = 1920
        self.height = 1080
        
    def ground_element(self, instruction: str, screenshot_base64: str) -> Optional[Dict]:
        """Find coordinates of a UI element on screen."""
        
        prompt = f"""I need to click on: "{instruction}"

The screen is {self.width}x{self.height} pixels.

LAYOUT HINTS:
- Taskbar is at the BOTTOM (Y around {self.height - 25})
- Windows Start button is BOTTOM-LEFT (X around 25, Y around {self.height - 20})
- Browser bookmarks bar is near TOP (Y around 60-90)
- Browser address bar is near TOP (Y around 50-70)
- Buttons on web pages are usually in the CENTER

Look at the screenshot and find where "{instruction}" is located.
Return ONLY JSON with coordinates: {{"x": number, "y": number}}"""

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [screenshot_base64],
                    "stream": False
                },
                timeout=30  # Shorter timeout for grounding
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                logger.info(f"Grounding response: {result[:150]}")
                return self._extract_json_object(result)
                    
        except Exception as e:
            logger.error(f"Grounding failed: {e}")
        
        return None
    
    def _extract_json_object(self, text: str) -> Optional[Dict]:
        """Extract JSON object from text."""
        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass
        
        # Extract from code block
        if "```" in text:
            for part in text.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("{"):
                    try:
                        return json.loads(part.split("}")[0] + "}")
                    except:
                        pass
        
        # Regex extract
        match = re.search(r'\{[^}]+\}', text)
        if match:
            try:
                return json.loads(match.group())
            except:
                pass
        
        return None


class OCRGrounder:
    """Grounding engine using Tesseract OCR - FAST and ACCURATE for text-based UI elements."""
    
    def __init__(self):
        try:
            import pytesseract
            # Set Tesseract path for Windows
            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
            self.pytesseract = pytesseract
            self.available = True
            logger.info("OCRGrounder initialized with Tesseract")
        except ImportError:
            self.available = False
            logger.warning("pytesseract not available")
    
    def ground_element(self, instruction: str, screenshot_base64: str) -> Optional[Dict]:
        """Find coordinates of text on screen using OCR."""
        if not self.available:
            return None
        
        try:
            # Decode screenshot
            from PIL import Image
            import io
            import base64
            
            img_data = base64.b64decode(screenshot_base64)
            img = Image.open(io.BytesIO(img_data))
            
            # Get OCR data with bounding boxes
            data = self.pytesseract.image_to_data(img, output_type=self.pytesseract.Output.DICT)
            
            # Search for the target text (case-insensitive, partial match)
            search_terms = instruction.lower().split()
            best_match = None
            best_score = 0
            
            for i, text in enumerate(data['text']):
                if not text.strip():
                    continue
                
                text_lower = text.lower()
                
                # Check if any search term matches
                for term in search_terms:
                    if term in text_lower or text_lower in term:
                        # Calculate center of bounding box
                        x = data['left'][i] + data['width'][i] // 2
                        y = data['top'][i] + data['height'][i] // 2
                        
                        # Score based on match quality
                        score = len(term) if term in text_lower else len(text_lower)
                        if score > best_score:
                            best_score = score
                            best_match = {"x": x, "y": y, "found": text}
            
            if best_match:
                logger.info(f"OCR found '{best_match['found']}' at ({best_match['x']}, {best_match['y']})")
                return best_match
            
            logger.warning(f"OCR could not find: {instruction}")
            
        except Exception as e:
            logger.error(f"OCR grounding failed: {e}")
        
        return None


class HybridGrounder:
    """Uses OCR first (fast, accurate) then falls back to VLM (for non-text elements)."""
    
    def __init__(self, vlm_model: str = "gemma3:4b"):
        self.ocr = OCRGrounder()
        self.vlm = OllamaGrounder(model=vlm_model)
    
    def ground_element(self, instruction: str, screenshot_base64: str) -> Optional[Dict]:
        """Try OCR first, then VLM as fallback."""
        
        # Try OCR first (fast!)
        result = self.ocr.ground_element(instruction, screenshot_base64)
        if result:
            return result
        
        # Fall back to VLM (slower but handles non-text elements)
        logger.info("OCR failed, trying VLM...")
        return self.vlm.ground_element(instruction, screenshot_base64)


class AgentSLoop:
    """Computer use loop with vision verification and cancellation support."""
    
    def __init__(
        self, 
        grounding_model: str = "gemma3:4b",
    ):
        # Use HybridGrounder: OCR first (fast!), then VLM fallback
        self.grounder = HybridGrounder(vlm_model=grounding_model)
        self.steps: List[Dict] = []
        self.pipeline_log: List[Dict] = []  # Detailed log for UI
        self._cancel_flag = threading.Event()
        logger.info("AgentSLoop initialized with HybridGrounder (OCR + VLM)")
    
    def cancel(self):
        """Set the cancellation flag to stop execution."""
        self._cancel_flag.set()
        logger.info("AgentSLoop cancellation requested")
    
    def _is_cancelled(self) -> bool:
        """Check if cancellation was requested."""
        return self._cancel_flag.is_set()
    
    def _log_pipeline(self, stage: str, model: str, input_data: str, output_data: str, screenshot_preview: str = None):
        """Log pipeline step for UI visibility."""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "stage": stage,
            "model": model,
            "input": input_data[:500] if input_data else "",
            "output": output_data[:500] if output_data else "",
            "has_screenshot": screenshot_preview is not None
        }
        self.pipeline_log.append(entry)
        logger.info(f"[PIPELINE] {stage}: {model} -> {output_data[:100]}")
    
    def take_screenshot(self) -> str:
        """Take a screenshot and return as base64."""
        screenshot = pyautogui.screenshot()
        buffer = io.BytesIO()
        screenshot.save(buffer, format='PNG')
        return base64.b64encode(buffer.getvalue()).decode()
    
    async def execute_task(self, instruction: str) -> Dict[str, Any]:
        """Execute a computer use task with vision verification."""
        self.steps = []
        self.pipeline_log = []
        self._cancel_flag.clear()
        
        try:
            # Check cancellation
            if self._is_cancelled():
                return {"status": "cancelled", "steps": self.steps, "pipeline": self.pipeline_log}
            
            # Step 1: Take screenshot
            self._add_step("Taking screenshot", "running")
            screenshot = self.take_screenshot()
            self._add_step("Taking screenshot", "completed")
            self._log_pipeline("screenshot", "pyautogui", "capture screen", f"base64 image ({len(screenshot)} chars)", screenshot[:50])
            
            if self._is_cancelled():
                return {"status": "cancelled", "steps": self.steps, "pipeline": self.pipeline_log}
            
            # Step 2: Plan the task
            self._add_step("Planning task", "running")
            self._log_pipeline("planning_start", "gemma3:4b", f"Task: {instruction}", "Waiting for response...")
            
            plan = await self._plan_task(instruction, screenshot)
            
            if self._is_cancelled():
                return {"status": "cancelled", "steps": self.steps, "pipeline": self.pipeline_log}
            
            if not plan:
                self._add_step("Planning task", "failed", "Could not create plan")
                return {"status": "failed", "error": "Planning failed - model returned empty plan", "steps": self.steps, "pipeline": self.pipeline_log}
            
            self._add_step("Planning task", "completed", f"Planned {len(plan)} steps")
            self._log_pipeline("planning_done", "gemma3:4b", f"Task: {instruction}", f"Plan: {json.dumps(plan)[:300]}")
            
            # Step 3: Execute each action
            for i, action in enumerate(plan):
                if self._is_cancelled():
                    return {"status": "cancelled", "steps": self.steps, "pipeline": self.pipeline_log}
                
                action_type = action.get("action", "unknown")
                step_name = f"Step {i+1}: {action_type}"
                self._add_step(step_name, "running")
                self._log_pipeline(f"action_{i+1}", "executor", f"Action: {json.dumps(action)}", "Executing...")
                
                # ALWAYS take a FRESH screenshot before each action!
                # This is critical - the screen changes after each action
                await asyncio.sleep(0.8)  # Wait for UI to settle
                screenshot = self.take_screenshot()
                logger.info(f"Took fresh screenshot before action {i+1}")
                
                success = await self._execute_action(action, screenshot)
                
                if success:
                    self._add_step(step_name, "completed")
                    self._log_pipeline(f"action_{i+1}_done", "executor", f"Action: {json.dumps(action)}", "Success")
                else:
                    self._add_step(step_name, "failed", action.get('error', 'Unknown error'))
                    self._log_pipeline(f"action_{i+1}_failed", "executor", f"Action: {json.dumps(action)}", f"Failed: {action.get('error')}")
            
            return {
                "status": "completed",
                "steps": self.steps,
                "pipeline": self.pipeline_log,
                "instruction": instruction
            }
            
        except Exception as e:
            logger.error(f"Task execution failed: {e}")
            self._log_pipeline("error", "system", str(e), "Task failed")
            return {
                "status": "failed",
                "error": str(e),
                "steps": self.steps,
                "pipeline": self.pipeline_log
            }
    
    async def _plan_task(self, instruction: str, screenshot: str) -> List[Dict]:
        """Use vision model to plan task steps."""
        
        prompt = f"""Look at this Windows screenshot. Plan how to do this task:

TASK: {instruction}

Return a JSON array of steps. Available actions:
- {{"action": "click", "target": "what to click"}}
- {{"action": "type", "text": "text to type"}}
- {{"action": "press", "key": "enter" or "ctrl+t"}}
- {{"action": "wait", "seconds": 2}}

RULES:
1. Look at what's visible NOW
2. For bookmarks - use click with bookmark name
3. For buttons - use click with button text
4. After page loads - add wait
5. One action per step

Example for clicking bookmark: [{{"action": "click", "target": "BROMCOM bookmark"}}]

Return ONLY a JSON array:"""

        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "gemma3:4b",
                    "prompt": prompt,
                    "images": [screenshot],
                    "stream": False
                },
                timeout=60  # Reduced from 120
            )
            
            if response.status_code == 200:
                result = response.json().get("response", "")
                logger.info(f"Planner response: {result[:300]}")
                self._log_pipeline("planner_response", "gemma3:4b", prompt[:200], result[:300])
                
                parsed = self._extract_json_array(result)
                if parsed:
                    return parsed
                
                logger.error(f"Could not parse plan: {result}")
                return []
            else:
                logger.error(f"Planner API error: {response.status_code}")
                return []
                
        except requests.exceptions.Timeout:
            logger.error("Planner timed out (60s)")
            self._log_pipeline("planner_timeout", "gemma3:4b", prompt[:200], "TIMEOUT after 60s")
            return []
        except Exception as e:
            logger.error(f"Planning failed: {e}")
            return []
    
    def _extract_json_array(self, text: str) -> Optional[List]:
        """Extract JSON array from text."""
        
        # Direct parse
        try:
            parsed = json.loads(text.strip())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass
        
        # From code block
        if "```" in text:
            for part in text.split("```"):
                part = part.strip()
                if part.startswith("json"):
                    part = part[4:].strip()
                if part.startswith("["):
                    try:
                        # Find balanced brackets
                        count = 0
                        for i, c in enumerate(part):
                            if c == '[': count += 1
                            elif c == ']': 
                                count -= 1
                                if count == 0:
                                    return json.loads(part[:i+1])
                    except:
                        pass
        
        # Find array in text
        start = text.find('[')
        if start >= 0:
            count = 0
            for i, c in enumerate(text[start:]):
                if c == '[': count += 1
                elif c == ']':
                    count -= 1
                    if count == 0:
                        try:
                            return json.loads(text[start:start+i+1])
                        except:
                            pass
        
        return None
    
    async def _execute_action(self, action: Dict, screenshot: str) -> bool:
        """Execute a single action."""
        action_type = action.get("action", "").lower()
        
        try:
            if action_type == "click":
                target = action.get("target", "")
                logger.info(f"Clicking: {target}")
                self._log_pipeline("grounding", "gemma3:4b", f"Find: {target}", "Searching...")
                
                coords = self.grounder.ground_element(target, screenshot)
                if coords and "x" in coords and "y" in coords:
                    x, y = int(coords["x"]), int(coords["y"])
                    logger.info(f"Found at ({x}, {y})")
                    self._log_pipeline("grounding_done", "gemma3:4b", f"Find: {target}", f"Found at ({x}, {y})")
                    pyautogui.click(x, y)
                    return True
                else:
                    action["error"] = f"Could not find: {target}"
                    self._log_pipeline("grounding_failed", "gemma3:4b", f"Find: {target}", "NOT FOUND")
                    return False
                    
            elif action_type == "type":
                text = action.get("text", "")
                logger.info(f"Typing: {text}")
                pyautogui.write(text, interval=0.02)
                return True
                
            elif action_type == "press":
                key = action.get("key", "")
                logger.info(f"Pressing: {key}")
                if "+" in key:
                    pyautogui.hotkey(*key.lower().split("+"))
                else:
                    pyautogui.press(key.lower())
                return True
                
            elif action_type == "wait":
                seconds = float(action.get("seconds", 1))
                logger.info(f"Waiting {seconds}s")
                await asyncio.sleep(seconds)
                return True
                
            else:
                action["error"] = f"Unknown action: {action_type}"
                return False
                
        except Exception as e:
            action["error"] = str(e)
            logger.error(f"Action failed: {e}")
            return False
    
    def _add_step(self, name: str, status: str, result: str = ""):
        """Add or update a step."""
        for step in self.steps:
            if step["name"] == name:
                step["status"] = status
                step["result"] = result
                return
        self.steps.append({
            "name": name,
            "status": status,
            "result": result,
            "timestamp": datetime.now().isoformat()
        })


# Test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop = AgentSLoop()
    result = asyncio.run(loop.execute_task("Open notepad"))
    print("Result:", result)
    print("Pipeline log:", loop.pipeline_log)
