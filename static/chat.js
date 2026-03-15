// ============================================
// Companion AI — Chat: Pipeline, Messages, Streaming, SSE, Attachments, Voice
// ============================================
import {
  bus, state, authHeaders, setApiToken,
  escapeHtml, scrollToBottom,
  renderMarkdown, renderMath, addCopyButtons
} from './utils.js';

// ---- DOM refs (safe — modules are deferred) ----
const chatPane     = document.getElementById('chatPane');
const welcomeScreen= document.getElementById('welcomeScreen');
const userInput    = document.getElementById('userInput');
const sendBtn      = document.getElementById('sendBtn');
const stopBtn      = document.getElementById('stopBtn');
const attachBtn    = document.getElementById('attachBtn');
const fileInput    = document.getElementById('fileInput');
const attachmentPreview = document.getElementById('attachmentPreview');
const previewImage = document.getElementById('previewImage');
const previewName  = document.getElementById('previewName');
const removeAttachmentBtn = document.getElementById('removeAttachment');

// ============================================
// Pipeline Rendering — Enhanced Tool Display
// ============================================
const STEP_ICONS = { decision: '🎯', vision: '👁️', result: '✅', error: '❌', tool: '🔧' };

function formatToolResult(data, operation) {
  if (!data) return null;

  if (operation === 'get_time' || data.formatted || data.time) {
    return `<div class="tool-result-card time">
      <div class="tool-result-icon">🕐</div>
      <div class="tool-result-content">
        <div class="tool-result-main">${data.formatted || data.time || 'Unknown'}</div>
        ${data.date ? `<div class="tool-result-sub">${data.date}</div>` : ''}
      </div>
    </div>`;
  }

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

  if (operation === 'list_files' || data.files) {
    return `<div class="tool-result-card files">
      <div class="tool-result-icon">📁</div>
      <div class="tool-result-content">
        <div class="tool-result-main">Files Listed</div>
        <div class="tool-result-sub">${data.directory || 'Directory'}</div>
      </div>
    </div>`;
  }

  if (operation?.includes('browser') || data.url) {
    return `<div class="tool-result-card browser">
      <div class="tool-result-icon">🌐</div>
      <div class="tool-result-content">
        <div class="tool-result-main">Browser Action</div>
        <div class="tool-result-sub">${data.url || data.result || 'Completed'}</div>
      </div>
    </div>`;
  }

  if (operation === 'wikipedia' || data.topic) {
    return `<div class="tool-result-card wiki">
      <div class="tool-result-icon">📖</div>
      <div class="tool-result-content">
        <div class="tool-result-main">${data.topic || 'Wikipedia'}</div>
        <div class="tool-result-preview">${escapeHtml((data.result || '').substring(0, 200))}</div>
      </div>
    </div>`;
  }

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

  return null;
}

function renderPipeline(metadata) {
  if (!metadata || !metadata.source) return '';

  const steps = [];
  const tokenSteps = metadata.token_steps || [];
  const getTokensForStep = (name) => tokenSteps.find(s => s.name === name || s.name.includes(name));
  const parseModelTag = (modelRaw) => {
    const raw = String(modelRaw || '').trim();
    if (!raw) return { provider: 'unknown', model: 'unknown' };

    const idx = raw.indexOf(':');
    if (idx > 0) {
      const prefix = raw.slice(0, idx).toLowerCase();
      const model = raw.slice(idx + 1) || 'unknown';
      if (prefix === 'browser_agent') return { provider: 'browser', model };
      if (prefix === 'groq' || prefix === 'local') return { provider: prefix, model };
    }

    if (raw.includes('openai/') || raw.includes('llama-') || raw.includes('gpt-')) {
      return { provider: 'groq', model: raw };
    }
    if (raw.includes(':') || raw.startsWith('Qwen/')) {
      return { provider: 'local', model: raw };
    }
    return { provider: 'unknown', model: raw };
  };

  // Image analysis step
  if (state.lastImageAnalysis) {
    steps.push({
      type: 'vision', title: 'Image Analysis',
      desc: 'Analyzed with Maverick vision',
      data: state.lastImageAnalysis.fullText || 'Image processed',
      tokens: { input: state.lastImageAnalysis.inputTokens || 0, output: state.lastImageAnalysis.outputTokens || 0, total: state.lastImageAnalysis.totalTokens || 0, ms: state.lastImageAnalysis.ms || 0, model: 'maverick' }
    });
    state.lastImageAnalysis = null;
  }

  // Orchestrator decision
  const orchTokens = getTokensForStep('orchestrator');
  steps.push({
    type: 'decision', title: 'Orchestrator Decision',
    desc: `Route to: ${metadata.source}`,
    data: metadata.source === 'loop_vision' ? 'Visual verification needed' :
          metadata.source === 'loop_tools' ? 'Tool execution required' : 'Direct conversation',
    tokens: orchTokens,
    role: 'orchestrator'
  });

  // Loop execution
  if (metadata.loop_result) {
    const res = metadata.loop_result;
    const status = res.status || 'unknown';
    const loopType = metadata.source.replace('loop_', '');
    const loopTokens = getTokensForStep(loopType) || getTokensForStep('loop');
    const operation = res.metadata?.operation || '';
    const loopRole = loopType === 'memory'
      ? (operation === 'save' ? 'memory-helper' : `memory-${operation || 'op'}`)
      : `${loopType}-${operation || 'op'}`;
    const formattedResult = formatToolResult(res.data, operation);

    steps.push({
      type: status === 'success' ? 'result' : 'error',
      title: `Tool: ${operation || loopType}`,
      desc: `Status: ${status}`,
      data: res.error ? res.error :
            (formattedResult ? formattedResult :
              (res.data ? JSON.stringify(res.data, null, 2) : 'Completed')),
      formatted: !!formattedResult,
      tokens: loopTokens,
      role: loopRole
    });
  }

  // Synthesis
  const synthTokens = getTokensForStep('synthesis') || getTokensForStep('generate');
  steps.push({ type: 'tool', title: 'Final Synthesis', desc: 'Response generation', data: null, tokens: synthTokens, role: 'synthesis' });

  const html = steps.map(step => {
    const icon = STEP_ICONS[step.type] || '⚡';
    const modelInfo = parseModelTag(step.tokens?.model);
    const modelLabel = modelInfo.provider === 'groq' ? 'groq' :
      modelInfo.provider === 'local' ? 'local' : '';
    const tokenBadge = step.tokens
      ? `<span class="token-badge" title="${step.tokens.input} in / ${step.tokens.output} out @ ${step.tokens.ms}ms (${modelInfo.provider}:${modelInfo.model})">
          ${modelLabel ? `<span class="model-label ${modelLabel}">${modelLabel}</span>` : ''}
          ${step.role ? `<span class="source-badge" style="margin-left:6px; font-size:10px; opacity:0.8;">${escapeHtml(step.role)}</span>` : ''}
          <span class="token-count">${step.tokens.total}</span>
          <span class="token-time">${step.tokens.ms}ms</span>
        </span>` : '';
    const dataHtml = step.data
      ? (step.formatted ? step.data : `<div class="step-data">${escapeHtml(step.data)}</div>`)
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
    </div>`;
  }).join('');

  return `
    <div class="pipeline-view">
      <div class="pipeline-toggle" onclick="this.classList.toggle('open'); this.nextElementSibling.classList.toggle('open')">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="9 18 15 12 9 6"></polyline>
        </svg>
        View Process Pipeline
      </div>
      <div class="pipeline-content">${html}</div>
    </div>`;
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

  const roleName = role === 'user' ? 'You' : 'Companion';
  let tokenHtml = '';
  if (role === 'ai' && state.showTokens) {
    let messageTotal = 0;
    let primarySource = 'unknown';

    if (metadata && metadata.token_steps) {
      for (const step of metadata.token_steps) {
        messageTotal += (step.total || 0);
        if (step.name === 'synthesis' || step.name === 'generate') {
          primarySource = step.model?.includes('groq') ? 'groq' :
                          step.model?.includes('local') ? 'local' : 'unknown';
        }
      }
    } else if (tokens) {
      messageTotal = (tokens.input || 0) + (tokens.output || 0);
      primarySource = tokens.source || 'unknown';
    }

    if (messageTotal > 0) {
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
    if (metadata) {
      const pipelineHtml = renderPipeline(metadata);
      if (pipelineHtml) {
        const pipelineDiv = document.createElement('div');
        pipelineDiv.innerHTML = pipelineHtml;
        textDiv.appendChild(pipelineDiv);
      }
    }
  } else {
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

export function addMessage(role, text, timestamp, tokens, metadata, attachment) {
  if (welcomeScreen && welcomeScreen.parentNode) welcomeScreen.remove();
  const messageEl = createMessageElement(role, text, timestamp, tokens, metadata, attachment);
  chatPane.appendChild(messageEl);
  renderMath(messageEl);
  scrollToBottom();
}

// ============================================
// Chat — Send & Stream
// ============================================
export async function sendMessage(retry = false) {
  let message = userInput.value.trim();
  if (!message && !state.currentAttachment) return;

  let attachmentContext = '';
  if (state.currentAttachment && state.currentAttachment.analysis) {
    attachmentContext = `\n\n[Visual context from user's uploaded file: ${state.currentAttachment.analysis}]`;
    if (!message) message = "What can you tell me about this?";
  }

  const fullMessage = message + attachmentContext;

  const messageAttachment = state.currentAttachment ? {
    isImage: state.currentAttachment.isImage,
    url: state.currentAttachment.url,
    name: state.currentAttachment.name
  } : null;

  addMessage('user', message, null, null, null, messageAttachment);
  userInput.value = '';
  resizeTextarea();
  updateSendButton();
  clearAttachment();

  // Streaming AI message structure
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
  state.currentCursorEl = cursorEl;

  state.isStreaming = true;
  if (stopBtn) stopBtn.style.display = 'flex';
  if (sendBtn) sendBtn.style.display = 'none';

  // Typewriter state
  let displayedText = '';
  let pendingText = '';
  let isTyping = false;
  let receivedMetadata = null;

  async function typeNextChar() {
    if (state.stopTyping || pendingText.length === 0) {
      isTyping = false;
      state.stopTyping = false;
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
    if (chars.includes('.') || chars.includes('!') || chars.includes('?')) delay = 80 + Math.random() * 40;
    else if (chars.includes(',')) delay = 40 + Math.random() * 20;
    setTimeout(typeNextChar, delay);
  }

  function queueText(text) {
    pendingText += text;
    if (!isTyping) typeNextChar();
  }

  state.abortController = new AbortController();

  try {
    const resp = await fetch('/api/chat/send', {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ message: fullMessage, tts_enabled: state.ttsEnabled }),
      signal: state.abortController.signal
    });

    if (resp.status === 401 && !retry) {
      const tok = prompt('API token required. Enter token:');
      if (tok) { setApiToken(tok); wrapper.remove(); return sendMessage(true); }
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

            if (data.meta) { receivedMetadata = data.meta; }
            if (data.token_meta) { receivedMetadata = { ...receivedMetadata, ...data.token_meta }; }

            // Plan events during streaming → forward to tasks module
            if (data.plan_event) {
              const pe = data.plan_event;
              bus.emit('plan:event', pe.event_type, pe.plan_id, pe.data || {});
            }

            if (data.chunk) {
              queueText(data.chunk);
              if (window._streamingEmergencyTimeout) clearTimeout(window._streamingEmergencyTimeout);
              window._streamingEmergencyTimeout = setTimeout(() => {
                if (state.isStreaming) {
                  console.warn("Emergency timeout: forcing stream end after 5s of no data");
                  state.isStreaming = false;
                  state.abortController = null;
                  if (stopBtn) stopBtn.style.display = 'none';
                  if (sendBtn) sendBtn.style.display = 'flex';
                }
              }, 5000);
            }

            if (data.done) {
              if (window._streamingEmergencyTimeout) clearTimeout(window._streamingEmergencyTimeout);
              if (data.tokens && state.showTokens) {
                const total = (data.tokens.input || 0) + (data.tokens.output || 0);
                const source = data.tokens.source || 'unknown';
                roleLabel.innerHTML = `Companion <span class="token-badge">(${total} tokens)</span> <span style="font-size:10px; opacity:0.7">[${source}]</span>`;
                bus.emit('tokens:refresh');
              }
              if (data.memory_saved && window.showToast) {
                showToast("Memory Updated ✨", "success");
              }
            }

            if (data.error) throw new Error(data.error);
          } catch (parseErr) { /* ignore partial JSON */ }
        }
      }
    }

    // Wait for typing to finish
    const waitForTyping = () => {
      if (pendingText.length > 0 || isTyping) {
        setTimeout(waitForTyping, 50);
      } else {
        cursorEl.style.transition = 'opacity 0.3s';
        cursorEl.style.opacity = '0';
        setTimeout(() => {
          cursorEl.remove();
          textDiv.innerHTML = renderMarkdown(displayedText);
          addCopyButtons(textDiv);
          renderMath(textDiv);

          if (receivedMetadata) {
            const pipelineHtml = renderPipeline(receivedMetadata);
            const pipelineDiv = document.createElement('div');
            pipelineDiv.innerHTML = pipelineHtml;
            textDiv.appendChild(pipelineDiv);
          }

          state.isStreaming = false;
          state.abortController = null;

          if (stopBtn) {
            if (state.ttsEnabled) {
              stopBtn.style.display = 'flex';
              setTimeout(() => { if (stopBtn && !state.isStreaming) stopBtn.style.display = 'none'; }, 45000);
            } else {
              stopBtn.style.display = 'none';
            }
          }
          if (sendBtn) sendBtn.style.display = 'flex';
          state.lastHistoryLength++;
          bus.emit('tokens:refresh');
        }, 300);
      }
    };
    waitForTyping();

  } catch (e) {
    state.isStreaming = false;
    state.abortController = null;
    if (e.name === 'AbortError') {
      if (displayedText.trim()) {
        cursorEl.remove();
        textDiv.innerHTML = renderMarkdown(displayedText + '\n\n*[Stopped]*');
      } else { wrapper.remove(); }
      if (stopBtn) stopBtn.style.display = 'none';
      if (sendBtn) sendBtn.style.display = 'flex';
      return;
    }
    wrapper.remove();
    addMessage('ai', 'Error: ' + e.message);
  }
}

// ============================================
// Stop / Resize / Send Button
// ============================================
export function stopGeneration() {
  if (state.abortController && state.isStreaming) {
    state.abortController.abort();
    state.abortController = null;
  }
}

export function resizeTextarea() {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 200) + 'px';
}

export function updateSendButton() {
  sendBtn.disabled = !userInput.value.trim();
}

// ============================================
// Suggestion Chips
// ============================================
export function attachChipListeners() {
  document.querySelectorAll('.chip').forEach(chip => {
    chip.addEventListener('click', () => {
      const prompt = chip.dataset.prompt;
      if (prompt) { userInput.value = prompt; updateSendButton(); userInput.focus(); }
    });
  });
}

// ============================================
// Chat History Sync & SSE
// ============================================
export function renderHistory(history) {
  if (!history || history.length === 0) return;
  if (state.isStreaming) return;

  state.currentConversation = history; // Store for re-render on settings change

  const totalMessages = history.reduce((n, e) => n + (e.user ? 1 : 0) + (e.ai ? 1 : 0), 0);
  if (totalMessages === state.lastHistoryLength) return;
  state.lastHistoryLength = totalMessages;

  const welcome = document.getElementById('welcomeScreen');
  if (welcome && welcome.parentNode) welcome.remove();
  const loading = document.getElementById('loading-message');
  if (loading) loading.remove();

  chatPane.querySelectorAll('.message-wrapper').forEach(el => el.remove());
  history.forEach(entry => {
    if (entry.user) addMessage('user', entry.user);
    if (entry.ai) addMessage('ai', entry.ai, null, entry.tokens, entry.metadata);
  });
  scrollToBottom(true);
}

export async function syncChatHistory() {
  try {
    const resp = await fetch('/api/chat/history', { headers: authHeaders() });
    if (!resp.ok) return;
    const data = await resp.json();
    renderHistory(data.history || []);
  } catch (e) { console.error('Failed to sync history:', e); }
}

export function startSSE() {
  if (state.eventSource) return;

  state.eventSource = new EventSource('/api/chat/stream');

  state.eventSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      const eventType = data.event || data.type;
      const payload = data.payload || {};
      const seq = Number(data.seq || 0);

      if (seq > 0) {
        if (state.lastSSESeq > 0 && seq > (state.lastSSESeq + 1)) {
          state.sseGapCount += (seq - state.lastSSESeq - 1);
          console.warn('SSE sequence gap detected', { lastSSESeq: state.lastSSESeq, seq, sseGapCount: state.sseGapCount });
        }
        state.lastSSESeq = Math.max(state.lastSSESeq, seq);
      }

      if (eventType === 'history.updated' || data.type === 'history') {
        renderHistory(payload.history || data.history || []);
      } else if (eventType === 'job.updated' || data.type === 'job_update') {
        bus.emit('tasks:refresh');
      } else if (eventType === 'approval.pending' || data.type === 'approval_request') {
        bus.emit('approval:pending', payload.approvals || []);
      } else if (eventType === 'insight.new' || data.type === 'insight') {
        if (payload.insight) {
          bus.emit('insight:new', payload.insight);
          // Pull latest history so proactively injected chat messages appear.
          syncChatHistory();
        }
      } else if (data.type === 'plan_update') {
        bus.emit('plan:event', data.event, data.plan_id, payload);
      } else {
        state.sseUnknownEvents += 1;
        console.debug('SSE unknown event type', { eventType, sseUnknownEvents: state.sseUnknownEvents });
        renderHistory(data.history || []);
      }
    } catch (e) { console.error('SSE parse error:', e); }
  };

  state.eventSource.onerror = () => { console.warn('SSE connection error, will auto-reconnect'); };
}

export function stopSSE() {
  if (state.eventSource) { state.eventSource.close(); state.eventSource = null; }
}

// ============================================
// File Attachments
// ============================================
export function handleFileSelect(file) {
  if (!file) return;
  const isImage = file.type.startsWith('image/');

  state.currentAttachment = { file, name: file.name, type: file.type, isImage, uploading: true };

  if (isImage) {
    const reader = new FileReader();
    reader.onload = (e) => { previewImage.src = e.target.result; previewImage.style.display = 'block'; };
    reader.readAsDataURL(file);
  } else {
    previewImage.style.display = 'none';
  }

  previewName.textContent = file.name;
  attachmentPreview.style.display = 'flex';
  if (isImage) previewName.innerHTML = `${file.name} <span class="analyzing">⏳ Analyzing...</span>`;

  uploadAttachment(file);
}

async function uploadAttachment(file) {
  const formData = new FormData();
  formData.append('file', file);

  try {
    const resp = await fetch('/api/upload', { method: 'POST', body: formData });
    const data = await resp.json();

    if (data.success) {
      state.currentAttachment = {
        ...state.currentAttachment, fileId: data.file_id, url: data.url,
        analysis: data.analysis, uploading: false
      };
      if (data.analysis && state.currentAttachment.isImage) {
        state.lastImageAnalysis = { fullText: data.analysis, totalTokens: 1300 };
      }
      if (state.currentAttachment.isImage) previewImage.src = data.url;
      previewName.textContent = `${file.name} ✓`;
    } else {
      console.error('Upload failed:', data.error);
      previewName.textContent = `${file.name} (failed)`;
      state.currentAttachment = null;
    }
  } catch (err) {
    console.error('Upload error:', err);
    previewName.textContent = `${file.name} (error)`;
    state.currentAttachment = null;
  }
}

export function clearAttachment() {
  state.currentAttachment = null;
  attachmentPreview.style.display = 'none';
  previewImage.src = '';
  previewName.textContent = '';
  fileInput.value = '';
}

// ============================================
// Voice Input (STT)
// ============================================
export function setupVoiceInput() {
  const micBtn = document.getElementById('micBtn');
  const micIcon = document.getElementById('micIcon');
  if (!micBtn || !micIcon || !userInput) return;

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SpeechRecognition) {
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

  recognition.onstart = () => { isListening = true; micBtn.classList.add('listening'); micIcon.style.stroke = '#EF4444'; };
  recognition.onend = () => { isListening = false; micBtn.classList.remove('listening'); micIcon.style.stroke = 'currentColor'; };
  recognition.onerror = (event) => {
    console.error('Speech recognition error', event.error);
    isListening = false; micBtn.classList.remove('listening'); micIcon.style.stroke = 'currentColor';
  };

  recognition.onresult = (event) => {
    let hasFinal = false;
    for (let i = event.resultIndex; i < event.results.length; ++i) {
      if (event.results[i].isFinal) { finalTranscript += event.results[i][0].transcript; hasFinal = true; }
    }
    if (hasFinal) {
      if (userInput.value && !userInput.value.endsWith(' ')) userInput.value += ' ';
      userInput.value += finalTranscript;
      finalTranscript = '';
      userInput.style.height = 'auto';
      userInput.style.height = userInput.scrollHeight + 'px';
    }
  };

  micBtn.addEventListener('click', () => {
    if (isListening) { recognition.stop(); }
    else { finalTranscript = ''; recognition.start(); }
  });
}

// ============================================
// Init — wire up core chat event listeners
// ============================================
export function initChat() {
  // Send button
  sendBtn.addEventListener('click', sendMessage);

  // Enter key
  userInput.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  // ESC to stop generation
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && state.isStreaming) { e.preventDefault(); stopGeneration(); }
  });

  // Input resize
  userInput.addEventListener('input', () => { resizeTextarea(); updateSendButton(); });

  // Stop button (single handler, merges the duplicate DOMContentLoaded handlers)
  if (stopBtn) {
    stopBtn.addEventListener('click', async () => {
      // Abort text streaming
      if (state.abortController) { state.abortController.abort(); }
      state.stopTyping = true;

      // Hide streaming cursor
      if (state.currentCursorEl) { state.currentCursorEl.style.display = 'none'; state.currentCursorEl = null; }

      // Toggle buttons
      stopBtn.style.display = 'none';
      if (sendBtn) sendBtn.style.display = 'flex';

      // Stop audio playback
      try { await fetch('/api/chat/stop', { method: 'POST' }); } catch (e) { console.error("Stop failed", e); }
    });
  }

  // Attachment button
  if (attachBtn) attachBtn.addEventListener('click', () => fileInput.click());
  if (fileInput) fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) handleFileSelect(e.target.files[0]);
  });
  if (removeAttachmentBtn) removeAttachmentBtn.addEventListener('click', clearAttachment);

  // Drag & drop on chat pane
  if (chatPane) {
    chatPane.addEventListener('dragover', (e) => { e.preventDefault(); chatPane.classList.add('drag-over'); });
    chatPane.addEventListener('dragleave', () => { chatPane.classList.remove('drag-over'); });
    chatPane.addEventListener('drop', (e) => {
      e.preventDefault(); chatPane.classList.remove('drag-over');
      if (e.dataTransfer.files.length > 0) handleFileSelect(e.dataTransfer.files[0]);
    });
  }

  // Clipboard paste (Ctrl+V for screenshots)
  document.addEventListener('paste', (e) => {
    const items = e.clipboardData?.items;
    if (!items) return;
    for (let i = 0; i < items.length; i++) {
      if (items[i].type.startsWith('image/')) {
        e.preventDefault();
        const file = items[i].getAsFile();
        if (file) {
          const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
          const namedFile = new File([file], `screenshot-${timestamp}.png`, { type: file.type });
          handleFileSelect(namedFile);
        }
        break;
      }
    }
  });

  // Listen for history re-render requests from settings
  bus.on('history:rerender', () => renderHistory(state.currentConversation));

  // Listen for addMessage requests from memory module
  bus.on('chat:addMessage', (role, text) => addMessage(role, text));

  // Stop ghost TTS from previous session
  fetch('/api/chat/stop', { method: 'POST' }).catch(() => {});
}
