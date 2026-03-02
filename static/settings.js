// ============================================
// Companion AI — Settings, Theme, Models, Metrics, Token Stats, Budget
// ============================================
import { bus, state, authHeaders, setApiToken, skeletonLines, skeletonCards } from './utils.js';

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
  document.getElementById('resetTokensBtn')?.addEventListener('click', async () => {
    try {
      await fetch('/api/tokens/reset', { method: 'POST', headers: authHeaders() });
      loadTokenStats();
    } catch (e) { console.error('Failed to reset tokens:', e); }
  });

  // Listen for token refresh requests from other modules (e.g. chat)
  bus.on('tokens:refresh', () => loadTokenStats());
}
