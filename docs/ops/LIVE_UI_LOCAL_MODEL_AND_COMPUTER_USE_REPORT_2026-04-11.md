# Live UI Local Model + Computer-Use Report (2026-04-11)

Status: Completed
Run type: Real web UI interaction (Playwright-driven browser session against running Companion web app)
Base URL: http://127.0.0.1:5000
Run ID: live_ui_local_ux_20260411_200033

## 1) Scope Executed

1. Added local heavy model contender support in runtime config and Stats UI runtime controls.
2. Pulled both requested local contender models in Ollama:
   - qwen3.5:27b
   - gemma4:31b
3. Switched models from the actual UI runtime panel and ran the same prompt for both.
4. Ran a vision interaction from chat UI.
5. Ran a computer-use interaction from chat UI and captured policy/activity outcomes.

## 2) Runtime/Model Evidence

Ollama local inventory at execution time included:
- gemma4:31b
- qwen3.5:27b
- qwen2.5:7b
- qwen2.5:3b
- llava:7b
- nomic-embed-text:latest

UI runtime panel confirmed selected local heavy model values changed between runs:
- qwen3.5:27b (first run)
- gemma4:31b (second run)

## 3) Prompts + Responses (Captured from UI)

### A) Contender model run 1
Model selected in UI: qwen3.5:27b
Prompt:

Go to https://example.com and tell me the exact page title and exact H1 text. Then summarize the page purpose in one sentence.

Response:

The page title is "Example Domain" and the H1 text is "Example Domain". The page appears to be a basic placeholder page for a domain, likely used for testing or demonstration purposes.

### B) Contender model run 2
Model selected in UI: gemma4:31b
Prompt:

Go to https://example.com and tell me the exact page title and exact H1 text. Then summarize the page purpose in one sentence.

Response:

The page title is "Example Domain" and the H1 text is "Example Domain". This page is a basic placeholder for a domain, probably used for testing.

### C) Vision run
Prompt:

Look at the current screen and list 3 concrete UI elements you can see right now.

Response:

The screen shows a navigation bar at the top, a large "Example Domain" heading (the H1), and a paragraph of descriptive text beneath it.

### D) Computer-use run
Prompt:

Use computer control and press Enter once, then confirm what action happened.

Response:

I gave it a try, but I don’t have the ability to actually press keys on your machine. If you’d like, I can walk you through the steps to hit Enter yourself and let you know what should happen next. Just let me know what you’re trying to trigger, and we’ll get it sorted out together!

Computer-use activity panel captured:
- Status: REJECTED
- Action: UNKNOWN ACTION
- Reason: plugin_denied
- Error: Tool 'use_computer' blocked by plugin policy (plugin='core')

## 4) Comparison Notes

1. Both contender models produced correct title/H1 extraction on the same navigation task.
2. qwen3.5:27b response was slightly more verbose; gemma4:31b response was shorter and tighter.
3. Vision interaction succeeded with concrete, on-screen element identification.
4. Computer-use path is reachable from UI but currently blocked by plugin policy in this environment, resulting in rejection rather than execution.

## 5) Artifact Proof

Artifacts directory:
- data/benchmarks/live_ui_local_ux_20260411_200033

Files:
- data/benchmarks/live_ui_local_ux_20260411_200033/ui_loaded.png
- data/benchmarks/live_ui_local_ux_20260411_200033/model_1_qwen3.5_27b.png
- data/benchmarks/live_ui_local_ux_20260411_200033/model_2_gemma4_31b.png
- data/benchmarks/live_ui_local_ux_20260411_200033/vision_run.png
- data/benchmarks/live_ui_local_ux_20260411_200033/computer_use_panel.png
- data/benchmarks/live_ui_local_ux_20260411_200033/ux_report.json

## 6) Practical Conclusion

- Local contender switching via UI is functional and fast enough for side-by-side UX comparisons.
- Both requested contender models are installed and usable through Ollama runtime selection.
- Vision path is operational in live UI flow.
- Computer-use requires policy adjustment before live keypress/click execution can complete successfully in this workspace policy state.
