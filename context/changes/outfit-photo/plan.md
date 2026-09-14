# Outfit Photo Implementation Plan

## Overview

A signed-in user adds a photo of themselves wearing an outfit, on that outfit's page. From then on, the outfit's wardrobe tile shows that photo instead of the garment collage. The photo can be replaced, or removed after a confirmation page, and the tile then falls back to the collage. Composing an outfit now lands on its page, so adding the photo is the next step. Every wardrobe tile becomes portrait 3:4, so a full-body photo and a collage sit evenly in the same grid. This is roadmap slice **S-04** (Jira OG-5), covering FR-007, FR-008 and US-01.

## Current State Analysis

- **An outfit has no photo.** `outfits.Outfit` (`outfits/models.py:145`) has `owner`, `name`, `garments`, `tags` and `created_at`. Migrations run to `outfits/migrations/0002_tag.py`.
- **The private photo store is ready for a second upload path.** `privatemedia.PrivateImage` (`privatemedia/models.py:22`) owns the file and its owner. Its docstring names S-04 as a planned consumer. `stored_private_image(owner, file, original_filename)` (`privatemedia/models.py:78`) stores a row for use inside a block and deletes the written file if anything in the block fails. `normalize_photo()` (`privatemedia/processing.py:27`) turns any accepted upload into an upright, EXIF-free JPEG of at most 1600 px.
- **The garment upload is the pattern to reuse.** `GarmentForm` (`garments/forms.py:10`) declares a non-model `photo` `FileField` with `accept="image/*"` and `data-shrink-photo`. Its `clean_photo()` checks size, normalizes, and keeps `original_filename`. `_store_garment()` (`garments/views.py:33`) links the image inside `stored_private_image`. `Garment.photo` is a `OneToOneField(PrivateImage, on_delete=RESTRICT)`, and `Garment.clean()` refuses a photo with another owner (`garments/models.py:105`).
- **Nothing ever deletes a stored file.** Deleting a `PrivateImage` row leaves its bytes on the volume, and no code path deletes a photo today. The Railway volume has a 5000 MB ceiling (roadmap Open Question 2).
- **The outfit page** (`outfits/views.py:356`, `templates/outfits/detail.html`) shows the title, date, a *Tags* section with add/remove, then the garment grid. Writes on it are `@require_POST` actions under `/wardrobe/<pk>/…` that redirect back to it. `_render_detail(request, outfit, form)` re-renders it with a bound form on errors.
- **Compose redirects to the wardrobe.** `outfit_compose` does this with "Outfit saved." (`outfits/views.py:350`), pinned by `test_valid_compose_stores_the_outfit_and_lands_on_the_wardrobe` (`outfits/tests/test_views.py:113`).
- **The wardrobe tile is a square collage.** `.outfit-preview` is a 2×2 grid with `aspect-ratio: 1` (`static/css/app.css:743`), and a comment there reserves the slot for S-04. `wardrobe.html` renders `preview_garments` and the `+N` badge inside one `<a>` per tile. The grid query count is pinned constant (`outfits/tests/test_views.py:817`). Tile images use `garment.photo_url`, built from `photo_id` with no query.
- **Browser-side shrinking** (`static/js/photo-shrink.js`) enhances any `input[type=file][data-shrink-photo]`. It disables the form's submit buttons only while it prepares the photo, not after the form is submitted (Jira OG-9).
- **Privacy contract.** Every guarded route must be registered in `tests/owner_scoped_routes.py`, or `test_new_guarded_route_cannot_skip_the_contract.py` fails. The registry drives the anonymous, stranger, photo and foreign-write scenarios (`tests/CLAUDE.md`). `snapshot_of` (`tests/foreign_id_writes/conftest.py`) already includes every `Outfit` column, so it will see `photo_id`. `assert_no_cross_owner_links` checks garments on foreign photos, but not outfits.
- **Test plan.** Risk #1 (photos visible to others) and Risk #3 (a second upload path for phone photos) apply directly; Risk #2 applies to the new writes.
- **Deploy.** Merges go through PRs, and each PR gets a Railway PR environment with an empty Postgres. Lessons require every plan check to pass on that PR deploy before merge, with close-out in the same PR (`context/foundation/lessons.md`). The developer moved the production database to an EU region (2026-09-14), so database reads and writes are much faster than before.

## Desired End State

On a new outfit's page, right after composing, a *Photo* section under *Tags* says there is no photo yet and offers a file input to add one. On a phone, the user picks a photo of themselves in the outfit from the gallery and taps *Upload photo*. The button disables until the page reloads, and the page shows the whole photo, uncropped, with *Replace photo* and *Remove photo*. In the wardrobe, that outfit's tile shows the photo cropped to a portrait 3:4 tile. Next to it, an outfit without a photo shows its garment collage in a tile of the same shape. Replacing uploads a new photo, and the old file is deleted from the volume once the change is committed. *Remove photo* opens a confirmation page with the photo, and confirming removes the photo and its file, so the tile shows the collage again. A second account gets 404 on the first account's outfit page, photo upload and remove confirmation, and cannot fetch the photo URL.

Verification: the automated suite proves ownership, file cleanup on commit, no stored file on refused uploads, the privacy contracts for the new routes, and constant query counts. Headless Chromium at 360 px and a two-account check on the Railway PR environment confirm the UI, the upload through the real volume, and privacy before merge.

### Key Discoveries:

- **`transaction.on_commit` callbacks do not run inside pytest-django's per-test transaction.** A test that asserts a replaced file is gone must use the `django_capture_on_commit_callbacks(execute=True)` fixture. Without it, the assertion fails against correct code, or passes vacuously if it was written as "file still present".
- **`FileSystemStorage.delete()` ignores a missing file**, so deleting an already-missing file after commit cannot raise.
- **`Garment.photo` uses `RESTRICT`.** If `Outfit.photo` does the same, a direct delete of an in-use `PrivateImage` is refused, while deleting the user still cascades cleanly. The remove flow therefore has to unlink the photo from the outfit before deleting the image row.
- **The foreign-write scenario posts to the owner's outfit URL with a valid upload.** The view must resolve the owned outfit before it validates the form. Otherwise a stranger's request decodes an image on the server before it is refused. Checking ownership first means nothing is ever written for a 404.
- **A wardrobe tile is one `<a>`,** and the photo tile must keep the same structure, name and tag line, so the tag-filter tests and the tile's accessible name stay unchanged.
- **The `+N` badge and the 3-photo layout** (`static/css/app.css:772`) assume square cells, but still work in a 3:4 box because every cell uses `object-fit: cover`.

## What We're NOT Doing

- More than one photo per outfit, a gallery, or a chosen cover photo.
- A trash can or history for replaced/removed photos — deletion is final after commit.
- A photo field on the compose form. The photo is added on the outfit page only.
- Fixing OG-9 on the compose and add-garment forms. Only the new photo form blocks a second submit, and OG-9 stays open.
- Deleting photo files when a user account or an outfit is deleted. Account deletion leaves files behind today for garments too, and outfit deletion is S-07. The gap for S-07 is recorded under Migration Notes.
- Cropping, rotating or editing the photo in the browser.
- A camera-capture button (`capture` attribute) — parked in the roadmap since S-02.
- Real-phone checks outside the PR environment; headless Chromium at 360 px stands in locally.
- Translating the UI.

## Implementation Approach

1. **One optional photo on the outfit**, reusing `PrivateImage` exactly as garments do: a `OneToOneField` with `RESTRICT`, an owner rule in `Outfit.clean()`, and a `photo_url` property built from `photo_id`.
2. **A single helper for "this image is no longer used".** It deletes the row inside the caller's transaction and the file only after commit, so a failed replace never loses the old photo. It lives in `privatemedia` next to `stored_private_image`, so there is still exactly one place that touches photo files.
3. **The garment photo field becomes a shared mixin** so the outfit form gets the same size check, normalization and original-name capture without a copy.
4. **Two owner-scoped routes on the outfit page:** a POST-only upload that adds or replaces, and a GET/POST remove with a confirmation page. Both resolve the owned outfit first, and both redirect to the outfit page.
5. **Tiles branch on `photo_id`:** a photo or the existing collage, in one shared 3:4 box.
6. **Pull request last,** verified on the Railway PR environment, with close-out in the same PR.

## Critical Implementation Details

**Order of operations on replace.** Inside one transaction: lock the owned outfit row (`select_for_update()`, a no-op on SQLite, real on PostgreSQL). Store the new image through `stored_private_image`. Point `outfit.photo` at it and save. Then discard the previous image, deleting its row now and its file on commit. Two concurrent uploads then serialize on the row lock, and each deletes exactly the photo it replaced. If anything raises, `stored_private_image` removes the new file, the rollback restores the old row, and the old file was never touched.

**Order of operations on remove.** Set `outfit.photo = None` and save before discarding the image. With `RESTRICT`, deleting the image first is refused. If the outfit has no photo, both GET and POST redirect to the outfit page without a message, so a stale tab or a double-tapped confirm never errors.

## Parallel Work & Delivery

- **Where the work happens.** Worktree `/home/ciastek/Projects/.worktrees/outfit-photo`, branch `feat/outfit-photo`, created from `origin/master` at `787aa1f`. Every command in this plan runs from that worktree. Never `cd` to the main checkout `/home/ciastek/Projects/outfits-garderobe`: it is on another branch with the developer's uncommitted work.
- **Local state is per worktree.**
  - `db.sqlite3`, the dev `MEDIA_ROOT`, `.venv` and `staticfiles/` all live under the worktree root. Run `uv sync` first.
  - Before the first `uv run pytest`, run `DJANGO_SETTINGS_MODULE=outfits_garderobe.settings_test uv run python manage.py collectstatic --noinput`, and re-run it after changing anything under `static/`.
  - Tests need no secrets.
- **Secrets path.** CLAUDE.md's relative `../.secrets/outfits-garderobe/.env` does not resolve from this worktree. The file is `/home/ciastek/Projects/.secrets/outfits-garderobe/.env`; pass that absolute path to `uv run --env-file …` when a command needs production-style settings. Never read the file.
- **Dev server.** `uv run python manage.py runserver 8003` (8000 is the main checkout, 8001 and 8002 earlier worktrees). Headless Chromium checks target that port.
- **Git hygiene.** The stash stack is shared across worktrees, so never use bare `git stash` / `git stash pop`. Set work aside with a WIP commit instead. Commit per phase on `feat/outfit-photo` only. The branch was created tracking `origin/master`, so push it with `git push -u origin feat/outfit-photo` to set the right upstream.
- **Possible parallel work.** S-06 (`garment-lifecycle`, OG-7) may start in its own worktree. It will also touch `outfits/models.py`, `templates/outfits/wardrobe.html`, `static/css/app.css` and `tests/owner_scoped_routes.py`, and will add its own `outfits` migration. Phase 4 rebases onto whatever `origin/master` holds. If a second `0003_*` migration lands first, renumber this slice's migration and regenerate it rather than merging migrations.
- **Delivery.** No direct push to `master`. Phase 4 opens a PR, and every manual check runs against the Railway PR environment before the developer merges. The worktree is removed by the developer after merge.

## Phase 1: Outfit photo model and file lifecycle

### Overview

Add the optional photo to `Outfit`, the rule that it belongs to the outfit's owner, the helper that discards an image and its file after commit, and a shared photo form mixin. There is no user-visible change.

### Changes Required:

#### 1. The model

**File**: `outfits/models.py`

**Intent**: An outfit may carry one photo of its owner wearing it, never someone else's photo, and the tile can link to it without a query.

**Contract**:
- `Outfit.photo`: `OneToOneField('privatemedia.PrivateImage', null=True, blank=True, on_delete=models.RESTRICT, related_name='outfit')`. The comment carries the same `RESTRICT` reasoning as `Garment.photo`.
- `Outfit.clean()`: when both `owner_id` and `photo_id` are set and `photo.owner_id != owner_id`, raise `ValidationError('An outfit can only use its owner’s photo.')`.
- `Outfit.photo_url` property: the `privatemedia:image` URL for `photo_id`, or `None` when there is no photo. Built with `reverse` like `Garment.photo_url`, with no query.

#### 2. Discarding an image

**File**: `privatemedia/models.py`

**Intent**: One place that retires a stored photo, so that no caller can delete bytes a rolled-back transaction still needs, or leave bytes nothing points at.

**Contract**: `discard_private_image(image)`. Must be called inside a transaction. It deletes the row immediately and registers `transaction.on_commit` to delete the stored file by its storage name, captured before the row is deleted. The docstring states the order guarantee and that callers must unlink the image from any `RESTRICT` relation first.

#### 3. Shared photo field

**File**: `privatemedia/forms.py` (new), `garments/forms.py`

**Intent**: The outfit photo form inherits the garment form's upload rules instead of copying them.

**Contract**:
- `NormalizedPhotoMixin`: declares `photo` (the `FileField` with `accept="image/*"` and `data-shrink-photo`, with the existing comments moved along), `clean_photo()` (size check, then `normalize_photo`, then `original_filename`), and initializes `original_filename = ''`.
- `GarmentForm` uses the mixin. Its field order, labels and behaviour are unchanged, and `garments/tests/` passes untouched.

#### 4. Migration and admin

**File**: `outfits/migrations/0003_outfit_photo.py`, `outfits/admin.py`

**Intent**: Add the nullable column. Staff inspect it by id, not through a picker of every user's images.

**Contract**:
- Migration generated with `uv run python manage.py makemigrations outfits`, adding one nullable column with no data migration.
- `OutfitAdmin.raw_id_fields` gains `'photo'`.

#### 5. Tests

**File**: `outfits/tests/test_model.py`, `privatemedia/tests/test_model.py`, `tests/factories.py`, `tests/foreign_id_writes/conftest.py`

**Intent**: Pin the ownership rule and the commit-time file deletion with values taken from this plan, not from the implementation.

**Contract**:
- `tests/factories.py`: `make_outfit(user, garments=(), photo=False, **fields)`. When `photo` is true it creates the outfit with `make_image(user)`. Existing callers are unchanged.
- An outfit with the owner's image saves, and `photo_url` resolves to the gate for that image's pk. An outfit without a photo has `photo_url is None`.
- An outfit given `stranger`'s image raises `ValidationError` and stores nothing.
- `discard_private_image` inside `django_capture_on_commit_callbacks(execute=True)` deletes the row, and the file no longer exists under `MEDIA_ROOT`.
- `discard_private_image` inside an atomic block that then raises leaves both the row and the file.
- Deleting an image still linked to an outfit is refused (`RestrictedError`). Deleting the owner removes the outfit and its image rows.
- `assert_no_cross_owner_links` additionally asserts no outfit has a photo with another owner.

### Success Criteria:

#### Automated Verification:

- The migration applies cleanly: `uv run python manage.py migrate`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- Model tests pass: `uv run pytest outfits/tests/test_model.py privatemedia/tests/test_model.py`
- Garment tests pass unchanged after the mixin refactor: `uv run pytest garments/tests`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- In `/admin/`, setting an outfit's photo to another user's image id is refused with the ownership message
- Adding a garment through the UI still works exactly as before (photo shrinks, garment appears in the list)

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Add, replace and remove on the outfit page

### Overview

Let the owner upload, replace and remove the outfit photo on its page, send them there after composing, and put both new routes under the privacy contract.

### Changes Required:

#### 1. Form

**File**: `outfits/forms.py`

**Intent**: The photo upload form, with the garment form's rules.

**Contract**: `OutfitPhotoForm(NormalizedPhotoMixin, forms.Form)`. The `photo` label is "Photo of you in this outfit".

#### 2. Views

**File**: `outfits/views.py`

**Intent**: Only the owner can set or clear the photo, a refused request stores nothing, and the previous photo's file disappears only once the change is committed.

**Contract**:
- `outfit_photo_upload(request, pk)`, `@login_required` and `@require_POST`. It resolves the owned outfit first (404 otherwise) and only then binds `OutfitPhotoForm(request.POST, request.FILES)`.
  - Invalid: re-render the detail page with status 200 and the bound form's errors. `_render_detail` gains a `photo_form` argument that defaults to an unbound form.
  - Valid: follow the replace order in Critical Implementation Details. Show "Photo added." or "Photo replaced." and redirect to the outfit page.
- `outfit_photo_remove(request, pk)`, `@login_required`, GET and POST only. It resolves the owned outfit (404 otherwise). With no photo, it redirects to the outfit page.
  - GET renders `outfits/photo_remove.html`.
  - POST follows the remove order in Critical Implementation Details. It shows "Photo removed." and redirects to the outfit page.
- `outfit_compose` success redirects to the new outfit's page (`redirect(outfit)`) with "Outfit saved." `_store_outfit` already returns the outfit.
- `outfit_detail` passes an unbound `OutfitPhotoForm`. No query is added: `photo_url` is built from `photo_id`.

#### 3. URLs

**File**: `outfits/urls.py`

**Intent**: Both actions sit under the outfit's own URL, like the tag actions.

**Contract**:
- `'<uuid:pk>/photo/upload/'` → `outfit_photo_upload`, named `photo_upload`.
- `'<uuid:pk>/photo/remove/'` → `outfit_photo_remove`, named `photo_remove`.

#### 4. Templates

**File**: `templates/outfits/detail.html`, `templates/outfits/photo_remove.html` (new)

**Intent**: A *Photo* section under *Tags* that works with a thumb and without JavaScript, and a confirmation step before the only irreversible action.

**Contract**:
- `detail.html`: a `<section aria-labelledby="photo-heading">` with an `<h2>` "Photo", placed between the Tags section and the garment grid.
  - With a photo, it shows the image (`src` = `outfit.photo_url`, `alt` "{{ outfit.name }} — worn") in a `.outfit-photo` wrapper. Below it: a multipart POST form to `outfits:photo_upload` with the file input and a *Replace photo* button, and a link *Remove photo* to `outfits:photo_remove`.
  - Without a photo, it shows "No photo yet." and the same form with an *Upload photo* button.
  - Either way the form has `enctype="multipart/form-data"`, `{% csrf_token %}`, the field errors, a `[data-shrink-status]` element, a `data-submit-once` attribute, and loads `js/photo-shrink.js` as `add.html` does.
- `photo_remove.html`: title and `<h1>` "Remove photo", the photo, the sentence "The photo is deleted permanently. The outfit and its garments stay.", a POST form with a *Remove photo* button, and a *Cancel* link back to the outfit page.

#### 5. Submit-once

**File**: `static/js/photo-shrink.js`

**Intent**: A slow upload on mobile data cannot be sent twice from the photo form (OG-9, this form only).

**Contract**: For a form carrying `data-submit-once`, a submit that is not blocked by shrinking disables that form's submit buttons after the event (the submission itself proceeds) and sets the status text to "Uploading…". On `pageshow` with `event.persisted` (back/forward cache), the buttons are re-enabled and the status cleared. Forms without the attribute (add garment) behave exactly as today. The header comment documents the attribute.

#### 6. Styles

**File**: `static/css/app.css`

**Intent**: The photo on the outfit page is shown whole and never taller than the screen.

**Contract**: `.outfit-photo img` is block-level with `width: 100%`, `max-height: 70vh` and `object-fit: contain`, and uses the same rounded corners as tiles. The confirmation page reuses the rule.

#### 7. Privacy contract registration

**File**: `tests/owner_scoped_routes.py`

**Intent**: Both new routes are covered by every registry-driven scenario, and the read scenarios also catch an outfit photo leaking.

**Contract**:
- `_seed_wardrobe` gives the seeded outfit a photo. It also adds a second outfit without one, with a username-carrying name, so the wardrobe renders both tile kinds. Markers gain the outfit photo URL, the photo pk and the second outfit's name and pk. `outfits[0]` stays the tagged outfit with the photo, so the existing tag seeders keep working.
- `'outfits:photo_upload'`: `kind='write'`, `seed=_seed_outfit_detail`, `shows_photos=False`, `post_only=True`, and a `foreign_payload` with a valid small JPEG upload under `photo`.
- `'outfits:photo_remove'`: `kind='write'`, `seed=_seed_outfit_detail`, `shows_photos=True` (the confirmation page renders the photo), and a `foreign_payload` that returns `{}`.
- `tests/CLAUDE.md` needs no change: the procedure is the same.

#### 8. Tests

**File**: `outfits/tests/test_views.py`

**Intent**: Prove through HTTP that the photo is stored for the right outfit and owner, the old file is gone after replace/remove, refused requests leave no file, and the page stays at a constant query count. Every assertion re-reads the database, and file assertions check `MEDIA_ROOT` on disk.

**Contract**:
- Compose success now redirects to the new outfit's page, and the followed page shows "Outfit saved." This replaces `test_valid_compose_stores_the_outfit_and_lands_on_the_wardrobe`.
- The detail page without a photo shows "No photo yet." and an upload form with `enctype="multipart/form-data"`. With a photo, it shows `photo_url` as an `<img>`, a *Replace photo* button and a link to the remove page.
- Uploading a portrait JPEG (e.g. 1200×1800, generated in memory) stores a `PrivateImage` owned by the owner and links it. The stored file decodes as JPEG with a long edge of at most 1600 px. The redirect shows "Photo added."
- Uploading an EXIF-rotated in-memory JPEG stores it upright (width/height swapped as the orientation dictates). This is the Risk #3 check for this path.
- Replacing inside `django_capture_on_commit_callbacks(execute=True)` links the new image, deletes the old row, and removes the old file from disk. The redirect shows "Photo replaced." Exactly one `PrivateImage` row remains for that outfit.
- A corrupt file or an 11 MB file returns 200 with a `photo` error. The outfit's photo is unchanged, no `PrivateImage` row is added, and no new file exists under `MEDIA_ROOT`.
- A replace where saving the outfit fails (e.g. monkeypatch `Outfit.save` to raise) keeps the old photo linked, the old file on disk, and no new file.
- Upload POST by `stranger` to the owner's outfit returns 404. No row or file is added, and the owner's photo is unchanged.
- GET on the remove page shows the photo and a confirm form. POST inside `django_capture_on_commit_callbacks(execute=True)` unlinks the photo, deletes the row and file, and shows "Photo removed."
- GET or POST on the remove page for an outfit without a photo redirects to the outfit page and changes nothing.
- GET and POST to the remove page from `stranger` return 404 and change nothing.
- GET to the upload URL returns 405.
- The detail page's query count is the same with and without a photo.
- Garments of the outfit keep their own photos after the outfit photo is replaced or removed.

### Success Criteria:

#### Automated Verification:

- View tests pass: `uv run pytest outfits/tests/test_views.py`
- The privacy contracts cover the new routes: `uv run pytest tests/`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- Composing an outfit lands on its page with "Outfit saved." and the *Photo* section under *Tags*
- Uploading a large phone-sized photo shows "Preparing photo…", then "Uploading…" with the button disabled, then the page with the photo shown whole
- Replacing shows the new photo; the old file is gone from the dev `MEDIA_ROOT`
- *Remove photo* → confirmation page with the photo → confirm → "Photo removed." and "No photo yet."
- At 360 px in headless Chromium the Photo section, the upload form and the confirmation page fit without horizontal scrolling

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Portrait tiles in the wardrobe

### Overview

Show the outfit photo as the tile when there is one, and make every tile portrait 3:4 so photo tiles and collage tiles line up.

### Changes Required:

#### 1. The grid template

**File**: `templates/outfits/wardrobe.html`

**Intent**: One tile shape, two contents.

**Contract**:
- Inside each tile's `<a>`, when `outfit.photo_id` is set, render `<div class="outfit-preview outfit-preview-photo">` with one `<img src="{{ outfit.photo_url }}" alt="" loading="lazy" decoding="async">`. Otherwise render the existing collage markup unchanged.
- Name and tag line are unchanged.
- The S-03 comment that points at S-04 is updated to describe both kinds of tile.

#### 2. Styles

**File**: `static/css/app.css`

**Intent**: Portrait tiles that keep a full-body photo mostly visible and a collage evenly split.

**Contract**:
- `.outfit-preview` changes `aspect-ratio: 1` to `aspect-ratio: 3 / 4`. `.outfit-preview-photo > *` spans the whole grid like `.outfit-preview-1`, with `object-fit: cover` and `object-position: center top`, so a crop loses feet rather than the head.
- The block comment above the tile rules is updated. The garment list and picker stay square.

#### 3. Tests

**File**: `outfits/tests/test_views.py`

**Intent**: The grid shows the right tile for each outfit, only the owner's, at constant cost.

**Contract**:
- With outfit A (photo) and outfit B (no photo, three garments), A's tile contains A's `photo_url` and none of A's garment photo URLs. B's tile contains its garment collage.
- `stranger`'s outfit with a photo never appears in the owner's grid, and its `photo_url` is absent from the page.
- After removing A's photo through the remove action, A's tile shows its collage.
- With a tag filter selecting only B, A's `photo_url` is absent.
- The grid query count is the same for one outfit without a photo as for five outfits with photos and tags (extending `test_grid_query_count_does_not_grow_with_outfits_tags_or_selections`).

### Success Criteria:

#### Automated Verification:

- View tests pass: `uv run pytest outfits/tests/test_views.py`
- The privacy contracts still pass: `uv run pytest tests/`
- The full suite passes: `uv run pytest`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- In the wardrobe, a photo tile and a collage tile in the same row have the same size, and the photo shows the upper body and head
- 2-, 3- and 4-garment collages and the `+N` badge still read correctly in the portrait tile
- At 360 px in headless Chromium the grid shows two portrait tiles per row with no horizontal scrolling, with and without a tag filter

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Pull request and PR-environment verification

### Overview

Bring the branch up to date, open the pull request, run every manual check against the Railway PR environment, and put the close-out into the same PR before the developer merges.

### Changes Required:

#### 1. Base branch check

**File**: none — an operation

**Intent**: The PR carries only this slice's commits and passes against whatever `master` holds now.

**Contract**: Run `git fetch origin`, then `git log --oneline origin/master..HEAD`. If commits that are not this slice's appear, stop and ask the developer. Otherwise `git rebase origin/master`. Resolve conflicts narrowly in `outfits/models.py`, `outfits/views.py`, `outfits/urls.py`, `outfits/tests/test_views.py`, `tests/owner_scoped_routes.py`, `tests/factories.py`, `static/css/app.css`, `templates/outfits/*` and `context/foundation/roadmap.md`. If another `outfits` `0003_*` migration landed, delete this slice's migration and regenerate it. Re-run the full suite and `makemigrations --check`.

#### 2. Pull request

**File**: none — an operation

**Intent**: Deliver for review; nothing reaches `master` without the developer's merge.

**Contract**: `git push -u origin feat/outfit-photo` (with `--force-with-lease` only if a rebase rewrote pushed commits), then `gh pr create --base master --head feat/outfit-photo`. Title: `feat(outfit-photo): own photo in an outfit as its wardrobe tile (S-04, OG-5)`. The body contains:
- a summary lifted from `plan-brief.md`
- the phases
- the test commands run
- the PR-environment checks
- links to `plan.md` and Jira OG-5
- a note that merging deploys migration `outfits.0003_*`

Never merge the PR.

#### 3. PR-environment checks and close-out

**File**: `context/changes/outfit-photo/plan.md`, `context/changes/outfit-photo/change.md`, `context/foundation/roadmap.md`

**Intent**: "Done" means the checks passed on the PR deploy, and the record of it rides in the same PR (lessons).

**Contract**:
- The PR environment has an empty database, so create two accounts there first.
- Run the Phase 4 manual checks against the PR environment URL. Put any fix into this PR, with its own commit.
- Once everything passes:
  - tick Progress with SHAs
  - add a dated "PR deploy" note to `change.md` (PR URL, deployment id, checks run, deviations from this plan)
  - set S-04 to `done` in `roadmap.md`, both in the At-a-glance table and in the item body, and update its Backlog Handoff row
  - push
- Per the Jira lesson, move OG-5 to Done after the developer merges, with a comment naming the PR. If S-06/S-07 are unblocked, say so there.

### Success Criteria:

#### Automated Verification:

- The full suite passes on the rebased branch: `uv run pytest`
- Nothing is left unmigrated after the rebase: `uv run python manage.py makemigrations --check --dry-run`
- The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- The PR against `master` exists and contains only this slice's commits: `gh pr view feat/outfit-photo --json baseRefName,commits`
- The PR has no merge conflicts: `gh pr view feat/outfit-photo --json mergeable`
- The Railway PR environment build (the PR status check) is green, and its deploy logs show `migrate` applying `outfits.0003_*`
- The PR environment's `/health/` returns 200

#### Manual Verification:

- On the PR environment, from a phone-sized headless Chromium (360 px): compose an outfit, land on its page, upload a real phone photo, see it on the page and as the tile in the wardrobe
- On the PR environment, replace the photo and then remove it through the confirmation page; the tile returns to the collage
- On the PR environment, a second account gets 404 on the first account's outfit page and remove page, and 404 on the first account's photo URL; its own wardrobe shows none of the first account's outfits
- The developer reviews and merges the PR; production `/health/` returns 200 afterwards

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `Outfit.photo` ownership rule, `photo_url` with and without a photo
- `discard_private_image`: row and file gone after commit; both kept on rollback
- `RESTRICT` on an in-use image; user deletion still cascades
- `GarmentForm` behaviour unchanged after the mixin extraction (existing tests)

### Integration Tests:

- Upload, replace and remove through HTTP, with rows re-read and files checked on disk
- A refused upload (invalid, too large, foreign outfit, failure mid-replace) leaves no new row or file and keeps the old photo
- An EXIF-rotated portrait photo is stored upright at no more than 1600 px (Risk #3)
- Registry-driven privacy scenarios for `outfits:photo_upload` and `outfits:photo_remove`, and the outfit photo in the wardrobe and detail markers (Risks #1 and #2)
- Wardrobe tiles: photo vs collage, filtered and unfiltered, constant query count

### Manual Testing Steps:

1. Compose an outfit → land on its page → *Upload photo* with a large phone photo → photo shown whole.
2. Wardrobe → the tile is the photo, portrait, head visible; a collage tile in the same row is the same size.
3. Replace the photo → the new one is shown; the old file is gone.
4. *Remove photo* → confirmation → confirm → the tile is the collage again.
5. Double-tap *Upload photo* on a throttled connection → one upload, button disabled.
6. Second account → 404 on the first account's outfit, remove page and photo URL.
7. Steps 1–6 on the Railway PR environment before merge.

## Performance Considerations

- **Grid and detail pages:** no added queries. `photo_url` is built from `photo_id`, and the tile reads no `PrivateImage` row.
- **Upload:** the same cost as adding a garment: browser-side shrink, then `normalize_photo` on the server. The foreign-owner check runs before decoding, so refused requests cost one query.
- **Replace/remove:** one row lock, one image insert or none, one row delete, and a file delete after commit.
- **Database latency:** the production database now runs in an EU region (developer, 2026-09-14), so the read/write round-trips of the upload and replace transactions are well within the 5-second NFR. The upload's cost is dominated by the photo transfer and decode, not the database.
- **Volume:** replace and remove free the old file, so one outfit never uses more than one photo's worth of space (~0.3–0.6 MB after normalization).

## Migration Notes

- `outfits.0003_outfit_photo` adds a nullable `photo_id` with a unique index to `outfits_outfit`. Existing outfits get `NULL` and keep showing collages.
- Rollback: first remove photos from outfits, or accept that reverting the code leaves the column unused. Then `migrate outfits 0002` drops it. `PrivateImage` rows of outfit photos then remain as unreferenced rows with files.
- Known gap for S-07: `RESTRICT` guards the image, not the outfit. Deleting an outfit (ORM or admin today, the UI in S-07) succeeds and leaves its `PrivateImage` row and file unreferenced. S-07's delete path must unlink the photo and call `discard_private_image` in the same transaction.

## References

- Roadmap item: `context/foundation/roadmap.md` — S-04 (`outfit-photo`), Jira OG-5
- PRD: `context/foundation/prd.md` — FR-007, FR-008, US-01, NFR *Prywatność*, *Responsywność*, *Trwałość danych*
- Test plan: `context/foundation/test-plan.md` — Risks #1, #2, #3; cookbook §6.1, §6.2
- Patterns: `garments/forms.py:10`, `garments/views.py:33`, `garments/models.py:45`, `privatemedia/models.py:78`, `outfits/views.py:364`, `tests/owner_scoped_routes.py`
- Prior plans: `context/changes/outfit-tags/plan.md`, `context/changes/compose-outfit/plan.md`, `context/changes/add-garment/plan.md`
- Related ticket: Jira OG-9 (double submit), left open for the other forms
- Worktree: `/home/ciastek/Projects/.worktrees/outfit-photo`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Outfit photo model and file lifecycle

#### Automated

- [x] 1.1 The migration applies cleanly: `uv run python manage.py migrate` — 4fba006
- [x] 1.2 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run` — 4fba006
- [x] 1.3 Model tests pass: `uv run pytest outfits/tests/test_model.py privatemedia/tests/test_model.py` — 4fba006
- [x] 1.4 Garment tests pass unchanged after the mixin refactor: `uv run pytest garments/tests` — 4fba006
- [x] 1.5 The full suite passes: `uv run pytest` — 4fba006
- [x] 1.6 System checks pass: `uv run python manage.py check` — 4fba006
- [x] 1.7 Linting passes: `uv run ruff check .` — 4fba006
- [x] 1.8 Formatting is clean: `uv run ruff format --check .` — 4fba006

#### Manual

- [x] 1.9 In `/admin/`, setting an outfit's photo to another user's image id is refused with the ownership message — 4fba006
- [x] 1.10 Adding a garment through the UI still works exactly as before (photo shrinks, garment appears in the list) — 4fba006

### Phase 2: Add, replace and remove on the outfit page

#### Automated

- [x] 2.1 View tests pass: `uv run pytest outfits/tests/test_views.py` — 1568a51
- [x] 2.2 The privacy contracts cover the new routes: `uv run pytest tests/` — 1568a51
- [x] 2.3 The full suite passes: `uv run pytest` — 1568a51
- [x] 2.4 System checks pass: `uv run python manage.py check` — 1568a51
- [x] 2.5 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run` — 1568a51
- [x] 2.6 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput` — 1568a51
- [x] 2.7 Linting passes: `uv run ruff check .` — 1568a51
- [x] 2.8 Formatting is clean: `uv run ruff format --check .` — 1568a51

#### Manual

- [x] 2.9 Composing an outfit lands on its page with "Outfit saved." and the *Photo* section under *Tags* — 1568a51
- [x] 2.10 Uploading a large phone-sized photo shows "Preparing photo…", then "Uploading…" with the button disabled, then the page with the photo shown whole — 1568a51
- [x] 2.11 Replacing shows the new photo; the old file is gone from the dev `MEDIA_ROOT` — 1568a51
- [x] 2.12 *Remove photo* → confirmation page with the photo → confirm → "Photo removed." and "No photo yet." — 1568a51
- [x] 2.13 At 360 px in headless Chromium the Photo section, the upload form and the confirmation page fit without horizontal scrolling — 1568a51

### Phase 3: Portrait tiles in the wardrobe

#### Automated

- [x] 3.1 View tests pass: `uv run pytest outfits/tests/test_views.py` — 4b9a74d
- [x] 3.2 The privacy contracts still pass: `uv run pytest tests/` — 4b9a74d
- [x] 3.3 The full suite passes: `uv run pytest` — 4b9a74d
- [x] 3.4 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput` — 4b9a74d
- [x] 3.5 Linting passes: `uv run ruff check .` — 4b9a74d
- [x] 3.6 Formatting is clean: `uv run ruff format --check .` — 4b9a74d

#### Manual

- [x] 3.7 In the wardrobe, a photo tile and a collage tile in the same row have the same size, and the photo shows the upper body and head — 4b9a74d
- [x] 3.8 2-, 3- and 4-garment collages and the `+N` badge still read correctly in the portrait tile — 4b9a74d
- [x] 3.9 At 360 px in headless Chromium the grid shows two portrait tiles per row with no horizontal scrolling, with and without a tag filter — 4b9a74d

### Phase 4: Pull request and PR-environment verification

#### Automated

- [x] 4.1 The full suite passes on the rebased branch: `uv run pytest`
- [x] 4.2 Nothing is left unmigrated after the rebase: `uv run python manage.py makemigrations --check --dry-run`
- [x] 4.3 The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- [x] 4.4 The PR against `master` exists and contains only this slice's commits: `gh pr view feat/outfit-photo --json baseRefName,commits`
- [x] 4.5 The PR has no merge conflicts: `gh pr view feat/outfit-photo --json mergeable`
- [x] 4.6 The Railway PR environment build is green, and its deploy logs show `migrate` applying `outfits.0003_*`
- [x] 4.7 The PR environment's `/health/` returns 200

#### Manual

- [x] 4.8 On the PR environment at 360 px: compose, land on the outfit page, upload a real phone photo, see it on the page and as the wardrobe tile
- [x] 4.9 On the PR environment, replace the photo, then remove it through the confirmation page; the tile returns to the collage
- [x] 4.10 On the PR environment, a second account gets 404 on the first account's outfit page, remove page and photo URL, and sees none of its outfits
- [ ] 4.11 The developer reviews and merges the PR; production `/health/` returns 200 afterwards
