# V6 Implementation TODO

> **Start Date**: December 20, 2024  
> **Goal**: Clean 120B orchestrator + local loops architecture

---

## Phase 1: Docker vLLM Setup ⏳

- [ ] Verify Docker Desktop version (need 4.54+)
- [ ] Create `docker-compose.vllm.yml`
- [ ] Test vLLM container with Qwen 3B
- [ ] Verify GPU passthrough working
- [ ] Create health check endpoint

**Expected Issues:**
- CUDA version mismatch
- GPU memory allocation

---

## Phase 2: Local Loops Module ⏳

- [ ] Create `companion_ai/local_loops/` directory
- [ ] Create base `Loop` class
- [ ] Implement `MemoryLoop`
- [ ] Implement `VisionLoop`
- [ ] Implement `ToolLoop`
- [ ] Create loop registry

**Files to Create:**
```
companion_ai/local_loops/
├── __init__.py
├── base.py          # Base Loop class
├── memory_loop.py
├── vision_loop.py
├── tool_loop.py
└── registry.py      # Loop discovery
```

---

## Phase 3: Refactor 120B Routing ⏳

- [ ] Create `companion_ai/orchestrator.py`
- [ ] Define structured decision format
- [ ] Implement loop delegation
- [ ] Handle loop responses
- [ ] Add memory save logic (AFTER response)
- [ ] Remove old hybrid routing from `llm_interface.py`

**Key Changes:**
- 120B outputs JSON decision (internal)
- Decision types: `answer`, `delegate`, `background`
- Never show raw decisions to user

---

## Phase 4: Memory System Fix ⏳

- [ ] Update `memory_v2.py` to use local Memory Loop
- [ ] Only save on explicit facts (not every message)
- [ ] Implement loop learning (save useful discoveries)
- [ ] Test with browser agent

---

## Phase 5: Background Task Panel ⏳

- [ ] Create left slide-in panel HTML
- [ ] Implement task list UI
- [ ] Add expandable timeline view
- [ ] SSE endpoint for task updates
- [ ] Notification on completion

---

## Testing Checklist

All tests via browser agent:

- [ ] "Hi" → Quick 120B response
- [ ] "My name is Bob" → Fact saved
- [ ] "What's my name?" → Memory retrieval
- [ ] "What's on my screen?" → Vision loop
- [ ] "Open Chrome, go to google" → Background task

---

## Pre-Implementation Prep (Done Tonight) ✅

- [x] Delete old documentation
- [x] Create ARCHITECTURE.md
- [x] Update README.md
- [x] Create TODO.md
- [x] Clean up code state

---

## Notes

- Keep current models for now (user will review later)
- Focus on clean architecture over features
- Test each phase before moving on
