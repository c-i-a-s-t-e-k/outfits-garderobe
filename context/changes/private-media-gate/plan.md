# Prywatna brama dostępu do zdjęć użytkownika — Implementation Plan

## Overview

Every photo a user uploads must land outside any publicly served directory, and every read of that photo must pass through a view that requires a login and verifies ownership. This change builds that gate *before* any upload feature exists, so no files ever need relocating and no URL ever needs rewriting.

It is roadmap item **F-01** (milestone M-1, stream A), it unblocks **S-02** (`add-garment`) and **S-04** (`outfit-photo`), and it satisfies the PRD's *Prywatność* NFR ("zero cross-user leaks"), the *Access Control* section, and the storage half of FR-003 and FR-007.

## Current State Analysis

The repository holds only the `outfits_garderobe` config package — no domain app, no models, no templates, no tests.

- **Media is entirely unconfigured.** `outfits_garderobe/settings.py` never sets `MEDIA_ROOT` or `MEDIA_URL`; Django resolves them to `''` and `'/'`. There are no uploaded files anywhere, so this is a greenfield gate with nothing to migrate.
- **Whitenoise does not currently leak media.** `whitenoise/middleware.py:102-111` serves only `STATIC_ROOT` under `STATIC_URL`, and `WHITENOISE_ROOT` is unset. The exposure risk is a future careless change, not today's config — which is exactly what the config-guard test in Phase 2 exists to pin down.
- **`STATICFILES_STORAGE` is dead config.** `settings.py:113` sets `whitenoise.storage.CompressedManifestStaticFilesStorage`, but Django removed that setting in 5.1. On the installed Django 6.0.5 it is silently ignored — the resolved `STORAGES` is Django's default pair, so production is currently shipping unhashed, uncompressed static files. Media storage is configured through that same `STORAGES` dict, so this change lands directly on top of it.
- **`urls.py` routes only `/health/` and `/admin/`.** No auth views exist; S-01 (`user-accounts`) runs *in parallel*, not before, so this change must work against `django.contrib.auth` alone and must not depend on S-01 landing first.
- **Pillow is not installed.** `ImageField` requires it.
- **No persistent storage on Railway.** `railway.toml` declares no volume and the service has none mounted. The gunicorn filesystem is ephemeral, so anything written to disk today is destroyed on the next deploy — a direct conflict with the PRD's *Trwałość danych* NFR.
- **Zero tests.** `pytest-django` is a dev dependency and `pyproject.toml` configures `DJANGO_SETTINGS_MODULE`, but no test file exists. This change writes the first ones.

## Desired End State

A logged-in user can fetch their own photo through `/media/<uuid>/` and gets the bytes. A different logged-in user requesting that same URL gets a `404` indistinguishable from a URL that was never valid. An anonymous visitor is redirected to login. The files themselves sit on a Railway volume, outside `STATIC_ROOT` and outside anything whitenoise serves, under names that carry no information. A redeploy does not destroy them.

Verify by: running `uv run pytest` (the gate suite passes, including the config guard), then, in production, uploading a file as one account via the admin and failing to fetch it from a second account in a separate browser session, then redeploying and confirming the file is still there.

### Key Discoveries:

- `FileResponse` sets `Content-Length`, `Content-Type` and `Content-Disposition` but **no** `ETag` or `Last-Modified` (`django/http/response.py:550`, `set_headers`), and `ConditionalGetMiddleware` is absent from `MIDDLEWARE` (`settings.py:49-58`). Conditional GET must therefore be wired explicitly with `django.views.decorators.http.condition` (`django/views/decorators/http.py:83`).
- `STATICFILES_STORAGE` is absent from `django.conf.global_settings` on 6.0.5 — confirmed by resolving the project's settings, which yield Django's stock `STORAGES` rather than the whitenoise backend.
- Railway volumes are **not** expressible in `railway.toml`. They are provisioned imperatively against a service with a mount path (Railway MCP `create_volume`, or the dashboard). Phase 3 is therefore an out-of-repo step, not a config commit.
- `infrastructure.md` risk register already accepts this shape: "Single volume for both garment and outfit photos is acceptable at MVP scale (< 10 GB)."
- The project targets PostgreSQL but develops on SQLite (`CLAUDE.md`). `UUIDField` is portable across both — it is not a SQLite-only convenience.

## What We're NOT Doing

- **No upload form or user-facing UI.** S-02 owns that. The admin registration in Phase 2 is the verification surface, not a product feature.
- **No image resizing, thumbnailing, or format conversion.** The roadmap flags large phone photos as an S-02 risk; this change only imposes a size ceiling.
- **No object storage, signed URLs, or CDN.** The Railway volume is the decision; `django-storages` is not added.
- **No `Garment` or `Outfit` models.** `PrivateImage` stands alone; downstream slices add the foreign keys.
- **No auth views, templates, or base layout.** S-01 owns those, concurrently.
- **No deletion / orphan-cleanup policy.** Removing a `PrivateImage` when its owning garment is deleted belongs to S-06 (`garment-lifecycle`).
- **No changes to the existing `/health/` endpoint, Procfile, or the gunicorn start command.**

## Implementation Approach

One central `PrivateImage` model owns every uploaded file and its owner. That gives exactly one place where the ownership check lives, exactly one URL pattern, and exactly one test to trust — and it is exercisable today against `django.contrib.auth.User`, with no domain models in existence. S-02 and S-04 later attach foreign keys to it rather than each re-implementing a file field and re-instantiating (and potentially re-breaking) the check.

Files are addressed by UUID and stored under UUID names, so the gate is defended twice: the ownership check is the barrier, and unguessability means there is nothing useful to probe even if the barrier were bypassed. Denials return `404` for both "does not exist" and "not yours", so a probe cannot distinguish them.

`MEDIA_ROOT` is read from the environment. In development it defaults to a gitignored directory inside the project; in production it points at the volume mount. The same code path serves both, so the gate is not a production-only construct that dev never exercises.

## Critical Implementation Details

**Ordering.** The Railway volume must be attached *before* any code path writes a file in production. Because F-01 ships no upload UI, the window is safe — but S-02 must not merge until Phase 3 is done, or its first upload will be written to ephemeral disk and lost. Record this dependency in `change.md` when Phase 2 lands.

**Conditional GET.** `@condition` computes the ETag/Last-Modified *before* the view body runs, so its `etag_func`/`last_modified_func` receive the same arguments as the view and will each need to load the `PrivateImage` row. Guard against the object being fetched three times per request — resolve it once and cache it on the request, or accept the two extra cheap primary-key lookups and say so in a comment. The functions must return `None` for a row the requester does not own, so a denial never emits a validator that confirms existence.

**`MEDIA_URL` must not overlap `STATIC_URL`.** `STATIC_URL` is `'static/'`. The gate route is a real Django URL pattern, not a static prefix; set `MEDIA_URL` to match the gate route so `ImageField.url` and the gate agree, and never add `django.conf.urls.static.static()` — that helper serves `MEDIA_ROOT` publicly and would defeat the entire change.

## Phase 1: Storage configuration

### Overview

Give the project a media root that lives outside every publicly served path, unify storage configuration into the single `STORAGES` dict Django 6 actually reads (repairing the dead static setting in the process), and add the Pillow dependency the model will need.

### Changes Required:

#### 1. Settings — media location

**File**: `outfits_garderobe/settings.py`

**Intent**: Define where uploaded files live and under what URL prefix they are addressed, driven by the environment so that development uses a local directory and production uses the volume mount without a code change.

**Contract**: Adds `MEDIA_ROOT`, read from a `MEDIA_ROOT` environment variable and defaulting to `BASE_DIR / 'media'`, and `MEDIA_URL` set to the gate's route prefix (`'media/'`). `MEDIA_ROOT` must resolve to a path that is neither inside `STATIC_ROOT` nor inside `BASE_DIR / 'staticfiles'`. Follows the existing `os.getenv` pattern used for `DEBUG` and `ALLOWED_HOSTS` (`settings.py:31-33`).

#### 2. Settings — unified STORAGES

**File**: `outfits_garderobe/settings.py`

**Intent**: Replace the `STATICFILES_STORAGE` line, which Django 6 ignores, with the `STORAGES` dict it reads — restoring whitenoise's compressed manifest storage for static files and declaring the default filesystem backend for uploads.

**Contract**: Deletes `STATICFILES_STORAGE` (`settings.py:113`) and adds a `STORAGES` dict with a `"default"` entry (`django.core.files.storage.FileSystemStorage`) and a `"staticfiles"` entry (`whitenoise.storage.CompressedManifestStaticFilesStorage`). Both keys are mandatory — omitting `"staticfiles"` fails `django.contrib.staticfiles`' system check (`django/contrib/staticfiles/checks.py:27`).

#### 3. Pillow dependency

**File**: `pyproject.toml` / `uv.lock`

**Intent**: `ImageField` decodes uploads to confirm they are genuinely images; that requires Pillow.

**Contract**: `uv add pillow` — never hand-edit `uv.lock`. Adds Pillow to `[project.dependencies]` so the production Nixpacks install picks it up (`nixpacks.toml` runs `uv sync --no-dev --frozen`).

#### 4. Ignore the local media directory

**File**: `.gitignore`

**Intent**: Development uploads must never be committed.

**Contract**: Adds an entry for the default development `MEDIA_ROOT` (`/media/`), scoped so it cannot also match a future static asset directory of the same name.

#### 5. Document the new environment variable

**File**: `.env.example`

**Intent**: Record `MEDIA_ROOT` as a deployment knob so the volume mount path is discoverable without reading settings.

**Contract**: Adds a commented `MEDIA_ROOT` line describing the production volume mount path. Do not touch the real `.env` at `../.secrets/outfits-garderobe/.env`.

### Success Criteria:

#### Automated Verification:

- System checks pass with no warnings: `uv run python manage.py check`
- Resolved settings are correct — `MEDIA_ROOT` is non-empty, is outside `STATIC_ROOT`, and `STORAGES['staticfiles']['BACKEND']` is the whitenoise manifest backend
- Static collection still succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`
- Pillow resolves in the locked environment: `uv run python -c "import PIL"`

#### Manual Verification:

- `git status` shows no stray media directory staged for commit

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: The gate

### Overview

Add the `privatemedia` app: the `PrivateImage` model that owns every uploaded file, the authenticated ownership-checking download view that is the only way to read one, and the test suite that proves both — including a guard against a future settings change reopening public media serving.

### Changes Required:

#### 1. New app scaffold

**File**: `privatemedia/` (new package), `outfits_garderobe/settings.py`

**Intent**: Create the first domain app, holding everything about private file storage and access.

**Contract**: `uv run python manage.py startapp privatemedia`, then add `'privatemedia'` to `INSTALLED_APPS` (`settings.py:40-47`). Remove the unused boilerplate `views.py`/`tests.py` scaffolding that `startapp` generates but this plan replaces.

#### 2. The PrivateImage model

**File**: `privatemedia/models.py`

**Intent**: One row per uploaded file, recording who owns it, so the ownership question has a single database-backed answer rather than being re-derived from a path or duplicated across future models.

**Contract**: A `PrivateImage` model with a UUID primary key (`default=uuid.uuid4`, `editable=False`), an `owner` foreign key to `settings.AUTH_USER_MODEL` with `on_delete=CASCADE` and a `related_name`, an `ImageField` whose `upload_to` is a callable generating a UUID filename that preserves only the lowercased extension, a validator enforcing a maximum file size, an `original_filename` char field retained as metadata only, and an `uploaded_at` timestamp. Index or order by `owner` — every future query filters on it.

Reference `settings.AUTH_USER_MODEL`, never `django.contrib.auth.models.User` directly, so S-01 stays free to introduce a custom user model.

The `upload_to` callable is the one non-obvious piece, because it must not leak the original name into the path:

```python
def upload_to_uuid(instance, filename):
    ext = Path(filename).suffix.lower().lstrip(".")
    name = f"{uuid.uuid4().hex}.{ext}" if ext else uuid.uuid4().hex
    return f"private/{name}"
```

#### 3. Size validator

**File**: `privatemedia/validators.py`

**Intent**: Reject files above a ceiling at the model layer, so that both S-02's and S-04's separate upload paths inherit the rule rather than each restating it in a form.

**Contract**: A module-level maximum-bytes constant and a validator callable raising `ValidationError` above it. Must be a named module-level function, not a lambda or closure — a migration will serialize a reference to it.

#### 4. Migration

**File**: `privatemedia/migrations/0001_initial.py`

**Intent**: Create the table.

**Contract**: `uv run python manage.py makemigrations privatemedia`. Must apply cleanly on both SQLite (dev) and PostgreSQL (prod) — `UUIDField` and `ImageField` are portable, but review the generated file rather than assuming.

#### 5. The gate view

**File**: `privatemedia/views.py`

**Intent**: The single path through which file bytes reach a browser. It requires a session, confirms the requester owns the row, and streams the file; anything else is indistinguishable from a nonexistent file.

**Contract**: A view taking a UUID from the URL. Anonymous requests redirect to login (`login_required`). For an authenticated request it looks up the row filtered by *both* primary key and `owner=request.user` and raises `Http404` when that yields nothing — so "not found" and "not yours" produce byte-identical responses. Returns a `FileResponse` (inline, not an attachment) with `Cache-Control: private` and conditional-GET validators supplied via `django.views.decorators.http.condition`; the validator functions must return `None` for a row the requester does not own.

Never accept a filename or path segment from the URL — the UUID primary key is the only input, which is what makes path traversal structurally impossible rather than something to sanitize.

#### 6. URL route

**File**: `privatemedia/urls.py` (new), `outfits_garderobe/urls.py`

**Intent**: Expose the gate at the prefix `MEDIA_URL` points to.

**Contract**: A named route `media/<uuid:pk>/` mapping to the gate view, included from the root URLconf alongside the existing `health/` and `admin/` entries (`outfits_garderobe/urls.py:26`). The route name is a load-bearing contract — S-02 and S-04 will reverse it. Do **not** add `django.conf.urls.static.static()`; that helper would serve `MEDIA_ROOT` publicly and defeat this change.

#### 7. Admin registration

**File**: `privatemedia/admin.py`

**Intent**: Provide a staff-only surface for creating and inspecting images so the gate can be exercised by hand before S-02 exists.

**Contract**: Registers `PrivateImage` with owner, upload timestamp, and original filename in the list display, and a filter on owner.

#### 8. Test suite

**File**: `privatemedia/tests/test_gate.py`, `privatemedia/tests/test_storage_config.py`

**Intent**: Prove every way the gate can fail, and pin the configuration so a later change cannot silently re-expose media.

**Contract**: Uses `pytest-django` (already a dev dependency; `DJANGO_SETTINGS_MODULE` is configured in `pyproject.toml`). Tests must set `MEDIA_ROOT` to a temporary directory (pytest's `tmp_path` via a fixture, or `override_settings`) so they never write into the real media root.

Gate cases:
- the owner fetches their own image and receives `200` with the file's bytes
- a second authenticated user fetches the same URL and receives `404`
- an anonymous request is redirected to login
- a well-formed but nonexistent UUID returns `404`
- the not-yours `404` and the nonexistent `404` are indistinguishable — same status, and no validator header that would confirm existence

Config guard cases:
- `MEDIA_ROOT` is non-empty and is not inside `STATIC_ROOT`
- no URL pattern serves `MEDIA_ROOT` directly (the root URLconf contains no static-serving helper for it)
- `STORAGES` defines both `default` and `staticfiles`

### Success Criteria:

#### Automated Verification:

- Migration applies cleanly: `uv run python manage.py migrate`
- Migrations are complete — no model changes are left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- The full test suite passes: `uv run pytest`
- Every gate test passes specifically: `uv run pytest privatemedia/tests/test_gate.py`
- The config guard passes: `uv run pytest privatemedia/tests/test_storage_config.py`
- System checks pass: `uv run python manage.py check`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`
- No new vulnerable dependencies from Pillow: `uv run pip-audit`

#### Manual Verification:

- Uploading an image through the admin as a superuser stores it under a UUID name in `MEDIA_ROOT` with the original filename nowhere in the path
- Copying that image's gate URL and opening it in a second browser session logged in as a different, non-staff account returns a 404 page rather than the image
- Opening the same URL while logged out lands on the login flow, not on the file
- Reloading the image in the owner's browser produces a `304` on the second request (visible in devtools), confirming conditional GET is live
- No stray file appears in `staticfiles/` after an upload

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Production storage

### Overview

Attach a persistent volume to the Railway service, point production's `MEDIA_ROOT` at its mount path, and prove that an uploaded file survives a redeploy. Until this phase lands, production writes to an ephemeral filesystem.

### Changes Required:

#### 1. Provision the volume

**File**: (no repo file — Railway service configuration)

**Intent**: Give the app a filesystem that outlives a deploy. Railway's config-as-code does not express volumes, so this is an imperative step against the service, not a commit.

**Contract**: A volume attached to the `outfits-garderobe` service (`ef901136-0af7-4104-8f42-cce2a8e7e8a7`) in the `production` environment at a mount path such as `/data`. Provisioned via the Railway MCP `create_volume` tool or the dashboard. Note the one-volume-per-service limit recorded in `infrastructure.md` — this consumes the service's only volume.

Confirmed by `railway volume list`: the only existing volume belongs to the **Postgres** service (`/var/lib/postgresql/data`, 217 MB used of **5000 MB**), and the application service has none. That 5 GB figure appears to be the plan's per-volume ceiling rather than a chosen size — half of what `infrastructure.md` assumed when it accepted "a single volume is sufficient below 10 GB". At 3–5 MB per phone photo that is roughly 1000–1500 images, which is ample for the MVP but is the threshold at which the object-storage conversation returns. Check the provisioned size after creating the volume and record the actual ceiling here.

#### 2. Point production at the mount

**File**: (no repo file — Railway environment variables)

**Intent**: Make the deployed app write beneath the volume rather than into the container's ephemeral layer.

**Contract**: Sets `MEDIA_ROOT` in the service's production environment to a directory *beneath* the mount path (e.g. `/data/media`, not `/data` itself), so the volume root stays free for any future use. The application must create the directory if it does not exist — `FileSystemStorage` does this on first write, but confirm rather than assume on a fresh volume.

#### 3. Record the deployment dependency

**File**: `context/changes/private-media-gate/change.md`

**Intent**: Close the roadmap's open unknown ("gdzie fizycznie leżą pliki") with the decision actually taken, and record that S-02 must not merge before this phase is done.

**Contract**: Replaces the "Otwarte pytanie" note with the resolved decision (Railway volume, the mount path, and the `MEDIA_ROOT` value), and adds a line stating that S-02 and S-04 depend on the volume being live. Sets `status: implemented` and `updated`.

### Success Criteria:

#### Automated Verification:

- The service reports a volume attached at the expected mount path
- The deployment reaches a healthy state — `/health/` returns `200` after deploy
- Deploy logs show `collectstatic` and `migrate` completing in `preDeployCommand` without error

#### Manual Verification:

- Uploading an image through the production admin succeeds and the gate serves it back to its owner
- A second production account cannot fetch that image's URL — this is the two-account verification named in `change.md` and in roadmap F-01
- After triggering a redeploy, the previously uploaded image is still served — proving the volume, not the container layer, holds it
- Railway logs show no permission errors writing beneath the mount path on the first upload after a fresh deploy

**Implementation Note**: This phase's manual verification is the acceptance evidence for roadmap item F-01. Do not mark the roadmap item done until the two-account production check and the redeploy-survival check have both been observed.

---

## Testing Strategy

### Unit Tests:

- `upload_to` produces a UUID-based path and never embeds the original filename
- The size validator rejects a file above the ceiling and accepts one below it
- `ImageField` rejects a non-image file whose extension claims otherwise

### Integration Tests:

- The five gate cases in Phase 2: owner success, cross-user 404, anonymous redirect, nonexistent 404, and indistinguishability of the two 404s
- The config guard: `MEDIA_ROOT` placement, absence of a static-serving route for it, and a complete `STORAGES` dict

### Manual Testing Steps:

1. In the local admin, upload an image as a superuser; confirm the on-disk name under `MEDIA_ROOT` is a UUID and the original name appears only in the model field.
2. Copy the gate URL. In a private window logged in as a second, non-staff account, open it — expect a 404, not the image.
3. Log out entirely and open the same URL — expect the login flow.
4. Back as the owner, reload the image and check devtools for a `304` on the second request.
5. Repeat steps 1–3 against production after Phase 3.
6. Trigger a Railway redeploy and re-open the production image URL as its owner — expect the image, not a 404.

## Performance Considerations

Each tile in the wardrobe grid is one authenticated request that occupies a gunicorn worker for the duration of the stream — a 20-outfit grid is 20 concurrent streams. Conditional GET with `Cache-Control: private` keeps repeat views to cheap `304` responses, which is what holds the grid inside the PRD's five-second interaction budget. This is adequate at MVP scale; if S-03's grid later proves slow, the next lever is thumbnails (S-02/S-03 scope), not weakening the gate.

The `infrastructure.md` pre-mortem specifically warns that N+1 queries silently inflate Railway's pay-per-second billing. Keep the gate's per-request database work to the single owner-filtered lookup, and be deliberate about the extra lookups the `@condition` validator functions introduce.

## Migration Notes

There is no data migration: no uploaded files exist, and `MEDIA_ROOT` was never configured, so nothing needs relocating. This is the entire reason F-01 stands before S-02 in the roadmap.

The one migration-shaped risk is the `STORAGES` repair in Phase 1. Re-enabling whitenoise's manifest storage means `collectstatic` will now fail loudly if a template ever references an asset that does not exist. No templates exist today, so the change is safe now — but S-01, which introduces the first templates and stylesheets, will meet this behaviour. That is the correct outcome (it catches broken asset references at deploy rather than in the browser) and worth flagging to whoever picks up S-01.

## References

- Change identity: `context/changes/private-media-gate/change.md`
- Roadmap item F-01: `context/foundation/roadmap.md`
- Storage and volume constraints: `context/foundation/infrastructure.md` (risk register, volume-per-service row)
- Privacy requirement: `context/foundation/prd.md` — *Non-Functional Requirements* → Prywatność; *Access Control*; FR-003; FR-007
- Existing settings to modify: `outfits_garderobe/settings.py:31-33` (env pattern), `:40-47` (INSTALLED_APPS), `:110-113` (static storage)
- Root URLconf to extend: `outfits_garderobe/urls.py:26`
- Django conditional-GET decorator: `django/views/decorators/http.py:83`
- `FileResponse` header behaviour: `django/http/response.py:550`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Storage configuration

#### Automated

- [ ] 1.1 System checks pass with no warnings: `uv run python manage.py check`
- [ ] 1.2 Resolved settings are correct — `MEDIA_ROOT` non-empty, outside `STATIC_ROOT`, whitenoise manifest backend active
- [ ] 1.3 Static collection still succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- [ ] 1.4 Linting passes: `uv run ruff check .`
- [ ] 1.5 Formatting is clean: `uv run ruff format --check .`
- [ ] 1.6 Pillow resolves in the locked environment: `uv run python -c "import PIL"`

#### Manual

- [ ] 1.7 `git status` shows no stray media directory staged for commit

### Phase 2: The gate

#### Automated

- [ ] 2.1 Migration applies cleanly: `uv run python manage.py migrate`
- [ ] 2.2 No model changes left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- [ ] 2.3 The full test suite passes: `uv run pytest`
- [ ] 2.4 Every gate test passes: `uv run pytest privatemedia/tests/test_gate.py`
- [ ] 2.5 The config guard passes: `uv run pytest privatemedia/tests/test_storage_config.py`
- [ ] 2.6 System checks pass: `uv run python manage.py check`
- [ ] 2.7 Linting passes: `uv run ruff check .`
- [ ] 2.8 Formatting is clean: `uv run ruff format --check .`
- [ ] 2.9 No new vulnerable dependencies from Pillow: `uv run pip-audit`

#### Manual

- [ ] 2.10 Admin upload stores the file under a UUID name with the original filename absent from the path
- [ ] 2.11 A second, non-staff account opening the gate URL gets a 404 rather than the image
- [ ] 2.12 Opening the same URL logged out lands on the login flow
- [ ] 2.13 Reloading as the owner produces a `304`, confirming conditional GET is live
- [ ] 2.14 No stray file appears in `staticfiles/` after an upload

### Phase 3: Production storage

#### Automated

- [ ] 3.1 The service reports a volume attached at the expected mount path
- [ ] 3.2 The deployment reaches a healthy state — `/health/` returns `200` after deploy
- [ ] 3.3 Deploy logs show `collectstatic` and `migrate` completing without error

#### Manual

- [ ] 3.4 Production admin upload succeeds and the gate serves it back to its owner
- [ ] 3.5 A second production account cannot fetch that image's URL (F-01 acceptance evidence)
- [ ] 3.6 After a redeploy, the previously uploaded image is still served
- [ ] 3.7 Railway logs show no permission errors writing beneath the mount path
