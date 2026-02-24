from companion_ai.services import jobs


def test_schedule_add_and_list(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule(
        "Daily summary",
        30,
        "start_background_task",
        {"query": "x"},
        timezone="UTC",
        retry_limit=2,
        retry_backoff_minutes=4,
    )
    rows = jobs.list_schedules()

    assert sid
    picked = next(r for r in rows if r["id"] == sid)
    assert picked["timezone"] == "UTC"
    assert picked["retry_limit"] == 2
    assert picked["retry_backoff_minutes"] == 4
    assert picked["interval_human"].startswith("Every")
    assert picked["next_run_at"]


def test_run_due_schedules_enqueues_job(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_due.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    jobs.add_schedule("Hourly check", 1, "start_background_task", {"description": "check"})

    captured = {"count": 0}

    def fake_add_job(description, tool_name, tool_args):
        captured["count"] += 1
        return "jid"

    monkeypatch.setattr(jobs, "add_job", fake_add_job)
    jobs._run_due_schedules()

    assert captured["count"] >= 1


def test_run_due_schedules_tracks_enqueue_failures(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_retry.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule(
        "Retry check",
        10,
        "start_background_task",
        {"description": "retry"},
        retry_limit=2,
        retry_backoff_minutes=1,
    )

    def fail_add_job(*args, **kwargs):
        raise RuntimeError("queue down")

    monkeypatch.setattr(jobs, "add_job", fail_add_job)
    jobs._run_due_schedules()

    rows = jobs.list_schedules()
    picked = next(r for r in rows if r["id"] == sid)
    assert picked["consecutive_failures"] == 1
    assert "queue down" in (picked.get("last_error") or "")


def test_update_and_delete_schedule(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_edit.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule("Morning check", 15, "start_background_task", {"a": 1})
    updated = jobs.update_schedule(
        sid,
        "Morning check updated",
        30,
        "start_background_task",
        {"a": 2},
        timezone="UTC",
        retry_limit=1,
        retry_backoff_minutes=2,
    )
    assert updated is True

    rows = jobs.list_schedules()
    picked = next(r for r in rows if r["id"] == sid)
    assert picked["description"] == "Morning check updated"
    assert picked["interval_minutes"] == 30

    deleted = jobs.delete_schedule(sid)
    assert deleted is True
    assert not any(r["id"] == sid for r in jobs.list_schedules())


def test_list_schedules_includes_policy_block_metadata(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_policy.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule("Background run", 20, "start_background_task", {"k": 1})

    import companion_ai.tools as tools_module
    monkeypatch.setattr(
        tools_module,
        'evaluate_tool_policy',
        lambda name, mode=None: {
            'allowed': False,
            'reason': 'plugin_denied',
            'message': f"Tool '{name}' blocked by plugin policy",
        },
    )

    rows = jobs.list_schedules()
    picked = next(r for r in rows if r["id"] == sid)

    assert picked['blocked_by_policy'] is True
    assert picked['policy_reason'] == 'plugin_denied'
    assert 'blocked by plugin policy' in (picked.get('policy_message') or '')


def test_list_schedules_parses_tool_args_and_includes_observability(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_observability.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule(
        "Observe schedule",
        45,
        "start_background_task",
        {"query": "health-check"},
        timezone="UTC",
    )

    rows = jobs.list_schedules()
    picked = next(r for r in rows if r["id"] == sid)

    assert isinstance(picked.get('tool_args'), dict)
    assert picked['tool_args'].get('query') == 'health-check'
    assert picked.get('interval_human')
    assert picked.get('next_run_at')


def test_run_schedule_now_enqueues_job_and_resets_failures(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_manual_run.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule(
        "Manual run schedule",
        30,
        "start_background_task",
        {"description": "manual"},
    )

    conn = jobs._get_db()
    cur = conn.cursor()
    cur.execute(
        'UPDATE schedules SET consecutive_failures = 2, last_error = ? WHERE id = ?',
        ("old failure", sid),
    )
    conn.commit()
    conn.close()

    monkeypatch.setattr(jobs, "add_job", lambda *args, **kwargs: "job-manual")
    result = jobs.run_schedule_now(sid)

    assert result["ok"] is True
    assert result["job_id"] == "job-manual"

    rows = jobs.list_schedules()
    picked = next(r for r in rows if r["id"] == sid)
    assert picked["consecutive_failures"] == 0
    assert picked["last_error"] is None
    assert picked.get("last_run_at")


def test_run_schedule_now_failure_increments_failures(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_manual_run_fail.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule(
        "Manual run fail schedule",
        30,
        "start_background_task",
        {"description": "manual fail"},
    )

    def fail_add_job(*args, **kwargs):
        raise RuntimeError("manual queue failure")

    monkeypatch.setattr(jobs, "add_job", fail_add_job)
    result = jobs.run_schedule_now(sid)

    assert result["ok"] is False
    assert "manual queue failure" in (result.get("error") or "")

    rows = jobs.list_schedules()
    picked = next(r for r in rows if r["id"] == sid)
    assert picked["consecutive_failures"] == 1
    assert "manual queue failure" in (picked.get("last_error") or "")


def test_run_schedule_now_policy_denied_updates_failure_state(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_manual_run_policy.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule(
        "Manual run policy schedule",
        30,
        "start_background_task",
        {"description": "policy"},
    )

    import companion_ai.tools as tools_module
    monkeypatch.setattr(
        tools_module,
        'evaluate_tool_policy',
        lambda name, mode=None: {
            'allowed': False,
            'reason': 'plugin_denied',
            'message': f"Tool '{name}' blocked by plugin policy",
        },
    )

    result = jobs.run_schedule_now(sid)

    assert result['ok'] is False
    assert result.get('reason') == 'policy_denied'

    rows = jobs.list_schedules()
    picked = next(r for r in rows if r['id'] == sid)
    assert picked['consecutive_failures'] == 1
    assert 'blocked by plugin policy' in (picked.get('last_error') or '')


def test_run_due_schedules_policy_denied_updates_failure_state(tmp_path, monkeypatch):
    db_path = tmp_path / "jobs_phase3_due_policy.db"
    monkeypatch.setattr(jobs, "DB_PATH", str(db_path))
    jobs.init_db()

    sid = jobs.add_schedule(
        "Due run policy schedule",
        1,
        "start_background_task",
        {"description": "due policy"},
    )

    import companion_ai.tools as tools_module
    monkeypatch.setattr(
        tools_module,
        'evaluate_tool_policy',
        lambda name, mode=None: {
            'allowed': False,
            'reason': 'plugin_denied',
            'message': f"Tool '{name}' blocked by plugin policy",
        },
    )

    jobs._run_due_schedules()

    rows = jobs.list_schedules()
    picked = next(r for r in rows if r['id'] == sid)
    assert picked['consecutive_failures'] == 1
    assert 'blocked by plugin policy' in (picked.get('last_error') or '')

