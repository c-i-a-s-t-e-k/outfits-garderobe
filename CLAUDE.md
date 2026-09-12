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

## 10xDevs AI Toolkit - Module 2, Lesson 5

Scale the single-change cycle into parallel work with **worktrees, goal-directed delegation, and multi-session orchestration**:

```
worktree per change -> /goal or claude -p -> PR -> review -> merge
```

The lesson focus is safe throughput: isolated contexts, choosing the right execution mode, and capping parallelism at review capacity.

### Task Router - Where to start

| Skill | Use it when |
| --- | --- |
| **Code isolation** | |
| `git worktree add` | You need a separate working directory for a parallel change. One change per worktree, one fresh agent context per worktree. |
| **Complex changes** | |
| `/10x-implement <change-id> phase <n>` | The change has multiple phases, needs manual gates, or benefits from interactive decision-making during execution. |
| **Simple changes** | |
| `/goal` | You have a clear, bounded task and want goal-directed delegation. The agent works autonomously toward the stated goal with a stop condition. |
| `claude -p` | You want headless execution for a well-defined task. The Ralph Wiggum loop (run, check, retry) is the universal autonomous pattern. |
| **Multi-session orchestration** | |
| Superset / Conductor / Antigravity / VS Code Agent View | You are running multiple agent sessions in parallel and need visibility, coordination, or session management across them. |

### Parallel work rules

- One change per worktree or isolated workspace. One fresh agent context per change.
- Choose interactive `/10x-implement` for complex changes, `/goal` or `claude -p` for simple ones.
- Parallelism is capped by review capacity. More agents without review means more unreviewed code, not higher throughput.
- The quality pain from faster shipping is intentional — it bridges into Module 3 testing gates.

### Lesson boundaries

- Do not reteach interactive `/10x-implement` or `/10x-impl-review`; those are Lessons 2 and 3.
- Do not introduce testing strategy here. The quality pain is the motivation for Module 3.
- Worktrees are a mechanism for isolation, not the topic of a full git tutorial.

### Paths used by this lesson

- `context/changes/<change-id>/` - active change folder
- `context/changes/<change-id>/plan.md` - implementation input for any execution mode

Skills must not write to `context/archive/`. Archived changes are immutable; if a resolved target path starts with `context/archive/`, abort with: "This change is archived. Open a new change with `/10x-new` instead."

<!-- END @przeprogramowani/10x-cli -->
