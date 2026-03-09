// ============================================
// Companion AI — App Entry Point (ES Module)
// ============================================
// This is the slim entry point that imports and initialises all modules.
// The heavy lifting lives in the domain modules:
//   utils.js      — shared state, event bus, helpers
//   chat.js       — pipeline, messages, streaming, SSE, attachments, voice
//   panel.js      — side panel, settings modal chrome
//   memory.js     — memory facts, insights, knowledge base
//   tasks.js      — background tasks, schedules, workflows, approvals, plan tracker
//   settings.js   — theme, models, metrics, token stats, budget
//   smarthome.js  — Loxone smart-home controls

import { state } from './utils.js';
import { initChat, attachChipListeners, syncChatHistory, updateSendButton, startSSE, setupVoiceInput } from './chat.js';
import { initPanel } from './panel.js';
import { initMemory } from './memory.js';
import { loadTasks, initTasks } from './tasks.js';
import { loadSettings, loadModelsPanel, loadMetrics, loadTokenStats, loadTokenBudget, initSettings } from './settings.js';
import { initSmartHome } from './smarthome.js';

// ---- Bootstrap on DOM ready ----
// (ES modules are deferred by default, but we wrap in DOMContentLoaded
//  for safety with any late-injected HTML.)
document.addEventListener('DOMContentLoaded', () => {
  // Phase 1 — Wire up event listeners (each init registers its own)
  initChat();
  initPanel();
  initMemory();
  initTasks();
  initSettings();
  initSmartHome();

  // Phase 2 — Initial data loads
  attachChipListeners();
  state.lastHistoryLength = -1; // Force initial sync
  syncChatHistory();
  loadModelsPanel();
  loadMetrics();
  loadTokenStats();
  loadSettings();
  updateSendButton();
  loadTasks();
  loadTokenBudget();

  // Phase 3 — Live updates
  startSSE();
  setupVoiceInput();
});
