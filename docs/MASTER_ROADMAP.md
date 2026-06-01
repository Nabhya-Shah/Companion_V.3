# Companion V3 - Master Roadmap & Strategic Autonomy Plan

This master roadmap synthesizes what Companion V3 has accomplished so far, alongside the forward-looking strategic evolution plan necessary to bring the platform up to highly secure "JARVIS-level" autonomy.

---

## 1. What Has Been Completed So Far (The Baseline)

### Architecture & Runtime
- **Streaming Web UI:** Deployed stable Flask application serving Server-Sent Events (SSE) natively.
- **Orchestrator-Led Routing:** Complete implementation of LLM-based deterministic routing decisions (`answer`, `delegate`, `plan`, `background`, `memory_search`).
- **Dynamic Fallbacks:** Configurable fallback mechanisms traversing between Cloud (Groq) and Local (Ollama/vLLM) runtimes.
- **Background Job Execution:** End-to-end trace IDs, background task schedules, and multi-step plan orchestration.

### Memory & State
- **Hybrid Memory Backend:** Unified integration between Mem0 (vectors) and SQLite (fact/rule metadata).
- **Knowledge Quality Pipeline:** Confidence score tracking, deduplication logic, and pending-review queues for incoming structural memory.
- **Brain Indexing:** File manager and indexing capable of capturing document context, mapping into semantic brain trees tightly confined to safe system scopes.

### Governance & Tools
- **Tool Sandbox:** Initial implementations of policy gates, block/allow lists, and permission-tiered registries (`registry.py`).
- **Feature Modules:** Delivery of specialized tool execution modules (`browser_tools.py`, Smart Home hooks, and document parsers).
- **Approval System:** Integration of a user-based approval gateway for `risk_tier="high"` requests to limit run-away automation.

---

## 2. Future Roadmap: The Journey to Autonomous Security

### Phase 1: Critical Security Remediation & Hardening
**Core Objective:** Remove foundational system destruction vulnerabilities and govern execution boundaries securely.
* [x] **Regex Filtering & Jails:** Add strict heuristic command sanitization inside `ComputerAgent.launch_app` (`computer.py`) to block commands like `rm`, `dd`, etc., and enforce secondary localized docker namespaces/chroots for operations.
* [x] **Action Rollback Systems:** Introduce immediate undo/transaction-reversion capabilities natively tailored for `brain_write`.
* [x] **API Rate Limiting & Quotas:** Stand up resource restriction mechanisms natively limiting tokens, API requests, and repeated background-loop queries.
* [ ] **Browser Reliability:** Strengthen Playwright loops with better deterministic contracts and visible telemetry diagnostics.

### Phase 2: Intelligence & Reflexive Autonomy 
**Core Objective:** Push standard deterministic execution towards intelligent, self-healing reflection.
* **The "Verifier" Agent Loop:** Insert an explicit layer between the Orchestrator and High-Risk Execution. Secondary independent local LLMs must perform pre-flight catastrophe checking before tools act.
* **Continuous Conflict Resolution:** Move memory review functionality into background, cross-referencing contradictions directly and presenting semantic summaries without pausing real-time UI chat streams.
* **Chain-of-Thought (CoT) Debug UI:** Expose the internal orchestrator and verifier routing logic visually to standard users, promoting diagnostic debugging natively.

### Phase 3: Capability Extension & Skill Generation 
**Core Objective:** Enhance external coverage securely while letting the agent expand its own knowledge graph.
* **Procedural Skill Factory:** Build pathways inside `workflows.py` allowing the AI to safely write, sandbox, and utilize new standalone Python routines generated from explicit user patterns.
* **MCP-First Infrastructure:** Extract and separate all heavy OS-operations (like Playwright contexts or shell invocations) out of the Companion app tier into detached Model Context Protocol (MCP) servers with localized network boundaries.
* **System Expansion:** Enhance core tool coverage natively spanning across precise file system modifiers (safe path-mapped file move/rename capabilities), calendar IMAP connectors, and deeper Smart Home device handling.

### Phase 4: Full Multi-User Extensibility & Goal Architecture
**Core Objective:** Transform the product into a long-horizon, proactive environment.
* **Proactive Goal Engine:** Move the current 'Insights' module into a forward-acting scheduler allowing the AI to create tasks and fetch memory information *before* the user prompts.
* **Advanced Multi-User RBAC:** Enhance system variables from workspace-scopes to fully distinct File/Tool permission profiles for multi-person deployments sharing one backend base.
* **Anomaly Detection Layers:** Evolve static computer action logs into real-time telemetry scanners designed to sever the loop pipeline if compromised prompts attempt jailbreaks.