import sqlite3
import threading
import time
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import os

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

# Configure logging
logger = logging.getLogger(__name__)


def _safe_log(level: str, message: str) -> None:
    """Best-effort logging for daemon threads during interpreter shutdown."""
    root = logging.getLogger()
    has_open_stream = False
    for handler in root.handlers:
        stream = getattr(handler, 'stream', None)
        if stream is None:
            has_open_stream = True
            break
        try:
            if not stream.closed:
                has_open_stream = True
                break
        except Exception:
            has_open_stream = True
            break

    if not has_open_stream:
        return

    prev_raise = logging.raiseExceptions
    logging.raiseExceptions = False
    try:
        getattr(logger, level)(message)
    except Exception:
        pass
    finally:
        logging.raiseExceptions = prev_raise

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'jobs.db')

# Global worker thread
_worker_thread = None
_stop_event = threading.Event()

def _get_db():
    """Get a database connection."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the jobs database."""
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            description TEXT,
            tool_name TEXT,
            tool_args TEXT,
            status TEXT, -- PENDING, RUNNING, COMPLETED, FAILED
            result TEXT,
            created_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS schedules (
            id TEXT PRIMARY KEY,
            description TEXT NOT NULL,
            interval_minutes INTEGER NOT NULL,
            tool_name TEXT NOT NULL,
            tool_args TEXT,
            enabled INTEGER DEFAULT 1,
            last_run_at TIMESTAMP,
            created_at TIMESTAMP,
            timezone TEXT DEFAULT 'UTC',
            retry_limit INTEGER DEFAULT 0,
            retry_backoff_minutes INTEGER DEFAULT 1,
            consecutive_failures INTEGER DEFAULT 0,
            last_error TEXT
        )
    ''')
    conn.commit()
    _ensure_schedule_schema(conn)
    conn.close()


def _ensure_schedule_schema(conn: sqlite3.Connection | None = None) -> None:
    owns_conn = conn is None
    if owns_conn:
        conn = _get_db()
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(schedules)")
    cols = {row[1] for row in cursor.fetchall()}
    required = {
        'timezone': "ALTER TABLE schedules ADD COLUMN timezone TEXT DEFAULT 'UTC'",
        'retry_limit': "ALTER TABLE schedules ADD COLUMN retry_limit INTEGER DEFAULT 0",
        'retry_backoff_minutes': "ALTER TABLE schedules ADD COLUMN retry_backoff_minutes INTEGER DEFAULT 1",
        'consecutive_failures': "ALTER TABLE schedules ADD COLUMN consecutive_failures INTEGER DEFAULT 0",
        'last_error': "ALTER TABLE schedules ADD COLUMN last_error TEXT",
    }
    changed = False
    for col, ddl in required.items():
        if col not in cols:
            cursor.execute(ddl)
            changed = True
    if changed:
        conn.commit()
    if owns_conn:
        conn.close()

def add_job(description: str, tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Add a new job to the queue."""
    job_id = str(uuid.uuid4())[:8]
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO jobs (id, description, tool_name, tool_args, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (job_id, description, tool_name, json.dumps(tool_args), 'PENDING', datetime.now().isoformat()))
    conn.commit()
    conn.close()
    logger.info(f"Job added: {job_id} - {description}")
    return job_id

def get_active_jobs():
    """Get jobs that are running or recently completed (for UI notifications)."""
    conn = _get_db()
    cursor = conn.cursor()
    # Get PENDING, RUNNING, and COMPLETED/FAILED in the last minute
    # EXCLUDE jobs cancelled on startup to prevent UI spam
    cursor.execute('''
        SELECT * FROM jobs 
        WHERE (status IN ('PENDING', 'RUNNING'))
        OR (
            status IN ('COMPLETED', 'FAILED') 
            AND completed_at > datetime('now', '-1 minute')
            AND result != 'Cancelled on startup'
        )
        ORDER BY created_at DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_job(job_id: str) -> Optional[dict]:
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM jobs WHERE id = ?', (job_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def cancel_job(job_id: str) -> bool:
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE jobs
        SET status = 'FAILED', result = 'Cancelled by user', completed_at = ?
        WHERE id = ? AND status IN ('PENDING', 'RUNNING')
    ''', (datetime.now().isoformat(), job_id))
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def get_tasks_for_ui() -> list[dict]:
    jobs = get_active_jobs()
    out = []
    for job in jobs:
        status = (job.get('status') or '').lower()
        state = 'pending' if status == 'pending' else 'running' if status == 'running' else 'completed' if status == 'completed' else 'failed'
        out.append({
            'id': job.get('id'),
            'description': job.get('description') or 'Background task',
            'state': state,
        })
    return out


def get_task_timeline(task_id: str) -> Optional[list[dict]]:
    job = get_job(task_id)
    if not job:
        return None
    timeline = [
        {
            'description': 'Job queued',
            'status': 'completed',
            'started': job.get('created_at'),
        }
    ]
    if (job.get('status') or '').upper() in {'RUNNING', 'COMPLETED', 'FAILED'}:
        timeline.append({
            'description': 'Job running',
            'status': 'completed' if (job.get('status') or '').upper() != 'PENDING' else 'pending',
            'started': job.get('created_at'),
        })
    if job.get('completed_at'):
        timeline.append({
            'description': f"Job {(job.get('status') or '').lower()}",
            'status': 'completed' if (job.get('status') or '').upper() == 'COMPLETED' else 'failed',
            'started': job.get('completed_at'),
        })
    return timeline


def add_schedule(
    description: str,
    interval_minutes: int,
    tool_name: str,
    tool_args: Dict[str, Any],
    timezone: str = 'UTC',
    retry_limit: int = 0,
    retry_backoff_minutes: int = 1,
) -> str:
    schedule_id = str(uuid.uuid4())[:8]
    conn = _get_db()
    _ensure_schedule_schema(conn)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO schedules (
            id, description, interval_minutes, tool_name, tool_args,
            enabled, created_at, timezone, retry_limit, retry_backoff_minutes,
            consecutive_failures, last_error
        )
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, ?, 0, NULL)
    ''', (
        schedule_id,
        description,
        int(interval_minutes),
        tool_name,
        json.dumps(tool_args or {}),
        datetime.now().isoformat(),
        (timezone or 'UTC').strip() or 'UTC',
        max(int(retry_limit or 0), 0),
        max(int(retry_backoff_minutes or 1), 1),
    ))
    conn.commit()
    conn.close()
    return schedule_id


def _format_interval_human(interval_minutes: int) -> str:
    mins = max(int(interval_minutes or 0), 1)
    if mins % 1440 == 0:
        days = mins // 1440
        return f"Every {days} day" + ("s" if days != 1 else "")
    if mins % 60 == 0:
        hours = mins // 60
        return f"Every {hours} hour" + ("s" if hours != 1 else "")
    return f"Every {mins} minute" + ("s" if mins != 1 else "")


def _next_run_iso(last_run_at: str | None, interval_minutes: int, timezone_name: str) -> str | None:
    try:
        tz = ZoneInfo(timezone_name) if (ZoneInfo and timezone_name) else None
    except Exception:
        tz = None
    base = datetime.now(tz=tz) if tz else datetime.now()
    if last_run_at:
        try:
            parsed = datetime.fromisoformat(last_run_at)
            base = parsed.astimezone(tz) if (tz and parsed.tzinfo) else parsed
        except Exception:
            pass
    from datetime import timedelta
    return (base + timedelta(minutes=max(int(interval_minutes or 1), 1))).isoformat()


def list_schedules() -> list[dict]:
    conn = _get_db()
    _ensure_schedule_schema(conn)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM schedules ORDER BY created_at DESC')
    rows = cursor.fetchall()
    conn.close()
    out = []
    for row in rows:
        item = dict(row)
        raw_args = item.get('tool_args')
        if isinstance(raw_args, str):
            try:
                parsed_args = json.loads(raw_args)
                item['tool_args'] = parsed_args if isinstance(parsed_args, dict) else {}
            except Exception:
                item['tool_args'] = {}
        elif not isinstance(raw_args, dict):
            item['tool_args'] = {}

        item['interval_human'] = _format_interval_human(item.get('interval_minutes') or 1)
        item['next_run_at'] = _next_run_iso(
            item.get('last_run_at'),
            item.get('interval_minutes') or 1,
            item.get('timezone') or 'UTC',
        )
        try:
            from companion_ai.tools import evaluate_tool_policy

            policy = evaluate_tool_policy(item.get('tool_name') or '', mode='restricted')
            item['blocked_by_policy'] = not bool(policy.get('allowed', True))
            item['policy_reason'] = policy.get('reason')
            item['policy_message'] = policy.get('message')
        except Exception:
            item['blocked_by_policy'] = False
            item['policy_reason'] = None
            item['policy_message'] = None
        out.append(item)
    return out


def set_schedule_enabled(schedule_id: str, enabled: bool) -> bool:
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE schedules SET enabled = ? WHERE id = ?', (1 if enabled else 0, schedule_id))
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def update_schedule(
    schedule_id: str,
    description: str,
    interval_minutes: int,
    tool_name: str,
    tool_args: Dict[str, Any],
    timezone: str = 'UTC',
    retry_limit: int = 0,
    retry_backoff_minutes: int = 1,
) -> bool:
    conn = _get_db()
    _ensure_schedule_schema(conn)
    cursor = conn.cursor()
    cursor.execute(
        '''
        UPDATE schedules
        SET description = ?, interval_minutes = ?, tool_name = ?, tool_args = ?,
            timezone = ?, retry_limit = ?, retry_backoff_minutes = ?
        WHERE id = ?
        ''',
        (
            description,
            max(int(interval_minutes or 1), 1),
            tool_name,
            json.dumps(tool_args or {}),
            (timezone or 'UTC').strip() or 'UTC',
            max(int(retry_limit or 0), 0),
            max(int(retry_backoff_minutes or 1), 1),
            schedule_id,
        ),
    )
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def delete_schedule(schedule_id: str) -> bool:
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM schedules WHERE id = ?', (schedule_id,))
    changed = cursor.rowcount > 0
    conn.commit()
    conn.close()
    return changed


def _update_schedule_run_state(schedule_id: str, run_at_iso: str, failures: int, last_error: str | None) -> None:
    conn = _get_db()
    cur = conn.cursor()
    cur.execute(
        'UPDATE schedules SET last_run_at = ?, consecutive_failures = ?, last_error = ? WHERE id = ?',
        (run_at_iso, max(int(failures or 0), 0), last_error, schedule_id),
    )
    conn.commit()
    conn.close()


def _enqueue_schedule_row(row: dict | sqlite3.Row, run_at_iso: str) -> dict:
    schedule_id = row['id']
    failures = max(int(row['consecutive_failures'] or 0), 0)

    try:
        tool_args = json.loads(row['tool_args']) if row['tool_args'] else {}
    except Exception:
        tool_args = {}

    try:
        from companion_ai.tools import evaluate_tool_policy

        policy = evaluate_tool_policy(row['tool_name'], mode='restricted')
        if not bool(policy.get('allowed', True)):
            message = policy.get('message') or f"Tool '{row['tool_name']}' blocked by policy"
            _update_schedule_run_state(schedule_id, run_at_iso, failures + 1, message)
            return {'ok': False, 'error': message, 'reason': 'policy_denied'}
    except Exception:
        pass

    try:
        job_id = add_job(f"[Scheduled] {row['description']}", row['tool_name'], tool_args)
        _update_schedule_run_state(schedule_id, run_at_iso, 0, None)
        return {'ok': True, 'job_id': job_id}
    except Exception as e:
        _update_schedule_run_state(schedule_id, run_at_iso, failures + 1, str(e))
        return {'ok': False, 'error': str(e), 'reason': 'enqueue_failed'}


def run_schedule_now(schedule_id: str) -> dict:
    conn = _get_db()
    _ensure_schedule_schema(conn)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM schedules WHERE id = ?', (schedule_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return {'ok': False, 'error': 'Schedule not found'}

    now_iso = datetime.now().isoformat()
    result = _enqueue_schedule_row(row, now_iso)
    if not result.get('ok'):
        logger.error(f"Manual schedule enqueue failed ({schedule_id}): {result.get('error')}")
    return result


def _run_due_schedules() -> None:
    now = datetime.now()
    conn = _get_db()
    _ensure_schedule_schema(conn)
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM schedules WHERE enabled = 1')
    rows = cursor.fetchall()
    conn.close()

    for row in rows:
        sid = row['id']
        interval = max(int(row['interval_minutes']), 1)
        retry_limit = max(int(row['retry_limit'] or 0), 0)
        retry_backoff = max(int(row['retry_backoff_minutes'] or 1), 1)
        failures = max(int(row['consecutive_failures'] or 0), 0)
        effective_interval = retry_backoff if (failures > 0 and failures <= retry_limit) else interval
        last_run = row['last_run_at']
        should_run = False
        if not last_run:
            should_run = True
        else:
            try:
                last_dt = datetime.fromisoformat(last_run)
                should_run = (now - last_dt).total_seconds() >= (effective_interval * 60)
            except Exception:
                should_run = True
        if not should_run:
            continue

        result = _enqueue_schedule_row(row, now.isoformat())
        if not result.get('ok'):
            reason = result.get('reason')
            if reason == 'policy_denied':
                logger.warning(f"Schedule blocked by policy ({sid}): {result.get('error')}")
            else:
                logger.error(f"Schedule enqueue failed ({sid}): {result.get('error')}")

def cleanup_stale_jobs():
    """Remove any PENDING or RUNNING jobs from previous session.

    We delete these rows to avoid emitting noisy UI notifications on startup.
    """
    conn = _get_db()
    cursor = conn.cursor()
    cursor.execute('''
        DELETE FROM jobs
        WHERE status IN ('PENDING', 'RUNNING')
           OR result = 'Cancelled on startup'
    ''')
    deleted = cursor.rowcount
    if deleted > 0:
        logger.warning(f"Deleted {deleted} stale jobs from previous session")
    conn.commit()
    conn.close()

_cancel_current_flag = False

def cancel_all_jobs():
    """Cancel all pending and running jobs."""
    logger.warning("Cancelling ALL jobs")
    conn = _get_db()
    cursor = conn.cursor()
    
    # Cancel pending
    cursor.execute('''
        UPDATE jobs 
        SET status = 'FAILED', result = 'Cancelled by user', completed_at = ? 
        WHERE status = 'PENDING'
    ''', (datetime.now().isoformat(),))
    
    # Mark running as failed
    cursor.execute('''
        UPDATE jobs 
        SET status = 'FAILED', result = 'Cancelled by user', completed_at = ? 
        WHERE status = 'RUNNING'
    ''', (datetime.now().isoformat(),))
    
    conn.commit()
    conn.close()
    
    # Signal worker to stop current task
    global _cancel_current_flag
    _cancel_current_flag = True

def should_cancel():
    """Check if current job should be cancelled."""
    return _cancel_current_flag

def _worker_loop():
    """Background worker loop to process jobs."""
    _safe_log('info', "Job Worker started")
    global _cancel_current_flag
    
    while not _stop_event.is_set():
        try:
            # Generate proactive digest once per day (best effort, non-blocking).
            try:
                from companion_ai.services.insights import generate_daily_insight_if_due
                generate_daily_insight_if_due()
            except Exception:
                pass

            _run_due_schedules()
            _cancel_current_flag = False # Reset flag for new job
            conn = _get_db()
            cursor = conn.cursor()
            
            # Find next pending job
            cursor.execute('SELECT * FROM jobs WHERE status = "PENDING" ORDER BY created_at ASC LIMIT 1')
            job = cursor.fetchone()
            
            if job:
                job_id = job['id']
                description = job['description']
                tool_name = job['tool_name']
                try:
                    tool_args = json.loads(job['tool_args'])
                except:
                    tool_args = {}
                
                # Mark as RUNNING
                cursor.execute('UPDATE jobs SET status = "RUNNING" WHERE id = ?', (job_id,))
                conn.commit()
                conn.close() # Close connection while working
                
                _safe_log('info', f"Starting job {job_id}: {description}")
                
                try:
                    if tool_name == "run_workflow" and "workflow_id" in tool_args:
                        # Direct workflow execution
                        from companion_ai.services.workflows import get_manager
                        import asyncio
                        
                        manager = get_manager()
                        results = asyncio.run(manager.execute_workflow(tool_args["workflow_id"]))
                        
                        result = f"Workflow '{tool_args['workflow_id']}' completed."
                        status = 'COMPLETED'
                        
                        # Forward chat output if needed
                        for res in results:
                            if res.get("output_target") == "chat":
                                try:
                                    from companion_ai.web.sse import emit_event
                                    emit_event("message", {"role": "assistant", "content": res["response"]})
                                except Exception as e:
                                    logger.error(f"Failed to emit workflow SSE: {e}")
                    else:
                        # Execute the tool via agent loop
                        from companion_ai.llm_interface import generate_response
                        from companion_ai.core.prompts import get_static_system_prompt_safe
                        from companion_ai.local_llm import is_local_available, OllamaClientWrapper, LocalLLM
                        from companion_ai.core import config as core_config
                        
                        # Create a mini-agent loop to solve the task
                        # We use the LLM to decide what tools to use based on the description
                        
                        system_prompt = get_static_system_prompt_safe()
                        system_prompt += "\n\n[BACKGROUND TASK MODE]\nYou are running as a background agent. Your goal is to complete the user's request autonomously. You have full access to tools. Do not ask the user for clarification. If you need to do multiple steps, do them. When finished, provide a final summary."
                        
                        # Use generate_model_response_with_tools directly to ensure tools are executed
                        # generate_response in llm_interface.py calls this internally, but let's be explicit
                        # and ensure we use the right model and context.
                        
                        from companion_ai.llm_interface import generate_model_response_with_tools
                        from companion_ai.tools import execution_mode
                        
                        # We pass a minimal memory context to avoid token bloat
                        # The background agent doesn't need full conversation history usually
                        memory_context = {'recent_conversation': ''}
                        
                        # Determine model and client
                        client = None
                        model = core_config.TOOLS_MODEL # Default Groq
                        
                        if is_local_available():
                            _safe_log('info', "Using LOCAL LLM (Ollama) for background task")
                            client = OllamaClientWrapper()
                            # Use centralized model config (defaults to qwen2.5-coder:7b for code)
                            model = LocalLLM.DEFAULT_MODELS['code']
                        else:
                            _safe_log('info', "Using CLOUD LLM (Groq) for background task")
                        
                        with execution_mode('restricted'):
                            response_text, tool_used, tool_result = generate_model_response_with_tools(
                                user_message=f"Perform this background task: {description}",
                                system_prompt=system_prompt,
                                model=model,
                                conversation_model=model,
                                memory_context=memory_context,
                                stop_callback=should_cancel,
                                client=client
                            )
                        
                        if _cancel_current_flag:
                            result = "Job cancelled by user."
                            status = 'FAILED'
                        else:
                            result = response_text
                            if tool_used:
                                result += f"\n\n(Tools used: {tool_used})"
                            if tool_result:
                                result += f"\n\n(Tool results: {tool_result})"
                            status = 'COMPLETED'
                        
                except Exception as e:
                    _safe_log('error', f"Job {job_id} failed: {e}")
                    result = f"Error: {str(e)}"
                    status = 'FAILED'
                
                # Update status
                conn = _get_db()
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE jobs 
                    SET status = ?, result = ?, completed_at = ? 
                    WHERE id = ?
                ''', (status, result, datetime.now().isoformat(), job_id))
                conn.commit()
                conn.close()
                _safe_log('info', f"Job {job_id} finished: {status}")
                
            else:
                conn.close()
                time.sleep(1) # Wait for new jobs
                
        except Exception as e:
            _safe_log('error', f"Worker loop error: {e}")
            time.sleep(5)

def start_worker():
    """Start the background worker thread."""
    global _worker_thread
    if _worker_thread is None or not _worker_thread.is_alive():
        init_db()
        cleanup_stale_jobs()
        _stop_event.clear()
        _worker_thread = threading.Thread(target=_worker_loop, daemon=True)
        _worker_thread.start()

def stop_worker():
    """Stop the background worker."""
    _stop_event.set()
    if _worker_thread:
        _worker_thread.join(timeout=2)
