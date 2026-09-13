# Test Plan

> Phased test rollout for this project. Strategy is frozen at the top
> (§1–§5); cookbook patterns at the bottom (§6) fill in as phases ship.
> Read before writing any new test.
>
> Refresh: re-run `/10x-test-plan --refresh` when stale (see §8).
>
> Last updated: 2026-09-13

## 1. Strategy

Tests follow three non-negotiable principles for this project:

1. **Cost × signal.** The cheapest test that gives a real signal for the
   risk wins. Do not promote to e2e because e2e "feels safer." Do not put a
   vision model on top of a deterministic visual diff that already catches
   the regression.
2. **User concerns are first-class evidence.** Risks anchored in "the
   developer is worried about private photos reaching another user, and the
   failure would surface somewhere in the owner-scoped views or the media
   gate" carry the same weight as PRD lines or hot-spot data.
3. **Risks are scenarios, not code locations.** This plan documents *what
   could fail* and *why we believe it's likely* — drawn from documents,
   interview, and codebase *signal* (churn, structure, test base). It does
   NOT claim to know which line owns the failure. That knowledge is
   produced by `/10x-research` during each rollout phase. If the plan and
   research disagree about where the failure lives, research is the
   ground truth.

Project-specific context: almost all code is written by Claude Code, not by
hand (interview Q3). The suite is the primary reviewer of agent changes, so
tests must assert behavior taken from the PRD and the risk below — never
expected values lifted from the implementation under test.

Hot-spot scope used for likelihood weighting: `accounts/`, `garments/`,
`privatemedia/`, `outfits_garderobe/`, `templates/`, `static/css/`
(excluding migrations, `static/vendor/`, `staticfiles/`, `context/`,
`uv.lock`). 13 commits in scope over 30 days — large per-phase commits, so
churn is thin signal and likelihood leans on roadmap and change reviews.

## 2. Risk Map

The top failure scenarios this project must protect against, ordered by
risk = impact × likelihood. Risks are failure scenarios in user / business
terms, not test names. The Source column cites the *evidence that surfaced
this risk* — never a specific file as "where the failure lives" (that is
research's job, see §1 principle #3).

| # | Risk (failure scenario) | Impact | Likelihood | Source (evidence — not anchor) |
|---|-------------------------|--------|------------|--------------------------------|
| 1 | A user's garment or outfit photo, or a garment/outfit record, becomes visible to another user or to an anonymous visitor — via a guessed media URL, a list/grid that forgets to scope by owner, or media served outside the gate | High | Medium | PRD Guardrails + NFR Prywatność + US-01 AC; interview Q1; change `private-media-gate` impl-review (public-serving temptation around the media URL accessor); roadmap S-03–S-07 add new photo-bearing views; hot-spot dir `privatemedia/` (3 commits/30d + uncommitted work). Likelihood lowered to Medium by the developer: unguessable file names, hobby-scale audience (brief edit) |
| 2 | *Abuse:* a user changes someone else's data because the server trusts an id from the request — composes an outfit from another user's garment, edits/deletes/tags another user's outfit or garment | High | Medium | PRD Access Control; roadmap S-03, S-05, S-06, S-07 (new write paths); interview Q3 (agent-written code). Likelihood lowered to Medium by the developer (brief edit) |
| 3 | *Abuse:* a hostile or oversized image exhausts worker memory and takes the service down; conversely a legitimate phone photo (HEIC, EXIF-rotated, very large JPEG, no-JS upload) is rejected or stored wrong | High | Medium | change `add-garment` impl-review (decompression-bomb memory spike measured, 200 MP JPEG rejected); PRD Guardrails (mobile upload is key); roadmap S-02, S-04 (second upload path); hot-spot dir `privatemedia/` |
| 4 | A settings or deploy change breaks production or loses photos — uploads written outside the persistent volume, healthcheck failing, an old build silently staying live | High | Medium | hot-spot dir `outfits_garderobe/` (11 commits/30d, the top churn area); change `user-accounts` Phase 5 notes (failed deploy from an HTTPS redirect on the healthcheck, prod stayed on an old build); change `private-media-gate` notes (media root must stay under the volume mount); PRD NFR Trwałość danych |
| 5 | Deleting a garment deletes the outfits that used it, or leaves them looking complete instead of flagged as incomplete with a repair/delete option | High | Medium | PRD FR-004 + Business Logic; roadmap S-06; CLAUDE.md (PostgreSQL target, do not rely on SQLite behavior) |
| 6 | Filtering by tag shows the wrong outfits — spelling/case variants of the same tag split results, a removed tag still matches, or another user's tags leak into the filter | Medium | Medium | PRD US-02 + FR-009/FR-010; roadmap S-05 (tag normalization risk) |

High × Low scenarios deliberately not in the map: Railway volume loss or
platform outage — observability/backup territory, not a test.

### Risk Response Guidance

| Risk | What would prove protection | Must challenge | Context `/10x-research` must ground | Likely cheapest layer | Anti-pattern to avoid |
|------|-----------------------------|----------------|--------------------------------------|-----------------------|-----------------------|
| #1 | With two accounts, user B gets a denial/404 on every photo and every owner-scoped page of user A; anonymous requests land on login; no media URL form bypasses the gate; a newly added owner-scoped route is covered without someone remembering to add a test | "The view requires login, so the data is private" — authentication is not ownership | Every entry point that returns photos or owner data (gate, lists, grids, detail, forms with choices); how ownership is derived; how media files are named and served in dev vs prod | integration (Django test client, two users) with a route-enumerating check for coverage of new views | owner-only happy path; asserting status code only while the response body still contains the other user's data |
| #2 | A write request carrying another user's object id changes nothing in the database and is refused; form choice lists contain only the requester's objects | "The form only offers my garments, so the server is safe" — the client can post any id | Every write path (create/edit/delete/tag/compose); where posted ids are validated against the owner; M2M assignment path | integration | asserting only the HTTP status without re-reading persisted state |
| #3 | A decompression-bomb image is refused before full decode without a large memory spike; HEIC, EXIF-rotated and large no-JS JPEGs are stored upright and within bounds; corrupt files give a clean form error | "The browser shrinks photos, so the server only sees small files" — no-JS and hostile clients skip that | Upload size limits at each layer, decode/pixel limits, processing order, error translation to form errors | unit on synthetic in-memory images, plus one integration upload | expected dimensions/bytes copied from the processing code (oracle problem); real multi-MB fixture files committed to the repo |
| #4 | Production settings keep media out of static serving, read the media root from the environment under the volume mount, exempt the healthcheck from HTTPS redirect, and `check --deploy` raises no new warnings beyond the agreed allow-list | "It works on runserver, so it works on Railway" | Production vs test settings split, env-var contract, healthcheck path, deliberate deploy-check deviations already recorded | settings/config pin tests (unit) | snapshotting the whole settings module; tests that pass only because test settings override the production value |
| #5 | After a garment is deleted, every outfit that used it still exists with its remaining garments, is flagged incomplete, and the grid shows the repair/delete affordance; the garment's other outfits are equally affected; other users' outfits are untouched | "M2M does not cascade, so nothing breaks" — absence of deletion is not the incomplete flag | How incompleteness is persisted or derived, delete path, behavior under PostgreSQL constraints | integration on models + view | running only on SQLite semantics; asserting the flag without checking the outfit still exists |
| #6 | A tag filter returns exactly the requester's outfits carrying that tag, treating agreed variants (case/whitespace) as one tag; removing a tag removes the outfit from the filter | "Filtering by name is trivial" | Tag normalization rule chosen in S-05, tag ownership model, filter query path | integration | computing the expected list with the same query the view uses |

## 3. Phased Rollout

Each row is a discrete rollout phase that will open its own change folder
via `/10x-new`. Status moves left-to-right through the values below; the
orchestrator updates Status as artifacts appear on disk.

| # | Phase name | Goal (one line) | Risks covered | Test types | Status | Change folder |
|---|------------|-----------------|---------------|------------|--------|---------------|
| 1 | Cross-user privacy contract | Prove no photo or owner data crosses accounts, on reads and writes, and make new owner-scoped views inherit the check before S-03 lands | #1, #2 | integration | change opened | testing-cross-user-privacy |
| 2 | Upload abuse and deploy durability | Prove hostile images cannot take the service down, real phone photos survive, and production settings keep photos persistent and the deploy healthy | #3, #4 | unit + config pin tests | not started | — |
| 3 | Outfit consistency and tag filtering | Prove garment deletion flags outfits incomplete without losing them, and tag filters return exactly the right own outfits — start only after roadmap S-05 and S-06 are done | #5, #6 | integration | not started | — |
| 4 | Agent-loop guardrails and gates | Run lint + the relevant tests at edit time in the agent loop and block deploys on a red suite, since code is agent-written and no CI exists | cross-cutting | post-edit hook + pre-deploy gate | not started | — |

## 4. Stack

The classic test base for this project. AI-native tools (if any) carry a
`checked:` date so future readers can see which lines need re-verification.

Test-base profile: `sparse` — pytest-django configured, 101 tests in 9 files
spread across `accounts/`, `garments/`, `privatemedia/`; no CI workflows.

| Layer | Tool | Version | Notes |
|-------|------|---------|-------|
| unit + integration | pytest + pytest-django (Django test client) | 9.0.3 / 4.12.0 | Existing runner; dedicated test settings module configured in `pyproject.toml` |
| test images | Pillow + pillow-heif (synthetic, generated in-test) | 12.3.0 / 1.7.0 | Build hostile/phone-like images in memory; do not commit large fixtures |
| external HTTP mocking | none | — | Only external edge is Brevo, out of scope (§7) |
| e2e | none — deliberately | — | Routing, looks and account flow are out of scope (§7); privacy is provable at integration level |
| lint / audit | ruff, pip-audit | 0.15.15 / 2.10.0 | Already in dev deps; not yet enforced anywhere — see Phase 4 |
| (AI-native) post-edit hook | Claude Code hooks — checked: 2026-09-13 | n/a | See Phase 4. When NOT to use: as a substitute for the pre-deploy gate, or running the full suite on every edit once it gets slow |

**Stack grounding tools (current session):**
- Docs: none (no Context7 or framework docs MCP) — versions taken from `pyproject.toml` and the installed environment; checked: 2026-09-13
- Search: WebSearch/WebFetch available, not used — no stack-sensitive recommendation needed verification at strategy level; checked: 2026-09-13
- Runtime/browser: Chrome browser skill available; headless Chromium (Playwright) was used ad hoc for manual verification in change `add-garment` — not adopted as a test layer; checked: 2026-09-13
- Provider/platform: Railway MCP available — deploy status, logs and healthcheck results are relevant to Risk #4 and the Phase 4 gate; no GitHub MCP; checked: 2026-09-13

## 5. Quality Gates

The full set of gates that must pass before a change reaches production.
"Required after §3 Phase <N>" means the gate is enforced once that rollout
phase lands; before that, the gate is `planned`.

| Gate | Where | Required? | Catches |
|------|-------|-----------|---------|
| lint (ruff check + format check) | local + pre-deploy | required after §3 Phase 4 | syntactic drift, unused/incorrect imports |
| unit + integration (pytest) | local + pre-deploy | required after §3 Phase 1 locally; enforced before deploy after §3 Phase 4 | privacy, abuse and consistency regressions |
| dependency audit (pip-audit) | pre-deploy | required after §3 Phase 4 | known-vulnerable dependencies |
| deploy config check (`check --deploy` against agreed allow-list) | test suite | required after §3 Phase 2 | insecure or broken production settings |
| post-edit hook | local (agent loop) | recommended after §3 Phase 4 | regressions at edit time, before a commit exists |
| platform healthcheck | Railway deploy | required (already wired) | a build that does not boot or answer the health endpoint |

No typecheck gate: the project has no type checker, and none is planned.
No e2e or visual gates: see §7.

## 6. Cookbook Patterns

How to add new tests in this project. Each sub-section is filled in once
the relevant rollout phase ships; before that, the sub-section reads
"TBD — see §3 Phase <N>."

### 6.1 Adding a cross-user access test for a new owner-scoped view

- TBD — see §3 Phase 1 (two-account read denial + write-with-foreign-id refusal pattern, and how a new route gets picked up automatically).

### 6.2 Adding an image-upload abuse or phone-photo test

- TBD — see §3 Phase 2 (synthetic hostile/phone-like image pattern, asserting outcome from the PRD rather than from processing code).

### 6.3 Pinning a production setting

- TBD — see §3 Phase 2 (deploy-config pin pattern for volume path, media serving, healthcheck redirect, deploy-check allow-list).

### 6.4 Adding a domain-consistency test (deletion, incomplete state, tag filter)

- TBD — see §3 Phase 3 (garment-deletion-flags-outfit and exact-tag-filter patterns).

### 6.5 Running tests in the agent loop and before deploy

- TBD — see §3 Phase 4.

### 6.6 Per-rollout-phase notes

(After each phase lands, `/10x-implement` appends a 2-3 line note here
capturing anything surprising the rollout phase taught.)

## 7. What We Deliberately Don't Test

Exclusions agreed during the rollout (Phase 2 interview, Q5). Future
contributors should respect these unless the underlying assumption changes.

- **Django admin** — used only by the developer. Re-evaluate if anyone else gets admin access. (Source: Phase 2 interview Q5.)
- **Account flow mechanics (signup, email confirmation, login, password reset/change)** — delegated to django-allauth and verified manually in production. Exception kept in scope: anonymous requests for private data must land on login (Risk #1). Re-evaluate if the account flow is customized beyond configuration. (Source: Phase 2 interview Q5.)
- **Brevo email delivery** — verified once end-to-end in production; not mocked. Re-evaluate if email becomes more than account mail. (Source: Phase 2 interview Q5.)
- **Look and styles (CSS, 360 px layout)** — checked by eye; snapshot or visual tests would be brittle. Re-evaluate if a layout regression reaches production and blocks a flow. (Source: Phase 2 interview Q5.)
- **Routing between views (redirect targets, link navigation)** — low blast radius, covered implicitly by use. Re-evaluate if a broken redirect loses user data. (Source: Phase 2 interview Q5.)

## 8. Freshness Ledger

- Strategy (§1–§5) last reviewed: 2026-09-13
- Stack versions last verified: 2026-09-13
- AI-native tool references last verified: 2026-09-13

Refresh (`/10x-test-plan --refresh`) when:

- a new top-3 risk surfaces from the roadmap or archive,
- a recommended tool's `checked:` date is older than three months,
- the project's tech stack changes (new framework, new test runner),
- §7 negative-space no longer matches what the team believes.
