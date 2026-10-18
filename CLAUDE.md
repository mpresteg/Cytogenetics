# Cytogenetics

ISCN karyotype parser and report extractor (FastAPI backend, static HTML/JS frontend, FHIR/mCODE export). Background: [README.md](README.md). The task queue and the full git/PR workflow are in [TASKS.md](TASKS.md); read both before starting.

## Commands

- Tests: `cd backend && python3 -m unittest discover -s tests -v`. Needs the OS-level Tesseract binary for the OCR tests.
- Run: `cd backend && python3 -m uvicorn main:app --reload --port 8010` (also `.claude/launch.json`).
- There is no linter or build step. CI (`.github/workflows/tests.yml`) runs the unit tests on pushes to `main` and every PR; `test` is a required check.

## Working agreement

- [TASKS.md](TASKS.md) is the queue (this repo keeps it tracked on purpose). When a message holds several asks, number them, do the ones wanted now, and add anything deferred to TASKS.md's Backlog. End a reply that changed the queue with one line: "Queue now: ...".
- **Docs-only edits** (`TASKS.md`, `README.md`) go straight to `main`. **Anything touching code** gets a branch and a PR; merge only on an explicit "merge please", and **never with red or pending CI** (the instruction does not waive it). Delete the branch after merging.
- Write or extend tests encoding a task's "Done when" before changing the parser.
- Update README's "What this prototype covers" if the change alters what the parser understands.
- **Auto-fix:** after opening a PR, turn Auto-fix on for it (`mcp__ccd_pr__set_monitor`) without asking. Merging is still only on "merge please".

## Rules that must not slip

- **No real or identifiable patient data in this public repo**, in code, tests, fixtures, screenshots, logs or PR text. Test inputs are synthetic or fully de-identified. Do not commit lab report PDFs or images; check `git status` before every commit.
- New entries in the knowledge tables (nomenclature, gene or cytoband data) need a dated citation to the source.
- Clinical content is never auto-merged; every code PR is reviewed by the owner.
- Project skills stay untracked (`.claude/skills/`); adopt them into `~/dotfiles-claude`, never `git add -f` them here.
