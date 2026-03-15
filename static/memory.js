// ============================================
// Companion AI — Memory Facts, Insights & Knowledge Base (Brain Files)
// ============================================
import { bus, state, authHeaders, setApiToken, escapeHtml, escapeRegex, formatTimeAgo, detectCategory, skeletonCards, skeletonLines } from './utils.js';

// ---- State ----
let allMemoryData = { facts: [], insights: [] };

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

    document.getElementById('memFactCount').textContent = detailed.length;
    document.getElementById('memInsightCount').textContent = insights.length;
    document.getElementById('memSummaryCount').textContent = summaries.length;

    const searchInput = document.getElementById('memorySearchInput');
    const query = searchInput?.value?.toLowerCase() || '';
    renderMemoryCards(query);
    await loadPendingFacts();
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
      `;

      card.addEventListener('click', (e) => {
        if (e.target.closest('.memory-edit-container')) return;
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
  document.getElementById('approveAllPendingBtn')?.addEventListener('click', () => bulkPendingFacts('approve'));
  document.getElementById('rejectAllPendingBtn')?.addEventListener('click', () => bulkPendingFacts('reject'));
  document.getElementById('refreshProactiveInsightsBtn')?.addEventListener('click', loadProactiveInsights);

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
