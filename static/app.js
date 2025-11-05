// Basic SPA behavior
const chatPane = document.getElementById('chatPane');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const healthBtn = document.getElementById('healthBtn');
const toggleSidebarBtn = document.getElementById('toggleSidebar');
const sidebar = document.getElementById('sidebar');

let API_TOKEN = localStorage.getItem('companion_api_token') || '';
function setApiToken(tok){ API_TOKEN = tok || ''; if(tok) localStorage.setItem('companion_api_token', tok); }
function authHeaders(extra={}) { return { 'Content-Type':'application/json', ...(API_TOKEN? {'X-API-TOKEN':API_TOKEN}:{}), ...extra }; }

// TTS Toggle
let ttsEnabled = localStorage.getItem('companion_tts_enabled') === 'true';
const ttsToggle = document.getElementById('ttsToggle');
if (ttsToggle) {
  ttsToggle.checked = ttsEnabled;
  ttsToggle.addEventListener('change', () => {
    ttsEnabled = ttsToggle.checked;
    localStorage.setItem('companion_tts_enabled', ttsEnabled);
    console.log('TTS ' + (ttsEnabled ? 'enabled' : 'disabled'));
  });
}

// Sidebar toggle
if (toggleSidebarBtn) {
  toggleSidebarBtn.addEventListener('click', () => {
    sidebar.classList.toggle('visible');
    // Add class to body to shift layout
    document.body.classList.toggle('sidebar-open');
  });
}

function addMessage(role, text) {
  // Remove welcome message on first interaction
  const welcome = chatPane.querySelector('.msg.system');
  if (welcome) welcome.remove();
  
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = text;
  const ts = document.createElement('span');
  ts.className = 'timestamp';
  ts.textContent = new Date().toLocaleTimeString();
  div.appendChild(ts);
  chatPane.appendChild(div);
  
  // Smooth scroll to bottom - scroll the container, not the element
  setTimeout(() => {
    chatPane.scrollTop = chatPane.scrollHeight;
  }, 50);
}

async function sendMessage(retry=false) {
  const message = userInput.value.trim();
  if (!message) return;
  addMessage('user', message);
  userInput.value = '';
  resizeTextarea();
  
  // Show loading indicator
  const loadingDiv = document.createElement('div');
  loadingDiv.className = 'msg ai loading';
  loadingDiv.textContent = '...';
  chatPane.appendChild(loadingDiv);
  chatPane.scrollTop = chatPane.scrollHeight;
  
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message, tts_enabled: ttsEnabled })
    });
    const data = await resp.json();
    if (resp.status === 401 && !retry) {
      // Prompt for token once
      const tok = prompt('API token required. Enter token:');
      if (tok) { setApiToken(tok); return sendMessage(true); }
    }
    if (!resp.ok) throw new Error(data.error || 'Error');
    
    // Remove loading indicator
    loadingDiv.remove();
    addMessage('ai', data.response);
  } catch (e) {
    loadingDiv.remove();
    addMessage('ai', 'Error: ' + e.message);
  }
}

sendBtn.addEventListener('click', sendMessage);
userInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});

function resizeTextarea() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
}
userInput.addEventListener('input', resizeTextarea);

// Tabs
const tabs = document.querySelectorAll('.tab');
const panes = document.querySelectorAll('.pane');
tabs.forEach(btn => btn.addEventListener('click', () => {
  tabs.forEach(b => b.classList.remove('active'));
  panes.forEach(p => p.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('pane-' + btn.dataset.tab).classList.add('active');
}));

async function loadMemory(retry=false) {
  try {
    const r = await fetch('/api/memory?detailed=1', { headers: authHeaders({}) });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required. Enter token:'); if(tok){ setApiToken(tok); return loadMemory(true);} else return;
    }
    const data = await r.json();
    if (data.error) return;
    const profileUl = document.getElementById('profileList');
    profileUl.innerHTML = '';
    const detailed = data.profile_detailed || [];
    detailed.forEach(row => {
      const li = document.createElement('li');
      li.classList.add('pfact');
      li.innerHTML = `<span class="pf-main"><strong>${row.key}</strong>: ${row.value}</span>`;
      const meta = document.createElement('span'); meta.className = 'meta';
      const badge = document.createElement('span'); badge.className = 'badge conf-' + row.confidence_label; badge.textContent = row.confidence_label;
      meta.appendChild(badge);
      const reaf = document.createElement('span'); reaf.className='badge'; reaf.textContent = `${row.reaffirmations}×`; meta.appendChild(reaf);
      li.appendChild(meta);
      const expand = document.createElement('div'); expand.className='pf-details';
      expand.style.display='none';
      expand.innerHTML = `<div><span class="sub">confidence:</span> ${row.confidence.toFixed(2)} | <span class="sub">updated:</span> ${row.last_updated || ''}</div>` +
        `<div><span class="sub">first seen:</span> ${row.first_seen_ts || '—'} | <span class=\"sub\">last seen:</span> ${row.last_seen_ts || '—'}</div>` +
        (row.evidence ? `<div class="pf-evidence">evidence: ${row.evidence}</div>`: '') ;
      li.appendChild(expand);
      li.addEventListener('click', () => { expand.style.display = expand.style.display==='none' ? 'block':'none'; });
      profileUl.appendChild(li);
    });
    const summaryUl = document.getElementById('summaryList');
    summaryUl.innerHTML='';
    (data.summaries||[]).forEach(s => { const li=document.createElement('li'); li.textContent=s.summary_text; summaryUl.appendChild(li); });
    const insightUl = document.getElementById('insightList');
    insightUl.innerHTML='';
    (data.insights||[]).forEach(s => { const li=document.createElement('li'); li.textContent=s.insight_text; insightUl.appendChild(li); });
    // Pending facts
    const pendingUl = document.getElementById('pendingFacts');
    pendingUl.innerHTML='';
    try {
      const pr = await fetch('/api/pending_facts', { headers: authHeaders({}) });
      const pdata = await pr.json();
      if (pdata.enabled) {
        document.getElementById('pendingBadge').textContent = `(${pdata.pending.length})`;
        pdata.pending.forEach(p => {
          const li = document.createElement('li');
          li.innerHTML = `<span>${p.key}: ${p.value} (${p.confidence.toFixed(2)})</span> <button data-act="approve" data-id="${p.id}">✓</button> <button data-act="reject" data-id="${p.id}">✗</button>`;
          pendingUl.appendChild(li);
        });
        pendingUl.querySelectorAll('button').forEach(btn => {
          btn.addEventListener('click', async () => {
            const id = btn.getAttribute('data-id');
            const act = btn.getAttribute('data-act');
            const ep = `/api/pending_facts/${id}/${act==='approve'?'approve':'reject'}`;
            await fetch(ep, { method:'POST', headers: authHeaders({}) });
            loadMemory();
          });
        });
      } else {
        document.getElementById('pendingBadge').textContent = '(disabled)';
      }
    } catch {}
  } catch {}
}

async function doSearch() {
  const q = document.getElementById('searchInput').value.trim();
  if (!q) return;
  const out = document.getElementById('searchResults');
  out.textContent = 'Searching...';
  try {
  const r = await fetch('/api/search?q=' + encodeURIComponent(q), { headers: authHeaders({ 'Content-Type': 'application/json' }) });
    const data = await r.json();
    if (data.error) { out.textContent = 'Error: ' + data.error; return; }
    let txt = '';
    (data.memory_hits||[]).forEach((h,i) => { txt += `${i+1}. [${h.type}] ${h.text}\n`; });
    if (data.web_snippet) txt += `\nWEB: ${data.web_snippet}`;
    out.textContent = txt || 'No results';
  } catch (e) { out.textContent = 'Error: ' + e.message; }
}

document.getElementById('searchBtn').addEventListener('click', doSearch);

document.getElementById('searchInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); doSearch(); }
});

async function loadHealth(retry=false) {
  try {
    const r = await fetch('/api/health', { headers: authHeaders({}) });
    if (r.status === 401 && !retry) { const tok = prompt('API token required. Enter token:'); if(tok){ setApiToken(tok); return loadHealth(true);} else return; }
    const data = await r.json();
    if (data.error) return;
    const pre = document.getElementById('metricsOut');
    const lines = [];
    lines.push('Interactions: ' + (data.metrics?.total_interactions || 0));
    Object.entries(data.metrics?.models || {}).forEach(([m, info]) => {
      lines.push(`- ${m}: count=${info.count} avg=${info.avg_latency_ms}ms p95=${info.p95_latency_ms}ms`);
    });
    lines.push('');
    if (data.metrics?.tools) {
      const t = data.metrics.tools;
      lines.push('Tools:');
      lines.push(` total_invocations=${t.total_invocations} blocked=${t.blocked} failures=${t.failures}`);
      if (t.by_name) {
        Object.entries(t.by_name).forEach(([n,c])=>lines.push(`  - ${n}: ${c}`));
      }
      if (t.decision_types) {
        lines.push(' decision_types: ' + Object.entries(t.decision_types).map(([k,v])=>`${k}=${v}`).join(', '));
      }
      lines.push('');
    }
    lines.push('Memory: facts=' + data.memory.profile_facts + ' summaries=' + data.memory.summaries + ' insights=' + data.memory.insights);
  lines.push('Refreshed: ' + new Date().toLocaleTimeString());
  pre.textContent = lines.join('\n');
  } catch {}
}

healthBtn.addEventListener('click', () => { loadHealth(); loadMemory(); });

async function loadModelsPanel(retry=false) {
  const panel = document.getElementById('modelsPanel');
  if (!panel) return;
  panel.textContent = 'Loading...';
  try {
    const r = await fetch('/api/models', { headers: authHeaders({}) });
    if (r.status === 401 && !retry) { const tok = prompt('API token required. Enter token:'); if(tok){ setApiToken(tok); return loadModelsPanel(true);} else { panel.textContent='Auth required'; return; } }
    const d = await r.json();
    if (d.error) { panel.textContent = 'Error loading models'; return; }
    const lines = [];
    lines.push(`<div><strong>Smart</strong>: ${d.roles.SMART_PRIMARY_MODEL}</div>`);
    lines.push(`<div><strong>Heavy</strong>: ${d.roles.HEAVY_MODEL}</div>`);
    if (d.roles.HEAVY_ALTERNATES?.length) lines.push(`<div><strong>Alternates</strong>: ${d.roles.HEAVY_ALTERNATES.join(', ')}</div>`);
    lines.push(`<div><strong>Fast</strong>: ${d.roles.FAST_MODEL}</div>`);
    lines.push('<h4>Ensemble</h4>');
    lines.push(`<div>${d.ensemble.enabled ? 'ENABLED' : 'disabled'} mode=${d.ensemble.mode} candidates=${d.ensemble.candidates}</div>`);
    lines.push('<h4>Flags</h4>');
    const flagKeys = Object.entries(d.flags).map(([k,v])=>`<span class="badge" style="margin:2px 4px 2px 0;">${k}:${v? 'on':'off'}</span>`).join('');
    lines.push(`<div>${flagKeys}</div>`);
    panel.innerHTML = lines.join('');
  } catch (e) {
    panel.textContent = 'Failed to load';
  }
}

async function loadRecentRouting() {
  const tgt = document.getElementById('recentRouting');
  if (!tgt) return;
  try {
    const r = await fetch('/api/routing/recent?n=20');
    const d = await r.json();
    if (d.error) { tgt.textContent = 'Error'; return; }
    const lines = [];
    (d.items||[]).forEach(item => {
      const rt = item.routing || {};
      let base = `${(item.ts||'').slice(11,19)}  c${item.complexity??'-'}  ${item.model}`;
      if (rt.ensemble) {
        base += `  ENS ${rt.mode} idx=${rt.chosen_index} conf=${rt.confidence??''}`;
      } else if (rt.escalated) {
        base += '  escalated';
      }
      lines.push(base);
    });
    tgt.textContent = lines.join('\n') || 'No routing records yet.';
  } catch (e) { tgt.textContent = 'Error loading'; }
}

// Keyboard shortcuts (Ctrl+R for refresh, Ctrl+1-4 for tabs)
document.addEventListener('keydown', e => {
  if (e.ctrlKey) {
    if (e.key === 'r') { e.preventDefault(); healthBtn.click(); }
    if (/^[1-4]$/.test(e.key)) { const idx = parseInt(e.key)-1; if (tabs[idx]) tabs[idx].click(); }
  }
});

// Live message polling
let lastMessageCount = 0;
async function pollForNewMessages() {
  try {
    const resp = await fetch('/api/chat/history');
    if (!resp.ok) return;
    const data = await resp.json();
    
    // If there are new messages, add them to the chat
    if (data.count > lastMessageCount) {
      const newMessages = data.history.slice(lastMessageCount);
      newMessages.forEach(entry => {
        // Check if message already exists to avoid duplicates
        const existingMessages = Array.from(chatPane.querySelectorAll('.msg')).map(m => m.textContent);
        const userExists = existingMessages.some(text => text.includes(entry.user));
        const aiExists = existingMessages.some(text => text.includes(entry.ai));
        
        if (!userExists) {
          addMessage('user', entry.user);
        }
        if (!aiExists) {
          addMessage('ai', entry.ai);
        }
      });
      lastMessageCount = data.count;
    }
  } catch (e) {
    console.error('Poll error:', e);
  }
}

// Start polling every 2 seconds
setInterval(pollForNewMessages, 2000);
// Initial poll to catch up
pollForNewMessages();

// Initial load
loadMemory();
loadHealth();
loadModelsPanel();
loadRecentRouting();
// Auto-refresh routing panel on health refresh
healthBtn.addEventListener('click', ()=>{ loadModelsPanel(); loadRecentRouting(); });

