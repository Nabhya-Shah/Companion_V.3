# Repository Root Structure Policy

Purpose: keep the repository root stable, readable, and low-noise.

## 1. Root Allowlist

Only these categories should live at repository root:

1. Entrypoints and runtime launch files (for example: run_companion.py, chat_cli.py, web_companion.py, wsgi.py, gunicorn.conf.py).
2. Canonical project docs (README.md, PLAN.md, ROADMAP.md, ARCHITECTURE.md).
3. Dependency and environment files (requirements.txt, pyrightconfig.json, .env.example, .gitignore).
4. Top-level code and asset folders (companion_ai/, static/, templates/, tests/, scripts/, tools/, prompts/, docs/, workflows/).
5. Runtime data folders required for local operation (BRAIN/, data/).

Everything else should be placed in an appropriate subfolder.

## 2. Placement Rules

1. New planning drafts, brainstorms, and temporary backlogs go in docs/notes/planning/.
2. Superseded long-form docs move to docs/archive/ or docs/archive/planning/.
3. Operational runbooks and process docs go in docs/ops/.
4. One-off experiments and probes belong in scripts/ or tools/, not root.
5. New application logic should be added under companion_ai/ subsystem folders, not as new root modules.

## 3. Root Hygiene Rules

1. Do not add date-stamped or temporary markdown files directly in root.
2. Do not add ad-hoc scratch scripts in root.
3. Keep root filenames stable to reduce onboarding friction.
4. If a file must briefly exist in root for migration, move it in the same change set.

## 4. Update Procedure

When adding a new folder/document pattern:

1. Update this policy file.
2. Update docs/README.md if discoverability changes.
3. If behavior or architecture changed, update PLAN.md.
4. If priority/scope changed, update ROADMAP.md.