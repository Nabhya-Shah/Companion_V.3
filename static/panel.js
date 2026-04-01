// ============================================
// Companion AI — Side Panel & Settings Modal Chrome
// ============================================
import { bus, state, authHeaders } from './utils.js';
import { loadMemory } from './memory.js';
import { loadBrainFiles, loadRecentUploads } from './memory.js';
import { loadTasks, startTasksPolling, stopTasksPolling } from './tasks.js';
import { loadTokenStats, loadModelsPanel, loadMetrics, loadSettings, loadQueueDiagnostics, loadMigrationReadiness } from './settings.js';
import { loadSmartHomeHealth, loadSmartHomeRooms, startSmartHomePolling, stopSmartHomePolling } from './smarthome.js';
import { attachChipListeners, renderHistory } from './chat.js';

// ---- DOM refs ----
const sidePanel      = document.getElementById('sidePanel');
const closePanelBtn  = document.getElementById('closePanelBtn');
const settingsModal  = document.getElementById('settingsModal');
const toggleSettingsBtn = document.getElementById('toggleSettingsBtn');
const closeSettingsBtn  = document.getElementById('closeSettingsBtn');
const shutdownBtn    = document.getElementById('shutdownBtn');
const exportChatBtn  = document.getElementById('exportChatBtn');
const clearMemoryBtn = document.getElementById('clearMemoryBtn');
const clearChatBtn   = document.getElementById('clearChatBtn');
const chatPane       = document.getElementById('chatPane');

// ============================================
// Panel Open / Close / Toggle
// ============================================
const panelLabels = { tasks: 'Tasks', memory: 'Memory', knowledge: 'Knowledge', stats: 'Stats', smarthome: 'Smart Home' };

export function openPanel(tabName) {
  sidePanel?.classList.add('visible');
  const titleEl = document.getElementById('panelTitle');
  if (titleEl) titleEl.textContent = panelLabels[tabName] || tabName;
  document.querySelectorAll('.panel-pane').forEach(p => p.classList.remove('active'));
  document.getElementById('pane-' + tabName)?.classList.add('active');
  document.querySelectorAll('.icon-btn[data-panel]').forEach(b => {
    b.classList.toggle('panel-active', b.dataset.panel === tabName);
  });
  onPanelTabSwitch(tabName);
}

export function closePanel() {
  sidePanel?.classList.remove('visible');
  document.querySelectorAll('.icon-btn[data-panel]').forEach(b => b.classList.remove('panel-active'));
  stopTasksPolling();
  stopSmartHomePolling();
}

export function togglePanel(tabName) {
  const isOpen = sidePanel?.classList.contains('visible');
  const currentTab = document.querySelector('.icon-btn.panel-active')?.dataset.panel;
  if (isOpen && currentTab === tabName) closePanel();
  else openPanel(tabName);
}

function onPanelTabSwitch(tabName) {
  stopTasksPolling();
  stopSmartHomePolling();
  if (tabName === 'tasks')     { loadTasks(); startTasksPolling(); }
  if (tabName === 'memory')    { loadMemory(); }
  if (tabName === 'knowledge') { loadBrainFiles(); loadRecentUploads(); }
  if (tabName === 'stats')     { loadTokenStats(); loadModelsPanel(); loadMetrics(); loadQueueDiagnostics(); loadMigrationReadiness(); }
  if (tabName === 'smarthome') { loadSmartHomeHealth(); loadSmartHomeRooms(); startSmartHomePolling(); }
}

// ============================================
// Init — wire up panel + modal event listeners
// ============================================
export function initPanel() {
  // Topbar icon clicks → toggle panel
  document.querySelectorAll('.icon-btn[data-panel]').forEach(btn => {
    btn.addEventListener('click', () => togglePanel(btn.dataset.panel));
  });

  closePanelBtn?.addEventListener('click', closePanel);

  // Settings modal chrome
  toggleSettingsBtn?.addEventListener('click', () => settingsModal.classList.add('visible'));
  closeSettingsBtn?.addEventListener('click', () => settingsModal.classList.remove('visible'));
  settingsModal?.addEventListener('click', (e) => {
    if (e.target === settingsModal) settingsModal.classList.remove('visible');
  });

  // Shutdown
  if (shutdownBtn) {
    shutdownBtn.addEventListener('click', async () => {
      if (!confirm('Are you sure you want to shut down the server? This will trigger a persona evolution check.')) return;
      showToast('Shutting down server...', 'info');
      try {
        const res = await fetch('/api/shutdown', { method: 'POST', headers: authHeaders(), body: JSON.stringify({}) });
        if (res.ok) { showToast('Server shutdown complete. You can close this tab.', 'success'); setTimeout(() => window.close(), 2000); }
        else showToast('Shutdown failed', 'error');
      } catch (err) { console.error(err); showToast('Connection lost (Server likely down)', 'success'); }
    });
  }

  // Export chat history
  exportChatBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    try {
      const resp = await fetch('/api/chat/history', { headers: authHeaders() });
      if (!resp.ok) throw new Error('Failed to fetch history');
      const data = await resp.json();

      let text = 'Companion AI - Chat History\n' + '='.repeat(40) + '\n\n';
      (data.history || []).forEach(entry => {
        if (entry.user) text += `You: ${entry.user}\n\n`;
        if (entry.ai) text += `Companion: ${entry.ai}\n\n`;
        text += '---\n\n';
      });

      const blob = new Blob([text], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `companion-chat-${new Date().toISOString().split('T')[0]}.txt`;
      a.click();
      URL.revokeObjectURL(url);
      settingsModal.classList.remove('visible');
    } catch (err) { console.error('Export failed:', err); alert('Failed to export chat history'); }
  });

  // Clear memory (with confirmation)
  clearMemoryBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    if (!confirm('Are you sure you want to clear all memory? This cannot be undone.')) return;
    try {
      await fetch('/api/memory/clear', { method: 'POST', headers: authHeaders() });
      await fetch('/api/debug/reset', { method: 'POST', headers: authHeaders() });

      chatPane.innerHTML = '';
      const welcome = document.createElement('div');
      welcome.className = 'welcome-screen';
      welcome.id = 'welcomeScreen';
      welcome.innerHTML = `
        <div class="welcome-icon">✨</div>
        <h1>Fresh start</h1>
        <p>Memory cleared - let's begin again!</p>
        <div class="suggestion-chips">
          <button class="chip" data-prompt="Tell me about yourself">Hi, who are you?</button>
          <button class="chip" data-prompt="What can you help me with?">What can you do?</button>
        </div>
      `;
      chatPane.appendChild(welcome);
      attachChipListeners();
      state.lastHistoryLength = 0;
      settingsModal.classList.remove('visible');
      loadMemory();
    } catch (err) { console.error('Clear memory failed:', err); alert('Failed to clear memory'); }
  });

  // Clear chat only (keep memory)
  clearChatBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    if (!confirm('Clear chat history? Your memory (facts about you) will be preserved.')) return;
    try {
      await fetch('/api/debug/reset', { method: 'POST', headers: authHeaders() });

      chatPane.innerHTML = '';
      const welcome = document.createElement('div');
      welcome.className = 'welcome-screen';
      welcome.id = 'welcomeScreen';
      welcome.innerHTML = `
        <div class="welcome-icon">✨</div>
        <h1>Chat cleared</h1>
        <p>Your memories are still intact!</p>
        <div class="suggestion-chips">
          <button class="chip" data-prompt="What do you know about me?">What do you remember?</button>
          <button class="chip" data-prompt="Let's talk about something new">Start fresh topic</button>
        </div>
      `;
      chatPane.appendChild(welcome);
      attachChipListeners();
      state.lastHistoryLength = 0;
      settingsModal.classList.remove('visible');
    } catch (err) { console.error('Clear chat failed:', err); alert('Failed to clear chat'); }
  });
}
