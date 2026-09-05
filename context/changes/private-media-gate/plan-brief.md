# Prywatna brama dostępu do zdjęć użytkownika — Plan Brief

> Full plan: `context/changes/private-media-gate/plan.md`
> Change identity: `context/changes/private-media-gate/change.md`
> Roadmap item: F-01, milestone M-1, stream A

## What & Why

Every photo a user uploads must land outside any publicly served directory, and every read of it must pass through a view that requires a login and verifies ownership. This is roadmap foundation **F-01**, built *before* the first upload feature exists — adding the gate later would mean relocating files already on disk and rewriting every URL that points at them. It satisfies the PRD's *Prywatność* NFR ("zero cross-user leaks"), the *Access Control* section, and the storage half of FR-003 and FR-007.

## Starting Point

The repo holds only the `outfits_garderobe` config package — no domain app, no models, no templates, no tests. `MEDIA_ROOT` and `MEDIA_URL` are never set, so Django resolves them to `''` and `'/'`; there are no uploaded files to migrate. Whitenoise serves only `STATIC_ROOT`, so nothing leaks today. Three things surfaced during research: `settings.py:113` sets `STATICFILES_STORAGE`, which Django removed in 5.1 and 6.0.5 silently ignores (production is shipping unhashed static files); Pillow is not installed; and Railway has **no volume mounted**, so anything written to disk is destroyed on the next deploy.

## Desired End State

A logged-in user fetches their own photo at `/media/<uuid>/` and gets the bytes. A different logged-in user requesting that same URL gets a `404` indistinguishable from a URL that was never valid. An anonymous visitor is redirected to login. The files sit on a Railway volume under names carrying no information, outside everything whitenoise serves, and a redeploy does not destroy them.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| Physical storage | Railway volume at `/data`, `MEDIA_ROOT=/data/media` | `infrastructure.md` already accepts a single volume as sufficient below 10 GB, and it needs no new dependency or credentials. | Plan |
| Ownership model | One central `PrivateImage` model (owner FK + file) | Puts the check in exactly one place with one URL and one test, and is exercisable today against `django.contrib.auth` before any domain model exists. | Plan |
| URL & filename | UUID in the URL, UUID on disk | Defense in depth — nothing is enumerable or guessable even if the check were bypassed, and it sidesteps collisions and unicode issues from phone uploads. | Plan |
| Denial response | `404` for both "missing" and "not yours" | A probe cannot distinguish them, which is what makes the two-account test meaningful. | Plan |
| Caching | `Cache-Control: private` + conditional GET | Keeps a 20-tile grid inside the PRD's 5-second budget without letting any shared cache hold the bytes. | Plan |
| Scope in F-01 | Model + storage + gate + tests + admin registration | Admin is a staff-only verification surface, so the gate gets exercised by hand without throwaway UI that S-02 would delete. | Plan |
| Validation | `ImageField` (Pillow) + explicit size cap | Rejects a renamed non-image rather than trusting the extension, and the rule lives in the storage layer so S-02 and S-04 both inherit it. | Plan |
| Test coverage | Gate behaviour + a configuration guard | The config assertion catches the regression that would silently re-expose media in a later change. | Plan |
| Dead static setting | Repaired in this change | The same `STORAGES` dict is being written anyway; leaving a known-broken setting beside a new one invites copying the broken pattern. | Plan |

## Scope

**In scope:** `MEDIA_ROOT`/`MEDIA_URL` configuration; a unified `STORAGES` dict (repairing the dead `STATICFILES_STORAGE`); Pillow; the `privatemedia` app with the `PrivateImage` model, migration, gate view, URL route and admin registration; the repo's first test suite; Railway volume provisioning and production verification.

**Out of scope:** any upload form or user-facing UI (S-02); resizing and thumbnails; object storage, signed URLs, CDN; `Garment` and `Outfit` models; auth views, templates and base layout (S-01, running in parallel); deletion and orphan-cleanup policy (S-06).

## Architecture / Approach

One `PrivateImage` row per uploaded file, carrying an owner foreign key. A single route, `media/<uuid:pk>/`, is the only path from bytes on disk to a browser: it requires a session, looks the row up filtered by primary key **and** owner, raises `Http404` when that yields nothing, and otherwise streams a `FileResponse` with private caching and conditional-GET validators. Files are stored under UUID names beneath `MEDIA_ROOT`, which is read from the environment — a local gitignored directory in development, the volume mount in production, so the same code path is exercised in both. `django.conf.urls.static.static()` is never added; it would serve `MEDIA_ROOT` publicly and defeat the change. S-02 and S-04 later attach foreign keys to `PrivateImage` rather than each re-implementing the check.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Storage configuration | `MEDIA_ROOT`/`MEDIA_URL`, unified `STORAGES`, Pillow, gitignore | Re-enabling manifest storage makes `collectstatic` fail loudly on a missing asset — safe now (no templates), but S-01 will meet it |
| 2. The gate | `privatemedia` app: model, migration, gate view, route, admin, full test suite | The `@condition` validators run before the view body and must not emit a validator for a row the requester doesn't own |
| 3. Production storage | Railway volume attached, `MEDIA_ROOT` pointed at it, redeploy-survival verified | Volumes aren't expressible in `railway.toml` — an imperative step outside the repo, and it consumes the service's only volume |

**Prerequisites:** none — F-01 has no upstream roadmap dependency and runs in parallel with S-01. Phase 3 needs Railway access to the `outfits-garderobe` project.
**Estimated effort:** ~3 sessions, one per phase; Phase 2 is the substantial one.

## Open Risks & Assumptions

- **S-02 must not merge before Phase 3.** F-01 ships no upload UI, so the ephemeral-disk window is harmless today — but the first real upload before the volume is live would be written to the container layer and lost.
- Phase 3 consumes the service's **only** volume (one per service on Railway). Any later need to separate storage tiers forces either external object storage or a service split.
- **The volume ceiling may be 5 GB, not the 10 GB `infrastructure.md` assumed.** `railway volume list` shows the Postgres volume provisioned at 5000 MB, which looks like a plan limit rather than a choice. That is ~1000–1500 phone photos — ample for the MVP, but it is the threshold at which object storage comes back on the table. Confirm the actual ceiling when the volume is created.
- The gate ties up a gunicorn worker per image stream. Conditional GET keeps repeat views cheap; if S-03's grid proves slow the answer is thumbnails, not a weaker gate.
- Assumes S-01 will not introduce a custom user model incompatible with a plain `AUTH_USER_MODEL` foreign key — the plan references the setting rather than the concrete model precisely to keep that door open.

## Success Criteria (Summary)

- A user opening their own photo's URL sees the photo; a second account opening that exact URL gets a 404 that reveals nothing about whether the file exists.
- A logged-out visitor never reaches a file — they land on the login flow.
- An uploaded photo is still there after a production redeploy.
