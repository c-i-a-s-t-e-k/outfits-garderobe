# Compose Outfit and Wardrobe Grid Implementation Plan

## Overview

A signed-in user composes an outfit by ticking garment photos, optionally names it, and saves it; the outfit then appears as a tile in the wardrobe grid at `/wardrobe/`, which becomes the landing page again. An outfit without the user's own photo — every outfit, until S-04 — shows a 2×2 preview built from its garments' photos. A garment can belong to any number of outfits. This is roadmap slice **S-03** (Jira OG-4), covering FR-005, FR-008 and the composition half of US-01 — the product's north star.

## Current State Analysis

- **Garments exist and are built to be referenced.** `garments.Garment` (`garments/models.py:27`) has a UUID primary key, an `owner` FK, and a `photo_url` property that reverses the private media gate from `photo_id` without a query (`garments/models.py:115`). Its docstring already names S-03's many-to-many.
- **The ownership pattern is "rules on every path".** `PrivateImage.save()` and `Garment.save()` both call `full_clean()` (`privatemedia/models.py:55`, `garments/models.py:76`); the view never takes `owner` or a photo from the request (`garments/views.py:33`).
- **`/wardrobe/` is a reserved placeholder waiting for this slice.** The route is named `wardrobe` in `outfits_garderobe/urls.py:35`, served by `accounts.views.wardrobe` (`accounts/views.py:29`) with `templates/wardrobe.html`. `LOGIN_REDIRECT_URL = 'garments:list'` (`outfits_garderobe/settings.py:283`) and `home` redirecting to `garments:list` (`accounts/views.py:24`) are both documented as temporary until S-03 points them back at `wardrobe`. Smoke tests pin the current landing (`accounts/tests/test_smoke.py:85`, `:221`).
- **UI conventions.** Server-rendered forms that work without JavaScript; Pico plus a deliberately small `static/css/app.css` with a `.garment-grid` of square lazy-loaded tiles (`static/css/app.css:59`); the nav lists *Garments* first (`templates/base.html:26`).
- **Test conventions.** `pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]`, shared `owner` / `stranger` fixtures (`conftest.py:18`), Pillow-generated images, query-count assertions (`garments/tests/test_views.py:210`).
- **Test plan.** Risks #1 (cross-user read leak) and #2 (write with a foreign id) apply directly. The test-plan §3 Phase 1 change (`testing-cross-user-privacy`) has not started; this slice ships its own two-account tests for its new views.

## Desired End State

A user logs in and lands on *Wardrobe*. With fewer than two garments, the page says so and links to *Garments*. Otherwise they tap *Compose outfit*, see their own garments as a two-per-row photo grid at 360 px, tick two or more (selected tiles are visibly marked and a sticky bar reads "3 selected"), optionally type a name, and tap *Save outfit*. They land back on the wardrobe with "Outfit saved." and the new outfit first: a square tile of up to four garment photos ordered outerwear-to-shoes, a "+N" badge when more are hidden, and the outfit's name underneath. Leaving the name empty gives the lowest free `outfit-N`. Tapping the tile opens a read-only page with every garment. A second account sees none of it — not in the grid, not on the detail URL, not in the compose picker — and a compose POST carrying another user's garment id stores nothing.

Verification: the automated suite proves the naming, ownership, minimum-size and preview rules; a headless Chromium session at 360 px and a two-account check against production confirm the UI and privacy.

### Key Discoveries:

- In Django 6.0.8, `ModelForm._post_clean()` validates constraints with the form's excluded fields in `exclude` (`django/forms/models.py:482-513`), and `UniqueConstraint.validate()` skips any constraint whose expressions reference an excluded field (`django/db/models/constraints.py:578-583`). `owner` is never a form field, so the `(owner, Lower('name'))` constraint is **silently skipped** during form validation — the form must check name uniqueness itself.
- `Model.validate_constraints()` maps a unique error to a field only when the constraint has exactly one plain field (`django/db/models/base.py:1657-1663`); an expression-based constraint surfaces as a non-field error. Another reason the form's own name check is what the user sees.
- `ModelChoiceIteratorValue` carries `.instance` (`django/forms/models.py:1419`), so a template iterating `form.garments` subwidgets can read `option.data.value.instance.photo_url` without extra queries.
- Many-to-many writes (`.set()`, `.add()`) never call `Outfit.save()`, so `full_clean()` cannot guard garment ownership; an `m2m_changed` `pre_add` receiver is the model-level hook that covers the ORM and admin paths.
- `Garment.photo_url` makes no query, so a grid tile's images cost only the prefetched garment rows.

## What We're NOT Doing

- The user's own photo in an outfit and swapping it into the tile — S-04.
- Tags and filtering — S-05.
- Editing or deleting an outfit, including rename — S-07.
- Garment edit/delete and the incomplete-outfit flag; deleting a garment keeps Django's default of removing its link rows — S-06.
- Warning about or refusing outfits with an identical garment set — duplicates are allowed by decision.
- A name counter that never reuses numbers — the lowest free `outfit-N` is reused after a deletion by decision.
- Enforcing the two-garment minimum outside the compose form — admin and ORM paths may create smaller outfits; S-06 handles outfits that shrink.
- Grouping, searching or filtering garments in the picker; pagination of the grid or picker.
- The test-plan's route-enumerating privacy net across all apps — test-plan §3 Phase 1.
- Real-phone checks — deferred to production use pre-MVP; headless Chromium at 360 px stands in.
- Translating the UI; it stays in English like S-01 and S-02.

## Implementation Approach

1. **A new `outfits` app** holds the `Outfit` model with a many-to-many to `garments.Garment`. Rules that can live on the model do (name tidying and default naming in `clean()`, name uniqueness and non-emptiness as database constraints, garment ownership in an `m2m_changed` guard); the two-garment minimum lives in the form, because the relation does not exist yet when the row is validated.
2. **The wardrobe moves into `outfits` but keeps its route name.** `wardrobe` stays the URL name at `/wardrobe/`; compose and detail are added under the same prefix in an `outfits` namespace. The placeholder view and template are deleted.
3. **Plain server-rendered pages.** The picker is a checkbox per garment wrapped in a photo tile; selection styling and the "N selected" count are pure CSS (`:has(:checked)` and CSS counters), so no JavaScript is added.
4. **Preview ordering is computed in Python from a prefetch**, so the grid costs a constant number of queries however many outfits and garments there are.
5. **Production last**, with the privacy check repeated against real accounts.

## Critical Implementation Details

**Name uniqueness in the form.** Because the form excludes `owner`, `ModelForm` never runs the `(owner, lower(name))` constraint. `OutfitForm.clean_name()` must check `Outfit.objects.filter(owner=..., name__iexact=...)` itself and raise a field error; `Outfit.save()`'s `full_clean()` and the database constraint stay as the backstop. When the name is left blank, the default is assigned in `Outfit.clean()`, which the form reaches in `_post_clean()` — so `owner` must be set on `form.instance` in the form's `__init__`, before validation.

**Default-name race.** Two unnamed saves in parallel can compute the same `outfit-N`. The store step runs inside a savepoint; if the save fails on the name constraint (`IntegrityError`, or a `ValidationError` from `full_clean()` if the other row committed first) and the name was auto-assigned, clear the name, recompute, and retry once. A typed name that became taken in the same window re-renders the form with the name error.

**CSS counter placement.** A CSS counter only displays values incremented earlier in document order, so the element that shows "N selected" must come after the checkboxes in the markup. The sticky save bar at the end of the form satisfies that; putting the count above the grid would always show 0.

## Parallel Work & Delivery

This slice is built in a separate git worktree while other work continues in the main checkout, and it ships as a pull request rather than a direct push.

- **Where the work happens.** Worktree `/home/ciastek/Projects/outfits-garderobe-compose-outfit`, branch `feat/compose-outfit`, created from `feat/user-accounts` at `c8c7079`. Every command in this plan runs from the worktree; never `cd` to the main checkout `/home/ciastek/Projects/outfits-garderobe`, which belongs to the parallel work.
- **Local state is per worktree.** `db.sqlite3` and the dev `MEDIA_ROOT` live under the project root, so this worktree starts with an empty database and no photos: run `uv run python manage.py migrate` and create test accounts here before manual checks. `staticfiles/` is untracked too, and without its manifest 22 tests fail with "Missing staticfiles manifest entry": before the first `uv run pytest`, run `DJANGO_SETTINGS_MODULE=outfits_garderobe.settings_test uv run python manage.py collectstatic --noinput` (the test settings stub the secrets a bare `manage.py` would need), and re-run it after changing anything under `static/`. The `.env` path `../.secrets/outfits-garderobe/.env` resolves to the same file from both checkouts. When both run a dev server, this worktree uses `uv run python manage.py runserver 8001`, and headless Chromium checks target that port.
- **Git hygiene.** The stash stack is shared across worktrees: never use bare `git stash` / `git stash pop`; set work aside with a WIP commit instead. Commit per phase on `feat/compose-outfit` only.
- **Files likely to conflict with the parallel work.** `context/foundation/roadmap.md`, `context/foundation/test-plan.md`, `context/foundation/lessons.md`, `templates/base.html` (nav), `static/css/app.css`, `outfits_garderobe/settings.py` (`INSTALLED_APPS`, `LOGIN_REDIRECT_URL`), `outfits_garderobe/urls.py`, `accounts/views.py`, `accounts/tests/test_smoke.py`. Keep edits to these narrow (add, don't reformat), and roadmap/test-plan edits limited to the S-03 row and body. If the parallel work adds a `garments` migration, re-run `makemigrations --check` after rebasing — `outfits.0001_initial` depends on the latest `garments` migration.
- **Base branch.** On 2026-09-13 `master` was fast-forwarded to this plan's commit, so it already contains the `feat/user-accounts` history (S-02 close-out, test plan, lessons, roadmap update) and this plan. A PR from `feat/compose-outfit` should therefore carry only S-03 commits; Phase 4 still checks this, because the parallel work may land on `master` in the meantime.
- **Delivery.** No direct push to `master`. Phase 4 rebases onto `origin/master`, pushes `feat/compose-outfit`, and opens a PR into `master` with `gh pr create`; production deploys when the developer merges it, and production verification runs after the merge.

## Phase 1: `Outfit` model

### Overview

Create the `outfits` app with the `Outfit` model, its naming rules, the garment-ownership guard, preview ordering, the migration and a staff-only admin. No user-visible change.

### Changes Required:

#### 1. The app

**File**: `outfits/__init__.py`, `outfits/apps.py`, `outfits/migrations/__init__.py`, `outfits_garderobe/settings.py`

**Intent**: A home for outfits that depends on `garments`, and a place to connect the many-to-many guard at startup.

**Contract**: `OutfitsConfig` with `default_auto_field = 'django.db.models.BigAutoField'` like the other apps; `ready()` imports the module that registers the `m2m_changed` receiver. `'outfits'` appended to `INSTALLED_APPS` after `'garments'`.

#### 2. The model

**File**: `outfits/models.py`

**Intent**: One outfit: whose it is, what it is called, and which of the owner's garments it combines — with names that are never empty, unique per user regardless of case, and defaulted to the lowest free `outfit-N`.

**Contract**:
- Fields: `id` UUID primary key (as `Garment`); `owner` FK to `settings.AUTH_USER_MODEL`, `CASCADE`, `related_name='outfits'`; `name` `CharField(max_length=60, blank=True)` (blank only so `clean()` can fill it); `garments` `ManyToManyField('garments.Garment', related_name='outfits')`; `created_at` `DateTimeField(auto_now_add=True)`.
- `Meta`: `ordering = ['-created_at']`; index on `['owner', '-created_at']`; `UniqueConstraint(Lower('name'), 'owner', name='outfit_name_unique_per_owner')` with a readable `violation_error_message`; `CheckConstraint` named `outfit_name_not_empty` — `name` is not `''`.
- `DEFAULT_NAME_PREFIX = 'outfit-'`.
- `default_name_for(owner)` (classmethod): reads the owner's names case-insensitively starting with the prefix and returns `outfit-<n>` for the smallest `n ≥ 1` whose name, case-insensitively, is not in use. Other users' outfits do not count. `outfit-02` does not occupy `outfit-2`.
- `clean()`: collapse whitespace runs and strip `name`; if it is then empty and `owner_id` is set, assign `default_name_for(owner)`.
- `save()` calls `full_clean()` first, with the same comment reasoning as `Garment.save()`.
- `preview_garments` property: the first four of `self.garments.all()` sorted by `(type rank, garment created_at)`; `hidden_garment_count` property: total minus the shown ones. Both read the (possibly prefetched) `all()` once and never issue their own ordered query, so a prefetch covers them.
- `ordered_garments` property: all garments in the same order, for the detail page.
- Type rank, as a module constant: outerwear, dress, sweater, shirt, tshirt, trousers, skirt, shorts, shoes, accessory, other.
- `get_absolute_url()` reverses `outfits:detail`.
- `__str__` returns `name`.

#### 3. The garment-ownership guard

**File**: `outfits/signals.py` (new)

**Intent**: Make it impossible, on any ORM or admin path, to link a garment into another user's outfit — the model-level half of test-plan Risk #2.

**Contract**: An `m2m_changed` receiver on `Outfit.garments.through`, acting on `pre_add` only. Forward (`reverse=False`, instance is an `Outfit`): raise `ValidationError` if any garment in `pk_set` has an `owner_id` different from the outfit's. Reverse (`reverse=True`, instance is a `Garment`): raise if any outfit in `pk_set` has a different owner. One query per add.

#### 4. Migration

**File**: `outfits/migrations/0001_initial.py`

**Intent**: Create the table, the link table and both constraints on SQLite and PostgreSQL.

**Contract**: Generated with `uv run python manage.py makemigrations outfits`; depends on `garments`' latest migration and the auth user model.

#### 5. Admin

**File**: `outfits/admin.py`

**Intent**: A staff-only inspection surface, matching `garments/admin.py`.

**Contract**: `OutfitAdmin` with `list_display` of name, owner and creation time; `list_filter` on owner; `list_select_related = ('owner',)`; `raw_id_fields = ('garments',)` so the form never lists every user's garments; `created_at` read-only.

#### 6. Tests

**File**: `outfits/tests/__init__.py`, `outfits/tests/test_model.py`

**Intent**: Pin the naming and ownership rules — expected values come from the decisions in this plan, not from the implementation.

**Contract**: Garments built through a small helper that stores a Pillow-generated image via `PrivateImage`. Cases:
- a blank name on a user's first outfit becomes `outfit-1`; with `outfit-1` and `outfit-3` existing it becomes `outfit-2`; with `outfit-1` and `OUTFIT-2` existing it becomes `outfit-3`
- another user's `outfit-1` does not affect the default; `outfit-02` existing still yields `outfit-1`, then `outfit-2`
- a whitespace-only name gets the default; `'  Summer   wedding '` is stored as `'Summer wedding'`
- a second outfit named `'summer wedding'` for the same owner is rejected; the same name for another owner saves
- the database enforces both constraints: a `QuerySet.update()` setting a case-variant duplicate name raises `IntegrityError`, and one setting `name=''` raises `IntegrityError`
- adding another user's garment to an outfit raises `ValidationError` and leaves the link table unchanged; the same through `garment.outfits.add(outfit)` also raises
- one garment can be added to two outfits of its owner
- two outfits with the identical garment set both save
- with seven garments of mixed types, `preview_garments` returns four in the type order above and `hidden_garment_count` is 3; with two garments it returns both and 0; two garments of the same type appear in the order they were added
- deleting the owner removes their outfits

### Success Criteria:

#### Automated Verification:

- The migration applies cleanly: `uv run python manage.py migrate`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- The model tests pass: `uv run pytest outfits/tests/test_model.py`
- The full suite still passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- In `/admin/`, a staff user creates an outfit with a blank name and it saves as `outfit-1`
- In `/admin/`, adding another user's garment id to an outfit is refused

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Compose and detail pages

### Overview

Ship the compose flow and the read-only outfit page, with the two-account tests that prove neither reads nor writes cross users. Saving redirects to `wardrobe`, which is still the placeholder until Phase 3.

### Changes Required:

#### 1. The form

**File**: `outfits/forms.py` (new)

**Intent**: Accept a name and a selection of the requester's own garments, refuse anything else with a readable message before anything is stored.

**Contract**: `OutfitForm(forms.ModelForm)` over `name` and `garments`, constructed as `OutfitForm(data=None, *, owner)`.
- `__init__` sets `self.instance.owner = owner` and narrows `garments` to `Garment.objects.filter(owner=owner)` (model ordering), widget `CheckboxSelectMultiple`. A posted id outside that queryset fails as an invalid choice.
- `name`: label "Name (optional)", help text saying an empty name becomes `outfit-N`, `maxlength` 60.
- `clean_name()`: tidy whitespace as the model does; if non-empty and the owner already has an outfit with that name case-insensitively, raise "You already have an outfit named …". (See Critical Implementation Details for why the model constraint does not reach the form.)
- `clean_garments()`: fewer than two selected raises "Choose at least 2 garments."; the required-field error for zero uses the same message.

#### 2. Views

**File**: `outfits/views.py` (new)

**Intent**: A compose flow that stores a complete outfit or nothing, and a detail page only the owner can open.

**Contract**:
- `outfit_compose` (`@login_required`): GET renders the form. If the requester has fewer than two garments, the template shows a message with a link to `garments:add` instead of the form. A valid POST, inside `transaction.atomic()`, saves the outfit and sets its garments; on the default-name race it retries once (see Critical Implementation Details). On success: `messages.success(request, 'Outfit saved.')` and redirect to `wardrobe`. An invalid POST re-renders with status 200, keeping the typed name and ticked garments.
- `outfit_detail` (`@login_required`): `get_object_or_404(Outfit.objects.prefetch_related('garments'), pk=pk, owner=request.user)` — "no such outfit" and "not your outfit" are the same 404.

#### 3. URLs

**File**: `outfits/urls.py` (new), `outfits_garderobe/urls.py`

**Intent**: Give compose and detail routes under `/wardrobe/` without disturbing the `wardrobe` route name.

**Contract**: `app_name = 'outfits'`; `'compose/'` → `outfit_compose` named `compose`; `'<uuid:pk>/'` → `outfit_detail` named `detail`. Included as `path('wardrobe/', include('outfits.urls'))` directly after the existing `wardrobe` path and above the catch-all `privatemedia` include.

#### 4. Templates

**File**: `templates/outfits/compose.html`, `templates/outfits/detail.html` (new)

**Intent**: A picker that is usable with a thumb at 360 px and a detail page that shows every garment.

**Contract**:
- Both extend `base.html`.
- `compose.html`: heading; a POST form with `{% csrf_token %}`; the name field with label, help and errors; the `garments` errors; a `<ul class="outfit-picker">` iterating `form.garments` — each `<li>` a `<label>` wrapping the checkbox, an `<img>` whose `src` is `option.data.value.instance.photo_url` (`loading="lazy"`, `decoding="async"`, `alt=""` since the caption names it), and a caption with the garment's `display_type`; after the list, a `<div class="outfit-picker-bar">` containing the "N selected" output element and the *Save outfit* button; a *Cancel* link to `wardrobe`. The fewer-than-two-garments branch replaces the form with a short message and an *Add garment* button.
- `detail.html`: the outfit name as heading, the creation date, a `.garment-grid` of `ordered_garments` using the same tile markup as `garments/list.html`, and a link back to `wardrobe`.

#### 5. Styles

**File**: `static/css/app.css`

**Intent**: Only the layout Pico does not provide, keeping the file's own "not a design system" warning.

**Contract**:
- `.outfit-picker` reuses the `.garment-grid` grid rules (shared selector, not a copy).
- A picker tile whose checkbox is checked (`li:has(input:checked)`) gets a visible outline in `--pico-primary`; the checkbox itself stays visible in the tile's corner and keyboard-focusable.
- `.outfit-picker-bar` is `position: sticky; bottom: 0` with the page background, so *Save* is reachable without scrolling to the end.
- The count uses a CSS counter reset on the form and incremented by `input:checked` inside the picker; the output element renders it via `::before { content: counter(…) }` followed by " selected". Browsers without `:has()` still get the counter and the checkboxes.

#### 6. Tests

**File**: `outfits/tests/test_views.py` (new)

**Intent**: Prove through HTTP that compose and detail never cross users, and that a failed compose stores nothing — each assertion re-reads the database rather than trusting the status code.

**Contract**: Cases:
- anonymous GET of compose and detail, and anonymous POST to compose, redirect to `settings.LOGIN_URL`
- compose GET for `owner` lists each own garment's `photo_url`; the page does not contain the `stranger`'s garment photo URL or description
- a valid POST with two own garments and a name creates one `Outfit` owned by the requester with exactly those garments, redirects to `wardrobe`, and the followed page shows "Outfit saved."
- a POST with a blank name stores `outfit-1`; a second one stores `outfit-2`
- a POST naming the outfit as a case variant of an existing name returns 200 with a `name` error and creates nothing
- a POST with one garment, and one with none, returns 200 with "Choose at least 2 garments." and creates nothing
- a POST with one own garment plus the `stranger`'s garment id returns 200 with a `garments` error, creates no `Outfit`, and the stranger's garment has no outfits afterwards
- a re-rendered invalid POST keeps the typed name and the ticked garments checked
- a user with one garment sees the add-garment message and no picker form
- a garment already in one outfit can be selected into a second outfit
- when `Outfit.default_name_for` is monkeypatched to return an already-taken name on its first call only, an unnamed POST still succeeds with the next free name (the retry)
- `Outfit.get_absolute_url()` is `/wardrobe/<uuid>/`
- detail for the owner returns 200 and contains every garment's `photo_url`, including the ones beyond the first four; the `stranger` gets 404; a random UUID gets 404
- compose GET query count is the same for two garments as for eight

### Success Criteria:

#### Automated Verification:

- The view tests pass: `uv run pytest outfits/tests/test_views.py`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- Composing an outfit from three garments with a typed name saves and redirects with "Outfit saved."
- Ticking and unticking tiles updates the outline and the "N selected" count without JavaScript
- Saving with one garment ticked shows the error and keeps the selection
- The detail page shows every garment of a seven-garment outfit
- At 360 px in headless Chromium the picker shows two tiles per row, the save bar stays visible while scrolling, and nothing scrolls horizontally
- Logged in as a second account, the first account's detail URL returns 404

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Wardrobe grid and landing

### Overview

Replace the `/wardrobe/` placeholder with the real outfit grid and its preview tiles, make it the landing page again, and reorder the navigation.

### Changes Required:

#### 1. The grid view

**File**: `outfits/views.py`, `outfits_garderobe/urls.py`, `accounts/views.py`, `templates/wardrobe.html`

**Intent**: Move the wardrobe into the `outfits` app under the unchanged route name, and delete the placeholder.

**Contract**:
- `wardrobe` (`@login_required`) in `outfits/views.py`: `Outfit.objects.filter(owner=request.user).prefetch_related('garments')` in model ordering, plus whether the requester has at least two garments, rendered with `outfits/wardrobe.html`. Query count does not grow with outfits or garments.
- `outfits_garderobe/urls.py`: the `wardrobe` path now points at `outfits.views.wardrobe`, keeping `name='wardrobe'`; its comment is updated to say the page is filled in.
- `accounts/views.py`: the `wardrobe` view is removed; the module docstring no longer mentions it.
- `templates/wardrobe.html` is deleted.

#### 2. The grid template

**File**: `templates/outfits/wardrobe.html` (new)

**Intent**: The outfit-first home page: every outfit as a square preview tile, and empty states that always say what to do next.

**Contract**:
- Extends `base.html`; heading "Your wardrobe"; a *Compose outfit* button at the top when the user has at least two garments.
- Empty states: no outfits and at least two garments → "No outfits yet" with the *Compose outfit* call to action; fewer than two garments → "Add at least 2 garments to compose an outfit" with a link to `garments:add`.
- `<ul class="outfit-grid">`; each `<li>` is an `<a>` to the outfit's `get_absolute_url()` containing a `<div class="outfit-preview outfit-preview-{{ n }}">` of the `preview_garments` images (`src` = `photo_url`, `loading="lazy"`, `decoding="async"`, `alt=""`), with a `+{{ hidden_garment_count }}` badge on the last cell when that count is non-zero, and the outfit name as a caption. The link's accessible name is the outfit name.

#### 3. Styles

**File**: `static/css/app.css`

**Intent**: A square collage that reads as one tile and keeps the same footprint as a garment tile, so S-04 can drop a single photo into the same slot.

**Contract**:
- `.outfit-grid` shares the `.garment-grid` grid rules.
- `.outfit-preview`: square (`aspect-ratio: 1`), `display: grid`, small gap, images `object-fit: cover` filling their cell. Layouts by count: `-2` two columns full height; `-3` first image spans both rows of the left column; `-4` 2×2.
- The `+N` badge is positioned over the last cell with enough contrast to read on any photo.

#### 4. Landing and navigation

**File**: `outfits_garderobe/settings.py`, `accounts/views.py`, `templates/base.html`

**Intent**: Point login and `/` back at the wardrobe, as the S-02 comments promised, and make both destinations reachable.

**Contract**:
- `LOGIN_REDIRECT_URL = 'wardrobe'`, with the adjacent comment updated.
- `home` redirects authenticated visitors to `wardrobe`; docstring updated.
- The authenticated nav lists *Wardrobe* (`wardrobe`) first, then *Garments*.

#### 5. Tests

**File**: `outfits/tests/test_views.py`, `accounts/tests/test_smoke.py`

**Intent**: Prove the grid shows exactly the requester's outfits in the agreed order and shape, and that the landing change is deliberate.

**Contract**: Cases:
- anonymous GET of `wardrobe` redirects to `settings.LOGIN_URL` (existing smoke test keeps covering this)
- the grid lists the owner's outfits newest first; the `stranger`'s grid contains neither the owner's outfit names nor any of the owner's garment photo URLs nor links to their detail pages
- a tile for a seven-garment outfit contains exactly four garment image URLs — the four the type order selects — and the text `+3`; a two-garment outfit's tile contains two image URLs and no badge
- each tile links to its outfit's detail URL
- with no outfits and two garments the page offers *Compose outfit*; with one garment it links to adding garments instead
- the grid's query count is the same for one outfit with two garments as for five outfits with seven garments each
- in `accounts/tests/test_smoke.py`, `test_root_sends_authenticated_visitors_to_the_garment_list` and `test_verified_account_logs_in_and_lands_on_the_garment_list` now expect `reverse('wardrobe')` and are renamed to say so

### Success Criteria:

#### Automated Verification:

- The view tests pass: `uv run pytest outfits/tests/test_views.py`
- The updated smoke suite passes: `uv run pytest accounts/tests/`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- Logging in lands on *Wardrobe*; the header shows *Wardrobe* then *Garments*
- A new outfit appears first in the grid after saving
- Tiles for two-, three-, four- and seven-garment outfits look like one square each, with `+3` readable on the seven
- A new account with no garments sees the "add at least 2 garments" state
- At 360 px in headless Chromium the grid shows two tiles per row with no horizontal scrolling
- Tapping a tile opens its detail page

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Pull request and production

### Overview

Bring the branch up to date with `master`, open a pull request instead of pushing to `master`, and — once the developer merges it — verify the deployed slice against production.

### Changes Required:

#### 1. Base branch check

**File**: none — an operation

**Intent**: Make sure the PR contains only this slice's commits (see Parallel Work & Delivery).

**Contract**: `git fetch origin`, then `git log --oneline origin/master..HEAD`. If commits that are not this slice's appear, stop and ask the developer how to handle them — do not decide alone. Then `git rebase origin/master`, resolve conflicts in the files listed under Parallel Work & Delivery, and re-run the full suite and `makemigrations --check` on the rebased branch.

#### 2. Pull request

**File**: none — an operation

**Intent**: Deliver the slice for review; nothing reaches `master` or production without the developer's merge.

**Contract**: `git push -u origin feat/compose-outfit` (with `--force-with-lease` only if the rebase rewrote already-pushed commits), then `gh pr create --base master --head feat/compose-outfit`. Title: `feat(compose-outfit): compose outfits and wardrobe grid (S-03, OG-4)`. Body: a short summary lifted from `plan-brief.md` (what and why, key decisions), the list of phases, the test commands run, the manual checks done so far and those pending after merge, links to `plan.md` and Jira OG-4, and a note that merging deploys to Railway (migration `outfits.0001_initial`). Never push to `master` directly and never merge the PR — merging is the developer's call. Stop here until the developer confirms the merge.

#### 3. Deploy on merge

**File**: none — an operation

**Intent**: Production follows the merge the same way S-02 Phase 5 followed its push.

**Contract**: After the merge, Railway builds `master` with nixpacks, runs `migrate` as the pre-deploy command (applying `outfits.0001_initial`), and passes the `/health/` check. No new environment variables, no data migration. The worktree can be removed once production verification passes (`git worktree remove`, run from the main checkout by the developer).

#### 4. Change record

**File**: `context/changes/compose-outfit/change.md`

**Intent**: Leave a record of what production verification found.

**Contract**: A dated "Production deploy" note in `## Notes` with the PR URL, the merge commit, the deployment id, the checks run and anything that deviated from this plan. Written after the merge, so it lands through a small follow-up PR (it can ride along with the `/10x-archive` change) — never pushed straight to `master`.

### Success Criteria:

#### Automated Verification:

- The full suite passes on the rebased branch: `uv run pytest`
- Nothing is left unmigrated after the rebase: `uv run python manage.py makemigrations --check --dry-run`
- The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- The PR against `master` exists and contains only this slice's commits: `gh pr view feat/compose-outfit --json baseRefName,commits`
- The PR has no merge conflicts: `gh pr view feat/compose-outfit --json mergeable`
- After merge, the deployment reaches a healthy state — `/health/` returns 200
- After merge, deploy logs show `migrate` applying `outfits.0001_initial`

#### Manual Verification:

- The developer reviews and merges the PR
- Against production, composing an outfit from garments and seeing it first in the wardrobe grid works end to end
- A second production account sees an empty wardrobe, gets 404 on the first account's outfit detail URL, and does not see the first account's garments in its compose picker
- The production wardrobe and compose pages at 360 px in headless Chromium show two tiles per row with no horizontal scrolling

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `Outfit` naming: lowest free `outfit-N`, case-insensitive occupancy, per-owner scope, whitespace tidying, both database constraints
- Garment-ownership guard on both sides of the relation
- Many-to-many semantics: one garment in many outfits, identical garment sets allowed
- Preview ordering and hidden count

### Integration Tests:

- Two-account reads: grid, detail, compose picker (test-plan Risk #1)
- Foreign garment id on compose changes nothing in the database (test-plan Risk #2)
- Compose failures store nothing: under two garments, taken name
- Default-name retry
- Tile shape: four images plus `+N`
- Constant query counts for grid and picker
- Landing through `/` and login

### Manual Testing Steps:

1. Log in → land on *Wardrobe* → *Compose outfit* → tick three garments → save without a name → tile `outfit-1` first.
2. Compose again with one of the same garments → both outfits show it.
3. Compose a seven-garment outfit → tile shows four photos and `+3` → tap → all seven on the detail page.
4. Try saving one garment → error, selection kept.
5. Second account → empty wardrobe, 404 on the first account's detail URL.
6. Headless Chromium at 360 px on compose and wardrobe.

## Performance Considerations

- **Grid**: two queries for outfits and their garments regardless of count; preview ordering runs in Python on the prefetched rows. Each tile fires at most four lazy-loaded gate requests, each answered with 304 on repeat visits by the gate's existing conditional GET.
- **Picker**: one query for the owner's garments; `photo_url` needs no photo row. Tiles are lazy-loaded, so a long wardrobe does not fire every image request up front.
- **Default naming**: one query over the owner's names starting with `outfit-`.

## Migration Notes

- Two new tables (`outfits_outfit`, `outfits_outfit_garments`) with a unique expression constraint and a check constraint; no changes to existing tables and no data migration.
- Rollback: reverting the code leaves unused tables; `migrate outfits zero` removes them. Garments and photos are unaffected.

## References

- Roadmap item: `context/foundation/roadmap.md` — S-03 (`compose-outfit`), Jira OG-4
- PRD: `context/foundation/prd.md` — FR-005, FR-008, US-01, NFR *Prywatność*, *Responsywność*
- Test plan: `context/foundation/test-plan.md` — Risks #1 and #2
- Model to reference: `garments/models.py:27`; view pattern: `garments/views.py:20`
- Landing contract: `outfits_garderobe/urls.py:31`, `outfits_garderobe/settings.py:283`, `accounts/views.py:13`
- Test conventions: `garments/tests/test_views.py`, `conftest.py`
- Prior plan: `context/changes/add-garment/plan.md`
- Django `ModelForm` constraint validation: `django/forms/models.py:482-513`, `django/db/models/constraints.py:572-606`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: `Outfit` model

#### Automated

- [x] 1.1 The migration applies cleanly: `uv run python manage.py migrate` — bdc4d87
- [x] 1.2 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run` — bdc4d87
- [x] 1.3 The model tests pass: `uv run pytest outfits/tests/test_model.py` — bdc4d87
- [x] 1.4 The full suite still passes: `uv run pytest` — bdc4d87
- [x] 1.5 System checks pass: `uv run python manage.py check` — bdc4d87
- [x] 1.6 Linting passes: `uv run ruff check .` — bdc4d87
- [x] 1.7 Formatting is clean: `uv run ruff format --check .` — bdc4d87

#### Manual

- [ ] 1.8 In `/admin/`, an outfit with a blank name saves as `outfit-1`
- [ ] 1.9 In `/admin/`, adding another user's garment id to an outfit is refused

### Phase 2: Compose and detail pages

#### Automated

- [x] 2.1 The view tests pass: `uv run pytest outfits/tests/test_views.py`
- [x] 2.2 The full suite passes: `uv run pytest`
- [x] 2.3 System checks pass: `uv run python manage.py check`
- [x] 2.4 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- [x] 2.5 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- [x] 2.6 Linting passes: `uv run ruff check .`
- [x] 2.7 Formatting is clean: `uv run ruff format --check .`

#### Manual

- [ ] 2.8 Composing an outfit from three garments with a typed name saves and redirects with "Outfit saved."
- [ ] 2.9 Ticking and unticking tiles updates the outline and the "N selected" count without JavaScript
- [ ] 2.10 Saving with one garment ticked shows the error and keeps the selection
- [ ] 2.11 The detail page shows every garment of a seven-garment outfit
- [ ] 2.12 At 360 px in headless Chromium the picker shows two tiles per row, the save bar stays visible, and nothing scrolls horizontally
- [ ] 2.13 A second account gets 404 on the first account's detail URL

### Phase 3: Wardrobe grid and landing

#### Automated

- [ ] 3.1 The view tests pass: `uv run pytest outfits/tests/test_views.py`
- [ ] 3.2 The updated smoke suite passes: `uv run pytest accounts/tests/`
- [ ] 3.3 The full suite passes: `uv run pytest`
- [ ] 3.4 System checks pass: `uv run python manage.py check`
- [ ] 3.5 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- [ ] 3.6 Linting passes: `uv run ruff check .`
- [ ] 3.7 Formatting is clean: `uv run ruff format --check .`

#### Manual

- [ ] 3.8 Logging in lands on *Wardrobe*; the header shows *Wardrobe* then *Garments*
- [ ] 3.9 A new outfit appears first in the grid after saving
- [ ] 3.10 Tiles for two-, three-, four- and seven-garment outfits each read as one square, with `+3` readable
- [ ] 3.11 A new account with no garments sees the "add at least 2 garments" state
- [ ] 3.12 At 360 px in headless Chromium the grid shows two tiles per row with no horizontal scrolling
- [ ] 3.13 Tapping a tile opens its detail page

### Phase 4: Pull request and production

#### Automated

- [ ] 4.1 The full suite passes on the rebased branch: `uv run pytest`
- [ ] 4.2 Nothing is left unmigrated after the rebase: `uv run python manage.py makemigrations --check --dry-run`
- [ ] 4.3 The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- [ ] 4.4 The PR against `master` exists and contains only this slice's commits: `gh pr view feat/compose-outfit --json baseRefName,commits`
- [ ] 4.5 The PR has no merge conflicts: `gh pr view feat/compose-outfit --json mergeable`
- [ ] 4.6 After merge, the deployment reaches a healthy state — `/health/` returns 200
- [ ] 4.7 After merge, deploy logs show `migrate` applying `outfits.0001_initial`

#### Manual

- [ ] 4.8 The developer reviews and merges the PR
- [ ] 4.9 Against production, composing an outfit and seeing it first in the wardrobe grid works end to end
- [ ] 4.10 A second production account sees an empty wardrobe, 404 on the first account's detail URL, and none of the first account's garments in its picker
- [ ] 4.11 Production wardrobe and compose pages at 360 px in headless Chromium show two tiles per row with no horizontal scrolling
