# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - 2025-09-16
### Added
- Provenance memory UI (expandable fact metadata: confidence tier, reaffirmations, timestamps, evidence).
- `/api/memory?detailed=1` extended endpoint returning `profile_detailed` array.
- `/api/routing/recent` endpoint exposing tail of routing & ensemble decisions.
- Second-pass heavy fact verifier active (low-confidence gating) prior to staging/commit.
- Compound / agentic model routing stub (purpose `compound` / `agentic`) behind `ENABLE_COMPOUND_MODELS`.

### Changed
- README updated to reflect active verifier and provenance/routing features.
- Config `choose_model` now handles compound path when enabled.

### Fixed
- Removed stray debug artifact in model endpoint test.

### Notes
- Ensemble path unchanged (trio choose_refine); future work: embedding retrieval, streaming, cost dashboards.

## [0.2.0] - 2025-09-13
### Added
- Trio ensemble reasoning (smart + heavy + alt) with judge + refine (`choose_refine`).
- `/api/models` transparency endpoint (roles, capabilities, flags, ensemble settings).
- Rich routing metadata logging (ensemble candidates, rationale, confidence, refinement stats).
- Skill-scored autonomous tool usage with gating & cooldown suppression.
- Confidence decay + resurfacing cycle for profile facts.
- Structured fact storage with evidence, justification, reaffirmations fields.
- Heavy model differentiation (SMART=`openai/gpt-oss-120b`, HEAVY=`deepseek-r1-distill-llama-70b`).
- Heavy alternates list including `moonshotai/kimi-k2-0905`.
- Feature flags: `ENABLE_ENSEMBLE`, `ENABLE_EXPERIMENTAL_MODELS`, `ENABLE_COMPOUND_MODELS`, fact approval & second-pass verifier placeholders.

### Changed
- README overhauled to reflect multi-model routing & new observability endpoints.
- Routing logic escalates by complexity (0..3) & importance.

### Planned / Pending
- Provenance UI for fact evidence & confidence visualization.
- Second-pass heavy fact verification pipeline.
- Compound / agentic model stub integration.
- Embedding + hybrid retrieval layer.

## [0.1.0] - 2025-08-XX
### Added
- Initial adaptive persona, memory persistence (facts, summaries, insights).
- Basic heuristic routing & context builder.
- Azure TTS integration and GUI/web shells.
- Tool framework (time, calc, search).

---
Adheres to Keep a Changelog recommendations (simplified).
