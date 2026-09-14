# Garment Lifecycle Implementation Plan

## Overview

A signed-in user can edit a garment, including replacing its photo, and delete it. Every outfit that used a deleted garment survives with its remaining garments and records what went missing. In the wardrobe grid the outfit carries an *Incomplete* badge, and a banner above the grid links to a view of just those outfits. On the outfit's page each missing garment offers three ways out:

- *Replace* picks one of the owner's other garments, with garments of the same type listed first;
- *Keep without it* closes that gap and adds nothing;
- *Delete outfit* removes the whole outfit.

To make those repairs possible, this slice also builds full outfit edit (name and garments) and outfit delete, with a warning when the outfit is tagged. This is roadmap slice **S-06** (Jira OG-7), covering FR-004 and US-01. It also delivers the edit and delete that FR-006 asks for, so its close-out marks roadmap S-07 (`outfit-lifecycle`, Jira OG-8) done as well: research found no scope left for a separate slice (`context/changes/outfit-lifecycle/research.md`, decision 2026-09-14).

## Current State Analysis

The research is `context/changes/garment-lifecycle/research.md` at `787aa1f`. This plan builds on master **after S-04 (`outfit-photo`) merges**. The branch `feat/garment-lifecycle` already exists, cut from `787aa1f` (before S-04) and carrying only the planning commit, so Phase 0 merges `origin/master` into it once S-04 has landed. Every S-04 fact below comes from S-04's plan and its in-progress worktree, and Phase 0 checks it against the merged code. Line references are at `787aa1f` and shift after that merge.

- **Nothing edits or deletes a garment.** `garments/urls.py` has only `list` and `add`. List tiles are `<figure>`s, not links (`templates/garments/list.html`). `GarmentForm` requires a photo (`garments/forms.py`). After S-04 the photo field and `clean_photo()` come from `NormalizedPhotoMixin` (`privatemedia/forms.py`), and that `clean_photo()` does not handle an empty upload.
- **Deleting a garment leaves no trace.** Django deletes its `outfits_outfit_garments` rows without `m2m_changed`. Only `pre_delete`/`post_delete` on `Garment` fire, and they fire for `QuerySet.delete()` and for the cascade from account deletion too. Inside `pre_delete`, `instance.outfits` is still readable. The garment's `PrivateImage` row and file stay behind (research §3).
- **Incompleteness cannot be derived afterwards.** It has to be written when the garment is deleted.
- **Outfits have create only.** `OutfitForm(data=None, *, owner)` builds a new instance, requires ≥ 2 garments (`MIN_GARMENTS`), and carries `tag_names`. `_store_outfit` retries an auto-assigned name once after a race and always sets tags. No outfit delete exists. Tag cleanup after an outfit delete already works (`outfits/signals.py`, `post_delete`).
- **S-04 provides the file primitives.** `discard_private_image(image)` (`privatemedia/models.py`) deletes the row now and the file on commit, after the caller has unlinked any `RESTRICT` relation. `Outfit.photo` is a `OneToOneField(PrivateImage, RESTRICT, null=True)`. S-04 also brings migration `outfits.0003_outfit_photo`, portrait tiles where a photo tile hides the collage, `data-submit-once` in `photo-shrink.js`, and a *Photo* section on the outfit page. `_seed_wardrobe` then seeds `outfits[0]` (tagged, with a photo) and `outfits[1]` (no photo). Compose redirects to the new outfit's page.
- **Privacy contract.** Every guarded route must be registered in `tests/owner_scoped_routes.py`. Owner-scoped models are listed in `snapshot_of` (`tests/foreign_id_writes/conftest.py`), `OWNED_MODELS` (`test_write_aimed_at_another_users_objects_changes_nothing.py:25`) and `_row_counts` (`test_anonymous_visitor_only_reaches_login.py:21`).
- **Query counts are pinned** for the garment list (`garments/tests/test_views.py:204`), the grid (`outfits/tests/test_views.py:374,817`), the detail page (`:623`) and the picker (`:98`).
- **Test plan Risk #5** requires proof that every outfit that used the garment still exists with its remaining garments and is flagged, that the grid shows the repair/delete affordance, that the garment's other outfits are affected the same way, and that other users are untouched (`context/foundation/test-plan.md:56,70`).

## Desired End State

A user taps a garment in their list and lands on its edit page. They change the description, optionally pick a new photo, and save. The old photo file is gone from the volume once the change is committed. *Delete garment* opens a confirmation page with the photo and the names of the outfits that will become incomplete. Confirming deletes the garment and its photo file.

In the wardrobe, each affected outfit's tile carries "Incomplete · 1 missing". The badge shows on collage tiles and photo tiles, filtered or not. A banner, "2 outfits need attention", links to `?incomplete=1`. The outfit page opens with a *Missing garments* section. It lists "Shoes — brown loafers", each with *Replace* (a picker of the owner's other garments, shoes first) and *Keep without it* (hidden when the outfit has no garments left), plus a link to *Delete outfit*. The page also offers *Edit outfit*: name and garments, at least one garment. The *Delete outfit* confirmation lists the outfit's tags when it has any and says its photo will be deleted. A second account gets 404 on every one of these pages and actions.

Verification: the automated suite proves the deletion rule at the model level, including the ORM, bulk delete and account-deletion paths. It also proves every new route through HTTP, the privacy contracts, file cleanup on commit, constant query counts, and the Risk #5 scenarios. Headless Chromium at 360 px and a two-account check on the Railway PR environment confirm the UI and privacy before merge.

### Key Discoveries:

- **A `pre_delete` receiver that inserts rows runs inside a cascade too.** When an account is deleted, each of its garments' `pre_delete` fires and writes `MissingGarment` rows for outfits that the same cascade is about to delete. This works only because `Collector.delete()` sends all `pre_delete` signals before it runs the fast deletes. `MissingGarment` has no receivers and no dependent relations, so its rows are removed with a query built from the doomed outfits' pks, evaluated after the inserts. Adding a signal receiver to `MissingGarment` later would turn that into an instance collection made *before* the inserts, and PostgreSQL would then refuse the outfit delete. A test pins this (Phase 1).
- **`bulk_create` skips `save()` and `full_clean()`.** That is fine for rows copied from a garment that was already valid. `auto_now_add` still applies.
- **`NormalizedPhotoMixin.clean_photo()` calls `validate_max_size(upload)` unconditionally.** An optional photo on the edit form needs its own `clean_photo()` that returns `None` for an empty upload before delegating.
- **Declaring `tag_names = None` on a form subclass removes the inherited declared field.** This is standard Django behaviour. The edit form can reuse `OutfitForm` without offering tags.
- **`_store_outfit` always calls `outfit.tags.set(...)`.** On an edit form without `tag_names`, that would clear the outfit's tags. The tag write must happen only when the form carries the field.
- **The views must resolve the owned object before binding a form.** S-04's foreign-write scenario posts a valid upload to the owner's URL. Checking ownership first means a stranger's request never decodes an image.
- **`transaction.on_commit` callbacks do not run inside pytest-django's test transaction.** File-deletion assertions need `django_capture_on_commit_callbacks(execute=True)`, as S-04 does.

## What We're NOT Doing

- Soft delete, undo or a trash for garments; deleting a garment is final after commit.
- Recording a missing slot when a garment is removed on purpose through *Edit outfit*. Only deleting a garment creates one.
- Adding garments through *Edit outfit* closes no missing slot. Only *Replace* and *Keep without it* close slots.
- Editing tags inside *Edit outfit*: tags stay on the outfit page.
- A confirmation checkbox or an outfit preview (photo or collage) on *Delete outfit*: the confirmation page with the outfit's name and the tag warning is the safeguard (developer's decision, `context/changes/outfit-lifecycle/research.md`, 2026-09-14).
- A separate plan for S-07. `/10x-plan outfit-lifecycle` is not run: this slice delivers FR-006, and Phase 5 closes S-07 and OG-8 together with S-06 and OG-7.
- Deleting photo files when a garment is deleted from the admin or the ORM, or when an account is deleted. Only the UI delete path discards the photo. The account-deletion gap already exists for garments and outfit photos.
- A backfill: no outfit can be marked incomplete for garments deleted before this ships, since nothing recorded them. No delete UI existed, so only the admin could have done it.
- Incomplete badges on the garment list, sorting incomplete outfits first, or notifications.
- Translating the UI, or real-phone checks outside the PR environment.

## Implementation Approach

0. **Start from S-04.** Wait until S-04 is merged into `master`, merge `origin/master` into this branch, and confirm that the S-04 primitives this plan relies on exist as described before writing any code.
1. **A tombstone per lost garment.** `MissingGarment` records the deleted garment's type, custom type name and description on each outfit that used it. It is written by a `Garment` `pre_delete` receiver, next to the other outfit rules in `outfits/signals.py`, so the view, the admin and the ORM all obey the rule. Ownership is read through the outfit: the model has no `owner` of its own to keep consistent.
2. **Garment edit and delete** follow S-04's order of operations. Resolve the owned garment, store the new image, point the garment at it, then discard the old image. To delete, capture the photo, delete the garment (the receiver writes the tombstones), then discard the photo.
3. **Outfit edit reuses `OutfitForm`** through an edit subclass: bound to an instance, ≥ 1 garment, no tags. The garment picker markup is extracted from `compose.html` and shared. **Outfit delete** is a confirmation page that also discards the S-04 photo.
4. **Repair lives on the outfit page.** The grid only signals and links there: a tile is one `<a>`, so it cannot hold actions. *Replace* is its own GET/POST page per slot. *Keep without it* is a POST-only action.
5. **The grid reads prefetched tombstones** for the badge and runs one count for the banner, so its query count stays constant.
6. **Pull request last,** verified on the Railway PR environment, with close-out in the same PR.

## Critical Implementation Details

**Order of operations on garment delete.** Inside one transaction: resolve the owned garment with its photo, keep a reference to the photo, then `garment.delete()`. The receiver writes the tombstones, and Django removes the link rows. Then `discard_private_image(photo)`. `Garment.photo` is `RESTRICT`, so discarding the image before the garment is gone is refused.

**Replace and dismiss under concurrency.** Both actions lock the tombstone row, `select_for_update()` looked up through `outfit.missing_garments`, inside a transaction. If the row is already gone (a second tab, a double tap), they redirect to the outfit page without a message and change nothing. That is the same stale-state rule S-04 uses for removing a photo that is already gone. A stranger still gets 404, because the outfit is resolved first.

## Parallel Work & Delivery

- **Prerequisite.** S-04 (`feat/outfit-photo`) is merged into `origin/master`. Phase 0 checks this and stops if it is not. S-04 is being implemented in parallel in `/home/ciastek/Projects/.worktrees/outfit-photo`. Never touch that worktree or its branch.
- **Where the work happens.** The worktree `/home/ciastek/Projects/.worktrees/garment-lifecycle` exists, on branch `feat/garment-lifecycle` cut from `787aa1f`. Its commits so far are docs only: the plan (`979ba62`, which includes the roadmap `planning` flip for S-06) and the plan-review commit Phase 0 makes. Phase 0 brings it up to date with a merge, never a rebase. Every command in this plan runs from the worktree. Never `cd` to the main checkout `/home/ciastek/Projects/outfits-garderobe`: it is on another branch with the developer's uncommitted work. `/10x-implement` sets S-06 to `in-progress` in the worktree.
- **Local state is per worktree.** Run `uv sync` first. Before the first `uv run pytest`, run `DJANGO_SETTINGS_MODULE=outfits_garderobe.settings_test uv run python manage.py collectstatic --noinput`. Re-run it after any change under `static/`. Tests need no secrets.
- **Secrets path.** The file is `/home/ciastek/Projects/.secrets/outfits-garderobe/.env` (absolute path, for `uv run --env-file …`). Never read it.
- **Dev server.** `uv run python manage.py runserver 8004`. Ports 8000–8003 belong to the main checkout and earlier worktrees.
- **Git hygiene.** Never use bare `git stash`, because the stash stack is shared across worktrees; use WIP commits instead. Commit per phase on `feat/garment-lifecycle`. Sync with `master` by merging `origin/master` (Phases 0 and 5), never by rebasing, so pushed history is never rewritten and no force-push is needed. Push with `git push -u origin feat/garment-lifecycle`.
- **Delivery.** No direct push to `master`. Phase 5 opens the PR, and every manual check runs against the Railway PR environment before the developer merges.

## Phase 0: Merge master after S-04

### Overview

Wait for S-04 to land on `master`, merge `origin/master` into `feat/garment-lifecycle`, and confirm that the merged S-04 code matches what this plan builds on. No application code changes.

### Changes Required:

#### 1. S-04 merge check

**File**: none — an operation

**Intent**: Nothing in this plan starts before S-04 is merged. Its migration, file helpers and templates are the base of Phases 1–4.

**Contract**:
- `git fetch origin`, then `git ls-tree origin/master outfits/migrations/ | grep 0003_outfit_photo`, and `gh pr list --state merged --head feat/outfit-photo`.
- If either shows S-04 is not merged, stop and tell the developer: "S-04 (`feat/outfit-photo`) is not merged into `master` yet; S-06 waits for it." Change nothing.

#### 2. Merge `origin/master`

**File**: none — an operation (a merge commit on `feat/garment-lifecycle`)

**Intent**: Bring S-04, and anything else merged since `787aa1f`, into this branch without rewriting the planning commit.

**Contract**:
- Pending edits under `context/changes/garment-lifecycle/` (the plan review of 2026-09-14, this Phase 0, the S-07 decision) are committed first as `docs(garment-lifecycle): plan review and Phase 0`. Any other uncommitted change: stop and ask. Never stash.
- The working tree is then clean (`git status --porcelain` is empty).
- Run `git merge origin/master` with the message `chore(garment-lifecycle): merge master after S-04 (p0)`.
- Conflicts:
  - The only expected one is in `context/foundation/roadmap.md`. Keep `master`'s version of every item, S-04 included, except S-06. S-06's At-a-glance row and item body keep this branch's status.
  - A conflict in `context/changes/garment-lifecycle/` or in any code file is not expected. Abort with `git merge --abort` and ask the developer.
- Do not push yet. Phase 5 pushes the branch.

#### 3. Local state on the merged branch

**File**: none — an operation

**Intent**: The worktree's venv, database and static files match the merged code before Phase 1 measures anything against them.

**Contract**: `uv sync`, `uv run python manage.py migrate`, then `DJANGO_SETTINGS_MODULE=outfits_garderobe.settings_test uv run python manage.py collectstatic --noinput`.

#### 4. S-04 contract check

**File**: `context/changes/garment-lifecycle/change.md` (a dated note), and this plan only if something deviates

**Intent**: Phases 1–4 name S-04 contracts taken from S-04's plan and its unmerged worktree. Confirm them in the merged code, so a deviation surfaces now and not halfway through a phase.

**Contract**: Confirm each of the following against the merged tree:
- `discard_private_image(image)` in `privatemedia/models.py` deletes the row now and the file on commit.
- `NormalizedPhotoMixin` in `privatemedia/forms.py` declares `photo`, and its `clean_photo()` calls `validate_max_size` unconditionally.
- `stored_private_image(owner, file, original_filename)` is a context manager.
- `Outfit.photo` is `OneToOneField(PrivateImage, RESTRICT, null=True)` with `photo_url`, in migration `outfits.0003_outfit_photo`, and it is the latest `outfits` migration.
- `make_outfit(..., photo=True)` exists in `tests/factories.py`.
- In `_seed_wardrobe`, `outfits[0]` is tagged and has a photo, and `outfits[1]` has no photo.
- `photo-shrink.js` honours `data-submit-once`, and compose redirects to the new outfit's page.
- The CSS rule `.outfit-photo img` exists.
- The outfit page has a *Photo* section. `_render_detail` takes `photo_form`.
- Wardrobe tiles render `.outfit-preview` for collages and `.outfit-preview outfit-preview-photo` for photo tiles, inside one `<a>`.
- The pinned query-count tests referenced by line in Phases 2–4 are found by name: the garment list, the grid (`test_grid_query_count_does_not_grow_with_outfits_tags_or_selections`), the detail page, the picker.

Record the result in `change.md` under a dated "Merged master after S-04" note, with the merge commit SHA. If a contract deviates, stop and ask the developer. Once agreed, update the affected phase's Contract in this plan.

### Success Criteria:

#### Automated Verification:

- S-04 is on `master`: `git ls-tree origin/master outfits/migrations/ | grep 0003_outfit_photo`
- The branch contains current `master`: `git merge-base --is-ancestor origin/master HEAD`
- The only non-merge commits ahead of `master` are docs commits touching `context/`: `git log --oneline --no-merges --stat origin/master..HEAD`
- Migrations apply cleanly: `uv run python manage.py migrate`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- The full suite passes on the merged branch: `uv run pytest`
- Linting passes: `uv run ruff check .`

#### Manual Verification:

- Every S-04 contract listed in change 4 is confirmed in the merged code, or its deviation is recorded in `change.md` and the plan was adjusted with the developer's agreement

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 1: Missing-garment record and deletion rule

### Overview

Add `MissingGarment`, the receiver that writes it whenever a garment is deleted, and its place in the privacy contracts. There is no user-visible change.

### Changes Required:

#### 1. The model

**File**: `outfits/models.py`

**Intent**: An outfit remembers each garment it lost, in enough detail to say what is missing and to suggest a replacement of the same kind.

**Contract**:
- `MissingGarment`:
  - `id` UUID pk;
  - `outfit` FK `Outfit`, `on_delete=CASCADE`, `related_name='missing_garments'`;
  - `type` (`GarmentType` choices), `type_other` (max 40, blank), `description` (max 200, blank), `removed_at` (`auto_now_add`);
  - `Meta.ordering = ['removed_at']`.
- `display_type` property with the same rule as `Garment.display_type`. `__str__` uses the same format as `Garment.__str__`.
- A docstring says that ownership is the outfit's, and why the model has no receivers (see Key Discoveries).
- `Outfit.is_incomplete` / `missing_count` helpers read `missing_garments.all()`, so a prefetch covers them.

#### 2. The deletion rule

**File**: `outfits/signals.py`

**Intent**: However a garment is deleted, every outfit that used it records the loss.

**Contract**:
- `@receiver(pre_delete, sender=Garment) record_missing_garment(sender, instance, **kwargs)` runs `bulk_create`: one `MissingGarment` per outfit in `instance.outfits.all()`, copying `type`, `type_other` and `description`.
- The module docstring gains a bullet for this rule and notes that the link rows are removed afterwards by Django itself.

#### 3. Migration and admin

**File**: `outfits/migrations/0004_missinggarment.py`, `outfits/admin.py`

**Intent**: The new table, and read-only visibility for staff.

**Contract**:
- Generate the migration with `uv run python manage.py makemigrations outfits`. It depends on `0003_outfit_photo`.
- `MissingGarmentInline(admin.TabularInline)` on `OutfitAdmin`, with every field read-only.

#### 4. Privacy contract model lists

**File**: `tests/foreign_id_writes/conftest.py`, `tests/foreign_id_writes/test_write_aimed_at_another_users_objects_changes_nothing.py`, `tests/cross_user_visibility/test_anonymous_visitor_only_reaches_login.py`

**Intent**: A foreign or anonymous write that creates, changes or deletes a tombstone shows up as a changed snapshot.

**Contract**:
- `snapshot_of` gains `'missing'`: `MissingGarment` rows filtered by `outfit__owner=user`, ordered by pk, as `.values()`.
- `OWNED_MODELS` and `_row_counts` gain `MissingGarment`.

#### 5. Tests

**File**: `outfits/tests/test_missing_garment_model.py` (new)

**Intent**: Pin the rule with values from the PRD and this plan, on every deletion path.

**Contract**:
- Setup: garments a (shoes, "brown loafers"), b and c. Outfit o1 = {a, b}, tagged. Outfit o2 = {a, c}. Outfit o3 = {b, c}.
- Deleting a leaves o1 and o2 in place with {b} and {c}, and o1's tag intact. Each has exactly one `MissingGarment` with type shoes, description "brown loafers" and `display_type` "Shoes". o3 has none.
- `Garment.objects.filter(pk__in=[a, b]).delete()` gives o1 two tombstones and o1 zero garments. o1 still exists.
- A garment in no outfit deletes with no tombstone.
- Deleting the owner (the `User` row) with garments in outfits succeeds. It leaves no `Outfit`, `Garment` or `MissingGarment` rows for that user, and `connection.check_constraints()` passes before the test ends.
- Deleting an outfit deletes its tombstones.
- The stranger's outfits and tombstones are unchanged by any of the above.
- Once prefetched, `missing_count` and `is_incomplete` make no query.

### Success Criteria:

#### Automated Verification:

- The migration applies cleanly: `uv run python manage.py migrate`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- Model tests pass: `uv run pytest outfits/tests/test_missing_garment_model.py`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- In `/admin/`, deleting a garment used by two outfits leaves both outfits with a read-only *Missing garment* inline row describing it

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Garment edit and delete

### Overview

The owner edits a garment, optionally replacing its photo, and deletes it after a confirmation page that names the outfits it will leave incomplete.

### Changes Required:

#### 1. Form

**File**: `garments/forms.py`

**Intent**: The same fields and rules as adding a garment, except that the photo is optional: no upload keeps the current one.

**Contract**:
- `GarmentEditForm(GarmentForm)`: `photo` is not required, and its label is "Replace photo (optional)".
- `clean_photo()` returns `None` for an empty upload and otherwise delegates to the mixin.
- `GarmentForm` itself is unchanged.

#### 2. Views

**File**: `garments/views.py`

**Intent**: Only the owner edits or deletes. A refused request stores nothing, and a retired photo's file disappears only once the change is committed.

**Contract**:
- A shared `_owned_garment(request, pk)` returns `get_object_or_404(Garment.objects.select_related('photo'), pk=pk, owner=request.user)`.
- `garment_edit(request, pk)`: GET and POST.
  - It resolves the owned garment first. Only then does it bind `GarmentEditForm(request.POST, request.FILES, instance=garment)`.
  - Invalid: re-render with 200.
  - Valid with no photo: save.
  - Valid with a photo: inside one transaction, `select_for_update` the garment, store the new image through `stored_private_image`, point `garment.photo` at it, save, then `discard_private_image(old)`.
  - Success shows "Garment updated." and redirects to `garments:list`.
- `garment_delete(request, pk)`: GET and POST.
  - GET renders the confirmation with `affected_outfits` (the garment's outfits, names only, one query).
  - POST follows the garment-delete order in Critical Implementation Details. It shows "Garment deleted." and redirects to `garments:list`. When outfits were affected, the message also says "N outfits are now incomplete."

#### 3. URLs

**File**: `garments/urls.py`

**Intent**: The actions sit under the garment's own URL.

**Contract**: `'<uuid:pk>/edit/'` → `garment_edit`, named `edit`; `'<uuid:pk>/delete/'` → `garment_delete`, named `delete`.

#### 4. Templates

**File**: `templates/garments/list.html`, `templates/garments/edit.html` (new), `templates/garments/delete.html` (new)

**Intent**: One tap from the list to editing. Deleting always passes through a page that says what happens to outfits.

**Contract**:
- `list.html`: each tile's `<figure>` is wrapped in an `<a href="{% url 'garments:edit' garment.pk %}">`, and the image alt stays as it is.
- `edit.html`:
  - title and `<h1>` "Edit garment";
  - the current photo (`photo_url`, same alt rule as the list);
  - a multipart form rendering every field like `add.html`, with `data-submit-once`, a `[data-shrink-status]` element and `js/photo-shrink.js`;
  - a *Save changes* button, a *Delete garment* link to `garments:delete` and a *Cancel* link to the list.
- `delete.html`:
  - title and `<h1>` "Delete garment", the photo, and the display type and description;
  - with affected outfits: "These outfits stay, marked incomplete, so you can add a replacement or delete them:" followed by the list of names;
  - otherwise: "This garment is not in any outfit.";
  - "The photo is deleted permanently.";
  - a POST form with a *Delete garment* button, and a *Cancel* link back to the edit page.

#### 5. Styles

**File**: `static/css/app.css`

**Intent**: Linked list tiles look like the current tiles, and the edit photo never fills more than the screen.

**Contract**: `.garment-grid a` inherits colour and has no underline. The edit and delete photos reuse S-04's `.outfit-photo img` rule, or a shared class extracted from it.

#### 6. Privacy contract registration

**File**: `tests/owner_scoped_routes.py`

**Intent**: Both routes are covered by every registry-driven scenario.

**Contract**:
- `_seed_garment(user)` is `_seed_wardrobe` with `kwargs_for` → `{'pk': garments[0].pk}`.
- `'garments:edit'`: `kind='write'`, `seed=_seed_garment`, `shows_photos=True`. Its `foreign_payload` is `_garment_edit_payload`: a valid upload, type and description, plus the seeded garment's `owner`, `id` and photo pk, like `_garment_add_payload`.
- `'garments:delete'`: `kind='write'`, `seed=_seed_garment`, `shows_photos=True`, and a `foreign_payload` that returns `{}`.

#### 7. Tests

**File**: `garments/tests/test_views.py`, `garments/tests/test_forms.py` (new or existing module)

**Intent**: Prove through HTTP that edits and deletes change the right rows and files, and that refused requests change nothing. Every assertion re-reads the database, and file assertions check `MEDIA_ROOT` on disk.

**Contract**:
- A list tile links to its garment's edit page, and the list query count is unchanged (extend `garments/tests/test_views.py:204` `test_list_query_count_does_not_grow_with_garments`).
- Editing the description without a photo keeps `photo_id` and its file, and shows "Garment updated."
- Editing with an in-memory JPEG inside `django_capture_on_commit_callbacks(execute=True)` links a new `PrivateImage` owned by the owner, deletes the old row and file, and leaves the garment's outfits unchanged.
- An edit whose save fails (monkeypatch `Garment.save` to raise) keeps the old photo row and file, and leaves no new file.
- An 11 MB or corrupt upload returns 200 with a `photo` error and changes nothing.
- The type rules still hold on edit: "Other" + "shirt" folds to Shirt.
- The GET delete page lists the names of both affected outfits. For a garment in no outfit it says so.
- POST delete inside `django_capture_on_commit_callbacks(execute=True)` removes the garment, its photo row and its file. Both outfits still exist, each with one tombstone. The message names the count.
- A stranger's GET and POST on edit and delete return 404 and change nothing, and no file is written.

### Success Criteria:

#### Automated Verification:

- Garment tests pass: `uv run pytest garments/tests`
- The privacy contracts cover the new routes: `uv run pytest tests/`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- Tapping a garment in the list opens its edit page; changing the description and saving returns to the list with the new text
- Replacing the photo with a large phone-sized photo shows the shrink status, then the new photo in the list; the old file is gone from the dev `MEDIA_ROOT`
- *Delete garment* shows the affected outfit names; confirming returns to the list with the count message, and the garment's photo file is gone
- At 360 px in headless Chromium the list, edit and delete pages fit without horizontal scrolling

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Outfit edit and delete

### Overview

The owner renames an outfit and changes its garments, and deletes an outfit after a confirmation page that warns about its tags and photo.

### Changes Required:

#### 1. Forms

**File**: `outfits/forms.py`

**Intent**: Edit reuses the compose form's picker and name rules, with a one-garment minimum and no tag input. The minimum differs from compose on purpose: a new outfit is a combination, so compose keeps two, while *Keep without it* can already leave an outfit with one garment, and that outfit must stay editable; zero garments is refused so that a saved outfit never looks complete while empty (plan review F6, 2026-09-14).

**Contract**:
- `OutfitForm.__init__(self, data=None, *, owner, instance=None)` passes `instance` to `ModelForm`. `self.instance.owner` and the owner-scoped queryset stay as they are.
- `clean_name()` excludes `self.instance.pk` from the uniqueness check.
- `clean_garments()` reads a `min_garments` class attribute, 2 on `OutfitForm`, and its message is built from that value.
- `OutfitEditForm(OutfitForm)`: `tag_names = None`, `min_garments = 1`. Its `garments` required-message is "Choose at least 1 garment."
- On `OutfitEditForm`, an empty `name` means "keep the name": its `clean_name()` returns `self.instance.name` when the cleaned value is empty, and otherwise applies the parent rule. The label is "Name" and the `outfit-N` help text is removed. Without this, `_store_outfit` would treat the empty value as auto-named and `Outfit.clean()` would rename the outfit to the lowest free `outfit-N` (plan review F2, 2026-09-14).
- Compose behaviour and messages are unchanged.

#### 2. Views

**File**: `outfits/views.py`

**Intent**: Only the owner edits or deletes. Deleting an outfit also retires its photo file.

**Contract**:
- `_store_outfit(form)` sets tags only when `'tag_names' in form.cleaned_data`. Its name-race handling applies to edit unchanged.
- `outfit_edit(request, pk)`: GET and POST. It resolves the owned outfit first and binds `OutfitEditForm(request.POST or None, owner=request.user, instance=outfit)`. On success it shows "Outfit updated." and redirects to the outfit. `OutfitNameTaken` becomes a name error, as in compose.
- `outfit_delete(request, pk)`: GET and POST.
  - GET renders the confirmation with the outfit's tags (from the prefetch).
  - POST, in one transaction: keep a reference to `outfit.photo`, `outfit.delete()`, then `discard_private_image(photo)` when there was one. It shows "Outfit deleted." and redirects to `wardrobe`.
  - Tag cleanup happens through the existing receiver.

#### 3. URLs

**File**: `outfits/urls.py`

**Intent**: The actions sit under the outfit's URL, next to tags and photo.

**Contract**: `'<uuid:pk>/edit/'` → `outfit_edit`, named `edit`; `'<uuid:pk>/delete/'` → `outfit_delete`, named `delete`.

#### 4. Templates

**File**: `templates/outfits/_garment_picker.html` (new), `templates/outfits/compose.html`, `templates/outfits/edit.html` (new), `templates/outfits/delete.html` (new), `templates/outfits/detail.html`

**Intent**: One picker markup for compose and edit, and a delete step that says what is lost.

**Contract**:
- `_garment_picker.html` holds the `outfit-picker` list, its comment and the counter bar from `compose.html`. `compose.html` includes it, and its rendered output is unchanged.
- `edit.html`:
  - title and `<h1>` "Edit outfit";
  - name field, errors and the picker include, with the current garments ticked;
  - when the outfit has missing slots (`outfit.is_incomplete`, Phase 1), a `<p class="notice">` above the picker: "This outfit has N missing garment(s). Adding garments here does not close them — use *Replace* or *Keep without it* on the outfit page." with a link to the outfit. It reuses the `.notice` style Phase 4 adds (plan review F3, 2026-09-14);
  - a *Save changes* button and a *Cancel* link to the outfit.
- `delete.html`:
  - title and `<h1>` "Delete outfit", with the outfit name;
  - "Its garments stay in your wardrobe.";
  - when tagged, a highlighted warning: "This outfit is tagged: letnie · smart-casual. Tags no other outfit uses disappear from your wardrobe filter.";
  - when it has a photo, "Its photo is deleted permanently." The page shows no `<img>`;
  - a POST form with a *Delete outfit* button, and a *Cancel* link to the outfit.
- `detail.html` gets an actions row under the `<h1>` with *Edit outfit* and *Delete outfit* links.

#### 5. Privacy contract registration

**File**: `tests/owner_scoped_routes.py`

**Intent**: Both routes are covered by every registry-driven scenario.

**Contract**:
- `'outfits:edit'`: `kind='write'`, `seed=_seed_outfit_detail`, `shows_photos=True` (the picker shows garment photos). Its `foreign_payload` is `_outfit_edit_payload`: a name, plus the seeded garments and the requester's own garment when they have one, like `_compose_payload`.
- `'outfits:delete'`: `kind='write'`, `seed=_seed_outfit_detail`, `shows_photos=False`, and a `foreign_payload` that returns `{}`.

#### 6. Tests

**File**: `outfits/tests/test_forms.py` (new or existing module), `outfits/tests/test_views.py`

**Intent**: Edit changes exactly the name and garments. Delete removes the outfit, its tombstones, its unused tags and its photo file, and nothing else.

**Contract**:
- `OutfitEditForm` accepts one garment, refuses zero with "Choose at least 1 garment.", accepts the outfit's own current name, refuses another outfit's name in any letter case, and keeps the current name when `name` is posted empty (an `outfit-2` stays `outfit-2`).
- Editing through HTTP to rename and swap garments keeps the tags and the photo. Garments unticked in edit create no tombstone, and existing tombstones are unchanged.
- The edit page of an outfit with one tombstone shows the missing-garments note with a link to the outfit page; adding a garment through edit leaves the tombstone in place. The note is absent for a complete outfit.
- An edit POST that also carries `tag_names` leaves the tags unchanged.
- The GET delete page of a tagged outfit shows the tag names and the photo sentence. An untagged outfit without a photo shows neither.
- POST delete inside `django_capture_on_commit_callbacks(execute=True)` removes the outfit, its tombstones and the tag only it used, keeps a tag another outfit uses, keeps every garment and its photo, and deletes the outfit photo's row and file.
- The detail page links to edit and delete, and its query count pins still hold (`outfits/tests/test_views.py:632`, `:933`).
- A stranger's GET and POST on edit and delete return 404 and change nothing.

### Success Criteria:

#### Automated Verification:

- Outfit tests pass: `uv run pytest outfits/tests`
- The privacy contracts cover the new routes: `uv run pytest tests/`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- *Edit outfit* shows the picker with current garments ticked; renaming and unticking a garment saves and returns to the outfit page with its tags and photo intact
- *Delete outfit* on a tagged outfit with a photo shows the tag warning and the photo sentence; confirming lands on the wardrobe without the outfit, and the photo file is gone
- Compose still works exactly as before
- At 360 px in headless Chromium the edit and delete pages fit without horizontal scrolling

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Incomplete outfits in the grid and on the outfit page

### Overview

Make incompleteness visible where the user browses, and give each missing garment its repair: replace, keep without it, or delete the outfit.

### Changes Required:

#### 1. Replacement form

**File**: `outfits/forms.py`

**Intent**: Pick exactly one of the owner's garments that is not already in the outfit, with garments of the missing type listed first.

**Contract**:
- `ReplaceMissingGarmentForm(data=None, *, outfit, missing)` has one `garment` `ModelChoiceField` with a `RadioSelect`.
- The queryset is the owner's garments excluding those in the outfit.
- The choices are ordered in Python: first garments whose `type` and, for Other, casefolded `type_other` match `missing`, then the rest, each group in the default order.

#### 2. Views

**File**: `outfits/views.py`

**Intent**: The owner closes one gap at a time. A stale tab never errors, and the grid can be narrowed to incomplete outfits.

**Contract**:
- `outfit_missing_replace(request, pk, missing_pk)`: GET and POST.
  - It resolves the owned outfit first (404 otherwise), then the tombstone through `outfit.missing_garments`. If the tombstone is gone, it redirects to the outfit.
  - GET renders the picker.
  - A valid POST follows Critical Implementation Details: `outfit.garments.add(garment)`, delete the tombstone, show "Garment added to the outfit.", redirect to the outfit.
- `outfit_missing_dismiss(request, pk, missing_pk)`: `@require_POST`. It resolves the owned outfit, then the tombstone (gone: redirect).
  - When the outfit has no garments, it shows the error message "An outfit with no garments needs a replacement or deletion." and redirects without changing anything.
  - Otherwise it deletes the tombstone, shows "Outfit kept without it.", and redirects to the outfit.
- `_owned_outfit` prefetches `missing_garments` too.
- `wardrobe`:
  - accepts `?incomplete=1`, which narrows the outfits with `missing_garments__isnull=False` and `.distinct()`, combined with any tag filters (AND);
  - prefetches `missing_garments`;
  - computes `incomplete_count` for all the owner's outfits, ignoring filters, with one count query, skipped when the incomplete filter is active;
  - `_wardrobe_url` preserves `incomplete` in every tag chip URL and builds a "remove Incomplete filter" URL;
  - `filtering` is true when either filter is active.

#### 3. URLs

**File**: `outfits/urls.py`

**Intent**: Each missing slot has its own URL under the outfit.

**Contract**: `'<uuid:pk>/missing/<uuid:missing_pk>/replace/'` → `outfit_missing_replace`, named `missing_replace`; `'<uuid:pk>/missing/<uuid:missing_pk>/dismiss/'` → `outfit_missing_dismiss`, named `missing_dismiss`.

#### 4. Templates

**File**: `templates/outfits/detail.html`, `templates/outfits/missing_replace.html` (new), `templates/outfits/wardrobe.html`

**Intent**: The outfit page leads with what is missing and how to fix it. The grid shows which outfits need it, on every kind of tile.

**Contract**:
- `detail.html`: when the outfit has tombstones, a `<section aria-labelledby="missing-heading">` with `<h2>` "Missing garments" is placed directly under the actions row, before *Tags*. It holds:
  - one line: "A garment in this outfit was deleted. Replace it, keep the outfit without it, or delete the outfit.";
  - a list where each item shows `display_type`, the description when set, and "removed <date>". Each item has a *Replace* link and a *Keep without it* POST form. The form is omitted when the outfit has no garments;
  - a closing *Delete outfit* link.
- `missing_replace.html`:
  - title and `<h1>` "Replace a missing garment";
  - "Missing: <display_type> — <description>";
  - a POST form whose radio list reuses the `outfit-picker` look (photo + display type), a *Add to outfit* button and a *Cancel* link to the outfit;
  - with no candidates: "You have no other garments to use." with a link to `garments:add`.
- `wardrobe.html`:
  - Inside each tile's `<a>`, when `missing_count` is at least 1, add `<span class="outfit-incomplete">Incomplete · N missing</span>` inside the `.outfit-preview` box. It sits there for both photo and collage tiles.
  - The `aria-label` becomes "<name>, incomplete" in that case.
  - Above the tag bar, when `incomplete_count` is at least 1 and the incomplete filter is off, show `<p class="notice">` "N outfit(s) need attention." with a *Show them* link to `?incomplete=1`, keeping the current tag selection.
  - When the incomplete filter is on, the filter bar shows a selected chip "Incomplete ×" that removes it.
  - With the filter on and no match, the empty state reads "No incomplete outfits match." with a link to show all.

#### 5. Styles

**File**: `static/css/app.css`

**Intent**: The badge reads on top of any photo or collage at 360 px, including an empty collage.

**Contract**:
- `.outfit-preview` is `position: relative`.
- `.outfit-incomplete` is absolutely positioned top-left inside the preview. It has an opaque warning background, sufficient contrast, small type and rounded corners, and it never covers the `+N` badge (bottom-right).
- The `.notice` banner style follows the existing messages look.

#### 6. Privacy contract registration

**File**: `tests/owner_scoped_routes.py`

**Intent**: The repair routes are covered, and every read scenario also catches a tombstone's description leaking.

**Contract**:
- `_seed_wardrobe` gains a third garment on `outfits[0]` (`"{username} red belt"`, accessory), deleted through the ORM so the receiver writes a tombstone. The seeder discards its image, so no orphan file is left.
- It also gains a spare garment in no outfit (`"{username} grey sneakers"`, shoes), appended as `garments[2]`.
- Markers gain the tombstone description and pk, and the spare garment's description, photo URL and pk.
- `_seed_missing_slot(user)` uses `kwargs_for` → `{'pk': outfit.pk, 'missing_pk': outfit.missing_garments.get().pk}`.
- `'outfits:missing_replace'`: `kind='write'`, `seed=_seed_missing_slot`, `shows_photos=True`. Its `foreign_payload` posts `{'garment': <requester's own garment pk, else the seeded spare garment pk>}`.
- `'outfits:missing_dismiss'`: `kind='write'`, `seed=_seed_missing_slot`, `shows_photos=False`, `post_only=True`, and a `foreign_payload` that returns `{}`.

#### 7. Risk #5 scenarios

**File**: `tests/garment_deletion_keeps_outfits/__init__.py`, `tests/garment_deletion_keeps_outfits/test_deleting_a_garment_keeps_every_outfit_that_used_it.py`, `tests/garment_deletion_keeps_outfits/test_incomplete_outfit_offers_repair_and_delete.py`, `tests/garment_deletion_keeps_outfits/test_garment_deleted_outside_the_page_still_marks_outfits.py`, `tests/CLAUDE.md`

**Intent**: Prove Risk #5's protection in user terms, through the real delete path, without asserting the flag alone.

**Contract**:
- *Keeps every outfit*:
  - Setup: the owner has o1 = {a, b} tagged, o2 = {a, c} with a photo, and o3 = {b, c}. The stranger has an outfit of their own garments, one of them the same type as a.
  - Deleting a through `garments:delete` leaves o1 and o2 existing with exactly {b} and {c}, o1's tag, o2's photo, and one missing slot each describing a.
  - o3 is unchanged with no missing slot, and `snapshot_of(stranger)` is unchanged.
- *Offers repair and delete*: after the same deletion,
  - the grid shows the *Incomplete* badge on o1's and o2's tiles, including o2's photo tile and the `?tag=` view containing o1, and never on o3's tile;
  - the banner says 2 outfits need attention;
  - `?incomplete=1` lists exactly o1 and o2;
  - o1's page links to `missing_replace` and `outfits:delete` and has the `missing_dismiss` form;
  - replacing with a new shoes garment removes o1's badge. Dismissing o2's slot removes o2's badge and keeps o2's garments;
  - on an outfit reduced to zero garments the dismiss form is absent, and a posted dismiss changes nothing.
- *Outside the page*: an instance `.delete()` and a `QuerySet.delete()` (the admin path) produce the same missing slots. Account deletion leaves no rows behind and passes `connection.check_constraints()`.
- `tests/CLAUDE.md` lists the new folder: "`garment_deletion_keeps_outfits/`: #5, deleting a garment deletes its outfits or leaves them looking complete."

#### 8. App-level tests

**File**: `outfits/tests/test_views.py`, `outfits/tests/test_forms.py`

**Intent**: The form ordering, the stale-state rules and the query pins.

**Contract**:
- `ReplaceMissingGarmentForm` lists same-type garments first, excludes garments already in the outfit and the stranger's garments, and refuses a posted id outside the queryset.
- GET and POST replace/dismiss for a tombstone that no longer exists redirect to the outfit and change nothing.
- The replace page with no candidates shows the add-garment link.
- The grid query count is the same for one complete outfit as for five outfits with tags, photos and missing slots. It is pinned separately with and without `?incomplete=1` and a tag (extend `outfits/tests/test_views.py:1188` `test_grid_query_count_does_not_grow_with_outfits_tags_selections_or_photos`).
- The detail query count is the same with zero and with three missing slots (extend `outfits/tests/test_views.py:632` `test_detail_query_count_does_not_grow_with_tags`; `:933` `test_detail_query_count_is_the_same_with_and_without_a_photo` must still hold).

### Success Criteria:

#### Automated Verification:

- Outfit tests pass: `uv run pytest outfits/tests`
- Risk #5 scenarios pass: `uv run pytest tests/garment_deletion_keeps_outfits`
- The privacy contracts cover the new routes and markers: `uv run pytest tests/`
- The full suite passes: `uv run pytest`
- System checks pass: `uv run python manage.py check`
- `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- After deleting a garment used by a collage outfit and a photo outfit, both tiles show the *Incomplete* badge legibly and the banner links to a grid of just those two
- On the outfit page, *Replace* lists same-type garments first; picking one adds it and the section disappears
- *Keep without it* closes the slot; on an outfit with no garments left only *Replace* and *Delete outfit* are offered
- At 360 px in headless Chromium the badge, banner, missing section and replace picker fit without horizontal scrolling, with and without a tag filter

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 5: Pull request and PR-environment verification

### Overview

Bring the branch up to date, open the pull request, run every manual check against the Railway PR environment, and put the close-out into the same PR before the developer merges.

### Changes Required:

#### 1. Base branch check

**File**: none — an operation

**Intent**: The PR carries only this slice's commits and passes against whatever `master` holds now.

**Contract**:
- Run `git fetch origin` and `git log --oneline --no-merges origin/master..HEAD`. If commits that are not this slice's appear, stop and ask the developer.
- Otherwise, unless `git merge-base --is-ancestor origin/master HEAD` already holds, run `git merge origin/master` with the message `chore(garment-lifecycle): merge master (p5)`. Never rebase: Phases 0–4 are already on the branch and may have been pushed.
- If another `outfits` migration numbered `0004_*` landed first, delete this slice's migration and regenerate it in its own commit.
- Re-run the full suite and `makemigrations --check`.

#### 2. Pull request

**File**: none — an operation

**Intent**: Deliver for review. Nothing reaches `master` without the developer's merge.

**Contract**:
- Run `git push -u origin feat/garment-lifecycle`, never with `--force`.
- Then `gh pr create --base master --head feat/garment-lifecycle`, titled `feat(garment-lifecycle): garment edit/delete and incomplete outfits with repair (S-06, OG-7)`.
- The body contains:
  - a summary lifted from `plan-brief.md`;
  - the phases;
  - the test commands run;
  - the PR-environment checks;
  - a note that outfit edit and delete (FR-006) shipped here and close roadmap S-07 (OG-8);
  - a note that merging deploys migration `outfits.0004_*`;
  - links to `plan.md` and Jira OG-7.
- Never merge the PR.

#### 3. PR-environment checks and close-out

**File**: `context/changes/garment-lifecycle/plan.md`, `context/changes/garment-lifecycle/change.md`, `context/changes/outfit-lifecycle/change.md`, `context/foundation/roadmap.md`

**Intent**: Done means the checks passed on the PR deploy, and the record of it rides in the same PR (lessons).

**Contract**:
- The PR environment has an empty database, so create two accounts there first.
- Run the manual checks against the PR environment URL. Put any fix into this PR, with its own commit.
- Once everything passes:
  - tick Progress with SHAs;
  - add a dated "PR deploy" note to `change.md` (PR URL, deployment id, checks run, deviations, and that outfit edit and delete shipped here and close S-07);
  - set S-06 to `done` in `roadmap.md`, in the At-a-glance row and in the item body, and update its Backlog Handoff row;
  - set S-07 to `done` the same way, with the note "delivered by `garment-lifecycle` PR #N (FR-006 in Phase 3)" in its item body and Backlog Handoff row;
  - bring S-06's own rows up to date with what was built (plan review F5, 2026-09-14): *Prerequisites* becomes `S-03, S-04, S-05` in the At-a-glance table and the item body, and *PRD refs* becomes `FR-004, FR-006, US-01`, so the milestone's FR trace survives S-07 being done by reference. No other edge of the graph changes;
  - add a *Parked* entry to `roadmap.md`: "Pliki zdjęć po usunięciu z admina, ORM lub konta" — every non-UI deletion path leaves the file on the volume (known gap since `user-accounts`, narrowed to UI paths here); revisit when volume usage nears the F-01 threshold or when account deletion gets a UI;
  - stamp `context/changes/outfit-lifecycle/change.md`: `status: implemented`, `updated: <today>`, and a dated note "delivered by `garment-lifecycle` PR #N";
  - push.
- Per the Jira lesson, move OG-7 and OG-8 to Done after the developer merges, each with a comment naming the PR; OG-8's comment says S-07 was delivered by S-06.
- After the merge, `/10x-archive outfit-lifecycle` follows `/10x-archive garment-lifecycle`, so the S-07 folder does not stay open in `context/changes/`.

### Success Criteria:

#### Automated Verification:

- The full suite passes on the branch merged with current `master`: `uv run pytest`
- Nothing is left unmigrated after the merge: `uv run python manage.py makemigrations --check --dry-run`
- The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- The PR against `master` exists and contains only this slice's commits, apart from merges of `master`: `gh pr view feat/garment-lifecycle --json baseRefName,commits`
- The PR has no merge conflicts: `gh pr view feat/garment-lifecycle --json mergeable`
- The Railway PR environment build is green, and its deploy logs show `migrate` applying `outfits.0004_*`
- The PR environment's `/health/` returns 200

#### Manual Verification:

- On the PR environment at 360 px: add three garments, compose two outfits sharing one garment, add a photo to one, delete the shared garment through its confirmation page (both outfit names listed), and see both tiles marked incomplete with the banner
- On the PR environment, repair one outfit with *Replace* and the other with *Keep without it*; the badges and banner disappear
- On the PR environment at 360 px, edit a garment's photo and an outfit's name and garments, then delete a tagged outfit through its warning page
- On the PR environment, a second account gets 404 on the first account's garment edit/delete pages, outfit edit/delete pages and replace page, and sees none of its garments or outfits
- The developer reviews and merges the PR; production `/health/` returns 200 afterwards

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- `MissingGarment` creation on instance delete, bulk delete and account deletion, with a constraint check
- Tombstones cascade with their outfit; `missing_count` makes no query after a prefetch
- `GarmentEditForm` optional photo; `OutfitEditForm` minimum 1, own name allowed, no tags; `ReplaceMissingGarmentForm` ordering and scope

### Integration Tests:

- Garment edit with and without a photo, a failed replace, garment delete with file cleanup after commit
- Outfit edit keeps tags and photo; outfit delete removes the outfit, its tombstones, unused tags and the photo file
- Replace and dismiss, including stale tombstones and zero-garment outfits
- Grid badge on collage and photo tiles, banner, `?incomplete=1` combined with tags, constant query counts
- Registry-driven privacy scenarios for six new routes, and tombstone and spare-garment markers in every read scenario (Risks #1, #2)
- `tests/garment_deletion_keeps_outfits/` (Risk #5)

### Manual Testing Steps:

1. Garments → tap a garment → edit description → save → list shows it.
2. Edit → replace photo with a large phone photo → list shows the new photo; old file gone.
3. Delete a garment used by two outfits → confirmation lists both → confirm → count message.
4. Wardrobe → both tiles show *Incomplete* (collage and photo tile) → banner → *Show them*.
5. Outfit page → *Replace* → same-type garments first → add → section gone.
6. Second outfit → *Keep without it* → badge gone.
7. *Edit outfit* → rename, untick a garment → tags and photo kept.
8. *Delete outfit* on a tagged outfit → tag warning → confirm → gone from the grid.
9. Second account → 404 on every page above.
10. Steps 1–9 on the Railway PR environment before merge.

## Performance Considerations

- **Grid:** one more prefetch (`missing_garments`) and one count for the banner. The count is skipped when the incomplete filter is on. The query count stays constant in the number of outfits.
- **Detail:** one more prefetch. **Replace picker:** one garments query plus the outfit and tombstone lookups.
- **Garment delete:** one query per garment for its outfits inside the receiver, one bulk insert, then Django's link-row delete and one image-row delete. The file is deleted after commit.
- **Garment photo replace:** the same cost as S-04's outfit photo replace.

## Migration Notes

- `outfits.0004_missinggarment` creates one table with an FK index on `outfit_id`. It needs no data migration and no backfill: no deletion before this release was recorded.
- Rollback: `migrate outfits 0003` drops the table and every recorded missing slot. The affected outfits then look complete again with their remaining garments.

## References

- Research: `context/changes/garment-lifecycle/research.md`
- Roadmap item: `context/foundation/roadmap.md`: S-06 (`garment-lifecycle`), Jira OG-7
- PRD: `context/foundation/prd.md`: FR-004, FR-006, FR-008, US-01, Business Logic, NFR *Prywatność*, *Trwałość danych*
- Test plan: `context/foundation/test-plan.md`: Risks #1, #2, #5
- S-04 plan (primitives, delivery pattern): `context/changes/outfit-photo/plan.md`
- Patterns: `outfits/signals.py`, `outfits/views.py` (`_owned_outfit`, `outfit_tag_remove`, `_store_outfit`), `garments/views.py` (`_store_garment`), `tests/owner_scoped_routes.py`
- Prior plans: `context/changes/outfit-tags/plan.md`, `context/changes/compose-outfit/plan.md`, `context/changes/add-garment/plan.md`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 0: Merge master after S-04

#### Automated

- [x] 0.1 S-04 is on `master`: `git ls-tree origin/master outfits/migrations/ | grep 0003_outfit_photo` — fec1013
- [x] 0.2 The branch contains current `master`: `git merge-base --is-ancestor origin/master HEAD` — fec1013
- [x] 0.3 The only non-merge commits ahead of `master` are docs commits touching `context/`: `git log --oneline --no-merges --stat origin/master..HEAD` — fec1013
- [x] 0.4 Migrations apply cleanly: `uv run python manage.py migrate` — fec1013
- [x] 0.5 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run` — fec1013
- [x] 0.6 The full suite passes on the merged branch: `uv run pytest` — fec1013
- [x] 0.7 Linting passes: `uv run ruff check .` — fec1013

#### Manual

- [x] 0.8 Every S-04 contract listed in change 4 is confirmed in the merged code, or its deviation is recorded in `change.md` and the plan was adjusted with the developer's agreement — fec1013

### Phase 1: Missing-garment record and deletion rule

#### Automated

- [x] 1.1 The migration applies cleanly: `uv run python manage.py migrate` — 46a7f54
- [x] 1.2 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run` — 46a7f54
- [x] 1.3 Model tests pass: `uv run pytest outfits/tests/test_missing_garment_model.py` — 46a7f54
- [x] 1.4 The full suite passes: `uv run pytest` — 46a7f54
- [x] 1.5 System checks pass: `uv run python manage.py check` — 46a7f54
- [x] 1.6 Linting passes: `uv run ruff check .` — 46a7f54
- [x] 1.7 Formatting is clean: `uv run ruff format --check .` — 46a7f54

#### Manual

- [x] 1.8 In `/admin/`, deleting a garment used by two outfits leaves both outfits with a read-only *Missing garment* inline row describing it — 46a7f54

### Phase 2: Garment edit and delete

#### Automated

- [x] 2.1 Garment tests pass: `uv run pytest garments/tests` — 42fb263
- [x] 2.2 The privacy contracts cover the new routes: `uv run pytest tests/` — 42fb263
- [x] 2.3 The full suite passes: `uv run pytest` — 42fb263
- [x] 2.4 System checks pass: `uv run python manage.py check` — 42fb263
- [x] 2.5 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput` — 42fb263
- [x] 2.6 Linting passes: `uv run ruff check .` — 42fb263
- [x] 2.7 Formatting is clean: `uv run ruff format --check .` — 42fb263

#### Manual

- [x] 2.8 Tapping a garment in the list opens its edit page; changing the description and saving returns to the list with the new text — 42fb263
- [x] 2.9 Replacing the photo with a large phone-sized photo shows the shrink status, then the new photo in the list; the old file is gone from the dev `MEDIA_ROOT` — 42fb263
- [x] 2.10 *Delete garment* shows the affected outfit names; confirming returns to the list with the count message, and the garment's photo file is gone — 42fb263
- [x] 2.11 At 360 px in headless Chromium the list, edit and delete pages fit without horizontal scrolling — 42fb263

### Phase 3: Outfit edit and delete

#### Automated

- [x] 3.1 Outfit tests pass: `uv run pytest outfits/tests` — f995583
- [x] 3.2 The privacy contracts cover the new routes: `uv run pytest tests/` — f995583
- [x] 3.3 The full suite passes: `uv run pytest` — f995583
- [x] 3.4 System checks pass: `uv run python manage.py check` — f995583
- [x] 3.5 Linting passes: `uv run ruff check .` — f995583
- [x] 3.6 Formatting is clean: `uv run ruff format --check .` — f995583

#### Manual

- [x] 3.7 *Edit outfit* shows the picker with current garments ticked; renaming and unticking a garment saves and returns to the outfit page with its tags and photo intact — f995583
- [x] 3.8 *Delete outfit* on a tagged outfit with a photo shows the tag warning and the photo sentence; confirming lands on the wardrobe without the outfit, and the photo file is gone — f995583
- [x] 3.9 Compose still works exactly as before — f995583
- [x] 3.10 At 360 px in headless Chromium the edit and delete pages fit without horizontal scrolling — f995583

### Phase 4: Incomplete outfits in the grid and on the outfit page

#### Automated

- [x] 4.1 Outfit tests pass: `uv run pytest outfits/tests` — fcbc482
- [x] 4.2 Risk #5 scenarios pass: `uv run pytest tests/garment_deletion_keeps_outfits` — fcbc482
- [x] 4.3 The privacy contracts cover the new routes and markers: `uv run pytest tests/` — fcbc482
- [x] 4.4 The full suite passes: `uv run pytest` — fcbc482
- [x] 4.5 System checks pass: `uv run python manage.py check` — fcbc482
- [x] 4.6 `collectstatic` succeeds under manifest storage: `uv run python manage.py collectstatic --noinput` — fcbc482
- [x] 4.7 Linting passes: `uv run ruff check .` — fcbc482
- [x] 4.8 Formatting is clean: `uv run ruff format --check .` — fcbc482

#### Manual

- [x] 4.9 After deleting a garment used by a collage outfit and a photo outfit, both tiles show the *Incomplete* badge legibly and the banner links to a grid of just those two — fcbc482
- [x] 4.10 On the outfit page, *Replace* lists same-type garments first; picking one adds it and the section disappears — fcbc482
- [x] 4.11 *Keep without it* closes the slot; on an outfit with no garments left only *Replace* and *Delete outfit* are offered — fcbc482
- [x] 4.12 At 360 px in headless Chromium the badge, banner, missing section and replace picker fit without horizontal scrolling, with and without a tag filter — fcbc482

### Phase 5: Pull request and PR-environment verification

#### Automated

- [x] 5.1 The full suite passes on the branch merged with current `master`: `uv run pytest`
- [x] 5.2 Nothing is left unmigrated after the merge: `uv run python manage.py makemigrations --check --dry-run`
- [x] 5.3 The deploy-configuration guard still passes: `uv run pytest accounts/tests/test_deploy_config.py`
- [x] 5.4 The PR against `master` exists and contains only this slice's commits, apart from merges of `master`: `gh pr view feat/garment-lifecycle --json baseRefName,commits`
- [x] 5.5 The PR has no merge conflicts: `gh pr view feat/garment-lifecycle --json mergeable`
- [x] 5.6 The Railway PR environment build is green, and its deploy logs show `migrate` applying `outfits.0004_*`
- [x] 5.7 The PR environment's `/health/` returns 200

#### Manual

- [ ] 5.8 On the PR environment at 360 px: add three garments, compose two outfits sharing one garment, add a photo to one, delete the shared garment through its confirmation page (both outfit names listed), and see both tiles marked incomplete with the banner
- [ ] 5.9 On the PR environment, repair one outfit with *Replace* and the other with *Keep without it*; the badges and banner disappear
- [ ] 5.10 On the PR environment at 360 px, edit a garment's photo and an outfit's name and garments, then delete a tagged outfit through its warning page
- [ ] 5.11 On the PR environment, a second account gets 404 on the first account's garment edit/delete pages, outfit edit/delete pages and replace page, and sees none of its garments or outfits
