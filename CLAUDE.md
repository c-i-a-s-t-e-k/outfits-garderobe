# CLAUDE.md
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Outfits Garderobe is a Django 6 wardrobe app where users compose and revisit *outfits* (groups of garments), not just catalog clothes. Product spec: @context/foundation/prd.md (in Polish — domain terms come from there). Stack rationale: @context/foundation/tech-stack.md.

## Secrets & environment variables

- **`.env` lives at `../.secrets/outfits-garderobe/.env`** (relative to the project root). Assume it exists and contains all required keys. Never read, cat, or inspect it.
- If a task would fail because a key is missing, stop and tell the developer: "Please check your `.env` — the key `<NAME>` appears to be missing or incorrect." Do not attempt to work around it or infer the value.
- Deny any task that requires reading the contents of `.env`.

## Environment & commands

- **uv manages everything** — do not use `pip`, `python -m venv`, or run a bare `python`. Run code through `uv run` (e.g. `uv run python manage.py ...`, `uv run pytest`). Add deps with `uv add` / `uv add --dev`; never hand-edit `uv.lock`.
- Tests: `uv run pytest` (pytest-django; settings come from `pyproject.toml`). Single test: `uv run pytest path/to/test.py::TestClass::test_method`.
- Lint/format: `uv run ruff check .` and `uv run ruff format .`.
- Security audit: `uv run pip-audit`.

## Conventions & gotchas

- **User photos are private.** Garment and outfit images must never be served publicly or be reachable by another user — enforce per-user ownership checks on every media access (guardrail FR in the PRD). Do not drop uploads into `MEDIA_URL` static serving without an auth gate.
- DB is SQLite in dev (`settings.py`), but the target is PostgreSQL — don't rely on SQLite-only behavior (e.g. loose typing, lack of real constraints).
- A garment can belong to many outfits (many-to-many) — model accordingly.
- No Django apps exist yet beyond the `outfits_garderobe` config package; create domain apps as the work needs them.

