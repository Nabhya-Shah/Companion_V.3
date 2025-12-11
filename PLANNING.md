# Companion AI - Master Plan & Roadmap

**Goal:** Evolve from a "Chatbot" to a proactive, autonomous, and evolving "Digital Companion."

---

## 🚀 Phase 1: Dynamic Evolution (Immediate Focus)

### 1. Dynamic Persona Evolution
**Goal:** The AI adapts its personality and style based on long-term interaction, not just a static config.
*   **Mechanism:** Background "Reflection" process (every ~20 turns) using `llama-3.1-8b`.
*   **Storage:** `data/companion_brain/system/learned_traits.yaml` (Auto-generated).
*   **Integration:** Injects `evolved_traits` (e.g., "Concise", "Playful") into the system prompt alongside the static persona.
*   **Safety:** Static `companion.yaml` remains the anchor for core rules.

---

## 🔮 Phase 2: Autonomy & Awareness (Short Term)

### 2. Asynchronous "Deep Work" Manager
**Goal:** Allow the AI to perform long-running tasks without blocking the chat.
*   **Mechanism:** SQLite-based Job Queue + Worker Thread.
*   **User Flow:** AI says "I'll start that research," adds job to DB. Worker executes it.
*   **Notification:** UI "Toast" alerts user when task is complete.

### 3. Proactive "Nervous System" (Sensors)
**Goal:** Give the AI "senses" to initiate conversation based on system state.
*   **Mechanism:** Plugin-based sensor system (`sensors/` folder).
*   **Extensibility:** Drop any script (Python/PS1) that outputs JSON.
*   **Logic:** `triggers.yaml` defines rules (e.g., `IF cpu > 90% -> SAY "Rendering something?"`).

### 4. Web-Based Voice Mode
**Goal:** Hands-free voice interaction via the Web UI.
*   **Stack:** Web Speech API (Frontend) -> Whisper (Backend) -> Azure TTS.
*   **UI:** "Mic" button in chat.

---

## 🧠 Phase 3: Advanced Memory & Resilience (Medium Term)

### 5. Autonomous Visual Memory
**Goal:** Automatically archive significant visual moments.
*   **Mechanism:** Vision model flags screenshots as `is_memorable: true`.
*   **Storage:** Saves image to `data/visual_memories/` + Mem0 entry.
*   **Result:** A visual diary the AI builds without being asked.

### 6. Tool "Immune System" (Self-Healing)
**Goal:** Runtime recovery from tool failures.
*   **Mechanism:** Feed tool errors back to the 120B model as "Observations."
*   **Action:** AI decides to Retry (new params), Alternate (different tool), or Diagnose.

### 7. Local Compute Strategy (RTX 5080)
**Goal:** Leverage local hardware for privacy and zero-cost background tasks.
*   **Plan:** See [LOCAL_MODEL_PLAN.md](LOCAL_MODEL_PLAN.md)
*   **Models:** `llama3.1:8b` (Tools), `minicpm-v` (Vision), `qwen2.5:14b` (Reasoning).
*   **Backend:** Ollama.

---

## 🎮 Phase 4: The "Jarvis" Goal (Long Term)

### 7. "Watch Dog" Vision Loop
**Goal:** Continuous visual monitoring for specific events.
*   **Mechanism:** Background loop taking screenshots every N seconds.
*   **Use Case:** "Watch my health bar," "Tell me when download finishes."

### 8. Live Game Companion
**Goal:** Real-time gameplay interaction and learning.
*   **Requirements:** High FPS capture, local quantized inference, RL/Imitation learning.
*   **Status:** Research phase.

