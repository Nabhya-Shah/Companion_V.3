// ============================================
// Companion AI — Shared Utilities & State
// ============================================

// ---- Simple Event Bus (cross-module communication) ----
export const bus = {
  _h: {},
  on(e, fn) { (this._h[e] ??= []).push(fn); },
  off(e, fn) { this._h[e] = (this._h[e] || []).filter(f => f !== fn); },
  emit(e, ...a) { (this._h[e] || []).forEach(fn => fn(...a)); }
};

// ---- Shared Mutable State ----
export const state = {
  API_TOKEN: sessionStorage.getItem('companion_api_token') || '',
  ttsEnabled: localStorage.getItem('companion_tts_enabled') === 'true',
  showTokens: localStorage.getItem('companion_show_tokens') === 'true',
  currentConversation: [],
  lastHistoryLength: -1,
  eventSource: null,
  isStreaming: false,
  abortController: null,
  stopTyping: false,
  currentCursorEl: null,
  currentAttachment: null,
  lastImageAnalysis: null,
  lastSSESeq: 0,
  sseGapCount: 0,
  sseUnknownEvents: 0,
};

// Clean up legacy persistent token from older builds.
localStorage.removeItem('companion_api_token');

// ---- Auth ----
export function setApiToken(tok) {
  state.API_TOKEN = tok || '';
  if (tok) {
    sessionStorage.setItem('companion_api_token', tok);
  } else {
    sessionStorage.removeItem('companion_api_token');
  }
}

export function authHeaders(extra = {}) {
  return {
    'Content-Type': 'application/json',
    ...(state.API_TOKEN ? { 'X-API-TOKEN': state.API_TOKEN } : {}),
    ...extra
  };
}

// ---- Formatting ----
export function formatTime(date) {
  return new Date(date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

export function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

export function formatTimeAgo(dateStr) {
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

export function escapeRegex(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function detectCategory(text) {
  const lower = text.toLowerCase();
  if (lower.includes('like') || lower.includes('prefer') || lower.includes('favorite') || lower.includes('enjoy')) {
    return 'preference';
  }
  if (lower.includes('work') || lower.includes('job') || lower.includes('study') || lower.includes('school')) {
    return 'fact';
  }
  return 'fact';
}

// ---- Scroll ----
export function scrollToBottom(instant = false) {
  const chatPane = document.getElementById('chatPane');
  if (!chatPane) return;
  setTimeout(() => {
    chatPane.scrollTo({
      top: chatPane.scrollHeight,
      behavior: instant ? 'auto' : 'smooth'
    });
  }, 50);
}

// ---- Markdown ----
export function renderMarkdown(text) {
  if (typeof marked === 'undefined') {
    return escapeHtml(text).replace(/\n/g, '<br>');
  }
  marked.setOptions({
    highlight: function (code, lang) {
      if (typeof hljs !== 'undefined' && lang && hljs.getLanguage(lang)) {
        try { return hljs.highlight(code, { language: lang }).value; } catch (e) { }
      }
      return code;
    },
    breaks: true,
    gfm: true
  });
  return marked.parse(text);
}

export function renderMath(element) {
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

export function addCopyButtons(container) {
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

// ---- Skeleton Helpers ----
export function skeletonCards(count = 3) {
  return Array.from({ length: count }, () =>
    `<div class="skeleton-card skeleton">
       <div class="skeleton-row">
         <div class="skeleton-circle skeleton"></div>
         <div class="skeleton-lines">
           <div class="skeleton-line skeleton w-75"></div>
           <div class="skeleton-line skeleton w-50"></div>
         </div>
       </div>
     </div>`
  ).join('');
}

export function skeletonLines(count = 4) {
  const widths = ['w-75', 'w-60', 'w-50', 'w-40'];
  return Array.from({ length: count }, (_, i) =>
    `<div class="skeleton-line skeleton ${widths[i % widths.length]}"></div>`
  ).join('');
}
