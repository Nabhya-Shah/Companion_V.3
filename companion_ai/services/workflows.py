import os
import json
import logging
import asyncio
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

from companion_ai.orchestrator import Orchestrator

logger = logging.getLogger(__name__)

WORKFLOWS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'workflows')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
SKILL_POLICY_PATH = os.path.join(DATA_DIR, 'skills_policy.json')
SKILL_DB_PATH = os.path.join(DATA_DIR, 'skills.db')
WORKFLOW_STEP_TIMEOUT_SECONDS = float(os.getenv("WORKFLOW_STEP_TIMEOUT_SECONDS", "15"))
SKILL_APPROVAL_TTL_SECONDS = int(os.getenv("SKILL_APPROVAL_TTL_SECONDS", "180"))


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
    category: str = 'routine'
    risk_tier: str = 'low'
    requires_approval: bool = False


class WorkflowManager:
    """Manages loading and executing multi-step workflows and skill lifecycle state."""

    def __init__(self):
        self._workflows: Dict[str, WorkflowDefinition] = {}
        self._workflow_signature: tuple = ()
        self._policy_lock = threading.Lock()
        self._approval_lock = threading.Lock()
        self._skill_policy = self._load_skill_policy()
        self._skill_approval_tokens: Dict[str, Dict[str, Any]] = {}
        self._init_skill_db()
        self.reload_workflows()

    def _init_skill_db(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(SKILL_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS skill_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                workflow_name TEXT,
                workspace_id TEXT,
                status TEXT,
                source TEXT,
                summary TEXT,
                metadata_json TEXT,
                error TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
            '''
        )
        cur.execute(
            '''
            CREATE TABLE IF NOT EXISTS skill_memory_candidates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_id TEXT NOT NULL,
                run_id TEXT NOT NULL,
                candidate_text TEXT NOT NULL,
                provenance_json TEXT,
                status TEXT DEFAULT 'staged',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            '''
        )
        conn.commit()
        conn.close()

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

    def _default_skill_policy(self) -> dict:
        return {
            'skills': {},
            'categories': {},
        }

    def _load_skill_policy(self) -> dict:
        os.makedirs(DATA_DIR, exist_ok=True)
        if not os.path.exists(SKILL_POLICY_PATH):
            return self._default_skill_policy()
        try:
            with open(SKILL_POLICY_PATH, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            if not isinstance(raw, dict):
                return self._default_skill_policy()
            policy = self._default_skill_policy()
            if isinstance(raw.get('skills'), dict):
                policy['skills'] = raw.get('skills')
            if isinstance(raw.get('categories'), dict):
                policy['categories'] = raw.get('categories')
            return policy
        except Exception as exc:
            logger.warning(f"Failed to load skills policy ({SKILL_POLICY_PATH}): {exc}")
            return self._default_skill_policy()

    def _save_skill_policy(self) -> None:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(SKILL_POLICY_PATH, 'w', encoding='utf-8') as f:
            json.dump(self._skill_policy, f, ensure_ascii=False, indent=2, sort_keys=True)

    def _normalize_risk_tier(self, raw: str | None) -> str:
        normalized = str(raw or 'low').strip().lower()
        if normalized not in {'low', 'medium', 'high'}:
            return 'medium'
        return normalized

    def _workflow_skill_state(self, wf: WorkflowDefinition) -> dict:
        skill_row = self._skill_policy.get('skills', {}).get(wf.id, {})
        category_row = self._skill_policy.get('categories', {}).get(wf.category, {})

        enabled = bool(skill_row.get('enabled', True))
        category_enabled = bool(category_row.get('enabled', True))
        requires_approval = bool(wf.requires_approval or wf.risk_tier == 'high')

        return {
            'enabled': enabled,
            'category_enabled': category_enabled,
            'can_run': enabled and category_enabled,
            'requires_approval': requires_approval,
            'category': wf.category,
            'risk_tier': wf.risk_tier,
        }

    def list_skills(self) -> List[dict]:
        rows = []
        for wf in self._workflows.values():
            runtime = self._workflow_skill_state(wf)
            rows.append(
                {
                    'id': wf.id,
                    'name': wf.name,
                    'description': wf.description,
                    'step_count': len(wf.steps),
                    'category': wf.category,
                    'risk_tier': wf.risk_tier,
                    'enabled': runtime['enabled'],
                    'category_enabled': runtime['category_enabled'],
                    'can_run': runtime['can_run'],
                    'requires_approval': runtime['requires_approval'],
                }
            )
        return rows

    def set_skill_enabled(self, workflow_id: str, enabled: bool) -> dict:
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        with self._policy_lock:
            row = self._skill_policy.setdefault('skills', {}).setdefault(workflow_id, {})
            row['enabled'] = bool(enabled)
            row['updated_at'] = datetime.utcnow().isoformat()
            self._save_skill_policy()

        wf = self._workflows[workflow_id]
        runtime = self._workflow_skill_state(wf)
        self._append_audit(
            event='skill_toggle',
            workflow_id=workflow_id,
            status='updated',
            metadata={'enabled': bool(enabled)},
            source='manual',
        )
        return {
            'workflow_id': workflow_id,
            'enabled': runtime['enabled'],
            'category_enabled': runtime['category_enabled'],
            'can_run': runtime['can_run'],
        }

    def set_category_enabled(self, category: str, enabled: bool) -> dict:
        cleaned = str(category or '').strip() or 'routine'
        with self._policy_lock:
            row = self._skill_policy.setdefault('categories', {}).setdefault(cleaned, {})
            row['enabled'] = bool(enabled)
            row['updated_at'] = datetime.utcnow().isoformat()
            self._save_skill_policy()
        return {'category': cleaned, 'enabled': bool(enabled)}

    def issue_skill_approval_token(self, workflow_id: str, ttl_seconds: int | None = None) -> str:
        if workflow_id not in self._workflows:
            raise ValueError(f"Workflow '{workflow_id}' not found")

        ttl = max(int(ttl_seconds or SKILL_APPROVAL_TTL_SECONDS), 5)
        token = uuid.uuid4().hex
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        with self._approval_lock:
            self._skill_approval_tokens[token] = {
                'workflow_id': workflow_id,
                'expires_at': expires_at,
                'used': False,
            }
        return token

    def consume_skill_approval_token(self, workflow_id: str, token: str | None) -> bool:
        if not token:
            return False
        now = datetime.utcnow()
        with self._approval_lock:
            row = self._skill_approval_tokens.get(token)
            if not row:
                return False
            if row.get('used'):
                return False
            if row.get('workflow_id') != workflow_id:
                return False
            expires_at = row.get('expires_at')
            if expires_at is None or expires_at <= now:
                self._skill_approval_tokens.pop(token, None)
                return False
            row['used'] = True
        return True

    def can_run_workflow(self, workflow_id: str, approval_token: str | None = None) -> tuple[bool, Optional[str]]:
        wf = self.get_workflow(workflow_id)
        if not wf:
            return False, 'workflow_not_found'

        runtime = self._workflow_skill_state(wf)
        if not runtime['enabled']:
            self._append_audit(
                event='workflow_denied',
                workflow_id=workflow_id,
                status='denied',
                metadata={'reason': 'skill_disabled'},
                source='policy',
            )
            return False, 'skill_disabled'

        if not runtime['category_enabled']:
            self._append_audit(
                event='workflow_denied',
                workflow_id=workflow_id,
                status='denied',
                metadata={'reason': 'category_disabled', 'category': wf.category},
                source='policy',
            )
            return False, 'category_disabled'

        if runtime['requires_approval'] and not self.consume_skill_approval_token(workflow_id, approval_token):
            self._append_audit(
                event='workflow_denied',
                workflow_id=workflow_id,
                status='denied',
                metadata={'reason': 'approval_required'},
                source='policy',
            )
            return False, 'approval_required'

        return True, None

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

                    skill_meta = data.get('skill') if isinstance(data.get('skill'), dict) else {}
                    wf_id = filename[:-5]
                    workflows[wf_id] = WorkflowDefinition(
                        id=wf_id,
                        name=data.get('name', wf_id),
                        description=data.get('description', ''),
                        steps=steps,
                        category=str(skill_meta.get('category') or 'routine').strip() or 'routine',
                        risk_tier=self._normalize_risk_tier(skill_meta.get('risk_tier')),
                        requires_approval=bool(skill_meta.get('requires_approval', False)),
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
                'id': wf.id,
                'name': wf.name,
                'description': wf.description,
                'step_count': len(wf.steps),
                'category': wf.category,
                'risk_tier': wf.risk_tier,
                'requires_approval': bool(wf.requires_approval or wf.risk_tier == 'high'),
                'enabled': self._workflow_skill_state(wf)['enabled'],
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
        accumulated_context = context.get('recent_conversation', '')

        results = []
        for step in wf.steps:
            logger.info(f"Executing workflow {workflow_id} step {step.id}")
            if step.action == 'prompt':
                # Ensure the orchestrator acts on behalf of the workflow step
                try:
                    response, metadata = await asyncio.wait_for(
                        orchestrator.process(
                            user_message=step.text,
                            context={'recent_conversation': accumulated_context}
                        ),
                        timeout=WORKFLOW_STEP_TIMEOUT_SECONDS,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        'Workflow %s step %s timed out after %.1fs',
                        workflow_id,
                        step.id,
                        WORKFLOW_STEP_TIMEOUT_SECONDS,
                    )
                    response = (
                        "I couldn't complete this workflow step in time, "
                        "but I'll keep moving and give you the best available summary."
                    )
                    metadata = {
                        'error': 'workflow_step_timeout',
                        'step_id': step.id,
                        'timeout_seconds': WORKFLOW_STEP_TIMEOUT_SECONDS,
                    }
                except Exception as exc:
                    logger.warning(
                        'Workflow %s step %s failed: %s',
                        workflow_id,
                        step.id,
                        exc,
                    )
                    response = "I hit an issue during this step, but I'll continue with what I have."
                    metadata = {
                        'error': 'workflow_step_error',
                        'step_id': step.id,
                        'detail': str(exc),
                    }

                # Append to context so the next step is aware
                accumulated_context += f"\nUser (Workflow): {step.text}\nAssistant: {response}\n"

                results.append({
                    'step_id': step.id,
                    'response': response,
                    'metadata': metadata,
                    'output_target': step.output_target
                })
            else:
                logger.warning(f"Unknown workflow action type '{step.action}' in step '{step.id}'")

        return results

    def _append_audit(
        self,
        *,
        event: str,
        workflow_id: str,
        status: str,
        metadata: dict | None = None,
        summary: str = '',
        source: str = 'manual',
        workspace_id: str = 'default',
        error: str | None = None,
    ) -> None:
        wf = self.get_workflow(workflow_id)
        wf_name = wf.name if wf else workflow_id
        run_id = uuid.uuid4().hex[:12]
        conn = sqlite3.connect(SKILL_DB_PATH)
        cur = conn.cursor()
        cur.execute(
            '''
            INSERT INTO skill_runs (
                run_id, workflow_id, workflow_name, workspace_id, status,
                source, summary, metadata_json, error, completed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''',
            (
                run_id,
                workflow_id,
                wf_name,
                workspace_id,
                status,
                source,
                (summary or '')[:500],
                json.dumps({'event': event, **(metadata or {})}),
                (error or '')[:500] if error else None,
                datetime.utcnow().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

    def record_workflow_outcome(
        self,
        workflow_id: str,
        *,
        results: list[dict],
        status: str,
        workspace_id: str = 'default',
        source: str = 'manual',
        error: str | None = None,
    ) -> None:
        responses = [str(r.get('response') or '').strip() for r in (results or []) if str(r.get('response') or '').strip()]
        full_text = responses[-1] if responses else (error or status)
        summary = full_text[:280]
        metadata = {
            'result_count': len(results or []),
            'chat_targets': sum(1 for r in (results or []) if r.get('output_target') == 'chat'),
            'recorded_at': datetime.utcnow().isoformat(),
        }

        self._append_audit(
            event='workflow_run',
            workflow_id=workflow_id,
            status=status,
            metadata=metadata,
            summary=summary,
            source=source,
            workspace_id=workspace_id,
            error=error,
        )

        # Post-run learning hooks: continuity + insight + staged memory candidate.
        try:
            from companion_ai.services.continuity import create_snapshot

            create_snapshot(
                summary=f"Skill {workflow_id} {status.lower()}: {summary}"[:300],
                projects=[workflow_id],
                blockers=[error] if (error and status != 'COMPLETED') else [],
                next_steps=[
                    'Review skill output and promote useful candidates'
                ] if status == 'COMPLETED' else ['Investigate failed skill run'],
                open_questions=[],
                metadata={
                    'source': 'skill_run',
                    'workflow_id': workflow_id,
                    'status': status,
                    'workspace_id': workspace_id,
                },
            )
        except Exception as exc:
            logger.debug(f"Continuity hook skipped for workflow {workflow_id}: {exc}")

        try:
            from companion_ai.services.insights import create_insight

            create_insight(
                title=f"Skill run: {workflow_id}",
                body=f"Status: {status}\n\n{full_text[:4000]}".strip(),
                category='skill_run',
                metadata={
                    'workflow_id': workflow_id,
                    'status': status,
                    'workspace_id': workspace_id,
                    'source': source,
                },
            )
        except Exception as exc:
            logger.debug(f"Insight hook skipped for workflow {workflow_id}: {exc}")

        if status == 'COMPLETED' and full_text:
            try:
                run_id = uuid.uuid4().hex[:12]
                conn = sqlite3.connect(SKILL_DB_PATH)
                cur = conn.cursor()
                cur.execute(
                    '''
                    INSERT INTO skill_memory_candidates (workflow_id, run_id, candidate_text, provenance_json, status)
                    VALUES (?, ?, ?, ?, 'staged')
                    ''',
                    (
                        workflow_id,
                        run_id,
                        full_text[:2000],
                        json.dumps({'source': 'workflow', 'workflow_id': workflow_id, 'workspace_id': workspace_id}),
                    ),
                )
                conn.commit()
                conn.close()
            except Exception as exc:
                logger.debug(f"Memory candidate hook skipped for workflow {workflow_id}: {exc}")

    def list_recent_runs(self, limit: int = 20) -> list[dict]:
        conn = sqlite3.connect(SKILL_DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            '''
            SELECT run_id, workflow_id, workflow_name, workspace_id, status, source, summary, metadata_json, error, created_at, completed_at
            FROM skill_runs
            ORDER BY id DESC
            LIMIT ?
            ''',
            (max(int(limit), 1),),
        )
        rows = cur.fetchall()
        conn.close()
        out: list[dict] = []
        for row in rows:
            try:
                metadata = json.loads(row['metadata_json']) if row['metadata_json'] else {}
            except Exception:
                metadata = {}
            out.append(
                {
                    'run_id': row['run_id'],
                    'workflow_id': row['workflow_id'],
                    'workflow_name': row['workflow_name'],
                    'workspace_id': row['workspace_id'],
                    'status': row['status'],
                    'source': row['source'],
                    'summary': row['summary'],
                    'metadata': metadata,
                    'error': row['error'],
                    'created_at': row['created_at'],
                    'completed_at': row['completed_at'],
                }
            )
        return out


# Singleton instance
_manager = None


def get_manager() -> WorkflowManager:
    global _manager
    if _manager is None:
        _manager = WorkflowManager()
    return _manager
