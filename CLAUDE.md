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

<!-- BEGIN @przeprogramowani/10x-cli -->

## 10xDevs AI Toolkit - Module 2, Lesson 3

Review AI-generated code before merge with the **implementation review chain**:

```
/10x-implement -> /10x-impl-review -> triage -> (/10x-lesson | fix | skip | disagree)
```

`/10x-impl-review` is the lesson focus. Review is a quality gate, not an instruction to fix every finding.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Code review (lesson focus)** | |
| `/10x-impl-review <change-id>` | You have implemented code and want a structured review before merge. The skill checks plan adherence, scope discipline, safety and quality, architecture, pattern consistency, and success criteria, then presents findings for triage. |
| **Recurring lesson outcome** | |
| `/10x-lesson` | A finding reveals a recurring project rule or agent failure pattern. Record it in `context/foundation/lessons.md` instead of treating it as a one-off note. |

### Triage discipline

- Severity says how bad the finding is. Impact says how much the decision matters now.
- Valid outcomes: fix now, fix differently, skip, accept as risk, record as recurring rule (`/10x-lesson`), disagree.
- Fix critical findings. Do not burn hours on low-impact observations just because the agent found them.
- Conscious skipping of low-impact findings is a valid review outcome, not negligence.
- If you disagree with a finding, record why. Wrong agent reasoning is also signal.

### Review boundaries

- This lesson reviews implemented code. It does not create the plan, execute new phases, or teach CI review.
- Testing strategy and quality gates are introduced in Module 3.
- Do not use `/10x-contract` as a triage outcome in this lesson.

### Paths used by this lesson

- `context/changes/<change-id>/plan.md` - expected implementation contract
- `context/changes/<change-id>/reviews/` - review output
- `context/foundation/lessons.md` - recurring lessons

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
