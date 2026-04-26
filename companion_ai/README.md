# Companion AI Package Map

This folder contains the application code.

## Primary Boundaries

1. web/: Flask app factory and HTTP routes.
2. llm/: provider clients, routing, token tracking.
3. memory/: memory backends, quality pipeline, write queue.
4. tools/: callable tools and tool-policy execution surface.
5. services/: workflows, jobs, persona, insights, continuity.
6. local_loops/: loop executors used by orchestrator delegation.
7. orchestration/: runtime orchestration engine routing.
8. brain/: brain-file manager and semantic brain index.
9. runtime/: canonical conversation/computer/orchestrator runtime implementations.

## Runtime Entry Modules

1. runtime/conversation.py: session conversation runtime and streaming glue.
2. runtime/orchestrator.py: orchestration decision engine.
3. runtime/computer.py: desktop/computer interaction runtime.
4. local_llm.py: local model runtime integration.

## Compatibility Shims

These are intentionally kept for import stability:

1. brain_index.py -> companion_ai.brain.index
2. brain_manager.py -> companion_ai.brain.manager
3. conversation_manager.py -> companion_ai.runtime.conversation
4. computer_agent.py -> companion_ai.runtime.computer
5. orchestrator.py -> companion_ai.runtime.orchestrator
6. llm_interface.py -> companion_ai.llm package re-exports

They allow older imports/tests/scripts to keep working while implementation lives in clearer subpackages.

## Cleanup Rule

When adding new code:

1. Put feature logic in a subsystem folder first (web, memory, tools, services, brain, etc.).
2. Keep top-level modules for runtime entrypoints and compatibility only.
3. Prefer importing from subsystem packages over compatibility shim modules.
