// ============================================
// Companion AI — Memory Facts, Insights & Knowledge Base (Brain Files)
// ============================================
import { bus, state, authHeaders, setApiToken, escapeHtml, escapeRegex, formatTimeAgo, detectCategory, skeletonCards, skeletonLines } from './utils.js';

// ---- State ----
let allMemoryData = { facts: [], insights: [] };
const provenanceCache = new Map();

async function loadProactiveInsights() {
  const listEl = document.getElementById('proactiveInsightsList');
  const badgeEl = document.getElementById('insightBadge');
  if (listEl) listEl.innerHTML = skeletonCards(2);

  try {
    const r = await fetch('/api/insights?limit=12', { headers: authHeaders() });
    const data = await r.json();
    const rows = Array.isArray(data.insights) ? data.insights : [];
    const unreadCount = Number(data.unread_count || 0);

    if (badgeEl) {
      if (unreadCount > 0) {
        badgeEl.textContent = String(unreadCount);
        badgeEl.style.display = 'flex';
      } else {
        badgeEl.style.display = 'none';
      }
    }

    if (!listEl) return;
    if (!rows.length) {
      listEl.innerHTML = '<div class="memory-empty">No proactive insights yet</div>';
      return;
    }

    listEl.innerHTML = rows.map((row) => {
      const title = escapeHtml(row.title || 'Insight');
      const body = escapeHtml(row.body || '');
      const status = String(row.status || 'unread').toLowerCase();
      const statusClass = status === 'read' ? 'read' : (status === 'dismissed' ? 'dismissed' : 'unread');
      const timeAgo = formatTimeAgo(row.created_at);
      const id = Number(row.id);

      return `
        <div class="memory-card proactive-insight ${statusClass}" data-insight-id="${id}">
          <div class="memory-card-header">
            <span class="memory-category insight">proactive</span>
            <span class="memory-timestamp">${escapeHtml(timeAgo)}</span>
          </div>
          <div class="memory-text"><strong>${title}</strong></div>
          <div class="memory-text">${body}</div>
          <div class="memory-meta" style="justify-content:flex-end; gap:6px;">
            <button class="small-btn" onclick="markInsightStatus(${id}, 'read')">Mark read</button>
            <button class="small-btn" onclick="markInsightStatus(${id}, 'dismissed')">Dismiss</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load proactive insights:', e);
    if (listEl) listEl.innerHTML = '<div class="memory-empty">Failed to load proactive insights</div>';
  }
}

async function markInsightStatus(insightId, status) {
  try {
    const r = await fetch(`/api/insights/${insightId}/status`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ status })
    });
    const data = await r.json();
    if (!r.ok) {
      showToast(data.error || 'Failed to update insight', 'error');
      return;
    }
    showToast(status === 'dismissed' ? 'Insight dismissed' : 'Insight marked read', 'success');
    await loadProactiveInsights();
  } catch (e) {
    showToast('Failed to update insight', 'error');
  }
}

// ---- Memory Loading ----
export async function loadMemory(retry = false) {
  // Show skeletons while loading
  const profileDiv = document.getElementById('profileList');
  const insightDiv = document.getElementById('insightList');
  if (profileDiv) profileDiv.innerHTML = skeletonCards(3);
  if (insightDiv) insightDiv.innerHTML = skeletonCards(2);

  try {
    const r = await fetch('/api/memory?detailed=1', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) { setApiToken(tok); return loadMemory(true); }
      return;
    }

    const data = await r.json();
    if (data.error) return;

    const detailed = data.profile_detailed || [];
    const insights = data.insights || [];
    const summaries = data.summaries || [];

    allMemoryData = { facts: detailed, insights };
    provenanceCache.clear();

    document.getElementById('memFactCount').textContent = detailed.length;
    document.getElementById('memInsightCount').textContent = insights.length;
    document.getElementById('memSummaryCount').textContent = summaries.length;

    const searchInput = document.getElementById('memorySearchInput');
    const query = searchInput?.value?.toLowerCase() || '';
    renderMemoryCards(query);
    await loadPendingFacts();
    await loadMemoryReview();
    await loadProactiveInsights();
  } catch (e) {
    console.error('Failed to load memory:', e);
  }
}

async function loadPendingFacts() {
  const container = document.getElementById('pendingFactsList');
  if (!container) return;

  try {
    const r = await fetch('/api/pending_facts', { headers: authHeaders() });
    const data = await r.json();
    if (!data.enabled) {
      container.innerHTML = '<div class="memory-empty">Fact review is disabled in config</div>';
      return;
    }

    const rows = Array.isArray(data.pending) ? data.pending : [];
    if (rows.length === 0) {
      container.innerHTML = '<div class="memory-empty">No pending facts</div>';
      return;
    }

    container.innerHTML = rows.map(row => {
      const pid = row.id;
      const text = escapeHtml(row.fact_value || row.value || '');
      const conf = row.model_conf_label ? escapeHtml(row.model_conf_label) : `${Math.round((Number(row.confidence || 0)) * 100)}%`;
      const source = row.source ? escapeHtml(row.source) : 'unknown';
      const evidence = row.evidence ? `<div class="memory-subtext">Evidence: ${escapeHtml(row.evidence)}</div>` : '';
      const why = row.justification ? `<div class="memory-subtext">Why: ${escapeHtml(row.justification)}</div>` : '';
      const conflict = row.conflict_with ? `<div class="memory-subtext">Conflicts with: ${escapeHtml(row.conflict_with)}</div>` : '';
      return `
        <div class="memory-card" data-pending-id="${pid}">
          <div class="memory-text">${text}</div>
          <div class="memory-meta">confidence: ${conf} · source: ${source}</div>
          ${evidence}
          ${why}
          ${conflict}
          <div class="memory-meta" style="justify-content:flex-end; gap:6px;">
            <button class="small-btn" onclick="approvePendingFact(${pid})">Approve</button>
            <button class="small-btn" onclick="rejectPendingFact(${pid})">Reject</button>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    console.error('Failed to load pending facts:', e);
    container.innerHTML = '<div class="memory-empty">Failed to load pending facts</div>';
  }
}

async function approvePendingFact(pid) {
  try {
    const r = await fetch(`/api/pending_facts/${pid}/approve`, { method: 'POST', headers: authHeaders() });
    const data = await r.json();
    if (!r.ok || !data.approved) { showToast(data.error || 'Approve failed', 'error'); return; }
    await loadPendingFacts();
    await loadMemory();
    showToast('Fact approved', 'success');
  } catch (e) { showToast('Approve failed', 'error'); }
}

async function rejectPendingFact(pid) {
  try {
    const r = await fetch(`/api/pending_facts/${pid}/reject`, { method: 'POST', headers: authHeaders() });
    const data = await r.json();
    if (!r.ok || !data.rejected) { showToast(data.error || 'Reject failed', 'error'); return; }
    await loadPendingFacts();
    showToast('Fact rejected', 'success');
  } catch (e) { showToast('Reject failed', 'error'); }
}

async function bulkPendingFacts(action) {
  const ids = [...document.querySelectorAll('#pendingFactsList [data-pending-id]')]
    .map(el => Number(el.dataset.pendingId)).filter(Boolean);
  if (!ids.length) { showToast('No pending facts to process', 'info'); return; }

  try {
    const r = await fetch('/api/pending_facts/bulk', {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ action, ids })
    });
    const data = await r.json();
    if (!r.ok) { showToast(data.error || 'Bulk action failed', 'error'); return; }
    await loadPendingFacts();
    await loadMemory();
    showToast(`${action === 'approve' ? 'Approved' : 'Rejected'} ${data.processed} facts`, 'success');
  } catch (e) { showToast('Bulk action failed', 'error'); }
}

function renderMemoryReviewSummary(summary) {
  const summaryEl = document.getElementById('memoryReviewSummary');
  if (!summaryEl) return;

  const total = Number(summary?.total_review_items || 0);
  const conflicts = Number(summary?.conflict_count || 0);
  const pending = Number(summary?.pending_count || 0);
  const dedup = Number(summary?.dedup_candidate_count || 0);
  const lowConf = Number(summary?.low_confidence_count || 0);
  summaryEl.textContent = `${total} items • ${conflicts} conflicts • ${pending} pending • ${dedup} dedup candidates • ${lowConf} low confidence`;
}

function renderMemoryReviewCards(items) {
  const list = document.getElementById('memoryReviewList');
  if (!list) return;

  if (!Array.isArray(items) || items.length === 0) {
    list.innerHTML = '<div class="memory-empty">No contradictions or duplicate candidates detected</div>';
    return;
  }

  list.innerHTML = items.map((item) => {
    const key = escapeHtml(String(item.key || ''));
    const value = escapeHtml(String(item.value || ''));
    const state = escapeHtml(String(item.contradiction_state || 'none'));
    const stateClass = state === 'conflict' ? 'conflict' : state === 'pending' ? 'pending' : state === 'resolved' ? 'resolved' : 'none';
    const confidence = Math.round(Number(item.confidence || 0) * 100);
    const confidenceLabel = escapeHtml(String(item.confidence_label || 'medium'));
    const reaffirmations = Number(item.reaffirmations || 0);
    const source = escapeHtml(String(item.source || 'mem0'));
    const dedupCount = Number(item.dedup_candidate_count || 0);
    const topDuplicate = Array.isArray(item.dedup_candidates) && item.dedup_candidates.length > 0 ? item.dedup_candidates[0] : null;
    const duplicateHint = topDuplicate
      ? `Potential duplicate: ${escapeHtml(String(topDuplicate.key || 'unknown'))} (${Math.round(Number(topDuplicate.similarity || 0) * 100)}% similar)`
      : '';

    return `
      <div class="memory-card memory-review-card" data-review-key="${key}">
        <div class="memory-card-header">
          <span class="memory-category fact">review</span>
          <span class="memory-review-state ${stateClass}">${state}</span>
        </div>
        <div class="memory-text">${value}</div>
        <div class="memory-meta" style="flex-wrap:wrap; gap:8px;">
          <span>source: ${source}</span>
          <span>confidence: ${confidence}% (${confidenceLabel})</span>
          <span>reaffirmations: ${reaffirmations}</span>
          <span>dedup candidates: ${dedupCount}</span>
        </div>
        ${duplicateHint ? `<div class="memory-subtext">${duplicateHint}</div>` : ''}
        <div class="memory-meta memory-review-actions" style="justify-content:flex-end; gap:6px; flex-wrap:wrap;">
          <button class="small-btn" data-review-action="reaffirm">Reaffirm</button>
          <button class="small-btn" data-review-action="set_state" data-review-state="pending">Set Pending</button>
          <button class="small-btn" data-review-action="set_state" data-review-state="conflict">Set Conflict</button>
          <button class="small-btn" data-review-action="set_state" data-review-state="resolved">Resolve</button>
          ${topDuplicate ? `<button class="small-btn" data-review-action="mark_duplicate" data-duplicate-of="${escapeHtml(String(topDuplicate.key || ''))}">Mark Duplicate</button>` : ''}
        </div>
      </div>
    `;
  }).join('');
}

async function loadMemoryReview(retry = false) {
  const list = document.getElementById('memoryReviewList');
  if (!list) return;
  list.innerHTML = skeletonCards(2);

  try {
    const res = await fetch('/api/memory/review?limit=20', { headers: authHeaders() });
    if (res.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) {
        setApiToken(tok);
        return loadMemoryReview(true);
      }
      return;
    }

    const payload = await res.json();
    if (!res.ok) {
      throw new Error(payload?.error || `HTTP ${res.status}`);
    }

    renderMemoryReviewSummary(payload.summary || {});
    renderMemoryReviewCards(payload.items || []);
  } catch (e) {
    console.error('Failed to load memory review queue:', e);
    renderMemoryReviewSummary({ total_review_items: 0, conflict_count: 0, pending_count: 0, dedup_candidate_count: 0, low_confidence_count: 0 });
    list.innerHTML = '<div class="memory-empty">Failed to load memory review queue</div>';
  }
}

async function applyMemoryReviewAction(key, action, extras = {}) {
  try {
    const res = await fetch(`/api/memory/review/${encodeURIComponent(key)}`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ action, ...extras }),
    });
    const payload = await res.json();

    if (!res.ok) {
      showToast(payload?.error || 'Memory review update failed', 'error');
      return;
    }

    const nextState = payload?.updated?.contradiction_state || action;
    showToast(`Memory review updated (${nextState})`, 'success');
    await loadMemory();
  } catch (e) {
    console.error('Memory review update failed:', e);
    showToast('Memory review update failed', 'error');
  }
}

function renderMemoryCards(query = '') {
  const profileDiv = document.getElementById('profileList');
  const insightDiv = document.getElementById('insightList');
  const searchCount = document.getElementById('memorySearchCount');

  let matchCount = 0;

  if (profileDiv) {
    profileDiv.innerHTML = '';

    allMemoryData.facts.forEach((row, index) => {
      const text = row.value.toLowerCase();
      const matches = !query || text.includes(query);
      if (!matches) return;
      matchCount++;

      const card = document.createElement('div');
      card.className = 'memory-card';
      card.dataset.key = row.key;
      card.dataset.index = index;

      const category = detectCategory(row.value);
      const confPercent = Math.round((row.confidence || 0.7) * 100);
      const timeAgo = formatTimeAgo(row.created_at || row.updated_at);
      const source = escapeHtml(String(row.source || 'mem0'));
      const confidenceLabel = escapeHtml(String(row.confidence_label || 'medium'));
      const contradictionState = escapeHtml(String(row.contradiction_state || 'none'));

      let displayText = escapeHtml(row.value);
      if (query) {
        const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
        displayText = displayText.replace(regex, '<span class="highlight">$1</span>');
      }

      card.innerHTML = `
        <div class="memory-card-header">
          <span class="memory-category ${category}">${category}</span>
        </div>
        <div class="memory-text">${displayText}</div>
        <div class="memory-meta">
          <span class="memory-timestamp">${timeAgo}</span>
          <div class="memory-confidence">
            <span>${confPercent}%</span>
            <div class="confidence-bar"><div class="confidence-fill" style="width: ${confPercent}%"></div></div>
          </div>
        </div>
        <div class="memory-meta" style="gap:8px; flex-wrap:wrap;">
          <span>source: ${source}</span>
          <span>quality: ${confidenceLabel}</span>
          <span>state: ${contradictionState}</span>
          <button type="button" class="small-btn memory-provenance-btn" aria-label="Show memory provenance">Why this memory?</button>
        </div>
        <div class="memory-subtext memory-provenance-detail" style="display:none;"></div>
      `;

      const provenanceBtn = card.querySelector('.memory-provenance-btn');
      provenanceBtn?.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        await toggleProvenanceDetail(card, row.key);
      });

      card.addEventListener('click', (e) => {
        if (e.target.closest('.memory-edit-container') || e.target.closest('.memory-provenance-btn') || e.target.closest('.memory-provenance-detail')) return;
        toggleEditMode(card, row.key, row.value);
      });

      card.addEventListener('contextmenu', (e) => {
        e.preventDefault();
        deleteFact(row.key, card);
      });

      profileDiv.appendChild(card);
    });

    if (!allMemoryData.facts.length) {
      profileDiv.innerHTML = '<div class="memory-empty">No facts stored yet. Chat with me so I can learn about you!</div>';
    } else if (!matchCount && query) {
      profileDiv.innerHTML = '<div class="memory-empty">No memories match your search</div>';
    }
  }

  if (insightDiv) {
    insightDiv.innerHTML = '';
    allMemoryData.insights.slice(0, 5).forEach(s => {
      const text = (s.insight_text || '').toLowerCase();
      if (query && !text.includes(query)) return;

      const card = document.createElement('div');
      card.className = 'memory-card';

      let displayText = escapeHtml(s.insight_text);
      if (query) {
        const regex = new RegExp(`(${escapeRegex(query)})`, 'gi');
        displayText = displayText.replace(regex, '<span class="highlight">$1</span>');
      }

      card.innerHTML = `
        <div class="memory-card-header"><span class="memory-category insight">insight</span></div>
        <div class="memory-text">${displayText}</div>
      `;
      insightDiv.appendChild(card);
    });

    if (!allMemoryData.insights.length) {
      insightDiv.innerHTML = '<div class="memory-empty">No insights yet</div>';
    }
  }

  if (searchCount) {
    searchCount.textContent = query ? `${matchCount} found` : '';
  }
}

function renderProvenanceHtml(payload) {
  const prov = payload?.provenance || {};
  const metadata = (prov.metadata && typeof prov.metadata === 'object') ? prov.metadata : {};
  const metadataRows = Object.entries(metadata)
    .slice(0, 8)
    .map(([k, v]) => `<div>${escapeHtml(String(k))}: ${escapeHtml(String(v))}</div>`)
    .join('');

  const base = [
    `source: ${escapeHtml(String(prov.source || 'unknown'))}`,
    `quality: ${escapeHtml(String(prov.confidence_label || 'medium'))} (${Math.round(Number(prov.confidence || 0) * 100)}%)`,
    `state: ${escapeHtml(String(prov.contradiction_state || 'none'))}`,
    `reaffirmations: ${escapeHtml(String(prov.reaffirmations ?? 0))}`,
  ];

  if (prov.updated_at) base.push(`updated: ${escapeHtml(String(prov.updated_at))}`);
  if (prov.last_validated_ts) base.push(`validated: ${escapeHtml(String(prov.last_validated_ts))}`);

  return `
    <div><strong>Provenance</strong></div>
    <div>${base.join(' · ')}</div>
    ${metadataRows ? `<div style="margin-top:4px;"><strong>Metadata:</strong></div><div>${metadataRows}</div>` : ''}
  `;
}

async function toggleProvenanceDetail(card, key) {
  const detail = card.querySelector('.memory-provenance-detail');
  if (!detail) return;

  const isOpen = detail.style.display !== 'none';
  if (isOpen) {
    detail.style.display = 'none';
    return;
  }

  detail.style.display = 'block';
  detail.innerHTML = 'Loading provenance...';

  try {
    let payload = provenanceCache.get(key);
    if (!payload) {
      const res = await fetch(`/api/memory/provenance/${encodeURIComponent(key)}`, { headers: authHeaders() });
      const data = await res.json();
      if (!res.ok) {
        detail.innerHTML = `Provenance unavailable: ${escapeHtml(String(data.error || 'not found'))}`;
        return;
      }
      payload = data;
      provenanceCache.set(key, payload);
    }

    detail.innerHTML = renderProvenanceHtml(payload);
  } catch (e) {
    console.error('Failed to load memory provenance:', e);
    detail.innerHTML = 'Failed to load provenance details';
  }
}

function toggleEditMode(card, key, currentValue) {
  document.querySelectorAll('.memory-card.editing').forEach(c => {
    c.classList.remove('editing');
    c.querySelector('.memory-edit-container')?.remove();
  });

  if (card.classList.contains('editing')) { card.classList.remove('editing'); return; }
  card.classList.add('editing');

  const editContainer = document.createElement('div');
  editContainer.className = 'memory-edit-container';
  editContainer.innerHTML = `
    <textarea class="memory-edit-textarea">${escapeHtml(currentValue)}</textarea>
    <div class="memory-edit-actions">
      <button class="memory-save-btn">Save</button>
      <button class="memory-cancel-btn">Cancel</button>
    </div>
  `;

  card.appendChild(editContainer);
  const textarea = editContainer.querySelector('textarea');
  textarea.focus();
  textarea.selectionStart = textarea.value.length;

  editContainer.querySelector('.memory-save-btn').addEventListener('click', async (e) => {
    e.stopPropagation();
    const newValue = textarea.value.trim();
    if (newValue && newValue !== currentValue) await updateFact(key, newValue, card);
    card.classList.remove('editing');
    editContainer.remove();
  });

  editContainer.querySelector('.memory-cancel-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    card.classList.remove('editing');
    editContainer.remove();
  });

  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); editContainer.querySelector('.memory-save-btn').click(); }
    else if (e.key === 'Escape') { editContainer.querySelector('.memory-cancel-btn').click(); }
  });
}

async function updateFact(key, newValue, cardElement) {
  try {
    const r = await fetch(`/api/memory/fact/${encodeURIComponent(key)}`, {
      method: 'PUT', headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ value: newValue })
    });

    if (r.ok) {
      const index = parseInt(cardElement.dataset.index);
      if (allMemoryData.facts[index]) allMemoryData.facts[index].value = newValue;
      cardElement.classList.add('highlight');
      setTimeout(() => cardElement.classList.remove('highlight'), 500);
      const query = document.getElementById('memorySearchInput')?.value?.toLowerCase() || '';
      renderMemoryCards(query);
    } else {
      const errText = await r.text();
      console.error('Update failed:', r.status, errText);
      alert(`Failed to update: ${errText}`);
    }
  } catch (e) {
    console.error('Update fact failed:', e);
    alert('Failed to update fact');
  }
}

async function deleteFact(key, cardElement) {
  const text = cardElement.querySelector('.memory-text')?.textContent || 'this memory';
  if (!confirm(`Delete: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"?`)) return;

  try {
    const r = await fetch(`/api/memory/fact/${encodeURIComponent(key)}`, {
      method: 'DELETE', headers: authHeaders()
    });

    if (r.ok) {
      cardElement.style.opacity = '0';
      cardElement.style.transform = 'translateX(-20px)';
      setTimeout(() => {
        cardElement.remove();
        const countEl = document.getElementById('memFactCount');
        if (countEl) countEl.textContent = parseInt(countEl.textContent) - 1;
        allMemoryData.facts = allMemoryData.facts.filter(f => f.key !== key);
      }, 200);
    } else {
      const errText = await r.text();
      console.error('Delete failed:', r.status, errText);
      alert(`Failed to delete: ${r.status} ${errText}`);
    }
  } catch (e) {
    console.error('Delete fact failed:', e);
    alert('Failed to delete fact');
  }
}

// ---- Knowledge Base (Brain Files) ----
export async function loadBrainFiles() {
  const list = document.getElementById('brainFilesList');
  if (!list) return;
  list.innerHTML = skeletonCards(2);

  try {
    const res = await fetch('/api/brain/files', { headers: authHeaders() });
    const data = await res.json();

    if (!data.files || data.files.length === 0) {
      list.innerHTML = '<div class="brain-empty">No documents indexed yet.<br>Upload files above to get started!</div>';
      return;
    }

    const icons = { '.pdf': '📄', '.md': '📝', '.txt': '📃', '.docx': '📋' };
    list.innerHTML = data.files.map(f => {
      const ext = '.' + (f.name || f.path || '').split('.').pop().toLowerCase();
      const icon = icons[ext] || '📁';
      const name = f.name || f.path;
      return `
        <div class="brain-file-card">
          <div class="brain-file-icon">${icon}</div>
          <div class="brain-file-info">
            <div class="brain-file-name">${name}</div>
            <div class="brain-file-meta">${f.chunks} chunk${f.chunks > 1 ? 's' : ''} indexed • ${Math.round((f.size || 0) / 1024)} KB</div>
            <div style="display:flex; gap:6px; margin-top:6px;">
              <button class="small-btn" onclick="deleteBrainFile('${encodeURIComponent(f.path)}')">Delete</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    list.innerHTML = '<div class="brain-empty">Error loading files</div>';
  }
}

async function deleteBrainFile(encodedPath) {
  const relPath = decodeURIComponent(encodedPath || '');
  if (!relPath) return;
  if (!confirm(`Delete ${relPath}?`)) return;

  try {
    const res = await fetch('/api/brain/file', {
      method: 'DELETE', headers: authHeaders(), body: JSON.stringify({ path: relPath })
    });
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Delete failed', 'error'); return; }
    showToast('File deleted', 'success');
    await loadBrainFiles();
  } catch (e) { showToast('Delete failed', 'error'); }
}

export async function loadRecentUploads() {
  const list = document.getElementById('recentUploadsList');
  if (!list) return;
  list.innerHTML = skeletonCards(2);

  try {
    const res = await fetch('/api/brain/files', { headers: authHeaders() });
    const data = await res.json();
    const files = (data.files || [])
      .filter(f => String(f.path || '').startsWith('documents/'))
      .slice(0, 12);

    if (!files.length) {
      list.innerHTML = '<div class="brain-empty">No uploaded files yet.</div>';
      return;
    }

    list.innerHTML = files.map(f => `
      <div class="brain-file-card">
        <div class="brain-file-icon">📎</div>
        <div class="brain-file-info">
          <div class="brain-file-name">${escapeHtml(f.name || f.path)}</div>
          <div class="brain-file-meta">${escapeHtml(formatTimeAgo(f.modified_at))} • ${Math.round((f.size || 0) / 1024)} KB</div>
          <div style="display:flex; gap:6px; margin-top:6px;">
            <button class="small-btn" onclick="summarizeBrainUpload('${encodeURIComponent(f.path)}')">Summary</button>
            <button class="small-btn" onclick="extractBrainUpload('${encodeURIComponent(f.path)}')">Extract</button>
            <button class="small-btn" onclick="deleteBrainFile('${encodeURIComponent(f.path)}')">Delete</button>
          </div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    list.innerHTML = '<div class="brain-empty">Failed to load uploads</div>';
  }
}

async function summarizeBrainUpload(encodedPath) {
  const relPath = decodeURIComponent(encodedPath || '');
  try {
    const res = await fetch('/api/brain/summarize', {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ path: relPath })
    });
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Summary failed', 'error'); return; }
    bus.emit('chat:addMessage', 'ai', `📄 Summary for ${data.filename}\n\n${data.summary}`);
    showToast('File summary added to chat', 'success');
  } catch (e) { showToast('Summary failed', 'error'); }
}

async function extractBrainUpload(encodedPath) {
  const relPath = decodeURIComponent(encodedPath || '');
  try {
    const res = await fetch('/api/brain/extract', {
      method: 'POST', headers: authHeaders(), body: JSON.stringify({ path: relPath, max_chars: 1800 })
    });
    const data = await res.json();
    if (!res.ok) { showToast(data.error || 'Extract failed', 'error'); return; }
    bus.emit('chat:addMessage', 'ai', `📑 Extract from ${data.filename}${data.truncated ? ' (truncated)' : ''}\n\n${data.text}`);
    showToast('File extract added to chat', 'success');
  } catch (e) { showToast('Extract failed', 'error'); }
}

async function uploadBrainFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('folder', 'documents');

  try {
    const res = await fetch('/api/brain/upload', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      console.log(`Uploaded ${file.name}: ${data.chunks_indexed} chunks indexed`);
      await loadBrainFiles();
      await loadRecentUploads();
    } else { console.error('Upload failed:', data.error); }
  } catch (e) { console.error('Upload error:', e); }
}

async function uploadBrainFiles(files) {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));
  formData.append('folder', 'documents');

  try {
    const res = await fetch('/api/brain/upload/batch', { method: 'POST', body: formData });
    const data = await res.json();
    if (data.success) {
      showToast(`Uploaded ${data.count} file${data.count === 1 ? '' : 's'} to knowledge`, 'success');
      await loadBrainFiles();
      await loadRecentUploads();
      if (Array.isArray(data.errors) && data.errors.length > 0) {
        console.warn('Some files failed during batch upload:', data.errors);
      }
    } else { showToast(data.error || 'Batch upload failed', 'error'); }
  } catch (e) {
    console.error('Batch upload error:', e);
    showToast('Batch upload failed', 'error');
  }
}

// ---- Expose for inline onclick handlers ----
window.approvePendingFact = approvePendingFact;
window.rejectPendingFact = rejectPendingFact;
window.deleteBrainFile = deleteBrainFile;
window.summarizeBrainUpload = summarizeBrainUpload;
window.extractBrainUpload = extractBrainUpload;
window.markInsightStatus = markInsightStatus;

// ---- Init ----
export function initMemory() {
  document.getElementById('memorySearchInput')?.addEventListener('input', (e) => {
    renderMemoryCards(e.target.value.toLowerCase());
  });
  document.getElementById('refreshMemoryBtn')?.addEventListener('click', loadMemory);
  document.getElementById('refreshMemoryReviewBtn')?.addEventListener('click', () => loadMemoryReview());
  document.getElementById('approveAllPendingBtn')?.addEventListener('click', () => bulkPendingFacts('approve'));
  document.getElementById('rejectAllPendingBtn')?.addEventListener('click', () => bulkPendingFacts('reject'));
  document.getElementById('refreshProactiveInsightsBtn')?.addEventListener('click', loadProactiveInsights);

  document.getElementById('memoryReviewList')?.addEventListener('click', (e) => {
    const btn = e.target.closest('[data-review-action]');
    if (!btn) return;

    const card = btn.closest('[data-review-key]');
    const key = card?.dataset?.reviewKey;
    if (!key) return;

    const action = btn.dataset.reviewAction;
    if (action === 'set_state') {
      applyMemoryReviewAction(key, action, { state: btn.dataset.reviewState || 'none' });
      return;
    }
    if (action === 'mark_duplicate') {
      const duplicateOf = btn.dataset.duplicateOf || '';
      applyMemoryReviewAction(key, action, { duplicate_of: duplicateOf });
      return;
    }

    applyMemoryReviewAction(key, action);
  });

  // Live insight events update badge/list without requiring a full memory reload.
  bus.on('insight:new', () => { loadProactiveInsights(); });

  // Knowledge tab handlers  
  const uploadZone = document.getElementById('brainUploadZone');
  const fileInput = document.getElementById('brainFileInput');
  const reindexBtn = document.getElementById('reindexBrainBtn');
  const refreshUploadsBtn = document.getElementById('refreshUploadsBtn');

  if (uploadZone && fileInput) {
    uploadZone.addEventListener('click', () => fileInput.click());

    uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
    uploadZone.addEventListener('dragleave', () => { uploadZone.classList.remove('drag-over'); });
    uploadZone.addEventListener('drop', async (e) => {
      e.preventDefault();
      uploadZone.classList.remove('drag-over');
      const files = Array.from(e.dataTransfer.files);
      if (files.length > 1) await uploadBrainFiles(files);
      else if (files.length === 1) await uploadBrainFile(files[0]);
    });

    fileInput.addEventListener('change', async (e) => {
      const files = Array.from(e.target.files);
      if (files.length > 1) await uploadBrainFiles(files);
      else if (files.length === 1) await uploadBrainFile(files[0]);
      fileInput.value = '';
    });
  }

  if (reindexBtn) {
    reindexBtn.addEventListener('click', async () => {
      reindexBtn.disabled = true;
      reindexBtn.textContent = '...';
      try { await fetch('/api/brain/reindex', { method: 'POST' }); await loadBrainFiles(); }
      finally { reindexBtn.disabled = false; reindexBtn.textContent = '↻'; }
    });
  }

  if (refreshUploadsBtn) {
    refreshUploadsBtn.addEventListener('click', async () => {
      refreshUploadsBtn.disabled = true;
      try { await loadRecentUploads(); }
      finally { refreshUploadsBtn.disabled = false; }
    });
  }
}
