#!/usr/bin/env python3
"""
Trainer Module (Agent0)
-----------------------
Implements a self-evolution loop for the Companion AI.
1. Selects a task from the Curriculum.
2. Executes the task using the ConversationSession (Planner -> Agent).
3. Verifies the result using Independent Vision (Verifier).
4. Saves successful traces for future fine-tuning/context injection.

Usage:
    python companion_ai/trainer.py
"""

import sys
import os
import time
import json
import logging
import datetime
from typing import List, Dict, Any, Optional

# Add root directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from companion_ai.conversation_manager import ConversationSession
from companion_ai.computer_agent import computer_agent
from companion_ai.vision_manager import vision_manager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/logs/trainer.log", encoding='utf-8')
    ]
)
logger = logging.getLogger("Trainer")

# ==================================================================================
# DATA STRUCTURES
# ==================================================================================

class TrainingTask:
    def __init__(self, name: str, prompt: str, success_criteria: str, timeout_seconds: int = 60):
        self.name = name
        self.prompt = prompt
        self.success_criteria = success_criteria # Natural language description for Vision Verifier
        self.timeout_seconds = timeout_seconds

class TrainingResult:
    def __init__(self, task: TrainingTask, success: bool, reasoning: str, duration: float, trace: List[Dict]):
        self.task = task
        self.success = success
        self.reasoning = reasoning
        self.duration = duration
        self.trace = trace
        self.timestamp = datetime.datetime.now().isoformat()

    def to_dict(self):
        return {
            "timestamp": self.timestamp,
            "task_name": self.task.name,
            "prompt": self.task.prompt,
            "success": self.success,
            "reasoning": self.reasoning,
            "duration": self.duration,
            "trace": self.trace
        }

# ==================================================================================
# CURRICULUM
# ==================================================================================

# "Reliable" curriculum using Win+R primitives
BASIC_CURRICULUM = [
    TrainingTask(
        name="Launch Notepad",
        prompt="Launch the Notepad application",
        success_criteria="Is the Notepad application window visible on the screen?",
        timeout_seconds=30
    ),
    TrainingTask(
        name="Launch Calculator",
        prompt="Launch the Calculator app",
        success_criteria="Is the Calculator application window visible on the screen?",
        timeout_seconds=30
    ),
    # A bit more complex: Launch, wait, verify
    TrainingTask(
        name="Launch Steam",
        prompt="Launch Steam",
        success_criteria="Is the Steam application window visible?",
        timeout_seconds=30
    )
]

# ==================================================================================
# TRAINER CLASS
# ==================================================================================

class Trainer:
    def __init__(self):
        self.output_file = "data/training_examples.jsonl"
        self.session_log_dir = "data/training_sessions"
        os.makedirs(self.session_log_dir, exist_ok=True)
        os.makedirs("data", exist_ok=True)
        
        # Ensure Computer Agent is enabled and LIVE
        computer_agent.enabled = True
        computer_agent.safe_mode = False 
        logger.warning("⚠️  TRAINER RUNNING IN LIVE MODE - COMPUTER CONTROL ENABLED ⚠️")

    def run_curriculum(self, curriculum: List[TrainingTask] = BASIC_CURRICULUM):
        """Run through all tasks in the curriculum."""
        logger.info(f"Starting Training Session with {len(curriculum)} tasks.")
        
        for i, task in enumerate(curriculum):
            logger.info(f"\n[{i+1}/{len(curriculum)}] Starting Task: {task.name}")
            try:
                self.run_task(task)
            except Exception as e:
                logger.error(f"Task '{task.name}' crashed: {e}")
                import traceback
                traceback.print_exc()
            
            # Pause between tasks to allow user to reset state if needed?
            # ideally agent cleans up, but for now we wait.
            logger.info("Waiting 5s before next task...")
            time.sleep(5)

    def run_task(self, task: TrainingTask):
        """Execute a single task with verification."""
        # 1. Initialize fresh session
        session = ConversationSession()
        
        # 2. Execute
        start_time = time.time()
        logger.info(f"Request: {task.prompt}")
        
        # We need to capture the 'trace' (tools used). 
        # Currently ConversationSession logs to file, but doesn't return trace efficiently.
        # We'll rely on the result and final state for now.
        
        # 2. Execute with Retries (Self-Correction Loop)
        max_retries = 3
        current_prompt = task.prompt
        
        for attempt in range(max_retries):
            logger.info(f"--- Attempt {attempt + 1}/{max_retries} ---")
            
            # Run the prompt (or feedback)
            start_t = time.time()
            response, _ = session.process_message(current_prompt, [])
            logger.info(f"Agent Response: {response}")
            
            # 3. Verify
            logger.info("Verifying result with Vision...")
            time.sleep(3) # Give UI time to settle
            
            success, reasoning = self.verify_outcome(task.success_criteria)
            
            duration = time.time() - start_t
            
            # 4. Log Result
            result = TrainingResult(
                task=task,
                success=success,
                reasoning=reasoning,
                duration=duration,
                trace=[] 
            )
            self.save_result(result)
            
            if success:
                logger.info(f"✅ SUCCESS: {reasoning}")
                return # Task Complete
            else:
                logger.warning(f"❌ FAIL: {reasoning}")
                # Construct feedback for next turn
                current_prompt = (
                    f"OBSERVATION: The previous action FAILED to achieve the goal ('{task.name}'). "
                    f"Vision Evidence: {reasoning}. "
                    "Please TRY A DIFFERENT STRATEGY (e.g., use keyboard shortcuts like 'win' key, or adjust click location)."
                )
                logger.info(f"Refining Plan -> {current_prompt}")
        
        logger.error(f"Task '{task.name}' FAILED after {max_retries} attempts.")

    def verify_outcome(self, criteria: str) -> tuple[bool, str]:
        """Use Maverick Vision to check if criteria is met."""
        prompt = (
            f"You are a Verification Judge. Look at this screenshot.\n"
            f"Goal Criteria: {criteria}\n"
            "Answer EXACTLY in this JSON format: {\"success\": true/false, \"reasoning\": \"explanation\"}"
        )
        
        try:
            # Capture screen and ask Maverick (Low Res for Efficiency)
            response = vision_manager.analyze_current_screen(prompt, low_detail=True)
            
            # Try to find JSON structure
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                data = json.loads(json_str)
                return data.get("success", False), data.get("reasoning", "No reasoning provided")
            else:
                # Fallback: simple text analysis
                lower = response.lower()
                success = "yes" in lower or "true" in lower or "success" in lower
                return success, f"(Fallback Parse) {response[:100]}"
            
        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return False, f"Verification Error: {e}"

    def save_result(self, result: TrainingResult):
        """Append result to JSONL file."""
        with open(self.output_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(result.to_dict()) + "\n")
        logger.info(f"Result saved to {self.output_file}")

if __name__ == "__main__":
    trainer = Trainer()
    trainer.run_curriculum()
