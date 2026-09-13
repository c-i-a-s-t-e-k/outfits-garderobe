# Outfit Tags and Wardrobe Filtering Implementation Plan

## Overview

A signed-in user tags outfits — while composing, or later on the outfit's page — removes tags there, sees each outfit's tags under its tile, and filters the wardrobe grid by one or more tags at once (an outfit must carry every selected tag). Tags are per user; `Letnie` and ` letnie ` are one tag that keeps the spelling it was first typed with. This is roadmap slice **S-05** (Jira OG-6), covering FR-009, FR-010 and US-02, and the last missing step of the PRD's primary success criterion.

## Current State Analysis

- **No tags exist anywhere.** `outfits.Outfit` (`outfits/models.py:37`) has `owner`, `name`, `garments` and `created_at`; the migration history is `outfits/migrations/0001_initial.py` only.
- **Rules live on the model, on every path.** `Outfit.save()` calls `full_clean()` (`outfits/models.py:80`); name uniqueness per owner is a database `UniqueConstraint(Lower('name'), 'owner')` (`outfits/models.py:64`); garment ownership on the many-to-many is an `m2m_changed` `pre_add` receiver (`outfits/signals.py:16`) connected in `OutfitsConfig.ready()` (`outfits/apps.py:8`).
- **Compose** is `OutfitForm(data=None, *, owner)` over `name` and `garments` (`outfits/forms.py:13`), stored by `_store_outfit()` inside `transaction.atomic()` with a savepoint around the row insert (`outfits/views.py:61`).
- **The outfit page is read-only** (`outfits/views.py:52`, `templates/outfits/detail.html`); there is no edit page until S-07.
- **The wardrobe grid** is `Outfit.objects.filter(owner=request.user).prefetch_related('garments')` (`outfits/views.py:23`); each tile is one `<a>` wrapping a preview and the name (`templates/outfits/wardrobe.html:27`).
- **UI conventions.** No JavaScript; Pico plus a deliberately small `static/css/app.css` whose tile grids share selectors (`static/css/app.css:59`). The UI is in English.
- **Test conventions.** `pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures('temp_media_root')]`; `owner` / `stranger` fixtures (`conftest.py:18`); `make_garment` helper (`outfits/tests/test_model.py:28`); every write test re-reads the database; query-count assertions with `CaptureQueriesContext` (`outfits/tests/test_views.py`).
- **Test plan.** Risk #6 (tag filter shows the wrong outfits) and Risk #2 (writes trusting a foreign id) apply directly. Rollout Phase 3, which formally covers #6, starts only after S-05 and S-06; this slice ships its own tests for its new behaviour.
- **Parallel work.** Worktree `/home/ciastek/Projects/.worktrees/testing-cross-user-privacy` (branch `feat/teasting-cross-user-privacy`, test-plan rollout Phase 1, not yet on `master`) adds `LoginRequiredMiddleware`, a route registry `tests/owner_scoped_routes.py`, and a test that fails when a guarded project route is not registered there. It also moves `make_garment` from `outfits/tests/test_model.py` to `tests/factories.py`. As of 2026-09-13 its phases 1–3 are committed (`93a0957`); only its documentation phase 4 remains. See Parallel Work & Delivery.

## Desired End State

On *Compose outfit* a user can type `Letnie, smart casual` in an optional *Tags* field; the outfit saves with both tags. On the outfit's page they see its tags as chips, each with a remove button, and an *Add tags* field that suggests their other tags. In the wardrobe, every tile shows its tags on one line under the name, and a tag bar above the grid lists their tags. Tapping `letnie` shows only outfits tagged `letnie` and shrinks the bar to the selected tag plus the tags those outfits also carry; tapping `smart casual` then shows only outfits carrying both; tapping a selected chip drops it; *All* clears the filter. Removing `letnie` from its last outfit removes it from the bar. A second account sees none of it, cannot attach or remove tags on the first account's outfits, and its own `letnie` is a different tag.

Verification: the automated suite proves tag identity, ownership, cleanup, the exact AND filter and constant query counts; headless Chromium at 360 px and a two-account production check confirm the UI and privacy.

### Key Discoveries:

- **SQLite's `LOWER()` and `LIKE` fold ASCII only.** Verified locally: `SELECT lower('ŚLUB')` returns `Ślub`, and `'ślub' LIKE 'ŚLUB'` is false. Django's SQLite backend maps `iexact` to `LIKE` (`django/db/backends/sqlite3/base.py:110`). A `Lower('name')` constraint or `name__iexact` lookup would therefore treat `Ślub`/`ślub` as two tags on the dev and test database but one on PostgreSQL. Tag identity must use a key computed in Python and compared exactly. (The existing outfit-name constraint has the same latent gap; not fixed here.)
- **`OutfitForm` is a `ModelForm` with `Meta.fields = ['name', 'garments']`.** A declared form field named `tags` would share its name with the new model relation. `_save_m2m()` skips it only because it is not in `Meta.fields`, which is a trap for the next edit. The form field gets a distinct name, `tag_names`.
- **Deleting an outfit removes its link rows by fast delete, with no `m2m_changed`.** Unused-tag cleanup needs an `Outfit` `post_delete` receiver as well as the `post_remove` / `post_clear` actions. By the time `post_delete` fires, the link rows are already gone.
- **A wardrobe tile is one `<a>`.** Tag chips inside it cannot be links (nested interactive content), so tile tags are plain text; the tag bar carries the links.
- **Tile tags are prefetched anyway**, so the tag bar can be derived in Python from the visible outfits' prefetched tags. That covers "only tags in use" and "only tags that narrow the current selection" with no extra query.

## What We're NOT Doing

- Renaming a tag, merging two tags, or a tag-management page.
- Treating separators as equal: `smart casual` and `smart-casual` stay two tags (decision).
- OR filtering, or saving a filter.
- The warning when deleting a tagged outfit, and editing an outfit's name or garments — S-07.
- The user's own outfit photo — S-04; garment delete and incomplete outfits — S-06.
- Fixing the ASCII-only case folding of outfit names on SQLite.
- Tag colours, counts per tag, or sorting the grid by tag.
- Updating `context/foundation/test-plan.md` §6 — its tag-filter cookbook entry belongs to rollout Phase 3.
- Real-phone checks — deferred to production use pre-MVP; headless Chromium at 360 px stands in.
- Translating the UI.

## Implementation Approach

1. **A `Tag` model in the `outfits` app** with `owner`, the display `name` and a `normalized` key computed in `clean()`. Uniqueness is `(owner, normalized)` in the database. `Outfit.tags` is a many-to-many to it.
2. **Model-level guards like the garment guard.** A `pre_add` receiver refuses another user's tag on either side of the relation. `post_remove` / `post_clear` and `Outfit` `post_delete` receivers delete the owner's tags that no outfit carries any more.
3. **One parsing and resolving path for both write surfaces.** A form field turns `"Letnie, , smart casual"` into cleaned, de-duplicated names. A model-level resolver maps names to the owner's existing tags by key, creating the missing ones race-safely. Compose and the outfit page both use them.
4. **Filtering by name in the query string.** `?tag=letnie&tag=smart casual`, with each value normalized and resolved against the requester's tags only. One filter per tag gives AND semantics, and an unresolvable value yields an empty grid.
5. **The bar is derived from what is on screen**, so it never offers a dead end.
6. **Pull request last**, rebased onto whatever the parallel privacy work has landed.

## Critical Implementation Details

**Normalization is Python, comparison is exact.** `Tag.normalize(text)` collapses whitespace runs, strips, then `casefold()`s. The display `name` keeps the whitespace-collapsed original. Every lookup, including the filter, compares `normalized=` or `normalized__in=` against the same function's output. Never use `iexact` or `Lower()` for tags (see Key Discoveries).

**First spelling wins, including under a race.** Resolving `letnie` when the owner already has `Letnie` returns the existing row unchanged. Creating a missing tag runs in its own savepoint. If it fails on the `(owner, normalized)` constraint (`IntegrityError`, or `ValidationError` from `full_clean()` when the other row committed first), fetch the row that won instead of erroring.

**Cleanup order in compose.** Tags are attached after `form.save_m2m()`, inside the same `_store_outfit()` transaction. A compose that fails validation never reaches the resolver, so it creates no tag rows.

## Parallel Work & Delivery

This slice is built in its own git worktree while the `testing-cross-user-privacy` slice continues in another, and it ships as a pull request.

- **Where the work happens.** Worktree `/home/ciastek/Projects/.worktrees/outfit-tags`, branch `feat/outfit-tags`, created from `master` at `cce90e9` plus this plan's commit. Every command in this plan runs from that worktree. Never `cd` to the main checkout `/home/ciastek/Projects/outfits-garderobe` or to the privacy worktree `/home/ciastek/Projects/.worktrees/testing-cross-user-privacy`.
- **Local state is per worktree.**
  - `db.sqlite3`, the dev `MEDIA_ROOT`, `.venv` and `staticfiles/` all live under the worktree root. Run `uv sync` first.
  - Before the first `uv run pytest`, run `DJANGO_SETTINGS_MODULE=outfits_garderobe.settings_test uv run python manage.py collectstatic --noinput`, and re-run it after changing anything under `static/`. Without the manifest, template-rendering tests fail with "Missing staticfiles manifest entry".
  - Tests need no secrets.
- **Secrets path.** From this worktree, CLAUDE.md's relative `../.secrets/outfits-garderobe/.env` does *not* resolve: it would point at `/home/ciastek/Projects/.worktrees/.secrets`. The file is `/home/ciastek/Projects/.secrets/outfits-garderobe/.env`. Pass that absolute path (e.g. `uv run --env-file /home/ciastek/Projects/.secrets/outfits-garderobe/.env python manage.py migrate`) for commands that load production-style settings. Never read the file.
- **Dev server.** Run `uv run python manage.py runserver 8002`, so it does not collide with the main checkout (8000) or the privacy worktree (8001). Headless Chromium checks target that port.
- **Git hygiene.** The stash stack is shared across worktrees: never use bare `git stash` / `git stash pop`; set work aside with a WIP commit. Commit per phase on `feat/outfit-tags` only.
- **Expected overlap with the privacy slice.** It adds no migrations, and its remaining phase touches only documentation (`tests/CLAUDE.md`, `context/foundation/test-plan.md` §6.1, `CLAUDE.md`). Once it reaches `master`, it changes three things for this slice:
  1. `make_garment` is imported from `tests.factories` instead of `outfits.tests.test_model`.
  2. `test_every_guarded_project_route_is_registered` fails until `outfits:tags_add` and `outfits:tag_remove` are in `tests/owner_scoped_routes.py`.
  3. `outfits/tests/test_views.py` and `outfits/tests/test_model.py` get one-line import conflicts.

  `LoginRequiredMiddleware` changes nothing here, because the new views are `@login_required`.
- **Sync points.**
  - *Phase 1* does not depend on the privacy slice and starts immediately.
  - *At the start of Phase 2*, if `feat/teasting-cross-user-privacy` has merged into `origin/master`, rebase onto it and apply Phase 2's "Privacy slice sync" change there.
  - If it has not merged, Phase 2 proceeds without it, and Phase 4's rebase applies the same change instead.
- **Delivery.** No direct push to `master`. Phase 4 rebases onto `origin/master`, pushes `feat/outfit-tags` and opens a PR with `gh pr create`. Production deploys when the developer merges it. The worktree can be removed after production verification (`git worktree remove`, run by the developer from the main checkout).

## Phase 1: `Tag` model and rules

### Overview

Add the `Tag` model, the `Outfit.tags` relation, the ownership guard, unused-tag cleanup, the name resolver, the migration and admin. No user-visible change.

### Changes Required:

#### 1. The model

**File**: `outfits/models.py`

**Intent**: One user's label for outfits: the spelling they first typed, and a key that makes case and whitespace variants the same tag on SQLite and PostgreSQL alike.

**Contract**:
- `Tag`: `id` UUID primary key (as `Outfit`); `owner` FK to `settings.AUTH_USER_MODEL`, `CASCADE`, `related_name='tags'`; `name` `CharField(max_length=30)`; `normalized` `CharField(max_length=30, editable=False)`; `created_at` `DateTimeField(auto_now_add=True)`.
- `Meta`: `ordering = ['normalized']`; `UniqueConstraint('owner', 'normalized', name='tag_unique_per_owner')` with a readable `violation_error_message`; `CheckConstraint` `tag_name_not_empty` — `normalized` is not `''`.
- `MAX_LENGTH = 30`, `MAX_PER_OUTFIT = 20` as class constants.
- `Tag.normalize(text)` (staticmethod): `' '.join(text.split()).casefold()`.
- `clean()`: collapse whitespace in `name`; set `normalized = Tag.normalize(name)`; a comma in `name` is a `ValidationError` (commas separate tags in every input). `save()` calls `full_clean()` first, with the same reasoning comment as `Outfit.save()`.
- `Tag.resolve(owner, names)` (classmethod): for a list of already-cleaned names, returns the owner's tags in input order, reusing existing rows by `normalized` (their `name` untouched) and creating missing ones race-safely (see Critical Implementation Details). One query to read the existing ones, plus one insert per new tag.
- `__str__` returns `name`.
- `Outfit.tags`: `ManyToManyField(Tag, related_name='outfits', blank=True)`.

#### 2. Guards and cleanup

**File**: `outfits/signals.py`

**Intent**: Make it impossible, on any ORM or admin path, to put another user's tag on an outfit, and keep a user's tag list equal to the tags their outfits actually carry.

**Contract**:
- `m2m_changed` on `Outfit.tags.through`, `pre_add`: forward (instance is an `Outfit`) raises `ValidationError` if any tag in `pk_set` has another owner; reverse (instance is a `Tag`) raises if any outfit in `pk_set` has another owner. Same shape as `refuse_foreign_garments`.
- `m2m_changed` on `Outfit.tags.through`, `post_remove` and `post_clear`: delete the affected owner's tags that no outfit carries (`Tag.objects.filter(owner_id=…, outfits__isnull=True).delete()`).
- `post_delete` on `Outfit`: the same cleanup for `instance.owner_id`.
- Module docstring updated to describe both relations.

#### 3. Migration

**File**: `outfits/migrations/0002_*.py`

**Intent**: Create the tag table, the link table and both constraints.

**Contract**: Generated with `uv run python manage.py makemigrations outfits`; no data migration.

#### 4. Admin

**File**: `outfits/admin.py`

**Intent**: Staff-only inspection that never lists every user's tags in a picker.

**Contract**: `TagAdmin` with `list_display` of name, owner, created time; `list_filter` on owner; `list_select_related = ('owner',)`; `created_at` read-only. `OutfitAdmin.raw_id_fields` gains `'tags'`.

#### 5. Tests

**File**: `outfits/tests/test_tags_model.py` (new)

**Intent**: Pin tag identity, ownership and cleanup, with expected values taken from the decisions in this plan.

**Contract**: Garments come from `make_garment`: import it from `tests.factories` when that module exists on the branch, otherwise from `outfits.tests.test_model`. Cases:
- `'  Letnie   wieczory '` is stored as name `'Letnie wieczory'`, normalized `'letnie wieczory'`
- a second owner tag `'LETNIE wieczory'` is rejected; the same name for `stranger` saves
- `'Ślub'` then `'ślub'` for one owner is rejected — this runs on SQLite and must pass there
- `'smart casual'` and `'smart-casual'` both save as separate tags
- a name with a comma is rejected; a whitespace-only name is rejected; a 31-character name is rejected
- database backstops: `QuerySet.update()` setting a duplicate `normalized` raises `IntegrityError`; setting `normalized=''` raises `IntegrityError`
- `Tag.resolve(owner, ['letnie', 'Nowy'])` with an existing `'Letnie'` returns `[<Letnie>, <Nowy>]`, keeps `'Letnie'` spelled as it was, and creates exactly one row
- `Tag.resolve` never returns or modifies `stranger`'s `'letnie'`
- when a concurrent insert is simulated (an existing row appears between the read and the create, e.g. by monkeypatching the read to return nothing once), `resolve` returns the existing row and raises nothing
- adding `stranger`'s tag to an owner's outfit raises `ValidationError` and leaves the link table unchanged; the same through `tag.outfits.add(outfit)`
- one tag on two of the owner's outfits: removing it from one keeps the tag; removing it from the second deletes the tag row
- `outfit.tags.clear()` deletes tags carried by no other outfit and keeps shared ones
- deleting an outfit deletes its now-unused tags, keeps tags another outfit still carries, and leaves `stranger`'s tags untouched
- deleting the owner removes their tags

### Success Criteria:

#### Automated Verification:

- The migration applies cleanly: `uv run python manage.py migrate`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- The tag model tests pass: `uv run pytest outfits/tests/test_tags_model.py`
- The full suite still passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- In `/admin/`, adding another user's tag id to an outfit is refused
- In `/admin/`, removing a tag from its only outfit makes it disappear from the tag list

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Tagging on compose and the outfit page

### Overview

Let the user tag an outfit while composing it, and add or remove tags on the outfit's page, with two-account tests proving neither write crosses users.

### Changes Required:

#### 0. Privacy slice sync (only if `feat/teasting-cross-user-privacy` has merged into `origin/master`)

**File**: none (rebase), then `outfits/tests/test_tags_model.py`, `tests/owner_scoped_routes.py`

**Intent**: Pick up the privacy net before adding the two new write routes, so they land already under its contract instead of being fixed up at PR time.

**Contract**:
- `git fetch origin`; if `git merge-base --is-ancestor origin/feat/teasting-cross-user-privacy origin/master` holds (or the PR shows as merged), `git rebase origin/master`. Resolve the import conflicts, then run the full suite and `makemigrations --check`.
- Phase 1's tests import `make_garment` from `tests.factories`.
- When routes are added in change 3 below, register them as described in Phase 4 change 2 in the same phase. That step then becomes a no-op check in Phase 4.
- If the privacy slice has not merged, skip this change; Phase 4 does it.

#### 1. Tag input field and forms

**File**: `outfits/forms.py`

**Intent**: One parsing rule for every place tags are typed, and forms that refuse what the model would refuse, as field errors the user can act on.

**Contract**:
- `TagNamesField(forms.CharField)`: `required=False`, generous `max_length` (e.g. 700). `to_python` / `clean` return a list of names: split on commas, collapse whitespace in each piece, drop empty pieces, de-duplicate by `Tag.normalize` keeping the first spelling in the input. Any name longer than `Tag.MAX_LENGTH` raises "Tags are at most 30 characters.". More than `Tag.MAX_PER_OUTFIT` names raises "An outfit can have at most 20 tags.". Help text: "Separate tags with commas.".
- `OutfitForm` gains a declared `tag_names = TagNamesField(label='Tags (optional)')`. It is not in `Meta.fields` (see Key Discoveries).
- `AddTagsForm(forms.Form)` with `tag_names = TagNamesField(required=True, label='Add tags')`, constructed as `AddTagsForm(data=None, *, outfit)`. `clean_tag_names()` fails with the 20-tag message when the outfit's existing tags plus the new, not-yet-carried names exceed `Tag.MAX_PER_OUTFIT`.

#### 2. Views

**File**: `outfits/views.py`

**Intent**: Store tags with the outfit or not at all, and give the owner, and only the owner, add and remove actions on the outfit page.

**Contract**:
- `_store_outfit(form)`: after `form.save_m2m()`, `outfit.tags.set(Tag.resolve(outfit.owner, form.cleaned_data['tag_names']))` inside the same transaction.
- `outfit_detail`: also prefetches `tags`. It renders an unbound `AddTagsForm` and a `suggested_tags` list — the owner's tags carried by at least one outfit and not already on this one. That list feeds a `<datalist>`.
- `outfit_tags_add` (`@login_required`, `@require_POST`): `get_object_or_404(Outfit, pk=pk, owner=request.user)`. Valid → `outfit.tags.add(*Tag.resolve(request.user, names))` in a transaction, `messages.success(request, 'Tags added.')`, redirect to the outfit page. Invalid → re-render `outfits/detail.html` with status 200, the bound form and its errors.
- `outfit_tag_remove` (`@login_required`, `@require_POST`): `outfit = get_object_or_404(Outfit, pk=pk, owner=request.user)`; `tag = get_object_or_404(outfit.tags, pk=tag_pk)`. Another user's outfit, another user's tag, and an own tag not on this outfit are all the same 404. Then `outfit.tags.remove(tag)`, `messages.success(request, 'Tag removed.')`, redirect to the outfit page.

#### 3. URLs

**File**: `outfits/urls.py`

**Intent**: Two POST-only actions under the outfit's own URL.

**Contract**: `'<uuid:pk>/tags/add/'` → `outfit_tags_add` named `tags_add`; `'<uuid:pk>/tags/<uuid:tag_pk>/remove/'` → `outfit_tag_remove` named `tag_remove`.

#### 4. Templates

**File**: `templates/outfits/compose.html`, `templates/outfits/detail.html`

**Intent**: Tag entry that works with a thumb and no JavaScript.

**Contract**:
- `compose.html`: the `tag_names` field with label, help text and errors, between the name field and the picker. A re-render keeps the typed text.
- `detail.html`: under the date, a `<ul class="tag-list">` of the outfit's tags. Each item has the tag name as a link to `{% url 'wardrobe' %}?tag=<name>` (URL-encoded) and a POST form to `outfits:tag_remove` with `{% csrf_token %}` and a small button with `aria-label="Remove tag <name>"`. When there are no tags, the list is replaced by a short "No tags yet." line. Below it, a POST form to `outfits:tags_add` with the `tag_names` input bound to `<datalist id="tag-suggestions">` of `suggested_tags`, its errors, and an *Add* button.

#### 5. Styles

**File**: `static/css/app.css`

**Intent**: Chips that wrap at 360 px, nothing more.

**Contract**: `.tag-list` is a wrapping flex row without bullets. A chip is a small rounded inline element with its remove button inline. Pico's full-width form controls and bottom margins are neutralized inside `.tag-list` only, in the same style as `.site-header nav form`. These chip rules will be shared with the tag bar in Phase 3.

#### 6. Tests

**File**: `outfits/tests/test_views.py`

**Intent**: Prove through HTTP that tags are stored with the right outfit and owner, and that no tag write crosses users. Every assertion re-reads the database.

**Contract**: Cases:
- compose with `tag_names='Letnie, smart casual'` stores an outfit carrying exactly tags named `Letnie` and `smart casual`
- with the owner already having `LETNIE`, compose with `letnie` attaches that existing tag, still named `LETNIE`, and creates no new tag row
- with `stranger` having `letnie`, the owner's compose with `letnie` creates the owner's own tag; `stranger`'s tag has no new outfits
- compose with one garment and `tag_names='Nowy'` returns 200 and creates neither an outfit nor a tag; the re-render keeps `Nowy` in the field
- compose with 21 distinct tags, or one 31-character tag, returns 200 with a `tag_names` error and stores nothing
- detail for the owner lists each tag with a remove form; the datalist offers the owner's other in-use tags and none of `stranger`'s
- add POST `'Nowy, letnie'` on the owner's outfit attaches both (reusing the existing `letnie`) and redirects to the outfit page
- add POST that would take the outfit past 20 tags returns 200 with an error and attaches nothing
- add POST by the owner to `stranger`'s outfit returns 404; `stranger`'s outfit tags are unchanged and no tag row is created
- remove POST of an own tag detaches it, and the tag row is gone when no other outfit carries it
- remove POST on `stranger`'s outfit with `stranger`'s tag id returns 404; the link still exists
- remove POST on the owner's own outfit with `stranger`'s tag id returns 404; `stranger`'s link still exists
- remove POST with an own tag that is not on this outfit returns 404 and changes nothing
- GET to either action returns 405; anonymous POST to either is sent to `settings.LOGIN_URL` and changes nothing
- detail query count is the same for an outfit with one tag as for one with eight

### Success Criteria:

#### Automated Verification:

- The view tests pass: `uv run pytest outfits/tests/test_views.py`
- If the privacy net is on the branch, it covers the new routes: `uv run pytest tests/`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- Composing with `Letnie, smart casual` shows both chips on the new outfit's page
- On the outfit page, adding `letnie` to a second outfit offers `Letnie` in the suggestions and keeps that spelling
- Removing a chip removes it after the redirect, with "Tag removed."
- At 360 px in headless Chromium, chips wrap, the remove buttons are tappable, and nothing scrolls horizontally

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Wardrobe filter bar and tile tags

### Overview

Filter the wardrobe grid by every selected tag, show a bar that only offers tags that narrow the current view, and show each outfit's tags under its tile.

### Changes Required:

#### 1. The grid view

**File**: `outfits/views.py`

**Intent**: Show exactly the requester's outfits carrying every selected tag, at a query count that does not grow with outfits, tags or selections.

**Contract**:
- Read `request.GET.getlist('tag')`, normalize each value with `Tag.normalize`, drop empties and duplicates.
- Resolve with one query: `Tag.objects.filter(owner=request.user, normalized__in=keys)`. If any key does not resolve, the result is an empty grid. The unresolved key still counts as selected, so the user can drop it.
- Outfits: `Outfit.objects.filter(owner=request.user)`, then one `.filter(tags=tag)` per resolved tag (AND), with `prefetch_related('garments', 'tags')`.
- Bar, computed in Python from the prefetched tags of the outfits on screen:
  - `selected`: the selected tags, in selection order, each with a URL that drops it. Unresolved values show as typed.
  - `available`: every distinct tag on the visible outfits that is not selected, ordered by `normalized`, each with a URL that adds it.
  - With no selection this is every tag the user has in use.
  - Build URLs with `urlencode(..., doseq=True)` on `reverse('wardrobe')`.
- Context adds `selected`, `available`, and `filtering` (whether any `tag` value was given).

#### 2. The grid template

**File**: `templates/outfits/wardrobe.html`

**Intent**: A filter bar that fits a phone and tiles that show their tags without breaking the square layout.

**Contract**:
- A `<nav class="tag-bar" aria-label="Filter by tag">` above the grid, rendered when there is anything to list or `filtering` is on. It contains an *All* link to `wardrobe`, marked `aria-current="page"` when not filtering, then the selected chips (styled as selected, `aria-pressed`-like wording in `aria-label`: "Remove filter <name>"), then the available chips.
- Each tile's `<a>` gains, after the name, a `<span class="outfit-tags">` listing the outfit's tags as plain text separated by `·`. It is not rendered when there are none.
- Empty state while filtering: "No outfits have all these tags." with a link to `wardrobe` labelled "Show all outfits". The existing empty states stay for the unfiltered page.

#### 3. Styles

**File**: `static/css/app.css`

**Intent**: A bar of wrapping chips and a one-line tag caption.

**Contract**:
- `.tag-bar` reuses the Phase 2 chip rules; a selected chip uses `--pico-primary` background with readable contrast.
- `.outfit-tags` is one line (`white-space: nowrap; overflow: hidden; text-overflow: ellipsis`), smaller and muted, so tiles in one row stay the same height at two per row.

#### 4. Tests

**File**: `outfits/tests/test_views.py`

**Intent**: Prove the filter returns exactly the right own outfits (test-plan Risk #6), the bar never offers a dead end or a foreign tag, and query counts are constant. Expected outfit sets are written out by hand from the fixture, never computed with the view's query.

**Contract**: Fixture: owner outfits A `{letnie}`, B `{Letnie → same tag, smart casual}`, C `{smart casual, zimowe}`, D `{}`; `stranger` outfit S `{letnie}`. Cases:
- every tile shows its own tags' names; D's tile has no `outfit-tags`; no page shows `stranger`'s outfit or tag
- `?tag=letnie` shows exactly A and B; `?tag=LETNIE` and `?tag=%20letnie%20` show the same
- `?tag=letnie&tag=smart%20casual` shows exactly B
- `?tag=letnie&tag=Letnie` is treated as one selection and shows A and B
- `?tag=smart-casual` shows no outfits and "No outfits have all these tags."
- `?tag=letnie&tag=nonexistent` shows no outfits; the bar lists `nonexistent` as a selected chip whose link leads to `?tag=letnie`
- for `stranger`, `?tag=letnie` shows exactly S, and the owner's A and B never appear
- unfiltered bar lists exactly `Letnie`, `smart casual`, `zimowe` — each once, alphabetically by key — and nothing of `stranger`'s
- with `?tag=letnie` the bar shows `Letnie` as selected and offers only `smart casual` (from B); `zimowe` is absent
- a chip's link adds its tag to the current selection; a selected chip's link removes only that tag
- after removing `letnie` from A and B through the Phase 2 remove action, `?tag=letnie` shows no outfits and the unfiltered bar no longer lists it
- the grid's query count is the same for one outfit with one tag as for five outfits with three tags each, both unfiltered and with two tags selected

### Success Criteria:

#### Automated Verification:

- The view tests pass: `uv run pytest outfits/tests/test_views.py`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- Tapping a chip filters the grid; tapping a second narrows to outfits with both; tapping a selected chip widens again; *All* clears
- With one tag selected, the bar offers only tags that keep at least one outfit on screen
- Tiles show their tags on one line with an ellipsis when long, and tiles in a row stay the same height
- At 360 px in headless Chromium, the bar wraps, the grid shows two tiles per row, and nothing scrolls horizontally

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Pull request and production

### Overview

Bring `feat/outfit-tags` up to date with `master`, put the new routes under the privacy contract if it has landed, open a pull request, and verify production after the developer merges.

### Changes Required:

#### 1. Base branch check

**File**: none — an operation

**Intent**: The PR carries only this slice's commits and passes against whatever `master` holds now.

**Contract**: `git fetch origin`, then `git log --oneline origin/master..HEAD`. If commits that are not this slice's appear, stop and ask the developer. Then `git rebase origin/master`. Resolve conflicts narrowly in `outfits/views.py`, `outfits/urls.py`, `outfits/tests/test_views.py`, `outfits/tests/test_model.py`, `outfits/tests/test_tags_model.py` (the `make_garment` import), `tests/owner_scoped_routes.py`, `static/css/app.css`, `templates/outfits/*`, `context/foundation/roadmap.md`. Re-run the full suite and `makemigrations --check`.

#### 2. Privacy contract registration (only if `tests/owner_scoped_routes.py` exists after the rebase and Phase 2 change 0 did not already do it)

**File**: `tests/owner_scoped_routes.py`

**Intent**: Keep the route-enumerating net green and make it cover the two new write routes and tag leaks on read pages.

**Contract**:
- Register `outfits:tags_add` and `outfits:tag_remove` as `kind='write'`, `shows_photos=False`. Seeds give the seeded user's outfit pk (and, for remove, a tag on it). The `foreign_payload` posts `tag_names` for add and nothing extra for remove.
- Give the shared wardrobe seed one tag whose name carries the username, and add it to the markers, so the existing read scenarios also catch a tag leak on the grid and the outfit page.
- If a `LoginRequiredMiddleware` is present, nothing else changes: the new views are already `@login_required`.

If the file does not exist, skip this step and note in the PR body that the privacy branch will need these registrations when it rebases.

#### 3. Pull request

**File**: none — an operation

**Intent**: Deliver for review; nothing reaches `master` without the developer's merge.

**Contract**: `git push -u origin feat/outfit-tags` (with `--force-with-lease` only if the rebase rewrote pushed commits), then `gh pr create --base master --head feat/outfit-tags`. Title: `feat(outfit-tags): tag outfits and filter the wardrobe (S-05, OG-6)`. Body:
- a summary lifted from `plan-brief.md`
- the phases
- the test commands run
- manual checks done and those pending after merge
- links to `plan.md` and Jira OG-6
- a note that merging deploys to Railway with migration `outfits.0002_*`

Never merge the PR.

#### 4. Change record

**File**: `context/changes/outfit-tags/change.md`

**Intent**: Record what production verification found.

**Contract**: A dated "Production deploy" note in `## Notes` with the PR URL, merge commit, deployment id, checks run and deviations from this plan. It lands through a small follow-up PR (it can ride with `/10x-archive`), never straight onto `master`.

### Success Criteria:

#### Automated Verification:

- The full suite passes on the rebased branch: `uv run pytest`
- Nothing is left unmigrated after the rebase: `uv run python manage.py makemigrations --check --dry-run`
- The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- The PR against `master` exists and contains only this slice's commits: `gh pr view feat/outfit-tags --json baseRefName,commits`
- The PR has no merge conflicts: `gh pr view feat/outfit-tags --json mergeable`
- The Railway PR environment build (the PR status check) is green
- After merge, the deployment reaches a healthy state — `/health/` returns 200
- After merge, deploy logs show `migrate` applying `outfits.0002_*`

#### Manual Verification:

- The developer reviews and merges the PR
- Against production, tagging an outfit at compose, adding and removing a tag on its page, and filtering by two tags works end to end
- A second production account with its own `letnie` tag sees only its own outfits under `?tag=letnie`, gets 404 on the first account's outfit page, and sees none of the first account's tags in its bar
- The production wardrobe with a tag selected, at 360 px in headless Chromium, wraps the bar and shows two tiles per row with no horizontal scrolling

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- Tag identity: whitespace and case (including non-ASCII `Ś`/`ś` on SQLite), separators stay distinct, first spelling wins, both database constraints
- The resolver: reuse, creation, race fallback, owner scope
- Ownership guard on both sides of `Outfit.tags`
- Unused-tag cleanup on remove, clear and outfit delete, scoped to the owner

### Integration Tests:

- Compose with tags: stored with the outfit, nothing stored on failure, limits enforced
- Add/remove on the outfit page: foreign outfit and foreign tag ids give 404 and change nothing (test-plan Risk #2)
- The AND filter returns hand-written expected sets, including case variants, unknown tags and another user's same-named tag (test-plan Risk #6)
- The bar offers only narrowing, own, in-use tags
- Constant query counts for detail and grid

### Manual Testing Steps:

1. Compose an outfit with `Letnie, smart casual` → both chips on its page.
2. On a second outfit, add `letnie` → the suggestion shows `Letnie`, and the chip keeps that spelling.
3. Wardrobe → tap `Letnie` → both outfits; tap `smart casual` → only the first; tap selected `Letnie` → back to the `smart casual` outfits; *All* → everything.
4. Remove `Letnie` from both outfits → it is gone from the bar.
5. Second account → its own `letnie` shows only its own outfits; 404 on the first account's outfit page.
6. Headless Chromium at 360 px on compose, outfit page and the filtered wardrobe.

## Performance Considerations

- **Grid:** one query to resolve selected tags (skipped without a filter), one for outfits (a join per selected tag), and one prefetch each for garments and tags. The bar is computed in Python from the prefetched tags.
- **Outfit page:** the outfit with prefetched garments and tags, plus one query for suggestions.
- **Writes:** one read of existing tags per resolve, one insert per new tag, one ownership check per add, and one cleanup delete per remove.
- An index on `(owner, normalized)` comes with the unique constraint; the filter's joins go through the link table's indexed foreign keys.

## Migration Notes

- `outfits.0002_*` adds `outfits_tag` (unique `(owner, normalized)`, non-empty check) and `outfits_outfit_tags`; existing tables and data are untouched.
- Rollback: reverting the code leaves unused tables; `migrate outfits 0001` removes them. Outfits, garments and photos are unaffected.

## References

- Roadmap item: `context/foundation/roadmap.md` — S-05 (`outfit-tags`), Jira OG-6
- PRD: `context/foundation/prd.md` — FR-009, FR-010, US-02, NFR *Prywatność*, *Responsywność*
- Test plan: `context/foundation/test-plan.md` — Risks #2 and #6
- Prior plan and patterns: `context/changes/compose-outfit/plan.md`; `outfits/models.py:37`, `outfits/signals.py:16`, `outfits/forms.py:13`, `outfits/views.py:61`
- Parallel privacy net: branch `feat/teasting-cross-user-privacy`, `tests/owner_scoped_routes.py`, plan `context/changes/testing-cross-user-privacy/plan.md` (on that branch)
- Worktree: `/home/ciastek/Projects/.worktrees/outfit-tags`
- Django SQLite `iexact`: `django/db/backends/sqlite3/base.py:110`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: `Tag` model and rules

#### Automated

- [x] 1.1 The migration applies cleanly: `uv run python manage.py migrate` — 708195d
- [x] 1.2 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run` — 708195d
- [x] 1.3 The tag model tests pass: `uv run pytest outfits/tests/test_tags_model.py` — 708195d
- [x] 1.4 The full suite still passes: `uv run pytest` — 708195d
- [x] 1.5 System checks pass: `uv run python manage.py check` — 708195d
- [x] 1.6 Linting passes: `uv run ruff check .` — 708195d
- [x] 1.7 Formatting is clean: `uv run ruff format --check .` — 708195d

#### Manual

- [x] 1.8 In `/admin/`, adding another user's tag id to an outfit is refused — 708195d
- [x] 1.9 In `/admin/`, removing a tag from its only outfit makes it disappear from the tag list — 708195d

### Phase 2: Tagging on compose and the outfit page

#### Automated

- [x] 2.1 The view tests pass: `uv run pytest outfits/tests/test_views.py` — e1da981
- [x] 2.2 If the privacy net is on the branch, it covers the new routes: `uv run pytest tests/` — e1da981
- [x] 2.3 The full suite passes: `uv run pytest` — e1da981
- [x] 2.4 System checks pass: `uv run python manage.py check` — e1da981
- [x] 2.5 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run` — e1da981
- [x] 2.6 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput` — e1da981
- [x] 2.7 Linting passes: `uv run ruff check .` — e1da981
- [x] 2.8 Formatting is clean: `uv run ruff format --check .` — e1da981

#### Manual

- [x] 2.9 Composing with `Letnie, smart casual` shows both chips on the new outfit's page — e1da981
- [x] 2.10 On the outfit page, adding `letnie` to a second outfit offers `Letnie` in the suggestions and keeps that spelling — e1da981
- [x] 2.11 Removing a chip removes it after the redirect, with "Tag removed." — e1da981
- [x] 2.12 At 360 px in headless Chromium, chips wrap, the remove buttons are tappable, and nothing scrolls horizontally — e1da981

### Phase 3: Wardrobe filter bar and tile tags

#### Automated

- [x] 3.1 The view tests pass: `uv run pytest outfits/tests/test_views.py` — 61f02e6
- [x] 3.2 The full suite passes: `uv run pytest` — 61f02e6
- [x] 3.3 System checks pass: `uv run python manage.py check` — 61f02e6
- [x] 3.4 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput` — 61f02e6
- [x] 3.5 Linting passes: `uv run ruff check .` — 61f02e6
- [x] 3.6 Formatting is clean: `uv run ruff format --check .` — 61f02e6

#### Manual

- [x] 3.7 Tapping a chip filters the grid; a second narrows to outfits with both; a selected chip widens again; *All* clears — 61f02e6
- [x] 3.8 With one tag selected, the bar offers only tags that keep at least one outfit on screen — 61f02e6
- [x] 3.9 Tiles show their tags on one line with an ellipsis when long, and tiles in a row stay the same height — 61f02e6
- [x] 3.10 At 360 px in headless Chromium, the bar wraps, the grid shows two tiles per row, and nothing scrolls horizontally — 61f02e6

### Phase 4: Pull request and production

#### Automated

- [x] 4.1 The full suite passes on the rebased branch: `uv run pytest`
- [x] 4.2 Nothing is left unmigrated after the rebase: `uv run python manage.py makemigrations --check --dry-run`
- [x] 4.3 The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- [ ] 4.4 The PR against `master` exists and contains only this slice's commits: `gh pr view feat/outfit-tags --json baseRefName,commits`
- [ ] 4.5 The PR has no merge conflicts: `gh pr view feat/outfit-tags --json mergeable`
- [ ] 4.6 The Railway PR environment build (the PR status check) is green
- [ ] 4.7 After merge, the deployment reaches a healthy state — `/health/` returns 200
- [ ] 4.8 After merge, deploy logs show `migrate` applying `outfits.0002_*`

#### Manual

- [ ] 4.9 The developer reviews and merges the PR
- [ ] 4.10 Against production, tagging at compose, adding and removing a tag on the outfit page, and filtering by two tags works end to end
- [ ] 4.11 A second production account with its own `letnie` sees only its own outfits under `?tag=letnie`, 404 on the first account's outfit page, and none of the first account's tags
- [ ] 4.12 The production wardrobe with a tag selected, at 360 px in headless Chromium, wraps the bar and shows two tiles per row with no horizontal scrolling
