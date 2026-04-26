# Beginner Folder Guide

This is a practical map of what matters day-to-day.

## Core App Files (keep visible)

1. run_companion.py: main launcher for the app.
2. companion_ai/: backend logic and all app features.
3. static/: frontend JavaScript and CSS.
4. templates/: HTML templates for the web UI.
5. requirements.txt: Python dependency list.
6. README.md: setup and run steps.
7. PLAN.md and ROADMAP.md: project truth and direction.

## Core Runtime Data (used while app runs)

1. BRAIN/: your personal notes, memories, logs and system rules.
2. data/: runtime database files and logs.

These are expected in local use.

## Helpful But Optional During Daily Use

1. tests/: automated tests.
2. scripts/: utility scripts and probes.
3. tools/: helper tooling used by development/testing workflows.
4. docs/: planning, notes, archived design/history.
5. workflows/: routine/workflow definitions.
6. prompts/: persona and prompt material.

## Usually Safe To Ignore

1. .venv/: local Python environment (required to run, but no need to edit manually).
2. .vscode/: editor settings.
3. .git/: version control internals.
4. .env.example: sample env template.

## Practical Rule of Thumb

If you only want to use the app, focus on:

1. run_companion.py
2. companion_ai/
3. static/
4. templates/
5. BRAIN/
6. data/
7. README.md

For a code-level map of companion_ai internals:

1. companion_ai/README.md
