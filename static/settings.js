// ============================================
// Companion AI — Settings, Theme, Models, Metrics, Token Stats, Budget
// ============================================
import { bus, state, authHeaders, setApiToken, skeletonLines, skeletonCards, escapeHtml, formatTimeAgo } from './utils.js';

// ---- Theme ----
export function applyTheme(themeName) {
  if (themeName === 'midnight') {
    document.documentElement.removeAttribute('data-theme');
  } else {
    document.documentElement.setAttribute('data-theme', themeName);
  }
  localStorage.setItem('companion_theme', themeName);
  document.querySelectorAll('.theme-swatch').forEach(s => {
    s.classList.toggle('active', s.dataset.theme === themeName);
  });
}

// Restore saved theme on load (runs immediately at import time)
(function () {
  const saved = localStorage.getItem('companion_theme');
  if (saved && saved !== 'midnight') {
    document.documentElement.setAttribute('data-theme', saved);
  }
})();

// ---- Settings modal ----
export function loadSettings() {
  const showTokensToggle = document.getElementById('showTokensToggle');
  if (showTokensToggle) {
    showTokensToggle.checked = state.showTokens;
    showTokensToggle.addEventListener('change', (e) => {
      state.showTokens = e.target.checked;
      localStorage.setItem('companion_show_tokens', state.showTokens);
      bus.emit('history:rerender');
    });
  }

  const themePicker = document.getElementById('themePicker');
  if (themePicker) {
    const savedTheme = localStorage.getItem('companion_theme') || 'midnight';
    document.querySelectorAll('.theme-swatch').forEach(s => {
      s.classList.toggle('active', s.dataset.theme === savedTheme);
      s.addEventListener('click', () => applyTheme(s.dataset.theme));
    });
  }
}

// ---- Models Panel ----
export async function loadModelsPanel(retry = false) {
  const modelCards = document.getElementById('modelCards');
  const featureFlags = document.getElementById('featureFlags');
  if (!modelCards) return;
  modelCards.innerHTML = skeletonCards(2);

  try {
    const r = await fetch('/api/models', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) { setApiToken(tok); return loadModelsPanel(true); }
      return;
    }

    const d = await r.json();
    if (d.error) return;

    modelCards.innerHTML = '';
    if (d.models) {
      [['Primary', d.models.PRIMARY_MODEL], ['Tools', d.models.TOOLS_MODEL],
      ['Vision', d.models.VISION_MODEL], ['Compound', d.models.COMPOUND_MODEL]
      ].forEach(([role, model]) => {
        const shortName = model?.split('/').pop() || 'N/A';
        const card = document.createElement('div');
        card.className = 'model-card';
        card.innerHTML = `<span class="model-role">${role}</span><span class="model-name" title="${model}">${shortName}</span>`;
        modelCards.appendChild(card);
      });
    }

    if (featureFlags) {
      featureFlags.innerHTML = '';
      Object.entries(d.flags || {}).forEach(([k, v]) => {
        const flag = document.createElement('div');
        flag.className = 'feature-flag';
        flag.innerHTML = `<span class="flag-dot ${v ? 'on' : 'off'}"></span><span class="flag-name">${k.replace('ENABLE_', '')}</span>`;
        featureFlags.appendChild(flag);
      });
    }
  } catch (e) {
    console.error('Failed to load models:', e);
  }
}

// ---- Metrics ----
export async function loadMetrics(retry = false) {
  try {
    const r = await fetch('/api/health', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) { setApiToken(tok); return loadMetrics(true); }
      return;
    }

    const data = await r.json();
    const interactions = data.metrics?.total_interactions || 0;
    const toolCalls = data.metrics?.tools?.total_invocations || 0;

    const interactionsEl = document.getElementById('metricInteractions');
    const latencyEl = document.getElementById('metricAvgLatency');
    const toolsEl = document.getElementById('metricToolCalls');

    if (interactionsEl) interactionsEl.textContent = interactions;
    if (toolsEl) toolsEl.textContent = toolCalls;

    let totalLatency = 0, modelCount = 0;
    const models = data.metrics?.models || {};
    Object.values(models).forEach(info => {
      if (info.avg_latency_ms) { totalLatency += info.avg_latency_ms; modelCount++; }
    });
    const avgLatency = modelCount > 0 ? Math.round(totalLatency / modelCount) : 0;
    if (latencyEl) latencyEl.textContent = avgLatency + 'ms';

    const latencyBars = document.getElementById('latencyBars');
    if (latencyBars) {
      const maxLatency = Math.max(...Object.values(models).map(m => m.avg_latency_ms || 0), 1);
      let barsHtml = '';
      Object.entries(models).forEach(([name, info]) => {
        const shortName = name.split('/').pop().substring(0, 12);
        const pct = Math.round((info.avg_latency_ms || 0) / maxLatency * 100);
        const color = pct > 66 ? 'var(--danger)' : pct > 33 ? 'var(--warning)' : 'var(--success)';
        barsHtml += `
          <div class="latency-row">
            <span class="latency-name">${shortName}</span>
            <div class="latency-bar-bg"><div class="latency-bar-fill" style="width: ${pct}%; background: ${color}"></div></div>
            <span class="latency-value">${info.avg_latency_ms || 0}ms</span>
          </div>`;
      });
      latencyBars.innerHTML = barsHtml || '<div class="empty-state">No latency data yet</div>';
    }
  } catch (e) {
    console.error('Failed to load metrics:', e);
  }
}

// ---- Memory Queue Diagnostics ----
function renderQueueItems(items) {
  const queueList = document.getElementById('queueItemsList');
  if (!queueList) return;

  if (!Array.isArray(items) || items.length === 0) {
    queueList.innerHTML = '<div class="memory-empty">Queue is empty</div>';
    return;
  }

  queueList.innerHTML = items.map((item) => {
    const requestId = escapeHtml(String(item.request_id || ''));
    const operation = escapeHtml(String(item.operation || 'unknown'));
    const userScope = escapeHtml(String(item.user_scope || 'default'));
    const preview = escapeHtml(String(item.payload_preview || '{}'));
    const createdAt = item.created_at || '';
    const createdLabel = createdAt ? formatTimeAgo(createdAt) : 'unknown';

    return `
      <div class="queue-item-row">
        <div class="queue-item-top">
          <span class="queue-op">${operation}</span>
          <span class="queue-time">${createdLabel}</span>
        </div>
        <div class="queue-item-meta">scope: ${userScope} • id: ${requestId}</div>
        <pre class="queue-item-preview">${preview}</pre>
      </div>
    `;
  }).join('');
}

function updateQueueControlsFromPayload(payload) {
  const depthEl = document.getElementById('queueDepthValue');
  const replayAtEl = document.getElementById('queueReplayAtValue');
  const cooldownEl = document.getElementById('queueCooldownValue');
  const replayBtn = document.getElementById('queueReplayBtn');

  const queuedCount = Number(payload?.queued_count || 0);
  if (depthEl) depthEl.textContent = String(queuedCount);

  const replayAt = payload?.replay_state?.last_replay_at;
  if (replayAtEl) replayAtEl.textContent = replayAt ? formatTimeAgo(replayAt) : 'never';

  const cooldownSeconds = Number(payload?.replay_state?.cooldown_seconds || 0);
  if (cooldownEl) cooldownEl.textContent = `${Math.max(0, Math.round(cooldownSeconds))}s`;

  if (replayBtn) {
    replayBtn.disabled = queuedCount <= 0;
    replayBtn.title = queuedCount <= 0 ? 'Queue is empty' : 'Replay up to 50 queued memory writes';
  }
}

export async function loadQueueDiagnostics(retry = false) {
  const queueList = document.getElementById('queueItemsList');
  if (!queueList) return;
  queueList.innerHTML = skeletonLines(3);

  try {
    const r = await fetch('/api/memory/write-queue?limit=12', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return loadQueueDiagnostics(true);
      }
      return;
    }

    const payload = await r.json();
    if (!r.ok) {
      throw new Error(payload?.error || `HTTP ${r.status}`);
    }

    updateQueueControlsFromPayload(payload);
    renderQueueItems(payload.items || []);
  } catch (e) {
    console.error('Failed to load queue diagnostics:', e);
    queueList.innerHTML = '<div class="memory-empty">Queue diagnostics unavailable</div>';
  }
}

function renderMigrationReadiness(payload) {
  const summaryEl = document.getElementById('migrationReadinessSummary');
  const guidanceEl = document.getElementById('migrationReadinessActions');
  if (!summaryEl || !guidanceEl) return;

  const readiness = String(payload?.level || 'healthy').toLowerCase();
  const metrics = payload?.metrics || {};
  const queueDepth = Number(metrics.queue_depth || 0);
  const totalWrites = Number(metrics.write_log_rows || 0);
  const failedWrites = Number(metrics.write_failed_count || 0);
  const failurePct = Math.round(Number(metrics.failure_rate || 0) * 100);
  const queuedRate = Math.round(Number(metrics.queued_rate || 0) * 100);
  const committed = Number(metrics.write_committed_count || 0);
  const threshold = payload?.thresholds || {};

  summaryEl.innerHTML = `
    <span class="migration-level ${escapeHtml(readiness)}">${escapeHtml(readiness.replace('_', ' '))}</span>
    <span>queue depth: ${queueDepth}</span>
    <span>writes: ${failedWrites}/${totalWrites} failed (${failurePct}%)</span>
    <span>queued ratio: ${queuedRate}%</span>
    <span>committed: ${committed}</span>
    <span>migration threshold: ${Number(threshold.queue_backlog_critical || 500)}</span>
  `;

  const reasons = Array.isArray(payload?.reasons) ? payload.reasons : [];
  const recommendations = Array.isArray(payload?.recommendations) ? payload.recommendations : [];
  const items = [...reasons, ...recommendations];

  if (items.length === 0) {
    guidanceEl.innerHTML = '<div class="memory-empty">System is operating within healthy bounds.</div>';
    return;
  }

  guidanceEl.innerHTML = items
    .map((line) => `<div class="queue-item-row migration-item">${escapeHtml(String(line || ''))}</div>`)
    .join('');
}

export async function loadMigrationReadiness(retry = false) {
  const summaryEl = document.getElementById('migrationReadinessSummary');
  const guidanceEl = document.getElementById('migrationReadinessActions');
  if (!summaryEl || !guidanceEl) return;

  summaryEl.textContent = 'Loading migration readiness...';
  guidanceEl.innerHTML = '<div class="memory-empty">Assessing queue pressure and write reliability...</div>';

  try {
    const r = await fetch('/api/memory/migration-readiness', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return loadMigrationReadiness(true);
      }
      return;
    }

    const payload = await r.json();
    if (!r.ok) {
      throw new Error(payload?.error || `HTTP ${r.status}`);
    }

    renderMigrationReadiness(payload);
  } catch (e) {
    console.error('Failed to load migration readiness:', e);
    summaryEl.textContent = 'Migration readiness unavailable';
    guidanceEl.innerHTML = '<div class="memory-empty">Could not load migration guidance.</div>';
  }
}

// ---- Local Runtime Controls ----
function renderLocalRuntime(payload) {
  const localModels = payload?.local_models || {};
  const readiness = payload?.readiness || {};

  const summaryEl = document.getElementById('localRuntimeSummary');
  const chipsEl = document.getElementById('localRuntimeChips');
  const runtimeSelect = document.getElementById('localRuntimeSelect');
  const profileSelect = document.getElementById('localProfileSelect');
  const modelsEl = document.getElementById('localRuntimeModels');
  const commandsEl = document.getElementById('localRuntimeCommands');

  if (summaryEl) {
    const available = readiness?.selected_runtime_available ? 'available' : 'unavailable';
    const fallback = readiness?.cloud_fallback_enabled ? 'enabled' : 'disabled';
    summaryEl.textContent = `runtime ${available} • cloud fallback ${fallback}`;
  }

  if (chipsEl) {
    const chips = [
      `runtime ${escapeHtml(String(localModels.runtime || 'hybrid'))}`,
      `profile ${escapeHtml(String(localModels.profile || 'balanced'))}`,
      `chat ${escapeHtml(String(localModels.chat_provider || 'cloud_primary'))}`,
      `memory ${escapeHtml(String(localModels.memory_provider_effective || 'groq'))}`,
      `vllm ${readiness?.vllm_available ? 'up' : 'down'}`,
      `ollama ${readiness?.ollama_available ? 'up' : 'down'}`,
    ];
    chipsEl.innerHTML = chips.map((c) => `<span class="queue-chip">${c}</span>`).join('');
  }

  if (runtimeSelect && Array.isArray(localModels.runtime_choices)) {
    runtimeSelect.innerHTML = localModels.runtime_choices
      .map((r) => `<option value="${escapeHtml(r)}">${escapeHtml(r)}</option>`)
      .join('');
    runtimeSelect.value = localModels.runtime || 'hybrid';
  }

  if (profileSelect && Array.isArray(localModels.profile_choices)) {
    profileSelect.innerHTML = localModels.profile_choices
      .map((p) => `<option value="${escapeHtml(p)}">${escapeHtml(p)}</option>`)
      .join('');
    profileSelect.value = localModels.profile || 'balanced';
  }

  if (modelsEl) {
    const pretty = JSON.stringify(localModels.preferred_models || {}, null, 2);
    modelsEl.textContent = pretty || 'No model map loaded.';
  }

  if (commandsEl) {
    const commands = [];
    if (!readiness?.vllm_available) {
      commands.push('python -m vllm.entrypoints.openai.api_server --model Qwen/Qwen2.5-3B-Instruct --host 0.0.0.0 --port 8000');
    }
    if (!readiness?.ollama_available) {
      commands.push('ollama serve');
    }
    commands.push('./.venv/bin/python scripts/local_model_doctor.py --json');
    commandsEl.textContent = commands.join('\n');
  }
}

export async function loadLocalRuntimePanel(retry = false) {
  try {
    const r = await fetch('/api/local-model/runtime', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return loadLocalRuntimePanel(true);
      }
      return;
    }

    const payload = await r.json();
    if (!r.ok) {
      throw new Error(payload?.error || `HTTP ${r.status}`);
    }
    renderLocalRuntime(payload);
  } catch (e) {
    console.error('Failed to load local runtime panel:', e);
    const summaryEl = document.getElementById('localRuntimeSummary');
    if (summaryEl) summaryEl.textContent = 'Local runtime diagnostics unavailable';
  }
}

async function saveLocalRuntimePanel(retry = false) {
  const runtime = document.getElementById('localRuntimeSelect')?.value || 'hybrid';
  const profile = document.getElementById('localProfileSelect')?.value || 'balanced';
  try {
    const r = await fetch('/api/local-model/runtime', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ runtime, profile }),
    });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return saveLocalRuntimePanel(true);
      }
      return;
    }

    const payload = await r.json();
    if (!r.ok) {
      throw new Error(payload?.error || `HTTP ${r.status}`);
    }

    if (window.showToast) showToast('Local runtime/profile updated', 'success');
    renderLocalRuntime(payload);
  } catch (e) {
    console.error('Failed to save local runtime profile:', e);
    if (window.showToast) showToast('Failed to update local runtime/profile', 'error');
  }
}

async function clearLocalRuntimePanelOverrides(retry = false) {
  try {
    const r = await fetch('/api/local-model/runtime', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ clear_overrides: true }),
    });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return clearLocalRuntimePanelOverrides(true);
      }
      return;
    }

    const payload = await r.json();
    if (!r.ok) {
      throw new Error(payload?.error || `HTTP ${r.status}`);
    }

    if (window.showToast) showToast('Local runtime overrides cleared', 'info');
    renderLocalRuntime(payload);
  } catch (e) {
    console.error('Failed to clear local runtime overrides:', e);
    if (window.showToast) showToast('Failed to clear local runtime overrides', 'error');
  }
}

// ---- Computer-use Activity ----
async function loadComputerUseArtifact(attemptId, retry = false) {
  const previewEl = document.getElementById('computerUseArtifactPreview');
  if (previewEl) previewEl.textContent = `Loading artifact ${attemptId}...`;
  try {
    const r = await fetch(`/api/computer-use/artifacts/${encodeURIComponent(attemptId)}`, { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return loadComputerUseArtifact(attemptId, true);
      }
      return;
    }
    const payload = await r.json();
    if (!r.ok) {
      throw new Error(payload?.error || `HTTP ${r.status}`);
    }
    if (previewEl) previewEl.textContent = JSON.stringify(payload, null, 2);
  } catch (e) {
    console.error('Failed to load computer-use artifact:', e);
    if (previewEl) previewEl.textContent = `Artifact load failed: ${e.message || e}`;
  }
}

function renderComputerUseActivity(activityPayload, configPayload) {
  const listEl = document.getElementById('computerUseActivityList');
  const summaryEl = document.getElementById('computerUsePolicySummary');
  if (!listEl || !summaryEl) return;

  const defaults = configPayload?.local_models?.computer_use_defaults || {};
  summaryEl.textContent = [
    `mode ${defaults.policy_mode || 'approve_only'}`,
    `allowlist ${defaults.allowlist_strategy || 'action_first'}`,
    `replay ${defaults.replay_access || 'operator_only'}`,
    `retention ${defaults.artifact_retention_days ?? '7'}d`,
    `two-step ${defaults.require_two_step_high_risk ? 'on' : 'off'}`,
  ].join(' • ');

  const items = Array.isArray(activityPayload?.items) ? activityPayload.items : [];
  if (!items.length) {
    listEl.innerHTML = '<div class="memory-empty">No computer-use activity yet</div>';
    return;
  }

  listEl.innerHTML = items.map((item) => {
    const status = String(item?.status || 'unknown');
    const action = escapeHtml(String(item?.action || ''));
    const text = escapeHtml(String(item?.text || ''));
    const attemptId = escapeHtml(String(item?.attempt_id || ''));
    const reason = escapeHtml(String(item?.reason || ''));
    const err = escapeHtml(String(item?.error || ''));
    const tsLabel = formatTimeAgo(String(item?.ts || ''));
    const statusClass = status.toLowerCase();

    return `
      <div class="queue-item-row">
        <div class="queue-item-top">
          <span class="queue-op">${action || 'unknown action'}</span>
          <span class="activity-status-badge ${statusClass}">${escapeHtml(status)}</span>
        </div>
        <div class="queue-item-meta">${attemptId} • ${escapeHtml(tsLabel || '')}</div>
        <pre class="queue-item-preview">text=${text || '""'}\nreason=${reason || '-'}\nerror=${err || '-'}</pre>
        <div class="activity-item-actions">
          <button class="activity-view-btn" data-attempt-id="${attemptId}">View Artifact</button>
        </div>
      </div>
    `;
  }).join('');

  listEl.querySelectorAll('.activity-view-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const attemptId = btn.getAttribute('data-attempt-id') || '';
      if (attemptId) loadComputerUseArtifact(attemptId);
    });
  });
}

export async function loadComputerUseActivity(retry = false) {
  try {
    const [activityResp, configResp] = await Promise.all([
      fetch('/api/computer-use/activity?limit=30', { headers: authHeaders() }),
      fetch('/api/config', { headers: authHeaders() }),
    ]);

    if ((activityResp.status === 401 || configResp.status === 401) && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return loadComputerUseActivity(true);
      }
      return;
    }

    const activityPayload = await activityResp.json();
    const configPayload = await configResp.json();
    if (!activityResp.ok) {
      throw new Error(activityPayload?.error || `HTTP ${activityResp.status}`);
    }
    renderComputerUseActivity(activityPayload, configPayload || {});
  } catch (e) {
    console.error('Failed to load computer-use activity:', e);
    const listEl = document.getElementById('computerUseActivityList');
    if (listEl) listEl.innerHTML = '<div class="memory-empty">Computer-use activity unavailable</div>';
  }
}

async function replayQueueWrites(retry = false) {
  const replayBtn = document.getElementById('queueReplayBtn');
  const originalLabel = replayBtn?.textContent || 'Replay <= 50';
  if (replayBtn) {
    replayBtn.disabled = true;
    replayBtn.textContent = 'Replaying...';
  }

  try {
    const r = await fetch('/api/memory/write-queue/replay', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ max_items: 50 }),
    });

    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return replayQueueWrites(true);
      }
      return;
    }

    const payload = await r.json();
    if (!r.ok) {
      if (window.showToast) {
        showToast(payload?.error || 'Queue replay failed', r.status === 429 || r.status === 409 ? 'warning' : 'error');
      }
      return;
    }

    const replayed = Number(payload?.replay?.replayed || 0);
    const remaining = Number(payload?.replay?.remaining || 0);
    if (window.showToast) {
      const type = replayed > 0 ? 'success' : 'info';
      showToast(`Replayed ${replayed} queued writes (${remaining} remaining)`, type);
    }
  } catch (e) {
    console.error('Queue replay failed:', e);
    if (window.showToast) {
      showToast('Queue replay failed', 'error');
    }
  } finally {
    if (replayBtn) replayBtn.textContent = originalLabel;
    await loadQueueDiagnostics(true);
  }
}

// ---- Token Stats ----
export async function loadTokenStats(retry = false) {
  const byModelDiv = document.getElementById('tokenByModel');
  if (byModelDiv) byModelDiv.innerHTML = skeletonLines(3);

  try {
    const r = await fetch('/api/tokens', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) { setApiToken(tok); return loadTokenStats(true); }
      return;
    }

    const data = await r.json();
    const total = (data.total_input || 0) + (data.total_output || 0);
    document.getElementById('tokenTotal').textContent = total.toLocaleString();
    document.getElementById('tokenInput').textContent = (data.total_input || 0).toLocaleString();
    document.getElementById('tokenOutput').textContent = (data.total_output || 0).toLocaleString();
    document.getElementById('tokenRequests').textContent = data.requests || 0;

    const byModelDiv = document.getElementById('tokenByModel');
    if (byModelDiv && data.by_model) {
      byModelDiv.innerHTML = '';
      Object.entries(data.by_model).forEach(([model, stats]) => {
        const shortName = model.split('/').pop().substring(0, 20);
        const modelTotal = (stats.input || 0) + (stats.output || 0);
        const row = document.createElement('div');
        row.className = 'model-token-row';
        row.innerHTML = `
          <span class="model-name" title="${model}">${shortName}</span>
          <span class="model-tokens">${modelTotal.toLocaleString()}</span>
          <span class="model-count">${stats.count} calls</span>
        `;
        byModelDiv.appendChild(row);
      });
      if (Object.keys(data.by_model).length === 0) {
        byModelDiv.innerHTML = '<div style="color: var(--text-muted); font-size: 13px;">No requests yet</div>';
      }
    }
  } catch (e) {
    console.error('Failed to load token stats:', e);
  }
}

// ---- Daily Token Budget ----
export async function loadTokenBudget() {
  try {
    const r = await fetch('/api/token-budget', { headers: authHeaders() });
    if (!r.ok) return;

    const data = await r.json();

    let budgetEl = document.getElementById('tokenBudgetDisplay');
    if (!budgetEl) {
      budgetEl = document.createElement('div');
      budgetEl.id = 'tokenBudgetDisplay';
      budgetEl.style.cssText = `
        position: fixed; top: 10px; left: 50%; transform: translateX(-50%);
        background: var(--surface-secondary, #1a1a2e); padding: 8px 14px; border-radius: 8px;
        font-size: 12px; z-index: 1000; display: flex; align-items: center; gap: 8px;
        border: 1px solid var(--border-color, #333);
      `;
      document.body.appendChild(budgetEl);
    }

    const percent = data.percent || 0;
    const used = data.used || 0;
    const limit = data.limit || 500000;

    let color = '#4ade80', icon = '🟢';
    if (data.warning) { color = '#fbbf24'; icon = '🟡'; }
    if (data.critical) { color = '#ef4444'; icon = '🔴'; }

    budgetEl.innerHTML = `
      <span>${icon}</span>
      <span style="color: ${color}; font-weight: 600;">${percent.toFixed(1)}%</span>
      <span style="color: var(--text-muted, #888);">${(used / 1000).toFixed(0)}K / ${(limit / 1000000).toFixed(1)}M tokens today</span>
    `;

    setTimeout(loadTokenBudget, 30000);
  } catch (e) {
    console.error('Failed to load token budget:', e);
  }
}

// ---- Init ----
export function initSettings() {
  document.getElementById('refreshMetricsBtn')?.addEventListener('click', loadMetrics);
  document.getElementById('refreshTokensBtn')?.addEventListener('click', loadTokenStats);
  document.getElementById('refreshQueueBtn')?.addEventListener('click', () => loadQueueDiagnostics());
  document.getElementById('refreshMigrationReadinessBtn')?.addEventListener('click', () => loadMigrationReadiness());
  document.getElementById('queueReplayBtn')?.addEventListener('click', () => replayQueueWrites());
  document.getElementById('refreshLocalRuntimeBtn')?.addEventListener('click', () => loadLocalRuntimePanel());
  document.getElementById('saveLocalRuntimeBtn')?.addEventListener('click', () => saveLocalRuntimePanel());
  document.getElementById('clearLocalRuntimeBtn')?.addEventListener('click', () => clearLocalRuntimePanelOverrides());
  document.getElementById('refreshComputerUseBtn')?.addEventListener('click', () => loadComputerUseActivity());
  document.getElementById('resetTokensBtn')?.addEventListener('click', async () => {
    try {
      await fetch('/api/tokens/reset', { method: 'POST', headers: authHeaders() });
      loadTokenStats();
    } catch (e) { console.error('Failed to reset tokens:', e); }
  });

  // Listen for token refresh requests from other modules (e.g. chat)
  bus.on('tokens:refresh', () => loadTokenStats());
}
