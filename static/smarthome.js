// ============================================
// Companion AI — Smart Home (Loxone)
// ============================================
import { bus, skeletonCards } from './utils.js';

let smartHomePollingInterval = null;
let smartHomeCountdownInterval = null;
let smartHomeCountdown = 15;

function updateCountdownDisplay() {
  const countdownEl = document.getElementById('smartHomeCountdown');
  if (countdownEl) {
    countdownEl.textContent = `(${smartHomeCountdown}s)`;
  }
}

export function startSmartHomePolling() {
  smartHomeCountdown = 15;
  updateCountdownDisplay();

  smartHomeCountdownInterval = setInterval(() => {
    smartHomeCountdown--;
    updateCountdownDisplay();
    if (smartHomeCountdown <= 0) smartHomeCountdown = 15;
  }, 1000);

  smartHomePollingInterval = setInterval(() => {
    refreshSmartHomeRooms();
    smartHomeCountdown = 15;
  }, 15000);
}

export function stopSmartHomePolling() {
  if (smartHomePollingInterval) { clearInterval(smartHomePollingInterval); smartHomePollingInterval = null; }
  if (smartHomeCountdownInterval) { clearInterval(smartHomeCountdownInterval); smartHomeCountdownInterval = null; }
  const countdownEl = document.getElementById('smartHomeCountdown');
  if (countdownEl) countdownEl.textContent = '';
}

export async function loadSmartHomeRooms() {
  const container = document.getElementById('smartHomeRooms');
  if (!container) return;

  container.innerHTML = skeletonCards(3);

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

      roomEl.addEventListener('click', (e) => {
        if (e.target.classList.contains('room-card-toggle')) return;
        toggleSmartHomeRoom(room.id, roomEl);
      });

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

export async function loadSmartHomeHealth() {
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
      roomEl.classList.toggle('on');
      roomEl.classList.toggle('off');
      icon.textContent = isOn ? '💡' : '🔅';
      status.textContent = isOn ? 'On' : 'Off';
      console.error('Light toggle failed:', data.error);
      showToast(data.error || 'Smart Home action failed', 'error');
    } else {
      showToast(data.message || `Turned ${action} ${roomId}`, 'success');
      setTimeout(loadSmartHomeRooms, 500);
    }
  } catch (err) {
    roomEl.classList.toggle('on');
    roomEl.classList.toggle('off');
    icon.textContent = isOn ? '💡' : '🔅';
    status.textContent = isOn ? 'On' : 'Off';
    console.error('Light toggle error:', err);
    showToast('Smart Home connection error', 'error');
  }
}

async function toggleSmartHomeMode(roomId, newMode) {
  const brightness = newMode === 'dim' ? 30 : 100;

  try {
    const resp = await fetch('/api/loxone/light/brightness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room: roomId, brightness })
    });
    const data = await resp.json();

    if (data.success) {
      showToast(data.message || `Set ${roomId} to ${brightness}%`, 'success');
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

// ---- Self-init: wire button listeners ----
export function initSmartHome() {
  document.getElementById('smartHomeAllOnBtn')?.addEventListener('click', () => setAllSmartHomeLights('on'));
  document.getElementById('smartHomeAllOffBtn')?.addEventListener('click', () => setAllSmartHomeLights('off'));
  document.getElementById('smartHomeRefreshBtn')?.addEventListener('click', async () => {
    await loadSmartHomeHealth();
    await loadSmartHomeRooms();
    showToast('Smart Home refreshed', 'info');
  });
}
