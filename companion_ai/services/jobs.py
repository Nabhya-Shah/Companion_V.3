import sqlite3
import threading
import time
import json
import logging
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
import os

# Configure logging
logger = logging.getLogger(__name__)

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
    conn.commit()
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
        logger.warning(f"🧹 Deleted {deleted} stale jobs from previous session")
    conn.commit()
    conn.close()

_cancel_current_flag = False

def cancel_all_jobs():
    """Cancel all pending and running jobs."""
    logger.warning("🛑 Cancelling ALL jobs")
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
    logger.info("👷 Job Worker started")
    global _cancel_current_flag
    
    while not _stop_event.is_set():
        try:
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
                
                logger.info(f"👷 Starting job {job_id}: {description}")
                
                try:
                    # Execute the tool
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
                    
                    # We pass a minimal memory context to avoid token bloat
                    # The background agent doesn't need full conversation history usually
                    memory_context = {'recent_conversation': ''}
                    
                    # Determine model and client
                    client = None
                    model = core_config.TOOLS_MODEL # Default Groq
                    
                    if is_local_available():
                        logger.info("🏠 Using LOCAL LLM (Ollama) for background task")
                        client = OllamaClientWrapper()
                        # Use centralized model config (defaults to qwen2.5-coder:7b for code)
                        model = LocalLLM.DEFAULT_MODELS['code']
                    else:
                        logger.info("☁️ Using CLOUD LLM (Groq) for background task")
                    
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
                    logger.error(f"Job {job_id} failed: {e}")
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
                logger.info(f"👷 Job {job_id} finished: {status}")
                
            else:
                conn.close()
                time.sleep(1) # Wait for new jobs
                
        except Exception as e:
            logger.error(f"Worker loop error: {e}")
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
