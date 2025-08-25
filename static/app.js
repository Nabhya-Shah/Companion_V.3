// Basic SPA behavior
const chatPane = document.getElementById('chatPane');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const statusEl = document.getElementById('status');
const personaSel = document.getElementById('personaSelect');
const modelSel = document.getElementById('modelSelect');
const healthBtn = document.getElementById('healthBtn');
const tokenInput = document.getElementById('tokenInput');
const cmdHints = document.getElementById('cmdHints');
const SLASH_COMMANDS = [
  '/help - list commands',
  '/memstats - memory counts',
  '/health - health metrics',
  '!search <query> - memory/web search (tool)',
  '!time now - show current time (tool)',
  '!calc 2+2*5 - calculator (tool)'
];

function authHeaders(extra={}) {
  const h = { ...extra };
  if (!h['Content-Type']) h['Content-Type'] = 'application/json';
  if (tokenInput.value.trim()) h['X-API-TOKEN'] = tokenInput.value.trim();
  return h;
}

function addMessage(role, text) {
  const div = document.createElement('div');
  div.className = `msg ${role}`;
  div.textContent = text;
  const ts = document.createElement('span');
  ts.className = 'timestamp';
  ts.textContent = new Date().toLocaleTimeString();
  div.appendChild(ts);
  chatPane.appendChild(div);
  chatPane.scrollTop = chatPane.scrollHeight;
}

async function sendMessage() {
  const message = userInput.value.trim();
  if (!message) return;
  addMessage('user', message);
  userInput.value = '';
  resizeTextarea();
  statusEl.textContent = '...';
  try {
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message, persona: personaSel.value, model: modelSel.value })
    });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || 'Error');
    addMessage('ai', data.response);
  } catch (e) {
    addMessage('ai', 'Error: ' + e.message);
  } finally {
    statusEl.textContent = '';
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

async function loadMemory() {
  try {
  const r = await fetch('/api/memory', { headers: authHeaders({}) });
    const data = await r.json();
    if (data.error) return;
    const profileUl = document.getElementById('profileList');
    profileUl.innerHTML = '';
    Object.entries(data.profile || {}).forEach(([k,v]) => {
      const li = document.createElement('li'); li.textContent = `${k}: ${v}`; profileUl.appendChild(li);
    });
    const summaryUl = document.getElementById('summaryList');
    summaryUl.innerHTML='';
    (data.summaries||[]).forEach(s => { const li=document.createElement('li'); li.textContent=s.summary_text; summaryUl.appendChild(li); });
    const insightUl = document.getElementById('insightList');
    insightUl.innerHTML='';
    (data.insights||[]).forEach(s => { const li=document.createElement('li'); li.textContent=s.insight_text; insightUl.appendChild(li); });
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

async function loadHealth() {
  try {
  const r = await fetch('/api/health', { headers: authHeaders({}) });
    const data = await r.json();
    if (data.error) return;
    const pre = document.getElementById('metricsOut');
    const lines = [];
    lines.push('Interactions: ' + (data.metrics?.total_interactions || 0));
    Object.entries(data.metrics?.models || {}).forEach(([m, info]) => {
      lines.push(`- ${m}: count=${info.count} avg=${info.avg_latency_ms}ms p95=${info.p95_latency_ms}ms`);
    });
    lines.push('');
    lines.push('Memory: facts=' + data.memory.profile_facts + ' summaries=' + data.memory.summaries + ' insights=' + data.memory.insights);
  lines.push('Refreshed: ' + new Date().toLocaleTimeString());
  pre.textContent = lines.join('\n');
  } catch {}
}

healthBtn.addEventListener('click', () => { loadHealth(); loadMemory(); });

// Slash command hints
userInput.addEventListener('input', () => {
  const v = userInput.value;
  if (v.startsWith('/') || v.startsWith('!')) {
    const q = v.toLowerCase();
    const matches = SLASH_COMMANDS.filter(c => c.startsWith(q) || c.includes(q.split(' ')[0]));
    if (matches.length) {
      cmdHints.style.display = 'block';
      cmdHints.innerHTML = matches.slice(0,6).map(m => `<div data-cmd="${m.split(' ')[0]}">${m}</div>`).join('');
      [...cmdHints.children].forEach(div => div.addEventListener('click', () => {
        userInput.value = div.dataset.cmd + ' ';
        resizeTextarea();
        cmdHints.style.display='none';
        userInput.focus();
      }));
    } else {
      cmdHints.style.display='none';
    }
  } else {
    cmdHints.style.display='none';
  }
});
document.addEventListener('click', e => { if(!cmdHints.contains(e.target) && e.target!==userInput) cmdHints.style.display='none'; });

async function initConfig() {
  try {
    const r = await fetch('/api/config');
    const data = await r.json();
    if (data.auth_required) tokenInput.style.display='inline-block';
  } catch {}
}

// Initial load
initConfig();
loadMemory();
loadHealth();

