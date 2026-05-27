# Companion V3 → JARVIS: Personal Roadmap

**Status:** Single-file plan for personal use  
**Date:** 2026-05-28  
**Goal:** Reliable daily driver with smart home control

---

## 📊 Current State (6.5/10 for JARVIS goal)

**What Works:**
- Chat streaming with SSE ✅
- Hybrid memory (Mem0 + SQLite) ✅
- Loxone light control (9 rooms configured) ✅
- Tool governance + approvals ✅
- 287 tests passing ✅

**What Blocks Daily Use:**
- No single-start command
- File tools can access any file on system (security risk)
- Calculator uses `eval()` (line 245 of tool_loop.py)
- Missing `.env` configuration

---

## 🔴 Phase 1: Safety & Setup (This Week)

> Quick fixes so you can run it without worry

| Task | Where | Why |
|------|-------|-----|
| Replace `eval()` calculator | `tool_loop.py:234-252` | Security - prevent code injection via math |
| Restrict file tools to allowed folders | `file_tools.py` + config | Security - prevent random file access |
| Add memory clear confirmation | `memory_routes.py` | Safety - no accidental wipe |
| Create `start_jarvis.sh` | Root folder | Convenience - one command starts it |

---

## 🟡 Phase 2: Smart Home Core (3-4 weeks)

> Your JARVIS needs to control your house

**Current (partial):**
- `loxone.py` has 9 rooms + aliases
- Only `light_on/light_off/light_dim` commands

**Add:**
- "All lights off" command
- Scene activation (movie mode, good morning, etc.)
- Shade/blind control
- Climate/thermostat integration

**Example commands:**
- "Turn on living room lights at 50%"
- "Activate movie scene"
- "Close bedroom shades"
- "Good morning" (routine: lights on, blinds open, weather)

---

## 🟢 Phase 3: Intelligence & Automation (4-6 weeks)

> Make it proactive, not just reactive

**Memory improvements:**
- Better recall after restart
- Provenance UX (why did it say that?)
- Memory pinning (never forget important stuff)

**Automation:**
- "Every weekday at 9am turn on kitchen lights"
- "Remind me about meetings from email"
- "You turn on the living room at 7pm, make this a routine?"

**Computer use:**
- "Open Chrome, go to gmail.com"
- "Screenshot this window"
- All with approval safety

---

## 🚀 Phase 4: Easy Running (This Week)

> One script, no thinking required

Create `start_jarvis.sh`:
```bash
#!/bin/bash
# Creates venv if needed, installs deps, starts server
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run_companion.py
```

Then just run: `./start_jarvis.sh`

---

## 📦 What You Need to Run It

1. **Groq API key** - Get at https://console.groq.com
2. **(Optional) Loxone credentials** - For smart home
3. **Python 3.10+**
4. **Tesseract OCR** - `sudo apt install tesseract-ocr` (for PDF/image reading)

**.env file you need:**
```
GROQ_API_KEY=your_key_here
LOXONE_HOST=192.168.0.200        # Your Loxone IP
LOXONE_USER=username
LOXONE_PASSWORD=password
```

---

## 🎯 Success = These 5 Things Work

1. One command starts the app
2. "Turn on all lights" works via Loxone
3. Upload a note, ask about it later (memory)
4. "What's 2+2?" answers safely
5. It only reads files you put in allowed folders

---

*This is your simplified plan. Focus on Phases 2-3 (smart home + intelligence), do Phase 1 quickly.*