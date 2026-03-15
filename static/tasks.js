// ============================================
// Companion AI — Tasks, Schedules, Workflows, Approvals, Plan Tracker
// ============================================
import { bus, state, authHeaders, setApiToken, escapeHtml, formatTime, scrollToBottom, skeletonCards } from './utils.js';

// ---- DOM refs ----
const tasksList = document.getElementById('tasksList');
const tasksEmpty = document.getElementById('tasksEmpty');
const taskCountBadge = document.getElementById('taskCountBadge');

// ---- State ----
let lastTasksSig = '';
let schedulesById = {};
let workflowsById = {};
let tasksInterval = null;
const _shownApprovalIds = new Set();
const _activePlanEls = {};

// ---- Tasks ----
export async function loadTasks() {
  // Show skeletons while loading
  if (tasksList) { tasksList.style.display = 'flex'; tasksList.innerHTML = skeletonCards(2); }
  const routinesList = document.getElementById('routinesList');
  if (routinesList) routinesList.innerHTML = skeletonCards(2);

  try {
    const [tasksResponse, schedulesResponse, workflowsResponse] = await Promise.all([
      fetch('/api/tasks', { headers: authHeaders() }),
      fetch('/api/schedules', { headers: authHeaders() }),
      fetch('/api/workflows', { headers: authHeaders() })
    ]);
    const data = await tasksResponse.json();
    const scheduleData = await schedulesResponse.json();
    const workflowsData = await workflowsResponse.json();

    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    const schedules = Array.isArray(scheduleData.schedules) ? scheduleData.schedules : [];
    const workflows = Array.isArray(workflowsData.workflows) ? workflowsData.workflows : [];

    renderWorkflows(workflows);

    if (tasks.length > 0 || schedules.length > 0) {
      if (tasksEmpty) tasksEmpty.style.display = 'none';
      if (tasksList) tasksList.style.display = 'flex';

      const currentSig = JSON.stringify({
        tasks: tasks.map(t => ({ id: t.id, state: t.state, desc: t.description })),
        schedules: schedules.map(s => ({ id: s.id, enabled: !!s.enabled, desc: s.description, interval_minutes: s.interval_minutes, blocked_by_policy: !!s.blocked_by_policy }))
      });

      const expandedIds = [...document.querySelectorAll('.task-card.expanded[data-kind="task"]')]
        .map(el => el.dataset.taskId);

      if (currentSig !== lastTasksSig) {
        lastTasksSig = currentSig;
        renderTasks(tasks, schedules);

        expandedIds.forEach(id => {
          const card = document.querySelector(`[data-task-id="${id}"][data-kind="task"]`);
          if (card) card.classList.add('expanded');
        });
      }

      expandedIds.forEach(id => {
        if (tasks.find(t => t.id === id)) toggleTaskDetails(id, true);
      });

      updateTaskBadge(data.count);
    } else {
      if (tasksEmpty) tasksEmpty.style.display = 'flex';
      if (tasksList) tasksList.style.display = 'none';
      updateTaskBadge(0);
    }
  } catch (error) {
    console.error('Error loading tasks:', error);
  }
}

function updateTaskBadge(count) {
  if (count > 0) {
    taskCountBadge.textContent = count;
    taskCountBadge.style.display = 'flex';
  } else {
    taskCountBadge.style.display = 'none';
  }
}

function renderWorkflows(workflows) {
  const routinesList = document.getElementById('routinesList');
  const routinesEmpty = document.getElementById('routinesEmpty');
  if (!routinesList) return;

  if (!workflows || workflows.length === 0) {
    if (routinesEmpty) routinesEmpty.style.display = 'flex';
    Array.from(routinesList.children).forEach(el => { if (el.id !== 'routinesEmpty') el.remove(); });
    return;
  }

  if (routinesEmpty) routinesEmpty.style.display = 'none';
  workflowsById = {};

  Array.from(routinesList.children).forEach(el => { if (el.id !== 'routinesEmpty') el.remove(); });

  workflows.forEach(wf => {
    workflowsById[wf.id] = wf;

    const card = document.createElement('div');
    card.className = 'task-card';
    card.dataset.kind = 'workflow';
    card.dataset.id = wf.id;

    const main = document.createElement('div');
    main.className = 'task-main';

    const icon = document.createElement('div');
    icon.className = 'task-icon result';
    icon.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>`;

    const info = document.createElement('div');
    info.className = 'task-info';

    const desc = document.createElement('div');
    desc.className = 'task-desc';
    desc.textContent = wf.name || wf.id;

    const meta = document.createElement('div');
    meta.className = 'task-meta';
    meta.textContent = `${wf.step_count} step(s) • ${wf.description || 'Custom routine'}`;

    info.appendChild(desc);
    info.appendChild(meta);

    const actionDiv = document.createElement('div');
    actionDiv.className = 'task-actions workflow-actions';
    actionDiv.style.marginLeft = 'auto';

    const runBtn = document.createElement('button');
    runBtn.className = 'task-cancel-btn';
    runBtn.textContent = 'Run now';
    runBtn.title = 'Run this routine immediately';
    runBtn.onclick = (e) => { e.stopPropagation(); runWorkflowNow(wf.id); };

    actionDiv.appendChild(runBtn);
    main.appendChild(icon);
    main.appendChild(info);
    main.appendChild(actionDiv);
    card.appendChild(main);
    routinesList.appendChild(card);
  });
}

async function runWorkflowNow(workflowId) {
  showToast(`Running routine: ${workflowId}...`, 'info');
  try {
    const res = await fetch(`/api/workflows/${workflowId}/run`, { method: 'POST', headers: authHeaders() });
    if (!res.ok) throw new Error('Run failed');
    const data = await res.json();

    const chatTargetCount = Number(data?.chat_target_count || 0);
    const chatDelivered = Boolean(data?.chat_delivered);

    if (chatTargetCount > 0 && chatDelivered) {
      showToast('Routine complete!', 'success');
    } else if (chatTargetCount > 0 && !chatDelivered) {
      showToast('Routine ran, but chat output was not delivered.', 'warning');
    } else {
      showToast('Routine ran (no chat output target).', 'info');
    }

    loadTasks();
  } catch (err) {
    console.error(err);
    showToast('Failed to run routine.', 'error');
  }
}

function renderTasks(tasks, schedules = []) {
  schedulesById = schedules.reduce((acc, s) => { acc[s.id] = s; return acc; }, {});

  const taskCards = tasks.map(task => `
    <div class="task-card" data-kind="task" data-task-id="${task.id}">
      <div class="task-card-header" onclick="toggleTaskDetails('${task.id}')">
        <div class="task-status-icon ${task.state}">
          ${getTaskIcon(task.state)}
        </div>
        <span class="task-title">${escapeHtml(task.description)}</span>
        ${(task.state === 'running' || task.state === 'pending') ? `
          <button class="task-cancel-btn" onclick="event.stopPropagation(); cancelTask('${task.id}')" title="Cancel task">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="m18 6-12 12M6 6l12 12"/>
            </svg>
          </button>
        ` : ''}
        <svg class="task-expand-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="m6 9 6 6 6-6"/>
        </svg>
      </div>
      <div class="task-timeline" id="timeline-${task.id}"></div>
    </div>
  `).join('');

  const scheduleCards = schedules.map(schedule => `
    <div class="task-card" data-kind="schedule" data-schedule-id="${schedule.id}">
      <div class="task-card-header">
        <div class="task-status-icon ${schedule.enabled ? 'running' : 'failed'}">
          ${schedule.enabled ? '⏱️' : '⏸️'}
        </div>
        <span class="task-title">${escapeHtml(schedule.description || 'Scheduled automation')}</span>
        <button class="task-cancel-btn" onclick="toggleSchedule('${schedule.id}', ${schedule.enabled ? 'false' : 'true'})" title="${schedule.enabled ? 'Pause schedule' : 'Resume schedule'}">
          ${schedule.enabled ? 'Pause' : 'Resume'}
        </button>
        <button class="task-cancel-btn" onclick="runScheduleNow('${schedule.id}')" title="Run schedule now">Run now</button>
        <button class="task-cancel-btn" onclick="editSchedule('${schedule.id}')" title="Edit schedule">Edit</button>
        <button class="task-cancel-btn" onclick="deleteSchedule('${schedule.id}')" title="Delete schedule">Delete</button>
      </div>
      <div class="task-timeline" style="display:block; max-height:none; padding-top:0.5rem;">
        <div class="timeline-step">
          <div class="timeline-dot completed"></div>
          <div class="timeline-content">
            <div class="timeline-description">${escapeHtml(schedule.interval_human || `Every ${Number(schedule.interval_minutes || 0)} minute(s)`)} • ${escapeHtml(schedule.timezone || 'UTC')}</div>
            <div class="timeline-description" style="margin-top: 4px; color: var(--text-secondary, #94a3b8);">Next run: ${escapeHtml(schedule.next_run_at ? formatScheduleTime(schedule.next_run_at) : 'Unknown')}</div>
            ${Number(schedule.consecutive_failures || 0) > 0 ? `<div class="timeline-description" style="color: var(--error, #ef4444); margin-top: 4px;">Failures: ${Number(schedule.consecutive_failures)}${schedule.last_error ? ` • ${escapeHtml(String(schedule.last_error).slice(0, 120))}` : ''}</div>` : ''}
            ${schedule.blocked_by_policy ? `<div class="timeline-description" style="color: var(--warning, #f59e0b); margin-top: 4px;">Policy warning: ${escapeHtml(schedule.policy_message || 'Tool is blocked by current policy')}</div>` : ''}
          </div>
        </div>
      </div>
    </div>
  `).join('');

  tasksList.innerHTML = `${taskCards}${scheduleCards}`;
}

function formatScheduleTime(isoString) {
  try {
    const date = new Date(isoString);
    if (Number.isNaN(date.getTime())) return 'Unknown';
    return date.toLocaleString();
  } catch { return 'Unknown'; }
}

async function toggleSchedule(scheduleId, enabled) {
  try {
    const r = await fetch(`/api/schedules/${scheduleId}/toggle`, {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ enabled })
    });
    const data = await r.json();
    if (!r.ok) { showToast(data.error || 'Failed to update schedule', 'error'); return; }
    showToast(enabled ? 'Schedule resumed' : 'Schedule paused', 'success');
    loadTasks();
  } catch (e) {
    console.error('Error toggling schedule:', e);
    showToast('Failed to update schedule', 'error');
  }
}

async function runScheduleNow(scheduleId) {
  try {
    const r = await fetch(`/api/schedules/${scheduleId}/run`, { method: 'POST', headers: authHeaders() });
    const data = await r.json();
    if (!r.ok) { showToast(data.error || 'Failed to run schedule', 'error'); return; }
    showToast(data.job_id ? `Schedule started (job ${data.job_id})` : 'Schedule started', 'success');
    loadTasks();
  } catch (e) {
    console.error('Error running schedule now:', e);
    showToast('Failed to run schedule', 'error');
  }
}

async function editSchedule(scheduleId) {
  const schedule = schedulesById[scheduleId];
  if (!schedule) { showToast('Schedule not found', 'error'); return; }

  const form = await openScheduleForm({
    title: 'Edit Schedule',
    submitLabel: 'Save',
    description: schedule.description || '',
    cadence: minutesToCadence(Number(schedule.interval_minutes || 15)),
  });
  if (!form) return;

  const intervalMinutes = cadenceToMinutes(form.cadence);

  try {
    const r = await fetch(`/api/schedules/${scheduleId}`, {
      method: 'PUT', headers: authHeaders(),
      body: JSON.stringify({
        description: form.description, interval_minutes: intervalMinutes,
        tool_name: schedule.tool_name || 'start_background_task',
        tool_args: schedule.tool_args || {},
        timezone: schedule.timezone || 'UTC',
        retry_limit: Number(schedule.retry_limit || 0),
        retry_backoff_minutes: Number(schedule.retry_backoff_minutes || 1),
      })
    });
    const data = await r.json();
    if (!r.ok) { showToast(data.error || 'Failed to update schedule', 'error'); return; }
    showToast('Schedule updated', 'success');
    loadTasks();
  } catch (e) {
    console.error('Error updating schedule:', e);
    showToast('Failed to update schedule', 'error');
  }
}

async function deleteSchedule(scheduleId) {
  const schedule = schedulesById[scheduleId];
  if (!schedule) { showToast('Schedule not found', 'error'); return; }
  if (!confirm(`Delete schedule: ${schedule.description || scheduleId}?`)) return;

  try {
    const r = await fetch(`/api/schedules/${scheduleId}`, { method: 'DELETE', headers: authHeaders() });
    const data = await r.json();
    if (!r.ok) { showToast(data.error || 'Failed to delete schedule', 'error'); return; }
    showToast('Schedule deleted', 'success');
    loadTasks();
  } catch (e) {
    console.error('Error deleting schedule:', e);
    showToast('Failed to delete schedule', 'error');
  }
}

export async function createSchedule() {
  const form = await openScheduleForm({
    title: 'Create Schedule',
    submitLabel: 'Create',
    description: 'Recurring background task',
    cadence: '30m',
  });
  if (!form) return;

  try {
    const r = await fetch('/api/schedules', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({
        description: form.description,
        cadence: form.cadence,
        tool_name: 'start_background_task',
        tool_args: { description: form.description }
      })
    });
    const data = await r.json();
    if (!r.ok) { showToast(data.error || 'Failed to create schedule', 'error'); return; }
    showToast('Schedule created', 'success');
    await loadTasks();
  } catch (e) {
    console.error('Error creating schedule:', e);
    showToast('Failed to create schedule', 'error');
  }
}

function cadenceToMinutes(cadence) {
  const m = String(cadence || '').trim().toLowerCase().match(/^(\d+)([mhd])$/);
  if (!m) return NaN;
  const n = Number(m[1]);
  const unit = m[2];
  if (!Number.isFinite(n) || n <= 0) return NaN;
  if (unit === 'm') return n;
  if (unit === 'h') return n * 60;
  return n * 1440;
}

function minutesToCadence(minutes) {
  const m = Number(minutes);
  if (!Number.isFinite(m) || m <= 0) return '30m';
  if (m % 1440 === 0) return `${m / 1440}d`;
  if (m % 60 === 0) return `${m / 60}h`;
  return `${m}m`;
}

function openScheduleForm({ title, submitLabel, description, cadence }) {
  return new Promise((resolve) => {
    const existing = document.getElementById('scheduleModalOverlay');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'scheduleModalOverlay';
    overlay.className = 'approval-overlay';
    overlay.innerHTML = `
      <div class="approval-modal schedule-modal" role="dialog" aria-modal="true" aria-labelledby="scheduleModalTitle">
        <div class="approval-header" id="scheduleModalTitle">${escapeHtml(title)}</div>
        <div class="approval-body schedule-modal-body">
          <label class="schedule-label" for="scheduleDescriptionInput">Description</label>
          <input id="scheduleDescriptionInput" class="schedule-input" type="text" maxlength="160" value="${escapeHtml(description || '')}" />
          <label class="schedule-label" for="scheduleCadenceInput">Cadence</label>
          <input id="scheduleCadenceInput" class="schedule-input" type="text" maxlength="16" value="${escapeHtml(cadence || '30m')}" placeholder="15m, 1h, 1d" />
          <div class="schedule-hint">Use cadence like 15m, 1h, or 1d.</div>
        </div>
        <div class="approval-actions">
          <button id="scheduleCancelBtn" class="approval-btn deny" type="button">Cancel</button>
          <button id="scheduleSaveBtn" class="approval-btn approve" type="button">${escapeHtml(submitLabel)}</button>
        </div>
      </div>
    `;
    document.body.appendChild(overlay);

    const descriptionInput = document.getElementById('scheduleDescriptionInput');
    const cadenceInput = document.getElementById('scheduleCadenceInput');
    const cancelBtn = document.getElementById('scheduleCancelBtn');
    const saveBtn = document.getElementById('scheduleSaveBtn');

    const closeWith = (result) => {
      overlay.remove();
      resolve(result);
    };

    cancelBtn?.addEventListener('click', () => closeWith(null));
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) closeWith(null);
    });

    const submit = () => {
      const trimmedDescription = String(descriptionInput?.value || '').trim();
      const trimmedCadence = String(cadenceInput?.value || '').trim().toLowerCase();

      if (!trimmedDescription) {
        showToast('Description is required', 'error');
        descriptionInput?.focus();
        return;
      }
      if (!/^\d+[mhd]$/.test(trimmedCadence)) {
        showToast('Cadence must look like 15m, 1h, or 1d', 'error');
        cadenceInput?.focus();
        return;
      }
      const minutes = cadenceToMinutes(trimmedCadence);
      if (!Number.isFinite(minutes) || minutes <= 0) {
        showToast('Cadence must be a positive interval', 'error');
        cadenceInput?.focus();
        return;
      }

      closeWith({ description: trimmedDescription, cadence: trimmedCadence });
    };

    saveBtn?.addEventListener('click', submit);
    cadenceInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submit();
    });
    descriptionInput?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') submit();
    });

    setTimeout(() => descriptionInput?.focus(), 0);
  });
}

async function cancelTask(taskId) {
  try {
    const r = await fetch(`/api/tasks/${taskId}/cancel`, { method: 'POST', headers: authHeaders() });
    const data = await r.json();
    if (data.status === 'success') { showToast('Task cancelled', 'success'); loadTasks(); }
    else { showToast(data.error || 'Failed to cancel task', 'error'); }
  } catch (e) {
    console.error('Error cancelling task:', e);
    showToast('Failed to cancel task', 'error');
  }
}

function getTaskIcon(s) {
  switch (s) {
    case 'running': return '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>';
    case 'completed': return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 12 2 2 4-4"/></svg>';
    case 'failed': return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m18 6-12 12M6 6l12 12"/></svg>';
    default: return '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="4"/></svg>';
  }
}

async function toggleTaskDetails(taskId, forceLoad = false) {
  const card = document.querySelector(`[data-task-id="${taskId}"]`);
  const timeline = document.getElementById(`timeline-${taskId}`);

  if (!forceLoad && card.classList.contains('expanded')) { card.classList.remove('expanded'); return; }
  card.classList.add('expanded');

  try {
    const r = await fetch(`/api/tasks/${taskId}`, { headers: authHeaders() });
    const data = await r.json();
    if (data.data && data.data.timeline) {
      timeline.innerHTML = data.data.timeline.map(step => `
        <div class="timeline-step">
          <div class="timeline-dot ${step.status}"></div>
          <div class="timeline-content">
            <div class="timeline-description">${escapeHtml(step.description)}</div>
            ${step.started ? `<div class="timeline-time">${formatTime(step.started)}</div>` : ''}
          </div>
        </div>
      `).join('');
    }
  } catch (e) {
    console.error('Error loading task timeline:', e);
    timeline.innerHTML = '<div class="timeline-step"><div class="timeline-description">Failed to load timeline</div></div>';
  }
}

export function startTasksPolling() {
  if (!tasksInterval) tasksInterval = setInterval(loadTasks, 5000);
}

export function stopTasksPolling() {
  if (tasksInterval) { clearInterval(tasksInterval); tasksInterval = null; }
}

// ---- Approval UI ----
export function handleApprovalRequests(approvals) {
  if (!Array.isArray(approvals)) return;
  for (const req of approvals) {
    if (_shownApprovalIds.has(req.id)) continue;
    _shownApprovalIds.add(req.id);
    showApprovalModal(req);
  }
}

function showApprovalModal(req) {
  const existingEl = document.getElementById(`approval-${req.id}`);
  if (existingEl) existingEl.remove();

  const overlay = document.createElement('div');
  overlay.id = `approval-${req.id}`;
  overlay.className = 'approval-overlay';
  overlay.innerHTML = `
    <div class="approval-modal">
      <div class="approval-header">Action Approval Required</div>
      <div class="approval-body">
        <p>The AI wants to execute:</p>
        <div class="approval-tool-name">${escapeHtml(req.tool)}</div>
        <div class="approval-args">${escapeHtml(req.args_summary || '')}</div>
      </div>
      <div class="approval-actions">
        <button class="approval-btn approve" onclick="resolveApproval('${req.id}', 'approve')">Approve</button>
        <button class="approval-btn deny" onclick="resolveApproval('${req.id}', 'deny')">Deny</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);
}

async function resolveApproval(requestId, decision) {
  try {
    const res = await fetch(`/api/approvals/${requestId}`, {
      method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision })
    });
    if (!res.ok) throw new Error('Failed to resolve');
    showToast(`Tool ${decision === 'approve' ? 'approved' : 'denied'}`, decision === 'approve' ? 'success' : 'info');
  } catch (err) {
    console.error(err);
    showToast('Failed to resolve approval', 'error');
  }
  const el = document.getElementById(`approval-${requestId}`);
  if (el) el.remove();
  _shownApprovalIds.delete(requestId);
}

// ---- Plan Progress Tracker ----
export function handlePlanEvent(eventType, planId, data) {
  if (eventType === 'plan.created') renderPlanTracker(planId, data);
  else if (eventType === 'step.updated') updatePlanStep(planId, data);
  else if (eventType === 'plan.completed') completePlanTracker(planId, data);
}

function renderPlanTracker(planId, planData) {
  if (_activePlanEls[planId]) return;

  const wrapper = document.createElement('div');
  wrapper.className = 'message-wrapper';

  const tracker = document.createElement('div');
  tracker.className = 'plan-tracker';
  tracker.id = `plan-${planId}`;

  const header = document.createElement('div');
  header.className = 'plan-tracker-header';
  header.innerHTML = `<span class="plan-icon">📋</span> Working on it...`;

  const stepsList = document.createElement('div');
  stepsList.className = 'plan-steps-list';

  for (const step of (planData.steps || [])) {
    const stepEl = document.createElement('div');
    stepEl.className = `plan-step status-${step.status}`;
    stepEl.id = `plan-${planId}-${step.id}`;
    stepEl.innerHTML = `
      <span class="plan-step-icon">${stepStatusIcon(step.status)}</span>
      <span class="plan-step-desc">${escapeHtml(step.description)}</span>
    `;
    stepsList.appendChild(stepEl);
  }

  tracker.appendChild(header);
  tracker.appendChild(stepsList);
  wrapper.appendChild(tracker);

  const chatPane = document.getElementById('chatPane');
  if (chatPane) { chatPane.appendChild(wrapper); scrollToBottom(); }

  _activePlanEls[planId] = tracker;
}

function updatePlanStep(planId, data) {
  const stepEl = document.getElementById(`plan-${planId}-${data.step_id}`);
  if (!stepEl) {
    if (data.plan) renderPlanTracker(planId, data.plan);
    return;
  }
  stepEl.className = `plan-step status-${data.status}`;
  const iconEl = stepEl.querySelector('.plan-step-icon');
  if (iconEl) iconEl.textContent = stepStatusIcon(data.status);
  scrollToBottom();
}

function completePlanTracker(planId, data) {
  const tracker = _activePlanEls[planId];
  if (!tracker) return;
  const header = tracker.querySelector('.plan-tracker-header');
  if (header) header.innerHTML = `<span class="plan-icon">✅</span> Done`;
  tracker.classList.add('plan-completed');
  setTimeout(() => { delete _activePlanEls[planId]; }, 5000);
}

function stepStatusIcon(status) {
  switch (status) {
    case 'queued': return '⏳';
    case 'running': return '⚙️';
    case 'completed': return '✅';
    case 'failed': return '❌';
    case 'skipped': return '⏭️';
    default: return '•';
  }
}

// ---- Expose for inline onclick handlers ----
window.toggleTaskDetails = toggleTaskDetails;
window.cancelTask = cancelTask;
window.toggleSchedule = toggleSchedule;
window.runScheduleNow = runScheduleNow;
window.editSchedule = editSchedule;
window.deleteSchedule = deleteSchedule;
window.resolveApproval = resolveApproval;

// ---- Init ----
export function initTasks() {
  document.getElementById('createScheduleBtn')?.addEventListener('click', createSchedule);
  bus.on('tasks:refresh', loadTasks);
  bus.on('approval:pending', handleApprovalRequests);
  bus.on('plan:event', handlePlanEvent);
}
