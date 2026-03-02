import os
import json
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass
from companion_ai.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'workflows')

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
        self.reload_workflows()
    
    def reload_workflows(self):
        """Loads all workflows from the workflows directory."""
        self._workflows.clear()
        if not os.path.exists(WORKFLOWS_DIR):
            os.makedirs(WORKFLOWS_DIR, exist_ok=True)
            return

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
                    self._workflows[wf_id] = WorkflowDefinition(
                        id=wf_id,
                        name=data.get('name', wf_id),
                        description=data.get('description', ''),
                        steps=steps
                    )
                    logger.info(f"Loaded workflow: {wf_id}")
                except Exception as e:
                    logger.error(f"Failed to load workflow {filename}: {e}")

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
                response, metadata = await orchestrator.process(
                    user_message=step.text,
                    context={"recent_conversation": accumulated_context}
                )
                
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