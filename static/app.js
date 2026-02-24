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
const createScheduleBtn = document.getElementById('createScheduleBtn');
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
let API_TOKEN = sessionStorage.getItem('companion_api_token') || '';
let ttsEnabled = localStorage.getItem('companion_tts_enabled') === 'true';
let showTokens = localStorage.getItem('companion_show_tokens') === 'true';
let currentConversation = [];
let lastHistoryLength = -1; // Start at -1 to force initial render
let eventSource = null;
let isStreaming = false; // Prevents SSE from overwriting during streaming
let abortController = null; // For stopping generation
let stopTyping = false; // Flag to stop typing animation
let currentCursorEl = null; // Reference to current streaming cursor
let currentAttachment = null; // Stores current file attachment {file, url, analysis}
let lastImageAnalysis = null; // Track last image analysis for pipeline display
let lastSSESeq = 0;
let sseGapCount = 0;
let sseUnknownEvents = 0;

// ============================================
// Utilities
// ============================================
function setApiToken(tok) {
  API_TOKEN = tok || '';
  if (tok) {
    sessionStorage.setItem('companion_api_token', tok);
  } else {
    sessionStorage.removeItem('companion_api_token');
  }
}

// Clean up legacy persistent token from older builds.
localStorage.removeItem('companion_api_token');

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

// Render LaTeX math using KaTeX
function renderMath(element) {
  if (typeof renderMathInElement !== 'undefined') {
    try {
      renderMathInElement(element, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\(', right: '\\)', display: false }
        ],
        throwOnError: false
      });
    } catch (e) {
      console.warn('Math rendering failed:', e);
    }
  }
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
// Pipeline Rendering - Enhanced Tool Display
// ============================================

// Icons for different step types
const STEP_ICONS = {
  decision: '🎯',
  vision: '👁️',
  result: '✅',
  error: '❌',
  tool: '🔧'
};

// Format tool result data based on operation type
function formatToolResult(data, operation) {
  if (!data) return null;

  // Time operation - show nicely formatted
  if (operation === 'get_time' || data.formatted || data.time) {
    return `<div class="tool-result-card time">
      <div class="tool-result-icon">🕐</div>
      <div class="tool-result-content">
        <div class="tool-result-main">${data.formatted || data.time || 'Unknown'}</div>
        ${data.date ? `<div class="tool-result-sub">${data.date}</div>` : ''}
      </div>
    </div>`;
  }

  // PDF reading - show file info and content preview
  if (operation === 'read_pdf' || data.content?.includes('📄 PDF:')) {
    const content = data.content || '';
    const preview = content.length > 300 ? content.substring(0, 300) + '...' : content;
    return `<div class="tool-result-card pdf">
      <div class="tool-result-icon">📄</div>
      <div class="tool-result-content">
        <div class="tool-result-main">PDF Document</div>
        <div class="tool-result-sub">${data.file_path || 'File read'}</div>
        <div class="tool-result-preview">${escapeHtml(preview)}</div>
      </div>
    </div>`;
  }

  // File listing
  if (operation === 'list_files' || data.files) {
    return `<div class="tool-result-card files">
      <div class="tool-result-icon">📁</div>
      <div class="tool-result-content">
        <div class="tool-result-main">Files Listed</div>
        <div class="tool-result-sub">${data.directory || 'Directory'}</div>
      </div>
    </div>`;
  }

  // Browser operations
  if (operation?.includes('browser') || data.url) {
    return `<div class="tool-result-card browser">
      <div class="tool-result-icon">🌐</div>
      <div class="tool-result-content">
        <div class="tool-result-main">Browser Action</div>
        <div class="tool-result-sub">${data.url || data.result || 'Completed'}</div>
      </div>
    </div>`;
  }

  // Wikipedia
  if (operation === 'wikipedia' || data.topic) {
    return `<div class="tool-result-card wiki">
      <div class="tool-result-icon">📖</div>
      <div class="tool-result-content">
        <div class="tool-result-main">${data.topic || 'Wikipedia'}</div>
        <div class="tool-result-preview">${escapeHtml((data.result || '').substring(0, 200))}</div>
      </div>
    </div>`;
  }

  // Light control
  if (operation?.includes('light')) {
    const icon = operation.includes('off') ? '🌙' : '💡';
    return `<div class="tool-result-card lights">
      <div class="tool-result-icon">${icon}</div>
      <div class="tool-result-content">
        <div class="tool-result-main">Smart Home</div>
        <div class="tool-result-sub">${data.message || operation}</div>
      </div>
    </div>`;
  }

  // Generic fallback - still show as JSON but formatted
  return null;
}

function renderPipeline(metadata) {
  if (!metadata || !metadata.source) return '';

  const steps = [];

  // Get token steps if available
  const tokenSteps = metadata.token_steps || [];
  const getTokensForStep = (stepName) => {
    return tokenSteps.find(s => s.name === stepName || s.name.includes(stepName));
  };

  // 0. Image Analysis (if an image was attached)
  if (lastImageAnalysis) {
    steps.push({
      type: 'vision',
      title: 'Image Analysis',
      desc: `Analyzed with Maverick vision`,
      data: lastImageAnalysis.fullText || 'Image processed',
      tokens: { input: lastImageAnalysis.inputTokens || 0, output: lastImageAnalysis.outputTokens || 0, total: lastImageAnalysis.totalTokens || 0, ms: lastImageAnalysis.ms || 0, model: 'maverick' }
    });
    // Clear after use so it doesn't show on subsequent messages
    lastImageAnalysis = null;
  }

  // 1. Initial Decision
  const orchTokens = getTokensForStep('orchestrator');
  steps.push({
    type: 'decision',
    title: 'Orchestrator Decision',
    desc: `Route to: ${metadata.source}`,
    data: metadata.source === 'loop_vision' ? 'Visual verification needed' :
      metadata.source === 'loop_tools' ? 'Tool execution required' :
        'Direct conversation',
    tokens: orchTokens
  });

  // 2. Loop Execution
  if (metadata.loop_result) {
    const res = metadata.loop_result;
    const status = res.status || 'unknown';
    const loopType = metadata.source.replace('loop_', '');
    const loopTokens = getTokensForStep(loopType) || getTokensForStep('loop');
    const operation = res.metadata?.operation || '';

    // Format the result nicely
    const formattedResult = formatToolResult(res.data, operation);

    steps.push({
      type: status === 'success' ? 'result' : 'error',
      title: `Tool: ${operation || loopType}`,
      desc: `Status: ${status}`,
      data: res.error ? res.error :
        (formattedResult ? formattedResult :
          (res.data ? JSON.stringify(res.data, null, 2) : 'Completed')),
      formatted: !!formattedResult,
      tokens: loopTokens
    });
  }

  // 3. Synthesis
  const synthTokens = getTokensForStep('synthesis') || getTokensForStep('generate');
  steps.push({
    type: 'tool',
    title: 'Final Synthesis',
    desc: 'Response generation',
    data: null,
    tokens: synthTokens
  });

  const html = steps.map(step => {
    // Get icon for step type
    const icon = STEP_ICONS[step.type] || '⚡';

    // Extract model type (groq vs local) from model string
    const modelLabel = step.tokens?.model?.includes('groq') ? 'groq' :
      step.tokens?.model?.includes('local') ? 'local' : '';
    const tokenBadge = step.tokens ?
      `<span class="token-badge" title="${step.tokens.input} in / ${step.tokens.output} out @ ${step.tokens.ms}ms (${step.tokens.model || 'unknown'})">
        ${modelLabel ? `<span class="model-label ${modelLabel}">${modelLabel}</span>` : ''}
        <span class="token-count">${step.tokens.total}</span>
        <span class="token-time">${step.tokens.ms}ms</span>
      </span>` : '';

    // Render data - either formatted HTML or escaped text
    const dataHtml = step.data ?
      (step.formatted ? step.data : `<div class="step-data">${escapeHtml(step.data)}</div>`)
      : '';

    return `
    <div class="pipeline-step ${step.type}">
      <div class="step-info">
        <div class="step-header">
          <span class="step-icon">${icon}</span>
          <span class="step-type">${step.type.toUpperCase()}</span>
          <span class="step-title">${step.title}</span>
          ${tokenBadge}
        </div>
        <div class="step-desc">${step.desc}</div>
        ${dataHtml}
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
  if (role === 'ai' && showTokens) {
    // Calculate total tokens for this message (sum all steps)
    let messageTotal = 0;
    let primarySource = 'unknown';

    if (metadata && metadata.token_steps) {
      for (const step of metadata.token_steps) {
        messageTotal += (step.total || 0);
        // Use the synthesis/generate source as primary
        if (step.name === 'synthesis' || step.name === 'generate') {
          primarySource = step.model?.includes('groq') ? 'groq' :
            step.model?.includes('local') ? 'local' : 'unknown';
        }
      }
    } else if (tokens) {
      // Fallback to tokens object if no metadata
      messageTotal = (tokens.input || 0) + (tokens.output || 0);
      primarySource = tokens.source || 'unknown';
    }

    if (messageTotal > 0) {
      // Color code source
      let sourceColor = '#888';
      if (primarySource === 'groq') sourceColor = '#f97316';
      else if (primarySource === 'local') sourceColor = '#3b82f6';

      tokenHtml = `<span class="token-badge" title="Total tokens for this message">(${messageTotal} tokens)</span>`;
      if (primarySource !== 'unknown') {
        tokenHtml += `<span class="source-badge" style="color: ${sourceColor}; margin-left: 6px; font-size: 10px;">[${primarySource}]</span>`;
      }
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
  renderMath(messageEl);  // Render LaTeX math
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
  currentCursorEl = cursorEl; // Store global reference for stop button

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
    if (stopTyping || pendingText.length === 0) {
      isTyping = false;
      stopTyping = false; // Reset for next message
      return;
    }
    isTyping = true;

    const charsToType = Math.min(pendingText.length, Math.random() > 0.7 ? 2 : 1);
    const chars = pendingText.slice(0, charsToType);
    pendingText = pendingText.slice(charsToType);
    displayedText += chars;

    // Use textContent during streaming for performance
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
          renderMath(textDiv);  // Render LaTeX math

          // Render Pipeline if metadata exists
          if (receivedMetadata) {
            const pipelineHtml = renderPipeline(receivedMetadata);
            const pipelineDiv = document.createElement('div');
            pipelineDiv.innerHTML = pipelineHtml;
            textDiv.appendChild(pipelineDiv);
          }

          isStreaming = false;
          abortController = null;

          if (stopBtn) {
            if (ttsEnabled) {
              // Keep stop visible for audio
              stopBtn.style.display = 'flex';
              // Auto-hide after 45s
              setTimeout(() => { if (stopBtn && !isStreaming) stopBtn.style.display = 'none'; }, 45000);
            } else {
              stopBtn.style.display = 'none';
            }
          }
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
// Memory Loading - Enhanced UI
// ============================================
let allMemoryData = { facts: [], insights: [] }; // Store for filtering

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

    // Store for filtering
    allMemoryData = { facts: detailed, insights };

    // Update stats
    document.getElementById('memFactCount').textContent = detailed.length;
    document.getElementById('memInsightCount').textContent = insights.length;
    document.getElementById('memSummaryCount').textContent = summaries.length;

    // Render with current search filter
    const searchInput = document.getElementById('memorySearchInput');
    const query = searchInput?.value?.toLowerCase() || '';
    renderMemoryCards(query);
    await loadPendingFacts();

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
      return `
        <div class="memory-card" data-pending-id="${pid}">
          <div class="memory-text">${text}</div>
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


window.approvePendingFact = async function approvePendingFact(pid) {
  try {
    const r = await fetch(`/api/pending_facts/${pid}/approve`, {
      method: 'POST',
      headers: authHeaders()
    });
    const data = await r.json();
    if (!r.ok || !data.approved) {
      showToast(data.error || 'Approve failed', 'error');
      return;
    }
    await loadPendingFacts();
    await loadMemory();
    showToast('Fact approved', 'success');
  } catch (e) {
    showToast('Approve failed', 'error');
  }
};


window.rejectPendingFact = async function rejectPendingFact(pid) {
  try {
    const r = await fetch(`/api/pending_facts/${pid}/reject`, {
      method: 'POST',
      headers: authHeaders()
    });
    const data = await r.json();
    if (!r.ok || !data.rejected) {
      showToast(data.error || 'Reject failed', 'error');
      return;
    }
    await loadPendingFacts();
    showToast('Fact rejected', 'success');
  } catch (e) {
    showToast('Reject failed', 'error');
  }
};


async function bulkPendingFacts(action) {
  const ids = [...document.querySelectorAll('#pendingFactsList [data-pending-id]')]
    .map(el => Number(el.dataset.pendingId))
    .filter(Boolean);
  if (!ids.length) {
    showToast('No pending facts to process', 'info');
    return;
  }

  try {
    const r = await fetch('/api/pending_facts/bulk', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ action, ids })
    });
    const data = await r.json();
    if (!r.ok) {
      showToast(data.error || 'Bulk action failed', 'error');
      return;
    }
    await loadPendingFacts();
    await loadMemory();
    showToast(`${action === 'approve' ? 'Approved' : 'Rejected'} ${data.processed} facts`, 'success');
  } catch (e) {
    showToast('Bulk action failed', 'error');
  }
}

// Render memory cards with optional filter
function renderMemoryCards(query = '') {
  const profileDiv = document.getElementById('profileList');
  const insightDiv = document.getElementById('insightList');
  const searchCount = document.getElementById('memorySearchCount');

  let matchCount = 0;

  // Profile facts as enhanced cards
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

      // Category detection
      const category = detectCategory(row.value);
      const confPercent = Math.round((row.confidence || 0.7) * 100);
      const timeAgo = formatTimeAgo(row.created_at || row.updated_at);

      // Highlight matching text
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
            <div class="confidence-bar">
              <div class="confidence-fill" style="width: ${confPercent}%"></div>
            </div>
          </div>
        </div>
      `;

      // Left-click to edit
      card.addEventListener('click', (e) => {
        if (e.target.closest('.memory-edit-container')) return;
        toggleEditMode(card, row.key, row.value);
      });

      // Right-click to delete
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

  // Insights as cards
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
        <div class="memory-card-header">
          <span class="memory-category insight">insight</span>
        </div>
        <div class="memory-text">${displayText}</div>
      `;
      insightDiv.appendChild(card);
    });

    if (!allMemoryData.insights.length) {
      insightDiv.innerHTML = '<div class="memory-empty">No insights yet</div>';
    }
  }

  // Update search count
  if (searchCount) {
    searchCount.textContent = query ? `${matchCount} found` : '';
  }
}

// Toggle inline edit mode
function toggleEditMode(card, key, currentValue) {
  // Remove any existing edit containers
  document.querySelectorAll('.memory-card.editing').forEach(c => {
    c.classList.remove('editing');
    c.querySelector('.memory-edit-container')?.remove();
  });

  if (card.classList.contains('editing')) {
    card.classList.remove('editing');
    return;
  }

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

  // Save button
  editContainer.querySelector('.memory-save-btn').addEventListener('click', async (e) => {
    e.stopPropagation();
    const newValue = textarea.value.trim();
    if (newValue && newValue !== currentValue) {
      await updateFact(key, newValue, card);
    }
    card.classList.remove('editing');
    editContainer.remove();
  });

  // Cancel button
  editContainer.querySelector('.memory-cancel-btn').addEventListener('click', (e) => {
    e.stopPropagation();
    card.classList.remove('editing');
    editContainer.remove();
  });

  // Enter to save, Escape to cancel
  textarea.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      editContainer.querySelector('.memory-save-btn').click();
    } else if (e.key === 'Escape') {
      editContainer.querySelector('.memory-cancel-btn').click();
    }
  });
}

// Update a fact
async function updateFact(key, newValue, cardElement) {
  try {
    const r = await fetch(`/api/memory/fact/${encodeURIComponent(key)}`, {
      method: 'PUT',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ value: newValue })
    });

    if (r.ok) {
      // Update in memory
      const index = parseInt(cardElement.dataset.index);
      if (allMemoryData.facts[index]) {
        allMemoryData.facts[index].value = newValue;
      }
      // Flash highlight
      cardElement.classList.add('highlight');
      setTimeout(() => cardElement.classList.remove('highlight'), 500);
      // Re-render cards
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

// Delete a single fact
async function deleteFact(key, cardElement) {
  const text = cardElement.querySelector('.memory-text')?.textContent || 'this memory';
  if (!confirm(`Delete: "${text.substring(0, 50)}${text.length > 50 ? '...' : ''}"?`)) return;

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
        const countEl = document.getElementById('memFactCount');
        if (countEl) countEl.textContent = parseInt(countEl.textContent) - 1;
        // Also remove from local data
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

// Category detection based on content
function detectCategory(text) {
  const lower = text.toLowerCase();
  if (lower.includes('like') || lower.includes('prefer') || lower.includes('favorite') || lower.includes('enjoy')) {
    return 'preference';
  }
  if (lower.includes('work') || lower.includes('job') || lower.includes('study') || lower.includes('school')) {
    return 'fact';
  }
  return 'fact';
}

// Format relative time
function formatTimeAgo(dateStr) {
  if (!dateStr) return '';
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now - date;
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

// Escape regex special chars
function escapeRegex(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// Search input handler
document.getElementById('memorySearchInput')?.addEventListener('input', (e) => {
  const query = e.target.value.toLowerCase();
  renderMemoryCards(query);
});

document.getElementById('refreshMemoryBtn')?.addEventListener('click', loadMemory);
document.getElementById('approveAllPendingBtn')?.addEventListener('click', () => bulkPendingFacts('approve'));
document.getElementById('rejectAllPendingBtn')?.addEventListener('click', () => bulkPendingFacts('reject'));

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

let pluginCatalogState = [];

function renderPluginCatalog(plugins) {
  const listEl = document.getElementById('pluginCatalogList');
  const statusEl = document.getElementById('pluginPolicyStatus');
  if (!listEl) return;
  if (!plugins || plugins.length === 0) {
    listEl.textContent = 'No plugins registered.';
    if (statusEl) statusEl.textContent = 'No plugin policy to apply.';
    return;
  }

  listEl.innerHTML = plugins.map((plugin) => {
    const risk = plugin.risk_tier || 'unknown';
    const toolCount = Number(plugin.tool_count || 0);
    const checked = plugin.enabled ? 'checked' : '';
    const title = escapeHtml(plugin.title || plugin.name);
    const pluginName = escapeHtml(plugin.name || '');
    return `
      <div class="setting-group" style="margin-bottom:8px;">
        <label class="toggle-label">
          <input type="checkbox" class="plugin-policy-checkbox" value="${pluginName}" ${checked}>
          <span>${title}</span>
        </label>
        <p class="setting-hint" style="margin:4px 0 0 28px;">${toolCount} tools • risk:${risk}</p>
      </div>
    `;
  }).join('');

  if (statusEl) {
    const enabledCount = plugins.filter(p => p.enabled).length;
    statusEl.textContent = `${enabledCount}/${plugins.length} plugin groups enabled. Changes apply when you click Apply Plugin Policy.`;
  }
}

async function loadPluginCatalog() {
  try {
    const resp = await fetch('/api/plugins/catalog', { headers: authHeaders() });
    if (!resp.ok) {
      showToast('Failed to load plugin catalog', 'error');
      return;
    }
    const data = await resp.json();
    pluginCatalogState = Array.isArray(data.plugins) ? data.plugins : [];
    renderPluginCatalog(pluginCatalogState);
  } catch (e) {
    console.error('Failed to load plugin catalog:', e);
    showToast('Failed to load plugin catalog', 'error');
  }
}

async function applyPluginPolicy() {
  const listEl = document.getElementById('pluginCatalogList');
  const statusEl = document.getElementById('pluginPolicyStatus');
  if (!listEl) return;

  const enabledPlugins = [...listEl.querySelectorAll('.plugin-policy-checkbox:checked')]
    .map(el => (el.value || '').trim())
    .filter(Boolean);

  try {
    const resp = await fetch('/api/plugins/policy', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ enabled_plugins: enabledPlugins })
    });
    const data = await resp.json();
    if (!resp.ok) {
      showToast(data.error || 'Failed to apply plugin policy', 'error');
      return;
    }

    if (statusEl) {
      const source = data.source || 'workspace';
      statusEl.textContent = `Saved plugin policy (${source}). Enabled: ${enabledPlugins.length}.`;
    }
    showToast('Plugin policy applied', 'success');
    await loadPluginCatalog();
  } catch (e) {
    console.error('Failed to apply plugin policy:', e);
    showToast('Failed to apply plugin policy', 'error');
  }
}

async function loadContextPanel() {
  try {
    const resp = await fetch('/api/context', { headers: authHeaders() });
    if (!resp.ok) return;
    const data = await resp.json();
    const workspaceInput = document.getElementById('contextWorkspaceInput');
    const profileInput = document.getElementById('contextProfileInput');
    const sessionInput = document.getElementById('contextSessionInput');
    const badge = document.getElementById('contextCurrentBadge');
    const known = document.getElementById('knownWorkspacesList');

    if (workspaceInput) workspaceInput.value = data.workspace_id || 'default';
    if (profileInput) profileInput.value = data.profile_id || 'default';
    if (sessionInput) sessionInput.value = data.session_id || 'default';
    if (badge) {
      badge.textContent = `Current: workspace=${data.workspace_id || 'default'} • profile=${data.profile_id || 'default'} • session=${data.session_id || 'default'}`;
    }
    if (known) {
      const rows = Array.isArray(data.known_workspaces) ? data.known_workspaces : ['default'];
      known.textContent = rows.join(', ');
    }
  } catch (e) {
    console.error('Failed to load context panel:', e);
  }
}

async function applyContextSwitch(newSession = false) {
  const workspaceInput = document.getElementById('contextWorkspaceInput');
  const profileInput = document.getElementById('contextProfileInput');
  const sessionInput = document.getElementById('contextSessionInput');
  const migrateToggle = document.getElementById('contextMigrateToggle');

  const payload = {
    workspace_id: (workspaceInput?.value || 'default').trim() || 'default',
    profile_id: (profileInput?.value || 'default').trim() || 'default',
    session_id: (sessionInput?.value || 'default').trim() || 'default',
    migrate_legacy: !!migrateToggle?.checked,
    new_session: !!newSession,
  };

  try {
    const resp = await fetch('/api/context/switch', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) {
      showToast(data.error || 'Failed to switch context', 'error');
      return;
    }

    stopSSE();
    startSSE();
    lastHistoryLength = -1;
    currentConversation = [];
    await syncChatHistory();
    await loadMemory();
    await loadTasks();
    await loadContextPanel();
    showToast(`Context switched to ${data.workspace_id}/${data.profile_id}`, 'success');
  } catch (e) {
    console.error('Failed to switch context:', e);
    showToast('Failed to switch context', 'error');
  }
}

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
  const contextApplyBtn = document.getElementById('contextApplyBtn');
  const contextNewSessionBtn = document.getElementById('contextNewSessionBtn');
  const pluginCatalogRefreshBtn = document.getElementById('pluginCatalogRefreshBtn');
  const pluginPolicyApplyBtn = document.getElementById('pluginPolicyApplyBtn');

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

  contextApplyBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    await applyContextSwitch(false);
  });

  contextNewSessionBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    await applyContextSwitch(true);
  });

  pluginCatalogRefreshBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    await loadPluginCatalog();
  });

  pluginPolicyApplyBtn?.addEventListener('click', async (e) => {
    e.preventDefault();
    await applyPluginPolicy();
  });

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

  await loadContextPanel();
  await loadPluginCatalog();
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
      const eventType = data.event || data.type;
      const payload = data.payload || {};
      const seq = Number(data.seq || 0);

      if (seq > 0) {
        if (lastSSESeq > 0 && seq > (lastSSESeq + 1)) {
          sseGapCount += (seq - lastSSESeq - 1);
          console.warn('SSE sequence gap detected', { lastSSESeq, seq, sseGapCount });
        }
        lastSSESeq = Math.max(lastSSESeq, seq);
      }

      if (eventType === 'history.updated' || data.type === 'history') {
        renderHistory(payload.history || data.history || []);
      } else if (eventType === 'job.updated' || data.type === 'job_update') {
        loadTasks();
      } else {
        sseUnknownEvents += 1;
        console.debug('SSE unknown event type', { eventType, sseUnknownEvents });
        renderHistory(data.history || []);
      }
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
let schedulesById = {};

async function loadTasks() {
  try {
    const [tasksResponse, schedulesResponse] = await Promise.all([
      fetch('/api/tasks', { headers: authHeaders() }),
      fetch('/api/schedules', { headers: authHeaders() })
    ]);
    const data = await tasksResponse.json();
    const scheduleData = await schedulesResponse.json();
    const tasks = Array.isArray(data.tasks) ? data.tasks : [];
    const schedules = Array.isArray(scheduleData.schedules) ? scheduleData.schedules : [];

    if (tasks.length > 0 || schedules.length > 0) {
      tasksEmpty.style.display = 'none';
      tasksList.style.display = 'flex';

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
          if (card) {
            card.classList.add('expanded');
          }
        });
      }

      expandedIds.forEach(id => {
        if (tasks.find(t => t.id === id)) {
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

function renderTasks(tasks, schedules = []) {
  schedulesById = schedules.reduce((acc, schedule) => {
    acc[schedule.id] = schedule;
    return acc;
  }, {});

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
      <div class="task-timeline" id="timeline-${task.id}">
        <!-- Timeline loaded on expand -->
      </div>
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
  } catch {
    return 'Unknown';
  }
}

async function toggleSchedule(scheduleId, enabled) {
  try {
    const response = await fetch(`/api/schedules/${scheduleId}/toggle`, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ enabled })
    });
    const data = await response.json();
    if (!response.ok) {
      showToast(data.error || 'Failed to update schedule', 'error');
      return;
    }
    showToast(enabled ? 'Schedule resumed' : 'Schedule paused', 'success');
    loadTasks();
  } catch (error) {
    console.error('Error toggling schedule:', error);
    showToast('Failed to update schedule', 'error');
  }
}

async function runScheduleNow(scheduleId) {
  try {
    const response = await fetch(`/api/schedules/${scheduleId}/run`, {
      method: 'POST',
      headers: authHeaders(),
    });
    const data = await response.json();
    if (!response.ok) {
      showToast(data.error || 'Failed to run schedule', 'error');
      return;
    }
    showToast(data.job_id ? `Schedule started (job ${data.job_id})` : 'Schedule started', 'success');
    loadTasks();
  } catch (error) {
    console.error('Error running schedule now:', error);
    showToast('Failed to run schedule', 'error');
  }
}

async function editSchedule(scheduleId) {
  const schedule = schedulesById[scheduleId];
  if (!schedule) {
    showToast('Schedule not found', 'error');
    return;
  }

  const description = prompt('Schedule description', schedule.description || '');
  if (description === null) return;

  const intervalInput = prompt('Run every how many minutes?', String(schedule.interval_minutes || 15));
  if (intervalInput === null) return;
  const intervalMinutes = Number(intervalInput);
  if (!Number.isFinite(intervalMinutes) || intervalMinutes <= 0) {
    showToast('Please enter a valid positive minute interval', 'error');
    return;
  }

  try {
    const response = await fetch(`/api/schedules/${scheduleId}`, {
      method: 'PUT',
      headers: authHeaders(),
      body: JSON.stringify({
        description: description.trim(),
        interval_minutes: intervalMinutes,
        tool_name: schedule.tool_name || 'start_background_task',
        tool_args: schedule.tool_args || {},
        timezone: schedule.timezone || 'UTC',
        retry_limit: Number(schedule.retry_limit || 0),
        retry_backoff_minutes: Number(schedule.retry_backoff_minutes || 1),
      })
    });
    const data = await response.json();
    if (!response.ok) {
      showToast(data.error || 'Failed to update schedule', 'error');
      return;
    }
    showToast('Schedule updated', 'success');
    loadTasks();
  } catch (error) {
    console.error('Error updating schedule:', error);
    showToast('Failed to update schedule', 'error');
  }
}

async function deleteSchedule(scheduleId) {
  const schedule = schedulesById[scheduleId];
  if (!schedule) {
    showToast('Schedule not found', 'error');
    return;
  }

  if (!confirm(`Delete schedule: ${schedule.description || scheduleId}?`)) {
    return;
  }

  try {
    const response = await fetch(`/api/schedules/${scheduleId}`, {
      method: 'DELETE',
      headers: authHeaders()
    });
    const data = await response.json();
    if (!response.ok) {
      showToast(data.error || 'Failed to delete schedule', 'error');
      return;
    }
    showToast('Schedule deleted', 'success');
    loadTasks();
  } catch (error) {
    console.error('Error deleting schedule:', error);
    showToast('Failed to delete schedule', 'error');
  }
}

async function createSchedule() {
  const description = prompt('Schedule description', 'Recurring background task');
  if (description === null) return;

  const trimmedDescription = (description || '').trim();
  if (!trimmedDescription) {
    showToast('Description is required', 'error');
    return;
  }

  const cadence = prompt('Cadence (examples: 15m, 1h, 1d)', '30m');
  if (cadence === null) return;

  const cadenceValue = (cadence || '').trim().toLowerCase();
  if (!/^\d+[mhd]$/.test(cadenceValue)) {
    showToast('Cadence must look like 15m, 1h, or 1d', 'error');
    return;
  }

  try {
    const response = await fetch('/api/schedules', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({
        description: trimmedDescription,
        cadence: cadenceValue,
        tool_name: 'start_background_task',
        tool_args: { description: trimmedDescription },
      })
    });
    const data = await response.json();
    if (!response.ok) {
      showToast(data.error || 'Failed to create schedule', 'error');
      return;
    }

    showToast('Schedule created', 'success');
    await loadTasks();
  } catch (error) {
    console.error('Error creating schedule:', error);
    showToast('Failed to create schedule', 'error');
  }
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

createScheduleBtn?.addEventListener('click', () => {
  createSchedule();
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

  // Stop any ghost TTS from previous session
  fetch('/api/chat/stop', { method: 'POST' }).catch(() => { });

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
const smartHomeAllOnBtn = document.getElementById('smartHomeAllOnBtn');
const smartHomeAllOffBtn = document.getElementById('smartHomeAllOffBtn');
const smartHomeRefreshBtn = document.getElementById('smartHomeRefreshBtn');
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
  loadSmartHomeHealth();
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
      container.innerHTML = '<div class="room-card loading">Smart home unavailable. Check Smart Home status above.</div>';
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
    container.innerHTML = '<div class="room-card loading">Connection error. Check Smart Home status above.</div>';
  }
}

async function loadSmartHomeHealth() {
  const statusEl = document.getElementById('smartHomeStatus');
  if (!statusEl) return;

  statusEl.textContent = 'Checking smart home connection...';

  try {
    const resp = await fetch('/api/loxone/health');
    const data = await resp.json();

    if (data.success && data.connected) {
      statusEl.textContent = 'Smart Home: Connected';
      return;
    }

    if (data.configured === false) {
      statusEl.textContent = data.message || 'Smart Home: Not configured. Set LOXONE_HOST, LOXONE_USER, and LOXONE_PASSWORD in .env.';
      return;
    }

    statusEl.textContent = data.message || 'Smart Home: Configured but unreachable';
  } catch (err) {
    console.error('Failed to load Smart Home health:', err);
    statusEl.textContent = 'Smart Home: Health check failed';
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
      showToast(data.error || 'Smart Home action failed', 'error');
    } else {
      showToast(data.message || `Turned ${action} ${roomId}`, 'success');
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
    showToast('Smart Home connection error', 'error');
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
      showToast(data.message || `Set ${roomId} to ${brightness}%`, 'success');
      // Refresh to show new state
      setTimeout(loadSmartHomeRooms, 500);
    } else {
      console.error('Mode toggle failed:', data.error);
      showToast(data.error || 'Failed to change lighting mode', 'error');
    }
  } catch (err) {
    console.error('Mode toggle error:', err);
    showToast('Smart Home connection error', 'error');
  }
}

async function setAllSmartHomeLights(action) {
  const label = action === 'on' ? 'on' : 'off';
  try {
    const resp = await fetch(`/api/loxone/light/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room: 'all' })
    });
    const data = await resp.json();
    if (!data.success) {
      showToast(data.error || `Failed to turn ${label} all lights`, 'error');
      return;
    }
    showToast(data.message || `Turned ${label} all lights`, 'success');
    await loadSmartHomeRooms();
  } catch (err) {
    console.error(`All lights ${action} error:`, err);
    showToast(`Failed to turn ${label} all lights`, 'error');
  }
}

smartHomeAllOnBtn?.addEventListener('click', () => setAllSmartHomeLights('on'));
smartHomeAllOffBtn?.addEventListener('click', () => setAllSmartHomeLights('off'));
smartHomeRefreshBtn?.addEventListener('click', async () => {
  await loadSmartHomeHealth();
  await loadSmartHomeRooms();
  showToast('Smart Home refreshed', 'info');
});

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
      // Track for pipeline display (full text, not truncated)
      if (data.analysis && currentAttachment.isImage) {
        lastImageAnalysis = {
          fullText: data.analysis,
          totalTokens: 1300  // Approximate based on our optimizations
        };
      }

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

// ============================================
// Voice Input (STT)
// ============================================
function setupVoiceInput() {
  const micBtn = document.getElementById('micBtn');
  const micIcon = document.getElementById('micIcon');
  const userInput = document.getElementById('userInput');

  if (!micBtn || !micIcon || !userInput) return;

  // Check browser support
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
    console.log('Web Speech API not supported');
    micBtn.style.opacity = '0.3';
    micBtn.style.cursor = 'not-allowed';
    micBtn.title = 'Voice Input (Not supported in this browser - try Chrome/Edge)';
    micBtn.onclick = () => alert("Your browser doesn't support built-in speech recognition. Please try Chrome or Edge.");
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.continuous = false;
  recognition.lang = 'en-US';
  recognition.interimResults = true;

  let isListening = false;
  let finalTranscript = '';

  recognition.onstart = () => {
    isListening = true;
    micBtn.classList.add('listening');
    micIcon.style.stroke = '#EF4444'; // Red
  };

  recognition.onend = () => {
    isListening = false;
    micBtn.classList.remove('listening');
    micIcon.style.stroke = 'currentColor';
  };

  recognition.onerror = (event) => {
    console.error('Speech recognition error', event.error);
    isListening = false;
    micBtn.classList.remove('listening');
    micIcon.style.stroke = 'currentColor';
  };

  recognition.onresult = (event) => {
    let interimTranscript = '';
    let hasFinal = false;

    // Build transcript
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) {
        finalTranscript += event.results[i][0].transcript;
        hasFinal = true;
      } else {
        interimTranscript += event.results[i][0].transcript;
      }
    }

    // Update input
    // Strategy: We keep what was there before speech started? 
    // Complexity: User might type while speaking.
    // Simple: Just append current speech.

    // Better: Only update if we have something new.
    // Logic: We need to insert the *current session's* transcript.
    // But handling cursor pos is hard. 
    // Let's just append to end for V1.

    if (hasFinal) {
      if (userInput.value && !userInput.value.endsWith(' ')) {
        userInput.value += ' ';
      }
      userInput.value += finalTranscript;
      finalTranscript = ''; // Reset for next sentence if continuous (but we are false)

      // Auto-resize
      userInput.style.height = 'auto';
      userInput.style.height = userInput.scrollHeight + 'px';
    }
  };

  micBtn.addEventListener('click', () => {
    if (isListening) {
      recognition.stop();
    } else {
      finalTranscript = ''; // Reset buffer
      recognition.start();
    }
  });
}

// Init Voice Input
document.addEventListener('DOMContentLoaded', setupVoiceInput);

// ============================================
// Groq TTS Logic
// ============================================
document.addEventListener('DOMContentLoaded', () => {
  const groqTtsToggle = document.getElementById('groqTtsToggle');
  if (groqTtsToggle) {
    groqTtsToggle.addEventListener('change', async (e) => {
      const isGroq = e.target.checked;
      try {
        await fetch('/api/tts/config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            provider: isGroq ? 'groq' : 'azure',
          })
        });
        console.log('TTS Provider:', isGroq ? 'Groq' : 'Azure');
      } catch (err) {
        console.error('Failed to set TTS provider:', err);
      }
    });
  }
});

// ============================================
// Stop Button Logic
// ============================================
document.addEventListener('DOMContentLoaded', () => {
  const stopBtn = document.getElementById('stopBtn');
  if (stopBtn) {
    stopBtn.addEventListener('click', async () => {
      console.log("Stopping generation...");

      // Abort text streaming
      if (typeof abortController !== 'undefined' && abortController) {
        abortController.abort();
        console.log("Text streaming aborted");
      }

      // Stop typing animation
      stopTyping = true;

      // Hide streaming cursor
      if (currentCursorEl) {
        currentCursorEl.style.display = 'none';
        currentCursorEl = null;
      }

      // Hide stop button, show send button
      if (stopBtn) stopBtn.style.display = 'none';
      const sendBtn = document.getElementById('sendBtn');
      if (sendBtn) sendBtn.style.display = 'flex';

      // Stop audio playback
      try {
        await fetch('/api/chat/stop', { method: 'POST' });
        console.log("Audio stop request sent");
      } catch (e) {
        console.error("Stop failed", e);
      }
    });
  }
});

// ============================================
// Knowledge Base (Brain Files)
// ============================================

async function loadBrainFiles() {
  const list = document.getElementById('brainFilesList');
  if (!list) return;

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


window.deleteBrainFile = async function deleteBrainFile(encodedPath) {
  const relPath = decodeURIComponent(encodedPath || '');
  if (!relPath) return;
  if (!confirm(`Delete ${relPath}?`)) return;

  try {
    const res = await fetch('/api/brain/file', {
      method: 'DELETE',
      headers: authHeaders(),
      body: JSON.stringify({ path: relPath })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Delete failed', 'error');
      return;
    }
    showToast('File deleted', 'success');
    await loadBrainFiles();
  } catch (e) {
    showToast('Delete failed', 'error');
  }
};

async function loadRecentUploads() {
  const list = document.getElementById('recentUploadsList');
  if (!list) return;

  try {
    const res = await fetch('/api/upload/list?limit=12', { headers: authHeaders() });
    const data = await res.json();

    if (!data.files || data.files.length === 0) {
      list.innerHTML = '<div class="brain-empty">No uploaded files yet.</div>';
      return;
    }

    list.innerHTML = data.files.map(f => {
      return `
        <div class="brain-file-card">
          <div class="brain-file-icon">📎</div>
          <div class="brain-file-info">
            <div class="brain-file-name">${escapeHtml(f.filename)}</div>
            <div class="brain-file-meta">${f.ext.toUpperCase()} • ${Math.round((f.size || 0) / 1024)} KB</div>
            <div style="display:flex; gap:6px; margin-top:6px;">
              <button class="small-btn" onclick="summarizeUploadedFile('${f.file_id}')">Summary</button>
              <button class="small-btn" onclick="extractUploadedFile('${f.file_id}')">Extract</button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  } catch (e) {
    list.innerHTML = '<div class="brain-empty">Failed to load uploads</div>';
  }
}

window.summarizeUploadedFile = async function summarizeUploadedFile(fileId) {
  try {
    const res = await fetch('/api/upload/summarize', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ file_id: fileId })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Summary failed', 'error');
      return;
    }
    addMessage('ai', `📄 Summary for ${data.filename}\n\n${data.summary}`);
    showToast('File summary added to chat', 'success');
  } catch (e) {
    showToast('Summary failed', 'error');
  }
};

window.extractUploadedFile = async function extractUploadedFile(fileId) {
  try {
    const res = await fetch('/api/upload/extract', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ file_id: fileId, max_chars: 1800 })
    });
    const data = await res.json();
    if (!res.ok) {
      showToast(data.error || 'Extract failed', 'error');
      return;
    }
    addMessage('ai', `📑 Extract from ${data.filename}${data.truncated ? ' (truncated)' : ''}\n\n${data.text}`);
    showToast('File extract added to chat', 'success');
  } catch (e) {
    showToast('Extract failed', 'error');
  }
};

// Initialize Knowledge tab handlers
document.addEventListener('DOMContentLoaded', () => {
  const uploadZone = document.getElementById('brainUploadZone');
  const fileInput = document.getElementById('brainFileInput');
  const reindexBtn = document.getElementById('reindexBrainBtn');
  const refreshUploadsBtn = document.getElementById('refreshUploadsBtn');

  if (uploadZone && fileInput) {
    // Click to upload
    uploadZone.addEventListener('click', () => fileInput.click());

    // Drag and drop
    uploadZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      uploadZone.classList.add('drag-over');
    });

    uploadZone.addEventListener('dragleave', () => {
      uploadZone.classList.remove('drag-over');
    });

    uploadZone.addEventListener('drop', async (e) => {
      e.preventDefault();
      uploadZone.classList.remove('drag-over');
      const files = Array.from(e.dataTransfer.files);
      if (files.length > 1) {
        await uploadBrainFiles(files);
      } else if (files.length === 1) {
        await uploadBrainFile(files[0]);
      }
    });

    // File input change
    fileInput.addEventListener('change', async (e) => {
      const files = Array.from(e.target.files);
      if (files.length > 1) {
        await uploadBrainFiles(files);
      } else if (files.length === 1) {
        await uploadBrainFile(files[0]);
      }
      fileInput.value = '';
    });
  }

  if (reindexBtn) {
    reindexBtn.addEventListener('click', async () => {
      reindexBtn.disabled = true;
      reindexBtn.textContent = '...';
      try {
        await fetch('/api/brain/reindex', { method: 'POST' });
        await loadBrainFiles();
      } finally {
        reindexBtn.disabled = false;
        reindexBtn.textContent = '↻';
      }
    });
  }

  if (refreshUploadsBtn) {
    refreshUploadsBtn.addEventListener('click', async () => {
      refreshUploadsBtn.disabled = true;
      try {
        await loadRecentUploads();
      } finally {
        refreshUploadsBtn.disabled = false;
      }
    });
  }

  // Load files when Knowledge tab is clicked
  document.querySelectorAll('.tab[data-tab="knowledge"]').forEach(tab => {
    tab.addEventListener('click', () => {
      loadBrainFiles();
      loadRecentUploads();
    });
  });

  loadRecentUploads();
});

async function uploadBrainFile(file) {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('folder', 'documents');

  try {
    const res = await fetch('/api/brain/upload', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (data.success) {
      console.log(`Uploaded ${file.name}: ${data.chunks_indexed} chunks indexed`);
      await loadBrainFiles();
    } else {
      console.error('Upload failed:', data.error);
    }
  } catch (e) {
    console.error('Upload error:', e);
  }
}


async function uploadBrainFiles(files) {
  const formData = new FormData();
  files.forEach(file => formData.append('files', file));
  formData.append('folder', 'documents');

  try {
    const res = await fetch('/api/brain/upload/batch', {
      method: 'POST',
      body: formData
    });
    const data = await res.json();

    if (data.success) {
      showToast(`Uploaded ${data.count} file${data.count === 1 ? '' : 's'} to knowledge`, 'success');
      await loadBrainFiles();
      if (Array.isArray(data.errors) && data.errors.length > 0) {
        console.warn('Some files failed during batch upload:', data.errors);
      }
    } else {
      const msg = data.error || 'Batch upload failed';
      showToast(msg, 'error');
    }
  } catch (e) {
    console.error('Batch upload error:', e);
    showToast('Batch upload failed', 'error');
  }
}
