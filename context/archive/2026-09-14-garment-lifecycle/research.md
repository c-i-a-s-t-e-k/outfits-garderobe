---
date: 2026-09-14T11:18:16+02:00
researcher: Claude (Opus 5) with ciastek
git_commit: 787aa1f1bbd5cc6d6fab1441ac471acfe37399fa
branch: chore/pre-commit-gate (fast-forwarded to origin/master)
repository: c-i-a-s-t-e-k/outfits-garderobe
topic: "S-06 garment-lifecycle: garment edit and delete, how an incomplete outfit can be recorded and shown, the quick-fix paths, the route/test contracts, and the overlap with S-04 (in progress) and S-07"
tags: [research, codebase, garments, outfits, privatemedia, incomplete-outfit, deletion, signals, owner-scoped-routes, s-04-overlap, s-07-overlap, risk-5]
status: complete
last_updated: 2026-09-14
last_updated_by: Claude (Opus 5)
---

# Research: S-06 garment-lifecycle

**Date**: 2026-09-14T11:18:16+02:00
**Researcher**: Claude (Opus 5) with ciastek
**Git Commit**: `787aa1f` (origin/master, Merge PR #5 `feat/outfit-tags`)
**Branch**: `chore/pre-commit-gate`, fast-forwarded to `origin/master`
**Repository**: c-i-a-s-t-e-k/outfits-garderobe

Permalink base: `https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/`

## Research Question

Roadmap S-06 (Jira OG-7, FR-004, US-01) covers the whole surface. The user can edit a garment, including its photo, and delete it. Outfits that used a deleted garment stay, are marked **incomplete** in the wardrobe grid, and offer an immediate choice: add a replacement or delete the outfit. The research has to cover:

- what exists today;
- how the incomplete state could be stored and shown;
- which route and test contracts the new views must satisfy;
- where S-06 overlaps S-04, in progress in a parallel worktree, and S-07 (outfit edit and delete).

## Baseline note: corrections after pulling origin/master

The first pass of this research read the local branch at `7d0ce76`, which was 13 commits behind `origin/master`. After fast-forwarding to `787aa1f`, these assumptions turned out to be wrong or incomplete:

1. **S-03 was reported "in progress" and treated as a blocker. That was wrong.** S-03 and S-05 are both `done` on master (`context/foundation/roadmap.md:47,49`). The Backlog Handoff marks S-06 `Ready for /10x-plan: yes`.
2. **Tags now exist (S-05).** `Outfit.tags` is an M2M to a per-owner `Tag` (`outfits/models.py:38-165`). Wardrobe tiles show a tag line, and a tag filter bar sits above the grid (`templates/outfits/wardrobe.html:17-31,62-66`). An incomplete marker has to work in the filtered grid too.
3. **Deleting an outfit already cleans up tags.** A `post_delete` receiver on `Outfit` does it (`outfits/signals.py:64-66`). If S-06 ships an outfit delete, it gets tag hygiene for free.
4. **The route contract now supports POST-only actions.** `OwnerScopedRoute.post_only` (`tests/owner_scoped_routes.py:54`) makes a GET answer 405, and the stranger test probes with a POST instead (`tests/cross_user_visibility/test_stranger_sees_nothing_of_the_owner.py:39-45`). A delete view no longer has to answer GET with 404: it can be `post_only`, or a GET confirmation page.
5. **The contract snapshot includes `Tag` and tag links.** See `tests/foreign_id_writes/conftest.py:30-40` and `OWNED_MODELS`/`_row_counts` in the write and anonymous scenario files. A new owner-scoped model gets the same treatment.
6. **S-04 `outfit-photo` is in progress in a parallel worktree** (`/home/ciastek/Projects/.worktrees/outfit-photo`, branch `feat/outfit-photo`, Phase 1 uncommitted). It introduces the photo-retirement helper, the shared photo-form mixin, and portrait tiles that hide the collage when a photo exists. All three change what S-06 should build (see "Overlap with S-04").

Every other finding below was re-verified on `787aa1f`.

## Summary

- **Nothing edits or deletes a garment today.** `garments` has only `list` and `add` (`garments/urls.py:7-10`). The garment list tiles are not links (`templates/garments/list.html:12-27`), so an entry point is needed too.
- **What deleting a garment does now, verified with a throwaway probe on `787aa1f`:**
  - Django deletes that garment's rows in `outfits_outfit_garments`. The outfits survive with their remaining garments.
  - No `m2m_changed` fires, and no signal fires for the through model. `pre_delete`/`post_delete` fire only for `Garment`, including on `QuerySet.delete()`.
  - The garment's `PrivateImage` row and its file both stay behind, so the photo is orphaned. `garment.photo` is the FK holder, and nothing ever deletes stored files (`privatemedia/models.py:77-97` only cleans up failed stores).
  - An outfit can shrink to 1 or 0 garments. `preview_garments` is then `[]`, and the CSS has `.outfit-preview-0` (`static/css/app.css:177`).
- **Incompleteness cannot be derived after the fact.** Once the link rows are gone, nothing records that a garment was ever there. It has to be written at deletion time, or the garment has to be soft-deleted. In a `Garment` `pre_delete` receiver, `instance.outfits` is still readable: the probe saw 2 outfits, and a queryset `.update()` on them succeeded. The same receiver runs harmlessly during an account-deletion cascade.
- **Quick fixes lean on code that doesn't exist yet.** No UI adds garments to an existing outfit: `OutfitForm` is create-only, its `__init__` takes no `instance`, and `outfits/forms.py:69-74` requires ≥ 2 garments. No UI deletes an outfit either. Both belong to S-07 in the roadmap, and FR-006's warning for deleting a tagged outfit is S-07's.
- **Contracts:** each new view must be registered in `tests/owner_scoped_routes.py` or the net fails. Test-plan Risk #5 defines what "done" must prove.
- **S-04 overlap:** S-04's plan adds `discard_private_image()`, which deletes the row now and the file on commit, and `NormalizedPhotoMixin`. S-06 needs both for the photo swap on edit and for delete. S-04 also adds migration `outfits.0003`, portrait tiles where a photo tile hides the garment collage, and a second, photo-less outfit in `_seed_wardrobe`.

## Detailed Findings

### 1. Garment model, and what edit must respect

- `Garment` (`garments/models.py:27-117`): UUID pk, `owner` FK CASCADE, `photo` `OneToOneField(PrivateImage, on_delete=RESTRICT, related_name='garment')` (`:45-49`), `type` choices, `type_other`, `description`, `created_at`.
- `save()` always calls `full_clean()` (`:76-81`). `clean()` folds "Other" text that matches a listed type into that type (`:87-101`) and refuses a photo owned by someone else (`:105-106`). Edit gets these rules for free as long as it saves through the model.
- The check constraint `garment_type_other_matches_type` (`:61-68`) holds against queryset `.update()` too.
- `photo_url` is built from `photo_id` with no query (`:114-117`). Replacing the photo means a new `PrivateImage` with a new UUID, so the URL changes and the gate's ETag (`privatemedia/views.py:30-38`) never serves a stale cached image.
- **`RESTRICT` sets the order of a photo swap.** Store the new image, point `garment.photo` at it and save, then delete the old `PrivateImage`. Deleting the old image while it is still linked raises `RestrictedError` (pinned by `garments/tests/test_model.py:121-125`). S-04's plan uses the same order for outfit photos (worktree `context/changes/outfit-photo/plan.md:59-61`).

### 2. Garment form and views today

- `GarmentForm` (`garments/forms.py:10-47`) has a non-model `photo = forms.FileField(...)`, which is **required**, and `clean_photo()` (size check, then `normalize_photo`, then `original_filename`). An edit form needs the photo to be optional: keep the current photo when none is uploaded.
- `garment_add` / `_store_garment` (`garments/views.py:20-41`) store the image inside `stored_private_image(...)` (`privatemedia/models.py:77-97`). If anything in the block fails, the written file is deleted.
- `garment_list` (`garments/views.py:12-17`) runs one query, and `garments/tests/test_views.py:204` pins that it doesn't grow with the number of garments.
- Templates: `templates/garments/add.html` renders every field and loads `static/js/photo-shrink.js` through `data-shrink-photo`. The list tile (`templates/garments/list.html:12-27`) is a `<figure>` with no link or actions.
- Nav links to `garments:list` (`templates/base.html:27`).

### 3. Deletion mechanics (probe results)

A throwaway test ran on `787aa1f` and was deleted afterwards. Setup: garments a, b, c; outfit o1 = {a, b} tagged `letnie`; outfit o2 = {a, c}.

- `a.delete()`, with receivers connected, ran this SQL: `SELECT` from the through table, `DELETE FROM outfits_outfit_garments WHERE id IN (...)`, `DELETE FROM garments_garment ...`.
- Signals: only `pre_delete(Garment)` and `post_delete(Garment)`. No `m2m_changed`, and nothing for the auto-created through model.
- A `Garment` `pre_delete` receiver still sees `instance.outfits` (2 outfits). A queryset `.update()` on those outfits committed. Afterwards both outfits exist, each with 1 garment, and the tag count is unchanged.
- The `PrivateImage` row and its file remain. Deleting the row afterwards leaves the file on disk.
- `QuerySet.delete()` on garments still sends per-object `pre_delete`/`post_delete`, because Django collects the objects when listeners exist. That covers admin bulk delete.
- Account deletion: the same receiver fired once per garment. Outfits and garments were then removed by the cascade without errors.
- Outfit shrunk to 0 garments: `preview_garments == []`, `hidden_garment_count == 0`.

Implications:

- A flag write in `pre_delete` must use queryset `.update()`, not `Outfit.save()`. `save()` runs `full_clean()` (`outfits/models.py:188-193`) and would be pointless work on outfits the same cascade is about to delete.
- The existing `outfits/signals.py` sets the precedent: tag cleanup lives in receivers because delete-driven link removal skips `m2m_changed`, and that module's docstring says so (`outfits/signals.py:12-13`).
- On PostgreSQL, cascades still run in Python's deletion collector (no `db_on_delete` in use), so the probe's order of events carries over. CLAUDE.md warns against SQLite-only behaviour, and nothing here relies on it.

### 4. How "incomplete" can be represented (options for /10x-plan)

| Option | Shape | Pros | Cons |
|---|---|---|---|
| **A. Flag on `Outfit`** | e.g. `missing_garment_count` (int) or `incomplete_since` (datetime), set in a `Garment` `pre_delete` receiver via `.update()` | One field; the grid needs no extra query; `snapshot_of` in `tests/foreign_id_writes/conftest.py:28` already covers every `Outfit` column | Loses *what* was removed, so "add a replacement" can't suggest the type; needs a rule for when the flag clears |
| **B. Tombstone rows** | e.g. `MissingGarment(outfit FK CASCADE, owner, type, type_other, description, removed_at)`, written in `pre_delete` | The outfit page can say "Missing: Shoes, brown loafers", and the replacement picker can pre-filter by type; filling one slot clears one row | A new owner-scoped model: must be added to `snapshot_of`, `OWNED_MODELS` and `_row_counts` (as S-05 did for `Tag`), plus one more prefetch in the grid query-count tests (`outfits/tests/test_views.py:374,817`); descriptions are owner data and must never leak |
| **C. Soft-delete garments** | `Garment.deleted_at`, hidden everywhere | Incompleteness derivable; undo possible | Every garment query must filter it (`garments/views.py:16`, `outfits/views.py:74,95`, `OutfitForm` queryset `outfits/forms.py:74`, the gate's photo); "deleted" photos stay stored, against the 5 GB volume and user expectations; raises Risk #1 surface. Poor fit. |

Whichever option is chosen, the rule for clearing it is a design question the plan has to settle. Adding any garment? Adding one per missing slot? An explicit "mark as complete"? Does a later intentional removal of a garment (S-07 edit) count as incomplete? The PRD only says the outfit "is marked incomplete" and offers repair or delete.

### 5. Where incompleteness must be visible

- **Wardrobe grid** (`outfits/views.py:21-85`, `templates/outfits/wardrobe.html:48-84`):
  - Each tile is one `<a>` with `aria-label="{{ outfit.name }}"`, the collage, the name and the tag line. A marker has to live inside it, as text or a badge, because nested links aren't allowed, and it should add to the accessible name or sit next to it.
  - Quick-fix actions cannot be links inside the tile. They belong on the outfit page, with the tile only signalling and linking there. Or the tile markup has to change.
  - The grid query count is pinned in `outfits/tests/test_views.py:374,817`. Option A adds no query; option B needs its rows prefetched (or annotated).
  - Filtered view: the marker must also appear when `?tag=` narrows the grid, since it's the same template loop.
- **Outfit detail** (`outfits/views.py:114-165`, `templates/outfits/detail.html`): the natural place for the "incomplete" explanation and the two actions, and where S-04 adds its *Photo* section.
- **Garment list**: optional. Deleting from here, or from a garment detail/edit page, is the entry point.
- **Empty collage:** an outfit with 0 garments renders `outfit-preview-0` with no images. With S-04 merged, an outfit *with* a photo shows the photo instead of the collage, so the incomplete marker can't depend on the collage.
- Test-plan Risk #5 guidance (`context/foundation/test-plan.md:56,70`) must prove all of these: every outfit that used the garment still exists with its remaining garments; it is flagged; the grid shows the repair/delete affordance; the garment's other outfits are affected the same way; other users' outfits are untouched. Anti-pattern to avoid: asserting the flag without checking that the outfit still exists.

### 6. Quick-fix paths, and the overlap with S-07

- **"Add a replacement"** needs a way to add garments to an existing outfit. Today:
  - `OutfitForm(data=None, *, owner)` builds a new instance only (`outfits/forms.py:69-74`).
  - `_store_outfit` handles the create path only (`outfits/views.py:168-190`).
  - `testing-cross-user-privacy/research.md:147` already noted that S-07's edit form will change this signature.
  - The M2M `pre_add` guard (`outfits/signals.py:24-35`) already refuses foreign garments on any `.add()`/`.set()`, so a new add path is protected at the model level.
- **"Delete the outfit"** needs an outfit delete that doesn't exist yet. FR-006 (S-07) requires a warning when the outfit is tagged. Tag cleanup after outfit delete already works (`outfits/signals.py:64-66`). S-04's plan records that deleting an outfit must also call `discard_private_image` for its photo, and hands that gap to S-07.
- **Garments available for a replacement:** deleting garments can take the user below `MIN_GARMENTS = 2` (`outfits/forms.py:9`). Compose is then disabled (`outfits/views.py:74,95-97`), but a repair picker for an existing outfit need not be.
- Boundary options for the plan:
  1. S-06 builds a narrow "add garments to this outfit" action on the outfit page (POST, owner's garments not already in the outfit) plus an outfit delete confirmation with the tag warning. S-07 then reuses or extends both.
  2. S-06 builds the full outfit edit form (instance-aware `OutfitForm`), and S-07 shrinks to rename and delete.
  3. S-06 ships only the marker and links to actions that land in S-07. This does not meet the S-06 roadmap outcome ("natychmiastowy wybór").
- Any delete S-06 builds should follow the precedent S-04 is setting: a GET confirmation page and a POST that deletes (worktree `outfit-photo/plan-brief.md`, decision "Usuwanie").

### 7. Route and test contracts for new views

- `LoginRequiredMiddleware` makes auth default-deny. A new view that isn't registered in `tests/owner_scoped_routes.py` fails `cross_user_visibility/test_new_guarded_route_cannot_skip_the_contract.py` (`tests/CLAUDE.md:13-15`).
- Probable registrations (names are placeholders for the plan):
  - `garments:edit` (`{'pk': garment.pk}`): `kind='write'`, `shows_photos=True` (the edit page shows the current photo), `foreign_payload` = a valid edit body for the owner's garment, optionally with a photo upload.
  - `garments:delete`: `kind='write'`. Either a GET confirmation page (`shows_photos=True` if it shows the photo, and it may list the affected outfit names, which are owner markers) or `post_only=True` with `shows_photos=False`. Its `foreign_payload` is `{}`, since the id is in the URL, like `_tag_remove_payload` (`tests/owner_scoped_routes.py:155-157`).
  - Any outfit-side repair or delete route S-06 adds.
- What the parametrized scenarios will then prove:
  - stranger GET/POST on the owner's pk returns 404 with the same bytes as a random UUID and no ETag (`test_stranger_sees_nothing_of_the_owner.py:35-55`);
  - anonymous requests get a 302 to login and every row count is unchanged (`test_anonymous_visitor_only_reaches_login.py`);
  - a foreign POST leaves the owner's snapshot unchanged, with no cross-owner links (`test_write_aimed_at_another_users_objects_changes_nothing.py`);
  - every gated `<img>` on the owner's page is owner-only.
- A new owner-scoped model (option B) must be added to `snapshot_of`, `OWNED_MODELS` and `_row_counts`, as `Tag` was in `9fa0704`.
- Risk-#5 scenarios belong in a `tests/<risk>/` folder named for the risk. #5 exists in test-plan §2, so a folder such as `tests/garment_deletion_keeps_outfits/` is allowed (`tests/CLAUDE.md:35-41`). Test-plan §3 Phase 3 formally covers #5 after S-05 and S-06 land, but S-05 shipped its own tests and S-06 should too.
- Factories: `make_garment`, `make_outfit` (`tests/factories.py`). S-04 changes `make_outfit` to accept `photo=False`.
- Pre-commit: `scripts/pytest_staged.py` runs the owning app, its importers and the whole `tests/` suite for staged app files. Editing `garments` runs `garments` + `outfits` + `tests`.

### 8. Overlap with S-04 (in progress, parallel worktree)

Source: worktree `/home/ciastek/Projects/.worktrees/outfit-photo`, `context/changes/outfit-photo/plan.md` and `plan-brief.md`, status `implementing`. Its uncommitted Phase 1 diff touches `outfits/models.py`, `outfits/tests/test_model.py`, `tests/factories.py` and `roadmap.md`.

- **`discard_private_image(image)`** will live in `privatemedia` (plan.md:99-101). Called inside a transaction, it deletes the row immediately and the file in `transaction.on_commit`, after the caller has unlinked any `RESTRICT` relation. S-06's garment delete and photo replace need exactly this. If S-06 starts before S-04 merges, it will duplicate the helper or have to rebase onto it.
- **`NormalizedPhotoMixin`** in `privatemedia/forms.py`, shared by `GarmentForm` and `OutfitPhotoForm`, refactors `garments/forms.py`. This conflicts directly with an S-06 edit form.
- **Migration `outfits.0003_*`:** both slices may add one. S-04's plan says to regenerate its migration if S-06's lands first.
- **Tiles:**
  - Every tile becomes portrait 3:4.
  - When `outfit.photo_id` is set, the tile shows the photo instead of the collage (plan.md:302-307). A photo tile never shows that a garment is missing, so the incomplete marker must be independent of the collage.
  - `wardrobe.html` and `app.css` both change.
- **`_seed_wardrobe`** gains an outfit photo and a second, photo-less outfit (plan.md:238). S-06 registrations that reuse the seeder should target `seeded.outfits[0]` and `seeded.garments[...]` explicitly.
- **`outfit_compose` now redirects to the new outfit's page** instead of the wardrobe.
- Both slices touch the same files: `outfits/models.py`, `templates/outfits/wardrobe.html`, `templates/outfits/detail.html`, `static/css/app.css`, `tests/owner_scoped_routes.py`, `tests/factories.py`, `outfits/tests/test_views.py`.

## Code References

- [`garments/models.py:27-117`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/garments/models.py#L27-L117) — `Garment`; `RESTRICT` photo at L45-49; `full_clean` in `save` L76-81; owner/photo rule L105-106
- [`garments/forms.py:10-47`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/garments/forms.py#L10-L47) — `GarmentForm`, required `photo`
- [`garments/views.py:12-41`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/garments/views.py#L12-L41) — list, add, `_store_garment`
- [`garments/urls.py:7-10`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/garments/urls.py#L7-L10) — only `list` and `add`
- [`templates/garments/list.html:12-27`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/templates/garments/list.html#L12-L27) — tiles without links
- [`privatemedia/models.py:22-97`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/privatemedia/models.py#L22-L97) — `PrivateImage`, `stored_private_image`
- [`privatemedia/views.py:30-73`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/privatemedia/views.py#L30-L73) — gate, ETag from pk + name, missing file → 404 and a log line
- [`outfits/models.py:144-240`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/models.py#L144-L240) — `Outfit`, M2M `garments` L164, `tags` L165, preview properties L230-240
- [`outfits/signals.py:1-66`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/signals.py#L1-L66) — foreign-garment/tag guards; tag cleanup on unlink and on outfit `post_delete`
- [`outfits/forms.py:9,46-86`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/forms.py#L46-L86) — `MIN_GARMENTS`, create-only `OutfitForm`
- [`outfits/views.py:21-190`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/views.py#L21-L190) — wardrobe (filter), compose, detail, tag add/remove (`require_POST`), `_owned_outfit`, `_store_outfit`
- [`templates/outfits/wardrobe.html:48-84`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/templates/outfits/wardrobe.html#L48-L84) — tile markup, one `<a>` per tile
- [`templates/outfits/detail.html`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/templates/outfits/detail.html) — tags section, garment grid
- [`static/css/app.css:147-216`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/static/css/app.css#L147-L216) — tile/collage rules, `.outfit-preview-0` L177
- [`tests/owner_scoped_routes.py:47-192`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/tests/owner_scoped_routes.py#L47-L192) — `OwnerScopedRoute` (with `post_only`), seeders, payloads, `ROUTES`
- [`tests/foreign_id_writes/conftest.py`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/tests/foreign_id_writes/conftest.py) — `snapshot_of`, `assert_no_cross_owner_links`
- [`tests/CLAUDE.md`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/tests/CLAUDE.md) — how to register routes and add risk scenarios
- `outfits/tests/test_views.py:374,817` — grid query-count pins; `:623` — detail query-count pin
- `garments/tests/test_model.py:111-125` — `RESTRICT` behaviour pins
- `context/foundation/test-plan.md:56,70` — Risk #5 and its response guidance

## Architecture Insights

- **Rules live in the model and in signal receivers, not in views.** Every model calls `full_clean()` in `save()`. M2M rules sit in `m2m_changed` receivers because M2M writes bypass `save()`, and delete-driven link removal is handled by `post_delete` because it bypasses `m2m_changed`. An incomplete flag set in a `Garment` `pre_delete` receiver fits this pattern and covers the view, the admin and the ORM alike.
- **One 404 for "missing" and "not yours".** The pattern is `get_object_or_404(Model, pk=pk, owner=request.user)` (`outfits/views.py:145-150`). Child lookups go through the parent's relation (`outfit.tags`, `outfits/views.py:139`).
- **Files are touched only by `privatemedia`.** Stores go through `stored_private_image`; S-04 adds `discard_private_image` for retirement. Deleting bytes only after commit is the agreed safety rule.
- **Constant query counts are pinned for grids and pages.** Anything S-06 adds to tiles must come from prefetched or annotated data.
- **No JavaScript for core flows.** Filtering uses links, and actions use POST forms (`templates/outfits/wardrobe.html:32-36`, `detail.html:103-114`).
- **Confirmation pages for irreversible actions** (S-04 precedent). Small reversible actions such as tag remove are plain `require_POST`.

## Historical Context (from prior changes)

- `context/foundation/shape-notes.md:25,95,149`: the original decision was that deleting a garment removes it from outfits, and each outfit stays but shows an incomplete state with quick fix and delete actions.
- `context/changes/private-media-gate/plan.md:42`, `reviews/impl-review.md:248`: deletion and orphan-file cleanup were deferred explicitly to S-06.
- `context/changes/add-garment/plan.md:25,33`: `RESTRICT` rather than `PROTECT`, so that account deletion cascades. Garment edit and delete were deferred to S-06.
- `context/changes/compose-outfit/plan.md:35,38`: garment delete keeps Django's default link-row removal. The 2-garment minimum applies only in the form, and "S-06 handles outfits that shrink".
- `context/changes/outfit-tags/plan.md:38-39,49`: the S-05 boundary. Tag cleanup receivers were added, including on outfit `post_delete`.
- `context/changes/testing-cross-user-privacy/research.md:144-147`: S-06 and S-07 write paths were anticipated; the `OutfitForm` signature will need an `instance`.
- `context/foundation/lessons.md`: plan in English with the brief in Polish; propagate roadmap changes to Jira (OG-7); done means every check passes on the PR deploy.

## Related Research

- `context/changes/testing-cross-user-privacy/research.md`: every read and write entry point and the route-contract design.
- Worktree `outfit-photo`: `context/changes/outfit-photo/plan.md`. Not research, but the source of the S-04 overlap above.

## Open Questions

1. **How is incompleteness stored:** a flag on `Outfit` (A) or tombstone rows (B)? B lets the page say what is missing and match the replacement by type, at the cost of a new owner-scoped model in the contracts.
2. **When does incompleteness clear?** When any garment is added, one per missing slot, or when the user explicitly dismisses it? Does removing a garment on purpose in S-07's edit ever count?
3. **Where is the S-06/S-07 boundary for the quick fixes?** Options: a narrow "add garments to this outfit" action plus an outfit delete with the tag warning in S-06, a full outfit edit form in S-06, or deferring the actions. Whatever S-06 builds for outfit delete must include FR-006's tag warning and discard the S-04 outfit photo.
4. **Sequencing with S-04:** wait for S-04 to merge and reuse `discard_private_image` and `NormalizedPhotoMixin` (recommended, since they are the exact primitives S-06 needs), or build in parallel and accept conflicts in the migration, tiles, forms and seeder?
5. **Garment delete confirmation:** should the page list the outfits that will become incomplete? That is useful for FR-004 and adds owner markers to the contract. Or should the action be POST-only?
6. **Edit entry point:** a separate garment detail/edit page linked from list tiles, or edit and delete controls on the list itself?
7. **Outfits left with 0 or 1 garments:** keep them as incomplete (the PRD says the outfit stays), or treat "fewer than 2" specially in the UI?
8. **Photo file on garment delete:** delete the `PrivateImage` row and the file on commit in the same flow. This looks implied by "no orphans on a 5 GB volume" but isn't stated in the PRD; confirm in the plan.
