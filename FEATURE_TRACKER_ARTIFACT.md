# Companion AI Feature Tracker

Date: 2026-03-11

This file tracks user-visible product status in plain language.

## How To Read This File

- `ROADMAP.md` is the planning source of truth.
- This file answers: what is live, what shipped recently, and what is next.
- `ROADMAP_ARTIFACT.md` is archived context only.

## Live Product Status

| Area | State | What it means for the user |
|---|---|---|
| Web chat + streaming | ✅ Live | Browser chat works with live streamed replies |
| Orchestrator routing | ✅ Live | Messages route through the main decision layer by default |
| Local loops | ✅ Live | Memory, tool, and vision delegation paths are built |
| Memory management UI | ✅ Live | Memories can be viewed, searched, edited, deleted, and cleared |
| Session/workspace isolation | ✅ Live | Memory and brain state stay scoped instead of bleeding across sessions |
| Tool safety policy | ✅ Live | Risky tools can be blocked with visible denial reasons |
| Schedules and workflows | ✅ Live | Recurring actions, routines, approvals, and task progress are available |
| Knowledge workflow | ✅ Live | Uploaded files can be indexed, searched, summarized, and managed |
| Smart home integration | ✅ Live | Health checks and core control flows are implemented |
| Persona evolution | ✅ Live | Persona updates exist and are triggered by conversation/memory events |

## Current Technical Baseline

| Layer | Current baseline | Why it matters |
|---|---|---|
| Primary chat | Groq `openai/gpt-oss-120b` | Current production baseline |
| Fast tool path candidate | Groq `llama-3.1-8b-instant` | Good fit for a later quick-tool slice |
| Memory processing | Groq plus local loops | Next work needs a clearer local-vs-cloud policy |
| Local heavy model path | vLLM `Qwen/Qwen2.5-3B-Instruct` | Useful for extraction, reflection, or other memory jobs |
| Local vision fallback | Ollama `llava:13b` | Preserves local multimodal fallback |

## Recently Completed

| ID | Feature | User value | Status |
|---|---|---|---|
| R-01 | Daily-use smoke checks | One command verifies core app health | ✅ Completed |
| R-02 | Clean-machine setup hardening | Faster reliable startup on new machines | ✅ Completed |
| R-03 | Simpler memory/settings UX | Less friction in daily use | ✅ Completed |
| R-04 | Startup token-burn reduction | Fresh page load avoids unnecessary hidden work | ✅ Completed |
| R-05 | Session-scoped Mem0 hardening | Memory reads no longer trigger migration-style churn | ✅ Completed |
| R-06 | Provider benchmark gate | Default provider was re-validated instead of assumed | ✅ Completed |
| R-07 | Browser fallback hardening | Browser agent can fall back to bundled Chromium if Chrome is missing | ✅ Completed |

## Next Execution Window

| ID | Initiative | Why it matters | Status |
|---|---|---|---|
| P7-03 | Memory extraction completion | Makes memory capture real enough to support long-horizon behavior | 🟡 Planned |
| P7-04 | Memory model manager | Gives memory jobs an explicit local-vs-Groq routing policy and a clean place for embeddings | 🟡 Planned |
| P8-01 | Long-horizon memory quality | Improves retrieval, consolidation, contradiction handling, and trust over time | 🟡 Planned |
| P8-02 | Persona grounded in memory | Makes persona depth reflect real accumulated context instead of style-only prompting | 🟡 Planned |
| P8-03 | Reflection and project continuity | Lets Companion track ongoing projects, open loops, and cross-session context better | 🟡 Planned |
| T-01 | Quick tool path | Useful latency/cost slice, but secondary to memory work | 🟡 Tactical |

## Current Product Bet

The product is no longer blocked on provider selection. The strongest next differentiators are:

1. trustworthy long-horizon memory
2. better recall quality over time
3. persona depth grounded in persistent context
4. continuity across projects and days

## Notes

- Active roadmap: `ROADMAP.md`
- Historical archive only: `ROADMAP_ARTIFACT.md`
- Architecture reference: `ARCHITECTURE.md`
- Update this file when user-visible status changes
