// Companion AI - Modern Chat UI JavaScript

// ============================================
// DOM Elements
// ============================================
const chatPane = document.getElementById('chatPane');
const welcomeScreen = document.getElementById('welcomeScreen');
const userInput = document.getElementById('userInput');
const sendBtn = document.getElementById('sendBtn');
const toggleMemoryBtn = document.getElementById('toggleMemoryBtn');
const toggleSettingsBtn = document.getElementById('toggleSettingsBtn');
const toggleTasksBtn = document.getElementById('toggleTasksBtn');
const shutdownBtn = document.getElementById('shutdownBtn');
const closeMemoryBtn = document.getElementById('closeMemoryBtn');
const closeSettingsBtn = document.getElementById('closeSettingsBtn');
const closeTasksBtn = document.getElementById('closeTasksBtn');
const memorySidebar = document.getElementById('memorySidebar');
const tasksSidebar = document.getElementById('tasksSidebar');
const settingsModal = document.getElementById('settingsModal');
const refreshMetricsBtn = document.getElementById('refreshMetricsBtn');
const exportChatBtn = document.getElementById('exportChatBtn');
const clearMemoryBtn = document.getElementById('clearMemoryBtn');
const clearChatBtn = document.getElementById('clearChatBtn');
const stopBtn = document.getElementById('stopBtn');
const tasksList = document.getElementById('tasksList');
const tasksEmpty = document.getElementById('tasksEmpty');
const taskCountBadge = document.getElementById('taskCountBadge');

// Attachment elements
const attachBtn = document.getElementById('attachBtn');
const fileInput = document.getElementById('fileInput');
const attachmentPreview = document.getElementById('attachmentPreview');
const previewImage = document.getElementById('previewImage');
const previewName = document.getElementById('previewName');
const removeAttachment = document.getElementById('removeAttachment');

// ============================================
// State
// ============================================
let API_TOKEN = localStorage.getItem('companion_api_token') || '';
let ttsEnabled = localStorage.getItem('companion_tts_enabled') === 'true';
let showTokens = localStorage.getItem('companion_show_tokens') === 'true';
let currentConversation = [];
let lastHistoryLength = -1; // Start at -1 to force initial render
let eventSource = null;
let isStreaming = false; // Prevents SSE from overwriting during streaming
let abortController = null; // For stopping generation
let currentAttachment = null; // Stores current file attachment {file, url, analysis}

// ============================================
// Utilities
// ============================================
function setApiToken(tok) {
  API_TOKEN = tok || '';
  if (tok) localStorage.setItem('companion_api_token', tok);
}

function authHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    ...(API_TOKEN ? { 'X-API-TOKEN': API_TOKEN } : {}),
    ...extra
  };
}

function formatTime(date) {
  return new Date(date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ============================================
// Markdown Rendering
// ============================================
function renderMarkdown(text) {
  if (typeof marked === 'undefined') {
    // Fallback if marked.js not loaded
    return escapeHtml(text).replace(/\n/g, '<br>');
  }

  // Configure marked
  marked.setOptions({
    highlight: function (code, lang) {
      if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
        try {
          return hljs.highlight(code, { language: lang }).value;
        } catch (e) { }
      }
      return code;
    },
    breaks: true,
    gfm: true
  });

  return marked.parse(text);
}

// Add copy buttons to code blocks
function addCopyButtons(container) {
  container.querySelectorAll('pre').forEach(pre => {
    if (pre.querySelector('.code-copy-btn')) return;

    const btn = document.createElement('button');
    btn.className = 'code-copy-btn';
    btn.textContent = 'Copy';
    btn.onclick = async () => {
      const code = pre.querySelector('code')?.textContent || pre.textContent;
      await navigator.clipboard.writeText(code);
      btn.textContent = 'Copied!';
      setTimeout(() => btn.textContent = 'Copy', 2000);
    };
    pre.style.position = 'relative';
    pre.appendChild(btn);
  });
}

// ============================================
// Pipeline Rendering
// ============================================
function renderPipeline(metadata) {
  if (!metadata || !metadata.source) return '';

  const steps = [];

  // Get token steps if available
  const tokenSteps = metadata.token_steps || [];
  const getTokensForStep = (stepName) => {
    return tokenSteps.find(s => s.name === stepName || s.name.includes(stepName));
  };

  // 1. Initial Decision
  const orchTokens = getTokensForStep('orchestrator');
  steps.push({
    type: 'decision',
    title: 'Orchestrator Decision',
    desc: `Route to: ${metadata.source}`,
    data: metadata.source === 'loop_vision' ? 'Visual verification needed' :
      metadata.source === 'loop_tool' ? 'External capabilities required' :
        'Direct conversation',
    tokens: orchTokens
  });

  // 2. Loop Execution
  if (metadata.loop_result) {
    const res = metadata.loop_result;
    const status = res.status || 'unknown';
    const loopType = metadata.source.replace('loop_', '');
    const loopTokens = getTokensForStep(loopType) || getTokensForStep('loop');

    steps.push({
      type: status === 'success' ? 'result' : 'error',
      title: `Loop Execution: ${loopType}`,
      desc: `Status: ${status}`,
      data: res.error ? res.error :
        (res.data ? JSON.stringify(res.data, null, 2) : 'No data returned'),
      tokens: loopTokens
    });
  }

  // 3. Synthesis
  const synthTokens = getTokensForStep('synthesis') || getTokensForStep('generate');
  steps.push({
    type: 'tool',
    title: 'Final Synthesis',
    desc: 'Generating response using 120B model',
    data: null,
    tokens: synthTokens
  });

  const html = steps.map(step => {
    // Extract model type (groq vs local) from model string
    const modelLabel = step.tokens?.model?.includes('groq') ? 'groq' :
      step.tokens?.model?.includes('local') ? 'local' : '';
    const tokenBadge = step.tokens ?
      `<span class="token-badge" title="${step.tokens.input} in / ${step.tokens.output} out @ ${step.tokens.ms}ms (${step.tokens.model || 'unknown'})">
        ${modelLabel ? `<span class="model-label ${modelLabel}">${modelLabel}</span>` : ''}
        <span class="token-count">${step.tokens.total}</span>
        <span class="token-time">${step.tokens.ms}ms</span>
      </span>` : '';

    return `
    <div class="pipeline-step ${step.type}">
      <div class="step-info">
        <div class="step-header">
          <span class="step-type">${step.type}</span>
          <span class="step-title">${step.title}</span>
          ${tokenBadge}
        </div>
        <div class="step-desc">${step.desc}</div>
        ${step.data ? `<div class="step-data">${escapeHtml(step.data)}</div>` : ''}
      </div>
    </div>
  `}).join('');

  return `
    <div class="pipeline-view">
      <div class="pipeline-toggle" onclick="this.classList.toggle('open'); this.nextElementSibling.classList.toggle('open')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
        View Process Pipeline
      </div>
      <div class="pipeline-content">
        ${html}
      </div>
    </div>
  `;
}

// ============================================
// Message Rendering
// ============================================
function createMessageElement(role, text, timestamp, tokens, metadata, attachment) {
  const wrapper = document.createElement('div');
  wrapper.className = 'message-wrapper';

  const message = document.createElement('div');
  message.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = role === 'user' ? '👤' : '✨';

  const content = document.createElement('div');
  content.className = 'message-content';

  const roleLabel = document.createElement('div');
  roleLabel.className = 'message-role';

  // Role label with optional token stats
  const roleName = role === 'user' ? 'You' : 'Companion';
  let tokenHtml = '';
  if (role === 'ai' && tokens && showTokens) {
    const total = (tokens.input || 0) + (tokens.output || 0);
    const source = tokens.source || 'unknown';
    // Color code source
    let sourceColor = '#888';
    if (source === 'groq') sourceColor = '#f97316';
    else if (source === 'local') sourceColor = '#3b82f6';

    tokenHtml = `<span class="token-badge" title="Input: ${tokens.input} | Output: ${tokens.output}">(${total} tokens)</span>`;
    if (source !== 'unknown') {
      tokenHtml += `<span class="source-badge" style="color: ${sourceColor}; margin-left: 6px; font-size: 10px;">${source}</span>`;
    }
  }

  roleLabel.innerHTML = `${roleName} ${tokenHtml}`;

  const textDiv = document.createElement('div');
  textDiv.className = 'message-text';

  if (role === 'ai') {
    textDiv.innerHTML = renderMarkdown(text);
    setTimeout(() => addCopyButtons(textDiv), 0);

    // Append Pipeline View if metadata exists
    if (metadata) {
      const pipelineHtml = renderPipeline(metadata);
      if (pipelineHtml) {
        const pipelineDiv = document.createElement('div');
        pipelineDiv.innerHTML = pipelineHtml;
        textDiv.appendChild(pipelineDiv);
      }
    }
  } else {
    // User message - show attachment image if present
    if (attachment && attachment.isImage && attachment.url) {
      const imgDiv = document.createElement('div');
      imgDiv.className = 'message-attachment';
      imgDiv.innerHTML = `<img src="${attachment.url}" alt="Attached image" onclick="window.open(this.src, '_blank')" style="cursor: pointer;" />`;
      textDiv.appendChild(imgDiv);
    }
    textDiv.innerHTML += escapeHtml(text).replace(/\n/g, '<br>');
  }

  content.appendChild(roleLabel);
  content.appendChild(textDiv);

  // Action buttons
  const actions = document.createElement('div');
  actions.className = 'message-actions';

  const copyBtn = document.createElement('button');
  copyBtn.className = 'action-btn';
  copyBtn.innerHTML = '📋 Copy';
  copyBtn.onclick = async () => {
    await navigator.clipboard.writeText(text);
    copyBtn.innerHTML = '✓ Copied';
    setTimeout(() => copyBtn.innerHTML = '📋 Copy', 2000);
  };
  actions.appendChild(copyBtn);

  content.appendChild(actions);

  message.appendChild(avatar);
  message.appendChild(content);
  wrapper.appendChild(message);

  return wrapper;
}

function createLoadingMessage() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message-wrapper';
  wrapper.id = 'loading-message';

  const message = document.createElement('div');
  message.className = 'message ai loading';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = '✨';

  const content = document.createElement('div');
  content.className = 'message-content';

  const roleLabel = document.createElement('div');
  roleLabel.className = 'message-role';
  roleLabel.textContent = 'Companion';

  const textDiv = document.createElement('div');
  textDiv.className = 'message-text';
  textDiv.innerHTML = '<span class="loading-dot"></span><span class="loading-dot"></span><span class="loading-dot"></span>';

  content.appendChild(roleLabel);
  content.appendChild(textDiv);
  message.appendChild(avatar);
  message.appendChild(content);
  wrapper.appendChild(message);

  return wrapper;
}

function addMessage(role, text, timestamp, tokens, metadata, attachment) {
  // Hide welcome screen on first message
  if (welcomeScreen && welcomeScreen.parentNode) {
    welcomeScreen.remove();
  }

  const messageEl = createMessageElement(role, text, timestamp, tokens, metadata, attachment);
  chatPane.appendChild(messageEl);
  scrollToBottom();
}

function scrollToBottom(instant = false) {
  setTimeout(() => {
    chatPane.scrollTo({
      top: chatPane.scrollHeight,
      behavior: instant ? 'auto' : 'smooth'
    });
  }, 50);
}

// ============================================
// Chat Functions
// ============================================
async function sendMessage(retry = false) {
  let message = userInput.value.trim();
  if (!message && !currentAttachment) return;

  // If there's an attachment with analysis, append the context to the message
  let attachmentContext = '';
  if (currentAttachment && currentAttachment.analysis) {
    // Use wording that won't trigger the orchestrator to re-delegate to vision
    attachmentContext = `\n\n[Visual context from user's uploaded file: ${currentAttachment.analysis}]`;
    // If user didn't type anything, just ask about the image
    if (!message) {
      message = "What can you tell me about this?";
    }
  }

  const fullMessage = message + attachmentContext;

  // Save attachment info before clearing (for display in chat)
  const messageAttachment = currentAttachment ? {
    isImage: currentAttachment.isImage,
    url: currentAttachment.url,
    name: currentAttachment.name
  } : null;

  // Add user message with attachment preview
  addMessage('user', message, null, null, null, messageAttachment);
  userInput.value = '';
  resizeTextarea();
  updateSendButton();

  // Clear attachment after sending
  clearAttachment();

  // Create streaming AI message structure
  const wrapper = document.createElement('div');
  wrapper.className = 'message-wrapper';

  const aiMsgEl = document.createElement('div');
  aiMsgEl.className = 'message ai';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.textContent = '✨';

  const content = document.createElement('div');
  content.className = 'message-content';

  const roleLabel = document.createElement('div');
  roleLabel.className = 'message-role';
  roleLabel.textContent = 'Companion';

  const textDiv = document.createElement('div');
  textDiv.className = 'message-text';
  textDiv.innerHTML = '<span class="text-content"></span><span class="streaming-cursor">▋</span>';

  content.appendChild(roleLabel);
  content.appendChild(textDiv);
  aiMsgEl.appendChild(avatar);
  aiMsgEl.appendChild(content);
  wrapper.appendChild(aiMsgEl);
  chatPane.appendChild(wrapper);
  scrollToBottom();

  const textEl = textDiv.querySelector('.text-content');
  const cursorEl = textDiv.querySelector('.streaming-cursor');

  // Set streaming flag
  isStreaming = true;

  // Show stop button
  if (stopBtn) stopBtn.style.display = 'flex';
  if (sendBtn) sendBtn.style.display = 'none';

  // Typewriter state
  let displayedText = '';
  let pendingText = '';
  let isTyping = false;
  let receivedMetadata = null;

  // Smooth typewriter effect
  async function typeNextChar() {
    if (pendingText.length === 0) {
      isTyping = false;
      return;
    }
    isTyping = true;

    const charsToType = Math.min(pendingText.length, Math.random() > 0.7 ? 2 : 1);
    const chars = pendingText.slice(0, charsToType);
    pendingText = pendingText.slice(charsToType);
    displayedText += chars;

    textEl.textContent = displayedText;
    scrollToBottom();

    let delay = 15 + Math.random() * 10;
    if (chars.includes('.') || chars.includes('!') || chars.includes('?')) {
      delay = 80 + Math.random() * 40;
    } else if (chars.includes(',')) {
      delay = 40 + Math.random() * 20;
    }

    setTimeout(typeNextChar, delay);
  }

  function queueText(text) {
    pendingText += text;
    if (!isTyping) {
      typeNextChar();
    }
  }

  abortController = new AbortController();

  try {
    const resp = await fetch('/api/chat/send', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message: fullMessage, tts_enabled: ttsEnabled }),
      signal: abortController.signal
    });

    if (resp.status === 401 && !retry) {
      const tok = prompt('API token required. Enter token:');
      if (tok) {
        setApiToken(tok);
        wrapper.remove();
        return sendMessage(true);
      }
    }

    if (!resp.ok) {
      const data = await resp.json();
      throw new Error(data.error || 'Error');
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value);
      const lines = text.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6));

            // Handle metadata event
            if (data.meta) {
              receivedMetadata = data.meta;
              // Optional: Show "Processing..." indicator or update status immediately
              console.log("Pipeline metadata received:", receivedMetadata);
            }

            // Handle token_meta event (sent after streaming with token_steps)
            if (data.token_meta) {
              receivedMetadata = { ...receivedMetadata, ...data.token_meta };
              console.log("Token metadata received:", data.token_meta);
            }

            if (data.chunk) {
              queueText(data.chunk);
              // Reset emergency timeout on each chunk
              if (window._streamingEmergencyTimeout) {
                clearTimeout(window._streamingEmergencyTimeout);
              }
              window._streamingEmergencyTimeout = setTimeout(() => {
                if (isStreaming) {
                  console.warn("Emergency timeout: forcing stream end after 5s of no data");
                  isStreaming = false;
                  abortController = null;
                  if (window.stopBtn) window.stopBtn.style.display = 'none';
                  if (window.sendBtn) window.sendBtn.style.display = 'flex';
                }
              }, 5000);
            }

            if (data.done) {
              // Clear emergency timeout on proper done
              if (window._streamingEmergencyTimeout) {
                clearTimeout(window._streamingEmergencyTimeout);
              }
              // Update token stats in UI
              if (data.tokens && showTokens) {
                // ... (existing token update logic)
                const total = (data.tokens.input || 0) + (data.tokens.output || 0);
                const source = data.tokens.source || 'unknown';
                roleLabel.innerHTML = `Companion <span class="token-badge">(${total} tokens)</span> <span style="font-size:10px; opacity:0.7">[${source}]</span>`;
                loadTokenStats();
              }

              if (data.memory_saved && window.showToast) {
                showToast("Memory Updated ✨", "success");
              }
            }

            if (data.error) throw new Error(data.error);
          } catch (parseErr) { }
        }
      }
    }

    // Wait for typing to finish
    const waitForTyping = () => {
      if (pendingText.length > 0 || isTyping) {
        setTimeout(waitForTyping, 50);
      } else {
        // Fade out cursor
        cursorEl.style.transition = 'opacity 0.3s';
        cursorEl.style.opacity = '0';
        setTimeout(() => {
          cursorEl.remove();

          // Render markdown final
          textDiv.innerHTML = renderMarkdown(displayedText);
          addCopyButtons(textDiv);

          // Render Pipeline if metadata exists
          if (receivedMetadata) {
            const pipelineHtml = renderPipeline(receivedMetadata);
            const pipelineDiv = document.createElement('div');
            pipelineDiv.innerHTML = pipelineHtml;
            textDiv.appendChild(pipelineDiv);
          }

          isStreaming = false;
          abortController = null;
          if (stopBtn) stopBtn.style.display = 'none';
          if (sendBtn) sendBtn.style.display = 'flex';
          lastHistoryLength++;
          loadTokenStats();
        }, 300);
      }
    };
    waitForTyping();

  } catch (e) {
    // ... (existing error handling)
    isStreaming = false;
    abortController = null;
    if (e.name === 'AbortError') {
      if (displayedText.trim()) {
        cursorEl.remove();
        textDiv.innerHTML = renderMarkdown(displayedText + '\n\n*[Stopped]*');
      } else {
        wrapper.remove();
      }
      if (stopBtn) stopBtn.style.display = 'none';
      if (sendBtn) sendBtn.style.display = 'flex';
      return;
    }
    wrapper.remove();
    addMessage('ai', 'Error: ' + e.message);
  }
}

// Stop current generation (ESC key or Stop button)
function stopGeneration() {
  if (abortController && isStreaming) {
    abortController.abort();
    abortController = null;
  }
}

function resizeTextarea() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
}

function updateSendButton() {
  sendBtn.disabled = !userInput.value.trim();
}

// ============================================
// Sidebar Toggles
// ============================================
toggleMemoryBtn?.addEventListener('click', () => {
  memorySidebar.classList.toggle('visible');
});

// Note: toggleTasksBtn listener is at bottom with polling logic

toggleSettingsBtn?.addEventListener('click', () => {
  settingsModal.classList.add('visible');
});

closeMemoryBtn?.addEventListener('click', () => {
  memorySidebar.classList.remove('visible');
});

// Note: closeTasksBtn listener is at bottom with polling logic

closeSettingsBtn?.addEventListener('click', () => {
  settingsModal.classList.remove('visible');
});

// Close modal on overlay click
settingsModal?.addEventListener('click', (e) => {
  if (e.target === settingsModal) {
    settingsModal.classList.remove('visible');
  }
});

// Export chat history
exportChatBtn?.addEventListener('click', async (e) => {
  e.preventDefault();
  try {
    const resp = await fetch('/api/chat/history', { headers: authHeaders() });
    if (!resp.ok) throw new Error('Failed to fetch history');
    const data = await resp.json();

    // Format as readable text
    let text = 'Companion AI - Chat History\n';
    text += '='.repeat(40) + '\n\n';

    (data.history || []).forEach(entry => {
      if (entry.user) text += `You: ${entry.user}\n\n`;
      if (entry.ai) text += `Companion: ${entry.ai}\n\n`;
      text += '---\n\n';
    });

    // Download as file
    const blob = new Blob([text], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `companion-chat-${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);

    settingsModal.classList.remove('visible');
  } catch (err) {
    console.error('Export failed:', err);
    alert('Failed to export chat history');
  }
});

// Clear memory (with confirmation)
clearMemoryBtn?.addEventListener('click', async (e) => {
  e.preventDefault();
  if (!confirm('Are you sure you want to clear all memory? This cannot be undone.')) return;

  try {
    // 1. Clear actual memory (SQLite + Mem0)
    await fetch('/api/memory/clear', { method: 'POST', headers: authHeaders() });

    // 2. Reset conversation history
    await fetch('/api/debug/reset', { method: 'POST', headers: authHeaders() });

    // Clear UI
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

    lastHistoryLength = 0;
    settingsModal.classList.remove('visible');
    loadMemory(); // Refresh memory panel
  } catch (err) {
    console.error('Clear memory failed:', err);
    alert('Failed to clear memory');
  }
});

// Clear chat only (keep memory)
clearChatBtn?.addEventListener('click', async (e) => {
  e.preventDefault();
  if (!confirm('Clear chat history? Your memory (facts about you) will be preserved.')) return;

  try {
    // Just reset conversation, not memory
    await fetch('/api/debug/reset', { method: 'POST', headers: authHeaders() });

    // Clear UI
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

    lastHistoryLength = 0;
    settingsModal.classList.remove('visible');
  } catch (err) {
    console.error('Clear chat failed:', err);
    alert('Failed to clear chat');
  }
});

// ============================================
// Suggestion Chips
// ============================================
function attachChipListeners() {
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt;
      if (prompt) {
        userInput.value = prompt;
        updateSendButton();
        userInput.focus();
      }
    });
  });
}

// ============================================
// Tabs
// ============================================
document.querySelectorAll('.tab').forEach(tab => {
  tab.addEventListener('click', () => {
    document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
    document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
    tab.classList.add('active');
    document.getElementById('pane-' + tab.dataset.tab)?.classList.add('active');
  });
});

// ============================================
// Memory Loading
// ============================================
async function loadMemory(retry = false) {
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

    // Update stats
    document.getElementById('memFactCount').textContent = detailed.length;
    document.getElementById('memInsightCount').textContent = insights.length;
    document.getElementById('memSummaryCount').textContent = summaries.length;

    // Profile facts as cards with delete capability
    const profileDiv = document.getElementById('profileList');
    if (profileDiv) {
      profileDiv.innerHTML = '';
      // Show ALL facts, not just first 10, since Mem0 might have many
      detailed.forEach(row => {
        const card = document.createElement('div');
        card.className = 'fact-card';
        card.dataset.key = row.key;
        card.title = 'Click to delete this fact';

        const confLabel = row.confidence_label || (row.confidence >= 0.8 ? 'high' : row.confidence >= 0.5 ? 'medium' : 'low');

        card.innerHTML = `
          <div class="fact-key" style="display:none">${row.key}</div>
          <div class="fact-value">${row.value}</div>
          <div class="fact-meta">
            <span class="fact-confidence ${confLabel}">${confLabel}</span>
            ${row.reaffirmations ? `<span>×${row.reaffirmations} confirmed</span>` : ''}
          </div>
        `;

        card.addEventListener('click', () => deleteFact(row.key, card));
        profileDiv.appendChild(card);
      });
      if (!detailed.length) {
        profileDiv.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; padding: 12px;">No facts stored yet. Chat with me so I can learn about you!</div>';
      }
    }

    // Insights as cards
    const insightDiv = document.getElementById('insightList');
    if (insightDiv) {
      insightDiv.innerHTML = '';
      insights.slice(0, 5).forEach(s => {
        const card = document.createElement('div');
        card.className = 'insight-card';
        card.textContent = s.insight_text;
        insightDiv.appendChild(card);
      });
      if (!insights.length) {
        insightDiv.innerHTML = '<div style="color: var(--text-muted); font-size: 13px; padding: 12px;">No insights yet</div>';
      }
    }
  } catch (e) {
    console.error('Failed to load memory:', e);
  }
}

// Delete a single fact
async function deleteFact(key, cardElement) {
  // For Mem0, the key is a UUID which isn't user friendly.
  // We'll show the text content in the confirmation dialog instead.
  const text = cardElement.querySelector('.fact-value').textContent;
  if (!confirm(`Delete memory: "${text}"?`)) return;

  try {
    const r = await fetch(`/api/memory/fact/${encodeURIComponent(key)}`, {
      method: 'DELETE',
      headers: authHeaders()
    });

    if (r.ok) {
      cardElement.style.opacity = '0';
      cardElement.style.transform = 'translateX(-20px)';
      setTimeout(() => {
        cardElement.remove();
        // Update count
        const countEl = document.getElementById('memFactCount');
        if (countEl) countEl.textContent = parseInt(countEl.textContent) - 1;
      }, 200);
    } else {
      const errText = await r.text();
      console.error('Delete failed:', r.status, errText);
      alert(`Failed to delete fact: ${r.status} ${errText}`);
    }
  } catch (e) {
    console.error('Delete fact failed:', e);
    alert('Failed to delete fact');
  }
}

document.getElementById('refreshMemoryBtn')?.addEventListener('click', loadMemory);

// ============================================
// Models Panel
// ============================================
async function loadModelsPanel(retry = false) {
  const modelCards = document.getElementById('modelCards');
  const featureFlags = document.getElementById('featureFlags');
  if (!modelCards) return;

  try {
    const r = await fetch('/api/models', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) { setApiToken(tok); return loadModelsPanel(true); }
      return;
    }

    const d = await r.json();
    if (d.error) return;

    // Model cards
    modelCards.innerHTML = '';
    if (d.models) {
      const roles = [
        ['Primary', d.models.PRIMARY_MODEL],
        ['Tools', d.models.TOOLS_MODEL],
        ['Vision', d.models.VISION_MODEL],
        ['Compound', d.models.COMPOUND_MODEL]
      ];
      roles.forEach(([role, model]) => {
        const shortName = model?.split('/').pop() || 'N/A';
        const card = document.createElement('div');
        card.className = 'model-card';
        card.innerHTML = `
          <span class="model-role">${role}</span>
          <span class="model-name" title="${model}">${shortName}</span>
        `;
        modelCards.appendChild(card);
      });
    }

    // Feature flags
    if (featureFlags) {
      featureFlags.innerHTML = '';
      Object.entries(d.flags || {}).forEach(([k, v]) => {
        const flag = document.createElement('div');
        flag.className = 'feature-flag';
        flag.innerHTML = `
          <span class="flag-dot ${v ? 'on' : 'off'}"></span>
          <span class="flag-name">${k.replace('ENABLE_', '')}</span>
        `;
        featureFlags.appendChild(flag);
      });
    }
  } catch (e) {
    console.error('Failed to load models:', e);
  }
}

// ============================================
// Metrics
// ============================================
async function loadMetrics(retry = false) {
  try {
    const r = await fetch('/api/health', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) { setApiToken(tok); return loadMetrics(true); }
      return;
    }

    const data = await r.json();

    // Update summary stats
    const interactions = data.metrics?.total_interactions || 0;
    const toolCalls = data.metrics?.tools?.total_invocations || 0;

    const interactionsEl = document.getElementById('metricInteractions');
    const latencyEl = document.getElementById('metricAvgLatency');
    const toolsEl = document.getElementById('metricToolCalls');

    if (interactionsEl) interactionsEl.textContent = interactions;
    if (toolsEl) toolsEl.textContent = toolCalls;

    // Calculate overall average latency
    let totalLatency = 0;
    let modelCount = 0;
    const models = data.metrics?.models || {};

    Object.values(models).forEach(info => {
      if (info.avg_latency_ms) {
        totalLatency += info.avg_latency_ms;
        modelCount++;
      }
    });

    const avgLatency = modelCount > 0 ? Math.round(totalLatency / modelCount) : 0;
    if (latencyEl) latencyEl.textContent = avgLatency + 'ms';

    // Build latency bars
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
            <div class="latency-bar-bg">
              <div class="latency-bar-fill" style="width: ${pct}%; background: ${color}"></div>
            </div>
            <span class="latency-value">${info.avg_latency_ms || 0}ms</span>
          </div>`;
      });

      if (barsHtml === '') {
        barsHtml = '<div class="empty-state">No latency data yet</div>';
      }

      latencyBars.innerHTML = barsHtml;
    }
  } catch (e) {
    console.error('Failed to load metrics:', e);
  }
}

refreshMetricsBtn?.addEventListener('click', loadMetrics);

// ============================================
// Token Stats
// ============================================
async function loadTokenStats(retry = false) {
  try {
    const r = await fetch('/api/tokens', { headers: authHeaders() });
    if (r.status === 401 && !retry) {
      const tok = prompt('API token required:');
      if (tok) { setApiToken(tok); return loadTokenStats(true); }
      return;
    }

    const data = await r.json();

    // Update totals
    const total = (data.total_input || 0) + (data.total_output || 0);
    document.getElementById('tokenTotal').textContent = total.toLocaleString();
    document.getElementById('tokenInput').textContent = (data.total_input || 0).toLocaleString();
    document.getElementById('tokenOutput').textContent = (data.total_output || 0).toLocaleString();
    document.getElementById('tokenRequests').textContent = data.requests || 0;

    // Update by-model breakdown
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

document.getElementById('refreshTokensBtn')?.addEventListener('click', loadTokenStats);

document.getElementById('resetTokensBtn')?.addEventListener('click', async () => {
  try {
    await fetch('/api/tokens/reset', { method: 'POST', headers: authHeaders() });
    loadTokenStats();
  } catch (e) {
    console.error('Failed to reset tokens:', e);
  }
});

// ============================================
// Daily Token Budget (Groq limits)
// ============================================
async function loadTokenBudget() {
  try {
    const r = await fetch('/api/token-budget', { headers: authHeaders() });
    if (!r.ok) return;

    const data = await r.json();

    // Create or update the budget display in header
    let budgetEl = document.getElementById('tokenBudgetDisplay');
    if (!budgetEl) {
      // Create the element if it doesn't exist
      budgetEl = document.createElement('div');
      budgetEl.id = 'tokenBudgetDisplay';
      budgetEl.style.cssText = `
        position: fixed;
        top: 10px;
        left: 50%;
        transform: translateX(-50%);
        background: var(--surface-secondary, #1a1a2e);
        padding: 8px 14px;
        border-radius: 8px;
        font-size: 12px;
        z-index: 1000;
        display: flex;
        align-items: center;
        gap: 8px;
        border: 1px solid var(--border-color, #333);
      `;
      document.body.appendChild(budgetEl);
    }

    const percent = data.percent || 0;
    const used = data.used || 0;
    const limit = data.limit || 500000;

    // Color based on usage
    let color = '#4ade80'; // green
    let icon = '🟢';
    if (data.warning) {
      color = '#fbbf24'; // yellow
      icon = '🟡';
    }
    if (data.critical) {
      color = '#ef4444'; // red
      icon = '🔴';
    }

    budgetEl.innerHTML = `
      <span>${icon}</span>
      <span style="color: ${color}; font-weight: 600;">${percent.toFixed(1)}%</span>
      <span style="color: var(--text-muted, #888);">
        ${(used / 1000).toFixed(0)}K / ${(limit / 1000000).toFixed(1)}M tokens today
      </span>
    `;

    // Auto-refresh every 30 seconds
    setTimeout(loadTokenBudget, 30000);
  } catch (e) {
    console.error('Failed to load token budget:', e);
  }
}

// Load token budget on startup
loadTokenBudget();

// ============================================
// Settings
// ============================================
async function loadSettings() {
  const ttsToggle = document.getElementById('ttsToggle');
  const voiceSelect = document.getElementById('voiceSelect');
  const rateSelect = document.getElementById('rateSelect');
  const visionToggle = document.getElementById('visionToggle');
  const visionStatus = document.getElementById('visionStatus');
  const showTokensToggle = document.getElementById('showTokensToggle');

  // Show Tokens toggle
  if (showTokensToggle) {
    showTokensToggle.checked = showTokens;
    showTokensToggle.addEventListener('change', (e) => {
      showTokens = e.target.checked;
      localStorage.setItem('companion_show_tokens', showTokens);
      // Re-render chat to show/hide tokens
      renderHistory(currentConversation);
    });
  }

  // TTS toggle
  if (ttsToggle) {
    ttsToggle.checked = ttsEnabled;
    ttsToggle.addEventListener('change', () => {
      ttsEnabled = ttsToggle.checked;
      localStorage.setItem('companion_tts_enabled', ttsEnabled);
    });
  }

  try {
    // Load voices
    const vResp = await fetch('/api/tts/voices', { headers: authHeaders() });
    const vData = await vResp.json();

    if (vData.voices && voiceSelect) {
      voiceSelect.innerHTML = '';
      vData.voices.forEach(v => {
        const opt = document.createElement('option');
        opt.value = v;
        opt.textContent = v.replace('en-US-', '').replace('Neural', '');
        voiceSelect.appendChild(opt);
      });
    }

    // Load current config
    const cResp = await fetch('/api/tts/config', { headers: authHeaders() });
    const cData = await cResp.json();

    if (cData.voice && voiceSelect) voiceSelect.value = cData.voice;
    if (cData.rate && rateSelect) rateSelect.value = cData.rate;

    // Voice change handler
    voiceSelect?.addEventListener('change', async () => {
      await fetch('/api/tts/config', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ voice: voiceSelect.value })
      });
    });

    rateSelect?.addEventListener('change', async () => {
      await fetch('/api/tts/config', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({ rate: rateSelect.value })
      });
    });

    // Vision toggle
    if (visionToggle) {
      const visResp = await fetch('/api/vision/status', { headers: authHeaders() });
      const visData = await visResp.json();
      visionToggle.checked = visData.enabled;
      if (visionStatus) {
        visionStatus.textContent = visData.enabled ? 'Status: Active' : 'Status: Off';
      }

      visionToggle.addEventListener('change', async () => {
        const resp = await fetch('/api/vision/toggle', {
          method: 'POST',
          headers: authHeaders()
        });
        const data = await resp.json();
        if (visionStatus) {
          visionStatus.textContent = data.enabled ? 'Status: Active' : 'Status: Off';
        }
      });
    }
  } catch (e) {
    console.error('Failed to load settings:', e);
  }
}

// ============================================
// Chat History Sync & SSE (Server-Sent Events)
// ============================================
function renderHistory(history) {
  if (!history || history.length === 0) return;

  // Don't overwrite while streaming - let the typewriter finish
  if (isStreaming) return;

  const totalMessages = history.reduce((n, e) => n + (e.user ? 1 : 0) + (e.ai ? 1 : 0), 0);

  // Skip if no change
  if (totalMessages === lastHistoryLength) return;
  lastHistoryLength = totalMessages;

  // Remove welcome screen
  const welcome = document.getElementById('welcomeScreen');
  if (welcome && welcome.parentNode) {
    welcome.remove();
  }

  // Remove loading indicator if present
  const loading = document.getElementById('loading-message');
  if (loading) loading.remove();

  // Clear and re-render
  chatPane.querySelectorAll('.message-wrapper').forEach(el => el.remove());

  history.forEach(entry => {
    if (entry.user) addMessage('user', entry.user);
    if (entry.ai) addMessage('ai', entry.ai, null, entry.tokens, entry.metadata);
  });

  scrollToBottom(true);
}

async function syncChatHistory() {
  try {
    const resp = await fetch('/api/chat/history', { headers: authHeaders() });
    if (!resp.ok) return;

    const data = await resp.json();
    renderHistory(data.history || []);
  } catch (e) {
    console.error('Failed to sync history:', e);
  }
}

function startSSE() {
  if (eventSource) return;

  eventSource = new EventSource('/api/chat/stream');

  eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      renderHistory(data.history || []);
    } catch (e) {
      console.error('SSE parse error:', e);
    }
  };

  eventSource.onerror = (e) => {
    console.warn('SSE connection error, will auto-reconnect');
    // EventSource auto-reconnects, no action needed
  };
}

function stopSSE() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

// ============================================
// Event Listeners
// ============================================
if (shutdownBtn) {
  shutdownBtn.addEventListener('click', async () => {
    if (!confirm('Are you sure you want to shut down the server? This will trigger a persona evolution check.')) return;

    showToast('Shutting down server...', 'info');
    try {
      const res = await fetch('/api/shutdown', {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({})
      });
      if (res.ok) {
        showToast('Server shutdown complete. You can close this tab.', 'success');
        setTimeout(() => window.close(), 2000);
      } else {
        showToast('Shutdown failed', 'error');
      }
    } catch (err) {
      console.error(err);
      showToast('Connection lost (Server likely down)', 'success');
    }
  });
}

sendBtn.addEventListener('click', sendMessage);

userInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// ESC key to stop generation
document.addEventListener('keydown', e => {
  if (e.key === 'Escape' && isStreaming) {
    e.preventDefault();
    stopGeneration();
  }
});

// Stop button click handler
if (stopBtn) {
  stopBtn.addEventListener('click', stopGeneration);
}

userInput.addEventListener('input', () => {
  resizeTextarea();
  updateSendButton();
});

// ============================================
// Job Polling (Deprecated - using SSE now)
// ============================================
// let notifiedJobs = new Set();
// async function pollJobs() { ... }

// ============================================
// ============================================
// Background Tasks Panel (V6)
// ============================================
let lastTasksSig = "";

async function loadTasks() {
  try {
    const response = await fetch('/api/tasks', { headers: authHeaders() });
    const data = await response.json();

    if (data.tasks && data.tasks.length > 0) {
      tasksEmpty.style.display = 'none';
      tasksList.style.display = 'flex';

      // Create signature based on task IDs, states, and descriptions
      // This prevents re-rendering (and killing the cancel button) if nothing basic changed
      const currentSig = JSON.stringify(data.tasks.map(t => ({ id: t.id, state: t.state, desc: t.description })));

      const expandedIds = [...document.querySelectorAll('.task-card.expanded')]
        .map(el => el.dataset.taskId);

      // Only re-render list if headers changed
      if (currentSig !== lastTasksSig) {
        lastTasksSig = currentSig;
        renderTasks(data.tasks);

        // Restore expanded state only after a re-render
        expandedIds.forEach(id => {
          const card = document.querySelector(`[data-task-id="${id}"]`);
          if (card) {
            card.classList.add('expanded');
          }
        });
      }

      // Always reload the timeline for expanded cards (to show progress)
      // We do this even if headers didn't change
      expandedIds.forEach(id => {
        // Only if the task still exists
        if (data.tasks.find(t => t.id === id)) {
          toggleTaskDetails(id, true);
        }
      });

      updateTaskBadge(data.count);
    } else {
      tasksEmpty.style.display = 'flex';
      tasksList.style.display = 'none';
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

function renderTasks(tasks) {
  tasksList.innerHTML = tasks.map(task => `
    <div class="task-card" data-task-id="${task.id}">
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
      <div class="task-timeline" id="timeline-${task.id}">
        <!-- Timeline loaded on expand -->
      </div>
    </div>
  `).join('');
}

async function cancelTask(taskId) {
  try {
    const response = await fetch(`/api/tasks/${taskId}/cancel`, {
      method: 'POST',
      headers: authHeaders()
    });
    const data = await response.json();

    if (data.status === 'success') {
      showToast('Task cancelled', 'success');
      loadTasks(); // Refresh the task list
    } else {
      showToast(data.error || 'Failed to cancel task', 'error');
    }
  } catch (error) {
    console.error('Error cancelling task:', error);
    showToast('Failed to cancel task', 'error');
  }
}

function getTaskIcon(state) {
  switch (state) {
    case 'running':
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"/></svg>';
    case 'completed':
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m9 12 2 2 4-4"/></svg>';
    case 'failed':
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="m18 6-12 12M6 6l12 12"/></svg>';
    default:
      return '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="4"/></svg>';
  }
}

async function toggleTaskDetails(taskId, forceLoad = false) {
  const card = document.querySelector(`[data-task-id="${taskId}"]`);
  const timeline = document.getElementById(`timeline-${taskId}`);

  if (!forceLoad && card.classList.contains('expanded')) {
    card.classList.remove('expanded');
    return;
  }

  card.classList.add('expanded');

  // Load timeline
  try {
    const response = await fetch(`/api/tasks/${taskId}`, { headers: authHeaders() });
    const data = await response.json();

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
  } catch (error) {
    console.error('Error loading task timeline:', error);
    timeline.innerHTML = '<div class="timeline-step"><div class="timeline-description">Failed to load timeline</div></div>';
  }
}

function formatTime(isoString) {
  const date = new Date(isoString);
  return date.toLocaleTimeString();
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Poll tasks every 5 seconds when panel is open
let tasksInterval = null;
function startTasksPolling() {
  if (!tasksInterval) {
    tasksInterval = setInterval(loadTasks, 5000);
  }
}

function stopTasksPolling() {
  if (tasksInterval) {
    clearInterval(tasksInterval);
    tasksInterval = null;
  }
}

// Toggle polling when panel opens/closes
toggleTasksBtn?.addEventListener('click', () => {
  tasksSidebar.classList.toggle('visible');

  if (tasksSidebar.classList.contains('visible')) {
    loadTasks();
    startTasksPolling();
  } else {
    stopTasksPolling();
  }
});

closeTasksBtn?.addEventListener('click', () => {
  tasksSidebar.classList.remove('visible');
  stopTasksPolling();
});

// ============================================
// Initialize
// ============================================
document.addEventListener('DOMContentLoaded', () => {
  attachChipListeners();
  lastHistoryLength = -1; // Force initial sync
  syncChatHistory();
  loadMemory();
  loadModelsPanel();
  loadMetrics();
  loadTokenStats();
  loadSettings();
  updateSendButton();
  loadTasks(); // Load initial task count

  // Use SSE for real-time updates (Chat + Jobs)
  startSSE();

  // Start job polling (Disabled - using SSE)
  // setInterval(pollJobs, 5000);
});

// ============================================
// Smart Home Modal (Loxone)
// ============================================
const smartHomeModal = document.getElementById('smartHomeModal');
const toggleSmartHomeBtn = document.getElementById('toggleSmartHomeBtn');
const closeSmartHomeBtn = document.getElementById('closeSmartHomeBtn');
let smartHomePollingInterval = null;
let smartHomeCountdownInterval = null;
let smartHomeCountdown = 15;

function updateCountdownDisplay() {
  const countdownEl = document.getElementById('smartHomeCountdown');
  if (countdownEl) {
    countdownEl.textContent = `(${smartHomeCountdown}s)`;
  }
}

function startSmartHomePolling() {
  smartHomeCountdown = 15;
  updateCountdownDisplay();

  // Countdown timer every second
  smartHomeCountdownInterval = setInterval(() => {
    smartHomeCountdown--;
    updateCountdownDisplay();
    if (smartHomeCountdown <= 0) {
      smartHomeCountdown = 15;
    }
  }, 1000);

  // Refresh every 15 seconds
  smartHomePollingInterval = setInterval(() => {
    refreshSmartHomeRooms();
    smartHomeCountdown = 15;
  }, 15000);
}

function stopSmartHomePolling() {
  if (smartHomePollingInterval) {
    clearInterval(smartHomePollingInterval);
    smartHomePollingInterval = null;
  }
  if (smartHomeCountdownInterval) {
    clearInterval(smartHomeCountdownInterval);
    smartHomeCountdownInterval = null;
  }
  const countdownEl = document.getElementById('smartHomeCountdown');
  if (countdownEl) countdownEl.textContent = '';
}

toggleSmartHomeBtn?.addEventListener('click', () => {
  smartHomeModal.classList.add('visible');
  loadSmartHomeRooms();
  startSmartHomePolling();
});

closeSmartHomeBtn?.addEventListener('click', () => {
  smartHomeModal.classList.remove('visible');
  stopSmartHomePolling();
});

smartHomeModal?.addEventListener('click', (e) => {
  if (e.target === smartHomeModal) {
    smartHomeModal.classList.remove('visible');
    stopSmartHomePolling();
  }
});

async function loadSmartHomeRooms() {
  const container = document.getElementById('smartHomeRooms');
  if (!container) return;

  container.innerHTML = '<div class="room-card loading">Loading rooms...</div>';

  try {
    const resp = await fetch('/api/loxone/rooms');
    const data = await resp.json();

    if (!data.success || !data.rooms) {
      container.innerHTML = '<div class="room-card loading">Smart home unavailable</div>';
      return;
    }

    container.innerHTML = '';
    data.rooms.forEach(room => {
      const roomEl = document.createElement('div');
      roomEl.className = `room-card ${room.status === 'on' ? 'on' : 'off'}`;
      roomEl.dataset.room = room.id;
      roomEl.dataset.mode = room.mode || 'off';
      roomEl.dataset.supportsDim = room.supports_dim ? 'true' : 'false';

      const modeLabel = room.mode === 'bright' ? 'Bright' : room.mode === 'dim' ? 'Dim' : '';
      const toggleLabel = room.mode === 'bright' ? '◐ Dim' : '☀ Bright';
      const showToggle = room.status === 'on' && room.supports_dim;

      roomEl.innerHTML = `
        <span class="room-card-icon">${room.status === 'on' ? '💡' : '🔅'}</span>
        <span class="room-card-name">${room.name}</span>
        <span class="room-card-status">${room.status === 'on' ? 'On' : 'Off'}</span>
        ${room.status === 'on' ? `<span class="room-card-mode ${room.mode}">${modeLabel}</span>` : ''}
        ${showToggle ? `<button class="room-card-toggle" data-toggle-mode="${room.mode === 'bright' ? 'dim' : 'bright'}">${toggleLabel}</button>` : ''}
      `;

      // Click on card to toggle on/off
      roomEl.addEventListener('click', (e) => {
        if (e.target.classList.contains('room-card-toggle')) return;
        toggleSmartHomeRoom(room.id, roomEl);
      });

      // Click on toggle button to switch mode
      const toggleBtn = roomEl.querySelector('.room-card-toggle');
      if (toggleBtn) {
        toggleBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          toggleSmartHomeMode(room.id, toggleBtn.dataset.toggleMode);
        });
      }

      container.appendChild(roomEl);
    });
  } catch (err) {
    console.error('Failed to load Smart Home rooms:', err);
    container.innerHTML = '<div class="room-card loading">Connection error</div>';
  }
}

// Refresh room states without rebuilding the entire list (for polling)
async function refreshSmartHomeRooms() {
  try {
    const resp = await fetch('/api/loxone/rooms');
    const data = await resp.json();

    if (!data.success || !data.rooms) return;

    data.rooms.forEach(room => {
      const roomEl = document.querySelector(`.room-card[data-room="${room.id}"]`);
      if (!roomEl) return;

      const isCurrentlyOn = roomEl.classList.contains('on');
      const shouldBeOn = room.status === 'on';

      // Only update if state changed
      if (isCurrentlyOn !== shouldBeOn) {
        roomEl.classList.toggle('on', shouldBeOn);
        roomEl.classList.toggle('off', !shouldBeOn);
        const icon = roomEl.querySelector('.room-card-icon');
        const status = roomEl.querySelector('.room-card-status');
        icon.textContent = shouldBeOn ? '💡' : '🔅';
        status.textContent = shouldBeOn ? 'On' : 'Off';
      }
    });
  } catch (err) {
    console.error('Failed to refresh Smart Home rooms:', err);
  }
}

async function toggleSmartHomeRoom(roomId, roomEl) {
  const isOn = roomEl.classList.contains('on');
  const action = isOn ? 'off' : 'on';

  // Optimistic update
  roomEl.classList.toggle('on');
  roomEl.classList.toggle('off');
  const icon = roomEl.querySelector('.room-card-icon');
  const status = roomEl.querySelector('.room-card-status');
  icon.textContent = isOn ? '🔅' : '💡';
  status.textContent = isOn ? 'Off' : 'On';

  try {
    const resp = await fetch(`/api/loxone/light/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room: roomId })
    });
    const data = await resp.json();

    if (!data.success) {
      // Revert on failure
      roomEl.classList.toggle('on');
      roomEl.classList.toggle('off');
      icon.textContent = isOn ? '💡' : '🔅';
      status.textContent = isOn ? 'On' : 'Off';
      console.error('Light toggle failed:', data.error);
    } else {
      // Refresh to get updated mode after 500ms
      setTimeout(loadSmartHomeRooms, 500);
    }
  } catch (err) {
    // Revert on error
    roomEl.classList.toggle('on');
    roomEl.classList.toggle('off');
    icon.textContent = isOn ? '💡' : '🔅';
    status.textContent = isOn ? 'On' : 'Off';
    console.error('Light toggle error:', err);
  }
}

// Toggle between dim and bright modes
async function toggleSmartHomeMode(roomId, newMode) {
  const brightness = newMode === 'dim' ? 30 : 100;

  try {
    const resp = await fetch('/api/loxone/light/brightness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room: roomId, brightness: brightness })
    });
    const data = await resp.json();

    if (data.success) {
      // Refresh to show new state
      setTimeout(loadSmartHomeRooms, 500);
    } else {
      console.error('Mode toggle failed:', data.error);
    }
  } catch (err) {
    console.error('Mode toggle error:', err);
  }
}

// ============================================
// FILE ATTACHMENTS
// ============================================

// Handle file selection via button or drag-drop
function handleFileSelect(file) {
  if (!file) return;

  const isImage = file.type.startsWith('image/');

  // Store file info
  currentAttachment = {
    file: file,
    name: file.name,
    type: file.type,
    isImage: isImage,
    uploading: true
  };

  // Show preview
  if (isImage) {
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImage.src = e.target.result;
      previewImage.style.display = 'block';
    };
    reader.readAsDataURL(file);
  } else {
    previewImage.style.display = 'none';
  }

  previewName.textContent = file.name;
  attachmentPreview.style.display = 'flex';

  // Show analyzing state for images
  if (isImage) {
    previewName.innerHTML = `${file.name} <span class="analyzing">⏳ Analyzing...</span>`;
  }

  // Upload file
  uploadAttachment(file);
}

// Upload file to server
async function uploadAttachment(file) {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const resp = await fetch('/api/upload', {
      method: 'POST',
      body: formData
    });

    const data = await resp.json();

    if (data.success) {
      currentAttachment = {
        ...currentAttachment,
        fileId: data.file_id,
        url: data.url,
        analysis: data.analysis,
        uploading: false
      };

      // Update preview with uploaded file URL
      if (currentAttachment.isImage) {
        previewImage.src = data.url;
      }

      previewName.textContent = `${file.name} ✓`;
      console.log('File uploaded:', data);
    } else {
      console.error('Upload failed:', data.error);
      previewName.textContent = `${file.name} (failed)`;
      currentAttachment = null;
    }
  } catch (err) {
    console.error('Upload error:', err);
    previewName.textContent = `${file.name} (error)`;
    currentAttachment = null;
  }
}

// Remove current attachment
function clearAttachment() {
  currentAttachment = null;
  attachmentPreview.style.display = 'none';
  previewImage.src = '';
  previewName.textContent = '';
  fileInput.value = '';
}

// Wire up attachment events
if (attachBtn) {
  attachBtn.addEventListener('click', () => fileInput.click());
}

if (fileInput) {
  fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
      handleFileSelect(e.target.files[0]);
    }
  });
}

if (removeAttachment) {
  removeAttachment.addEventListener('click', clearAttachment);
}

// Drag and drop support
if (chatPane) {
  chatPane.addEventListener('dragover', (e) => {
    e.preventDefault();
    chatPane.classList.add('drag-over');
  });

  chatPane.addEventListener('dragleave', () => {
    chatPane.classList.remove('drag-over');
  });

  chatPane.addEventListener('drop', (e) => {
    e.preventDefault();
    chatPane.classList.remove('drag-over');

    if (e.dataTransfer.files.length > 0) {
      handleFileSelect(e.dataTransfer.files[0]);
    }
  });
}

// Clipboard paste support (Ctrl+V for screenshots)
document.addEventListener('paste', (e) => {
  const items = e.clipboardData?.items;
  if (!items) return;

  for (let i = 0; i < items.length; i++) {
    if (items[i].type.startsWith('image/')) {
      e.preventDefault();
      const file = items[i].getAsFile();
      if (file) {
        // Give it a name since clipboard images don't have one
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
        const namedFile = new File([file], `screenshot-${timestamp}.png`, { type: file.type });
        handleFileSelect(namedFile);
      }
      break;
    }
  }
});
