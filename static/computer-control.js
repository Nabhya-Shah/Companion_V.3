/**
 * Computer Control Status Module
 * Shows a floating banner when the AI is controlling mouse/keyboard
 */

class ComputerControlStatus {
    constructor() {
        this.isActive = false;
        this.banner = null;
        this.checkInterval = null;
        this.evtSource = null;
        this.init();
    }

    init() {
        // Create the banner element
        this.banner = document.createElement('div');
        this.banner.className = 'computer-control-banner';
        this.banner.innerHTML = `
      <span class="pulse-dot"></span>
      <span class="status-text">Computer Control Active</span>
      <span class="status-detail">AI is using mouse & keyboard</span>
      <button class="stop-btn" onclick="computerControl.requestStop()">STOP</button>
    `;
        document.body.prepend(this.banner);

        // Prefer SSE updates; fallback to slow polling if needed
        this.startSSE();
    }

    startSSE() {
        try {
            if (this.evtSource) {
                this.evtSource.close();
            }
            this.evtSource = new EventSource('/api/computer/stream');

            this.evtSource.onmessage = (e) => {
                if (!e.data || e.data === ': keep-alive') return;
                try {
                    const data = JSON.parse(e.data);
                    if (data.type === 'computer_status' && data.status) {
                        this.setActive(!!data.status.active);
                    }
                } catch (err) {
                    // ignore parse errors
                }
            };

            this.evtSource.onerror = () => {
                try { this.evtSource.close(); } catch (_) {}
                this.evtSource = null;
                // Fallback to slow polling if SSE fails
                this.startPollingFallback();
            };
        } catch (e) {
            this.startPollingFallback();
        }
    }

    startPollingFallback() {
        if (this.checkInterval) return;
        // Very slow fallback to minimize HTTP noise
        this.checkInterval = setInterval(() => {
            this.checkStatus();
        }, 30000);
    }

    async checkStatus() {
        try {
            const response = await fetch('/api/computer/status');
            if (response.ok) {
                const data = await response.json();
                this.setActive(data.active);
            }
        } catch (e) {
            // Endpoint might not exist yet, that's ok
        }
    }

    setActive(active) {
        this.isActive = active;
        if (active) {
            this.banner.classList.add('visible');
            document.body.classList.add('computer-control-active');
        } else {
            this.banner.classList.remove('visible');
            document.body.classList.remove('computer-control-active');
        }
    }

    async requestStop() {
        try {
            await fetch('/api/computer/stop', { method: 'POST' });
            this.setActive(false);
        } catch (e) {
            console.error('Failed to stop computer control:', e);
        }
    }

    // Manual trigger for testing
    show() {
        this.setActive(true);
    }

    hide() {
        this.setActive(false);
    }
}

// Initialize and export
const computerControl = new ComputerControlStatus();
