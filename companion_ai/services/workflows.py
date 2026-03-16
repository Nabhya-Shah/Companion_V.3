import os
import json
import logging
import asyncio
from typing import Dict, List, Optional
from dataclasses import dataclass
from companion_ai.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'workflows')
WORKFLOW_STEP_TIMEOUT_SECONDS = float(os.getenv("WORKFLOW_STEP_TIMEOUT_SECONDS", "15"))

@dataclass
class WorkflowStep:
    id: str
    action: str
    text: str
    output_target: Optional[str] = None

@dataclass
class WorkflowDefinition:
    id: str
    name: str
    description: str
    steps: List[WorkflowStep]

class WorkflowManager:
    """Manages loading and executing multi-step workflows."""
    
    def __init__(self):
        self._workflows: Dict[str, WorkflowDefinition] = {}
        self._workflow_signature: tuple = ()
        self.reload_workflows()
    
    def _compute_signature(self) -> tuple:
        if not os.path.exists(WORKFLOWS_DIR):
            return ()

        signature = []
        for filename in sorted(os.listdir(WORKFLOWS_DIR)):
            if not filename.endswith('.json'):
                continue
            path = os.path.join(WORKFLOWS_DIR, filename)
            try:
                stat = os.stat(path)
            except OSError:
                continue
            signature.append((filename, stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def reload_workflows(self, force: bool = False) -> bool:
        """Loads all workflows from the workflows directory."""
        if not os.path.exists(WORKFLOWS_DIR):
            os.makedirs(WORKFLOWS_DIR, exist_ok=True)
            self._workflows = {}
            self._workflow_signature = ()
            return True

        signature = self._compute_signature()
        if not force and signature == self._workflow_signature:
            return False

        workflows: Dict[str, WorkflowDefinition] = {}

        for filename in os.listdir(WORKFLOWS_DIR):
            if filename.endswith('.json'):
                path = os.path.join(WORKFLOWS_DIR, filename)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        
                    steps = []
                    for step_data in data.get('steps', []):
                        steps.append(WorkflowStep(
                            id=step_data.get('id', f"step_{len(steps)}"),
                            action=step_data.get('action', 'prompt'),
                            text=step_data.get('text', ''),
                            output_target=step_data.get('output_target')
                        ))
                    
                    wf_id = filename[:-5]
                    workflows[wf_id] = WorkflowDefinition(
                        id=wf_id,
                        name=data.get('name', wf_id),
                        description=data.get('description', ''),
                        steps=steps
                    )
                    logger.info(f"Loaded workflow: {wf_id}")
                except Exception as e:
                    logger.error(f"Failed to load workflow {filename}: {e}")

        self._workflows = workflows
        self._workflow_signature = signature
        return True

    def get_workflow(self, workflow_id: str) -> Optional[WorkflowDefinition]:
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> List[Dict]:
        """Return a list of workflow metadata."""
        return [
            {
                "id": wf.id,
                "name": wf.name,
                "description": wf.description,
                "step_count": len(wf.steps)
            }
            for wf in self._workflows.values()
        ]

    async def execute_workflow(self, workflow_id: str, context: Optional[Dict] = None) -> List[Dict]:
        """Execute a workflow step-by-step using the Orchestrator."""
        wf = self.get_workflow(workflow_id)
        if not wf:
            raise ValueError(f"Workflow '{workflow_id}' not found.")
            
        orchestrator = Orchestrator()
        context = context or {}
        
        # We append workflow execution results into the conversation block for context.
        accumulated_context = context.get("recent_conversation", "")
        
        results = []
        for step in wf.steps:
            logger.info(f"Executing workflow {workflow_id} step {step.id}")
            if step.action == "prompt":
                # Ensure the orchestrator acts on behalf of the workflow step
                try:
                    response, metadata = await asyncio.wait_for(
                        orchestrator.process(
                            user_message=step.text,
                            context={"recent_conversation": accumulated_context}
                        ),
                        timeout=WORKFLOW_STEP_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Workflow %s step %s timed out after %.1fs",
                        workflow_id,
                        step.id,
                        WORKFLOW_STEP_TIMEOUT_SECONDS,
                    )
                    response = (
                        "I couldn't complete this workflow step in time, "
                        "but I'll keep moving and give you the best available summary."
                    )
                    metadata = {
                        "error": "workflow_step_timeout",
                        "step_id": step.id,
                        "timeout_seconds": WORKFLOW_STEP_TIMEOUT_SECONDS,
                    }
                except Exception as exc:
                    logger.warning(
                        "Workflow %s step %s failed: %s",
                        workflow_id,
                        step.id,
                        exc,
                    )
                    response = "I hit an issue during this step, but I'll continue with what I have."
                    metadata = {
                        "error": "workflow_step_error",
                        "step_id": step.id,
                        "detail": str(exc),
                    }
                
                # Append to context so the next step is aware
                accumulated_context += f"\nUser (Workflow): {step.text}\nAssistant: {response}\n"
                
                results.append({
                    "step_id": step.id,
                    "response": response,
                    "metadata": metadata,
                    "output_target": step.output_target
                })
            else:
                logger.warning(f"Unknown workflow action type '{step.action}' in step '{step.id}'")
                
        return results

# Singleton instance
_manager = None
def get_manager() -> WorkflowManager:
    global _manager
    if _manager is None:
        _manager = WorkflowManager()
    return _manager