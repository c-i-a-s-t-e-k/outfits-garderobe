---
date: 2026-09-14T12:17:55+02:00
researcher: Claude (Opus 5) with ciastek
git_commit: 787aa1f1bbd5cc6d6fab1441ac471acfe37399fa
branch: chore/pre-commit-gate (at origin/master)
repository: c-i-a-s-t-e-k/outfits-garderobe
topic: "Is roadmap slice S-07 outfit-lifecycle still worth doing, and feasible, after S-06 garment-lifecycle was widened to include outfit edit and delete?"
tags: [research, roadmap, s-07, s-06-overlap, outfits, tags, deletion, confirmation, privatemedia, orphan-files, fr-006]
status: complete
last_updated: 2026-09-14
last_updated_by: Claude (Opus 5)
last_updated_note: "Added the developer's decision: close S-07 through the S-06 close-out"
---

# Research: Is S-07 outfit-lifecycle still worth doing after S-06 was widened?

**Date**: 2026-09-14T12:17:55+02:00
**Researcher**: Claude (Opus 5) with ciastek
**Git Commit**: `787aa1f` (= origin/master, Merge PR #5 `feat/outfit-tags`)
**Branch**: `chore/pre-commit-gate`
**Repository**: c-i-a-s-t-e-k/outfits-garderobe

Permalink base (master code): `https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/`

Path shorthands for code not on master:
- **G**: `/home/ciastek/Projects/.worktrees/garment-lifecycle` (branch `feat/garment-lifecycle`, commit `979ba62`, docs only, not pushed)
- **W**: `/home/ciastek/Projects/.worktrees/outfit-photo` (branch `feat/outfit-photo`, S-04. Phase 1 is in `4fba006`; Phase 2 is uncommitted on disk)

## Research Question

The developer widened the scope of S-06 (`garment-lifecycle`). Given that, is S-07 (`outfit-lifecycle`: edit and delete an outfit, with a warning before deleting a tagged one; FR-006) still worth doing as its own slice, and is it feasible?

Scope agreed with the developer:
- Treat the S-06 plan (G `context/changes/garment-lifecycle/plan.md`) as frozen: it ships as written.
- Assess three candidates for leftover S-07 scope:
  1. protection against clicking through the delete warning;
  2. tags in the outfit edit form;
  3. gaps left after deleting an outfit (files, tags, tests).

## Summary

**If S-06 ships as planned, S-07 has no required scope left.** Its outcome, its FR and its acceptance criteria are all covered by S-06 Phase 3 together with S-05, which is already on master. S-07 is trivially feasible, but as a separate slice it is not worth the cost: none of the three candidates is required by the PRD or by a test-plan risk.

| Candidate | Value | Cost | Verdict |
|---|---|---|---|
| 1a. Checkbox or typing the name to confirm delete | low: the PRD asks only for a *warning* (`prd.md:85`) | **S**: about 4 files, no migration, no JS | optional; if wanted, add it to S-06 Phase 3 as an amendment |
| 1b. Outfit preview (photo or collage) on the delete page | medium: in a visual product the likelier mistake is deleting the *wrong* outfit | **S**: template, plus `shows_photos=True` in the registry | **best value per unit of cost**; add it to S-06 Phase 3 |
| 1c. Undo or soft delete | medium | **L**: about 12+ files, a migration, a purge job for files, the name constraint, tag cleanup | not worth it in M-1 |
| 2. Tags in *Edit outfit* | **negative**: duplicates a one-tap flow; `tags.set()` plus the cleanup receiver silently delete tags removed from the text | S–M | no |
| 3a. Photo files after admin/ORM/account deletion | low: developer-only paths, about 0.4 MB per orphan (estimate) | S–M | tech debt, not a user slice; park it |
| 3b. Tags after outfit delete | none: already correct on every path | — | nothing to do |
| 3c. Test for accidental deletion | low: no test-plan risk covers it | S | optional |

**Recommendation:** don't plan S-07 as a separate slice.
- Put the cheap delete-page hardening (1b, optionally 1a) into S-06 Phase 3 through `/10x-plan-review` or a plan edit.
- In the S-06 close-out, set S-07 to `done` as delivered by the `garment-lifecycle` PR, and move OG-8 along with OG-7.

This needs a one-line exception to S-06's "S-07 is not changed" rule (G `plan.md:51,611`). Without it, milestone M-1 cannot close: "Done when" requires every S-NN to be `done` (`roadmap.md:27`), and `/10x-archive` flips only an exact Change ID match.

## Detailed Findings

### 1. FR-006 and S-07 coverage after S-06 + S-05 + S-04

| Requirement | Source | Covered by |
|---|---|---|
| "Użytkownik może edytować i usunąć outfit" | `prd.md:84` | S-06 Phase 3: `outfit_edit` and `outfit_delete` (G `plan.md:325-329`), routes (`:337`) |
| "UI ostrzega przy usuwaniu outfitu, który jest otagowany" | `prd.md:85` | S-06: the confirmation page highlights the outfit's tags (G `plan.md:354`) and a test checks it (`:379`) |
| S-07 outcome: warning before confirmation | `roadmap.md:170` | S-06: GET confirmation, POST delete (G `plan.md:327-328,356`) |
| S-07 risk: warning clicked through without reading | `roadmap.md:177` | **Partly.** The confirmation page exists, but there is explicitly no checkbox (G `plan.md:50`, `plan-brief.md:30,48`) |
| US-02 AC "Tagi można dodawać i usuwać z outfitu" | `prd.md:65` | S-05 on master: `outfits/views.py:120-142`, `templates/outfits/detail.html:17-47` |
| Tag filter stays correct after edit and delete | `prd.md:64-66` | Edit keeps tags (G `plan.md:324,377-378`). Delete removes tags only when unused (`outfits/signals.py:52-53,64-66`; G `plan.md:380`) |
| Outfit photo private, no orphan after delete | `prd.md` Guardrails, NFR | S-06 calls `discard_private_image` in the UI delete (G `plan.md:328,380`), closing the gap S-04 left for S-07 (W `outfit-photo/plan.md:42,463`) |
| NFR "Trwałość danych" | `prd.md:104` | Confirmation page. Unticking a garment in edit is a deliberate change (G `plan.md:47,377`) |
| Another user cannot edit or delete | `test-plan.md:53` (Risk #2) | Registry entries `outfits:edit` and `outfits:delete` (G `plan.md:366-367`), 404 tests (`:382`) |
| 360 px | `prd.md` NFR | Headless check 3.10 (G `plan.md:400`) |

**Where each `Outfit` field is edited after S-04 + S-05 + S-06:**
- `name` and `garments`: *Edit outfit* (S-06). `garments` can also be changed through *Replace* on a missing slot.
- `tags`: set in compose; afterwards added and removed on the detail page (S-05).
- `photo`: detail page (S-04).
- `id`, `owner`, `created_at`: system fields.

Every user-owned field is editable. They are just spread across two places, the edit page and the detail page. That is a UX preference, not a missing requirement.

**Share of S-06 that is FR-006:**
- Phase 3 is G `plan.md:296-402`, about 107 of 556 phase lines, or roughly 20–25% of the slice (~0.7–1 session out of 3–4, per `plan-brief.md:68`).
- The delete half is needed anyway by FR-004's "usuń outfit" quick fix (G `plan.md:465`).
- The part purely attributable to FR-006 is edit (`OutfitEditForm`, extracting `_garment_picker.html`, `edit.html`): about 10–15%.

### 2. Candidate 1: protection against clicking through the warning

**What exists now:**
- There is no undo, soft delete or trash anywhere in the repo. Master's only destructive UI action is tag remove, a `require_POST` with no confirmation (`outfits/views.py:133-142`).
- S-04 (W, uncommitted) sets the confirmation precedent: `outfit_photo_remove` with GET and POST (W `outfits/views.py:163-174`), and `templates/outfits/photo_remove.html:1-19` showing the photo, one sentence, a plain button and *Cancel*. There is no checkbox and no danger styling.
- `static/css/app.css` has no danger or warning classes. S-06 would add the first ones (`.notice`, `.outfit-incomplete`; G `plan.md:485-488`).
- JS: the only script is `static/js/photo-shrink.js`, with `data-submit-once` in S-04. Every earlier plan requires flows to work without JS (`context/changes/add-garment/plan.md:12`, `compose-outfit/plan.md:48`, `outfit-tags/plan.md:14`). A JS-only safeguard would break that convention.

**S-06 plan as written (G `plan.md:351-356`):**
- `delete.html` shows the name, "Its garments stay in your wardrobe.", the tag warning when the outfit is tagged, and the photo sentence when it has a photo.
- **The page renders no `<img>`.** The user identifies the outfit by name alone, and names can be auto-assigned `outfit-N` (`outfits/views.py:163-189`).
- The warning never says the outfit itself cannot be recovered.

**Safeguard options, by cost:**
- **(1b) Outfit preview on the confirmation page.**
  - Reuse the tile markup: the photo if there is one, otherwise the collage.
  - Changes: `delete.html`, and `shows_photos=True` instead of `False` on the `'outfits:delete'` registry entry (G `plan.md:367`), so the photo privacy scenario checks the new `<img>`s.
  - This targets the most likely mistake, the wrong outfit among auto-named ones, rather than not reading.
- **(1a) Checkbox or typed name.**
  - A small form (`BooleanField(required=True)`, or a name compared with the outfit's name), the POST branch of `outfit_delete` re-rendering with an error, and one field in `delete.html`.
  - **Pitfall:** the `'outfits:delete'` `foreign_payload` must then carry the confirmation (`{'confirm': 'on'}`), not `{}`. Otherwise the foreign-write scenario passes only because of a form error, which proves nothing (`tests/owner_scoped_routes.py` pattern `_tag_remove_payload`).
  - About 4 files, no migration.
  - Friction: an extra tap on every delete. The project has no precedent for it.
- **(1c) Undo within N seconds.** This needs soft delete (`Outfit.deleted_at`) and therefore:
  - filtering in `wardrobe`, `_owned_outfit`, `outfit_tag_remove` and S-04's `outfit_photo_remove` / `_locked_outfit`;
  - rethinking the name uniqueness check (`outfits/forms.py:78`) and the DB constraint `outfit_name_unique_per_owner` (`outfits/models.py:171-177`);
  - adjusting `default_name_for`, tag suggestions and cleanup (`outfits/views.py:157`, `outfits/signals.py:53`);
  - ownership checks in `signals.py:30,44`, the admin, and the contract fixtures (`snapshot_of`, `OWNED_MODELS`, `_row_counts`).
  - S-04's `discard_private_image` deletes the file on commit (W `privatemedia/models.py:100-113`), so the file would have to wait for a purge job, which the app does not have.
  - An undo link in `messages` would require changing `base.html:58-63`, which autoescapes.
  - About 12+ files, a migration and a purge mechanism. That is well beyond the slice's value.

### 3. Candidate 2: tags in the outfit edit form

- **Today**, removing a tag takes one tap on × (`detail.html:17-26`, `views.py:133-142`), and adding tags takes typing plus *Add* (`views.py:120-130`, `forms.py:89-105`). Suggestions come from a native `<datalist>` of the owner's other tags (`views.py:145-160`, `detail.html:42-46`). No JS is involved. Limits are 30 characters per tag and 20 tags per outfit (`models.py:48-49`, `forms.py:39-42,99-105`).
- **If the edit form carried `tag_names`:** `_store_outfit` does `outfit.tags.set(...)` (`views.py:189`). `set()` calls `remove()` for tags that were dropped, which fires `post_remove`, so `delete_tags_left_unused_by_unlinking` deletes any tag that is no longer used (`signals.py:52-61`).
  - Removing a word from a comma-separated text field would therefore **permanently delete the tag** from the filter and the suggestions, without a warning.
  - That is exactly what FR-006 wants to warn about when an outfit is deleted.
- S-06 deliberately takes `tag_names` out of the edit form (`tag_names = None`, G `plan.md:314`). It writes tags only when the field is present (`:324`) and tests that a POST carrying `tag_names` does not change the tags (`:378`).
- **Verdict:** negative value. It duplicates the faster flow and creates a new way to lose tags.

### 4. Candidate 3: gaps after deleting an outfit

**Files.** `discard_private_image` is the only code that deletes stored bytes (W `privatemedia/models.py:100-113`). `RESTRICT` on `Outfit.photo` and `Garment.photo` protects the *image* from being deleted while something still points to it. It never blocks deleting the outfit or garment (W `outfit-photo/plan.md:463`).

| Deletion path | `PrivateImage` row | File |
|---|---|---|
| S-06 UI: outfit delete, garment delete | deleted | deleted after commit |
| Admin: outfit (single or bulk), no `delete_queryset` override (W `outfits/admin.py:9-15`) | **stays** (still served to the owner by the gate, W `privatemedia/views.py:25`) | **stays** |
| ORM `Outfit`/`Garment` `.delete()` | **stays** | **stays** |
| Admin: garment | **stays** (S-06 does write a tombstone) | **stays** |
| User deletion (admin only; allauth has no account-deletion view, `outfits_garderobe/settings.py:75-76`, `context/changes/user-accounts/plan.md:50`) | deleted (cascade) | **stays** for every photo |

- No orphan sweeper exists. `reset_legacy_accounts` was removed in `64b7bd5` as one-off and unsafe to re-run.
- **Volume cost** (estimate, not measured):
  - `normalize_photo` caps the long edge at 1600 px, JPEG quality 85 (W `privatemedia/processing.py:11-12`), so about 0.25–0.6 MB per photo;
  - one orphan is about 0.01% of the 5000 MB volume (`roadmap.md:88`);
  - the worst case is a raw upload through admin, up to 10 MB (W `privatemedia/validators.py:7`).
- **Test plan:** admin is explicitly out of scope, "used only by the developer" (`test-plan.md:170`). No risk covers orphan files or accidental deletion. Risk #4 (`test-plan.md:55`) is about *losing* photos, not leftover ones.
- **The fix, if it is ever needed:** a `post_delete` receiver on `PrivateImage` that deletes the file on commit. It covers every path at once, but has to be reconciled with how `discard_private_image` defers deletion (S–M). Alternatively, a dry-run sweeper command (M). Either way this is technical hygiene with no user outcome, so it belongs in *Parked* or a chore, not in S-07.

**Tags after outfit delete.**
- `post_delete(Outfit)` runs cleanup (`outfits/signals.py:64-66`).
- The collector does not fast-delete a model that has listeners, so `QuerySet.delete()` and the admin bulk action fire the signal for each outfit.
- The account cascade fires it too, and `Tag.owner` CASCADE removes the rest.
- The only cost is one `Tag` delete query per outfit in a bulk delete. There is no correctness gap.

### 5. Semantic issues in S-06 Phase 3 worth raising in the S-06 plan review (not S-07)

- **An add in *Edit outfit* does not close a missing slot** (G `plan.md:48`). A user who "repairs" the outfit through edit still sees the *Incomplete* badge. This is the most likely point of confusion.
- **Garment minimums differ:** edit allows ≥ 1, compose requires ≥ 2 (G `plan.md:314`, `plan-brief.md:28`).
- **Clearing the name in edit** probably runs the auto-name path in `_store_outfit` (`outfits/views.py:175-186`), renaming the outfit to `outfit-N`. The plan applies race handling "to edit unchanged" (G `plan.md:324`). No test covers it.
- The S-07 risk is left open without an explicit decision: G `plan.md:50` rejects the checkbox but says nothing about showing the outfit on the confirmation page.
- PR-environment check 5.10 (G `plan.md:631`) does not require a 360 px width for the delete and edit pages.

### 6. Process: what happens to S-07 in the roadmap

- **No precedent** for closing, merging or removing a slice. Until now overlapping scope was always pushed *toward* S-07:
  - `context/changes/compose-outfit/plan.md:34`: edit and delete deferred;
  - `context/changes/outfit-tags/plan.md:38`: tag warning deferred;
  - W `outfit-photo/plan.md:42,463`: photo cleanup deferred.
  - S-06 is the first slice to pull that scope back, and it deliberately leaves S-07 open (G `plan.md:11,51`, `plan-brief.md:27,75`).
- **Statuses:**
  - `10x-roadmap` knows `proposed | ready | planning | in-progress | done | blocked`; there is no `superseded` or `merged`.
  - Downstream flips (`/10x-plan`, `/10x-implement`, `/10x-archive`) match by exact Change ID, so archiving `garment-lifecycle` never touches S-07.
  - The existing `done` flips on this roadmap were made by hand in close-out PRs.
- **Dependencies:**
  - Nothing has S-07 as a prerequisite.
  - S-07 appears in the At-a-glance table (`roadmap.md:51`), Streams D `S-05 → S-07` (`:62`), S-06 "Parallel with" (`:162`), the body (`:168-178`), Backlog Handoff OG-8 (`:191`) and Jira "Blocks" links (`:193`).
  - Removing it would require adding FR-006 to S-06's PRD refs (`:160`, currently "FR-004, US-01"), so the milestone scope anchor "FR-001 – FR-010" (`:28`) does not lose its trace.
- **Two workable variants:**
  - **(i) Recommended.** The S-06 close-out sets S-07 to `done`, with a note "delivered by garment-lifecycle PR #N", and moves OG-8 to Done together with OG-7. This matches the manual-flip habit and needs no graph rewrite.
  - **(ii)** Remove S-07 and add FR-006 to S-06's PRD refs, Streams and Handoff. This is heavier and has no precedent.
- **Also out of date:** the roadmap still lists only S-03 as S-06's prerequisite (`:161`). The plan in fact requires S-04 merged (G `plan.md:74`), and the tag warning relies on S-05.

## Code References

- [`outfits/views.py:120-142`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/views.py#L120-L142): `outfit_tags_add`, `outfit_tag_remove`, both `require_POST` with no confirmation
- [`outfits/views.py:145-160`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/views.py#L145-L160): `_owned_outfit`, `_render_detail` with tag suggestions
- [`outfits/views.py:163-189`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/views.py#L163-L189): `_store_outfit`, which always calls `tags.set()`, plus the auto-name retry
- [`outfits/signals.py:52-66`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/signals.py#L52-L66): unused-tag cleanup on `post_remove`/`post_clear` and on `post_delete(Outfit)`
- [`outfits/forms.py:89-105`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/forms.py#L89-L105): `AddTagsForm`, with a limit that counts existing tags
- [`outfits/models.py:48-49,171-177`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/outfits/models.py#L171-L177): tag limits, outfit name uniqueness constraint per owner
- [`templates/outfits/detail.html:17-47`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/templates/outfits/detail.html#L17-L47): tag chips with ×, add form, `<datalist>`
- [`context/foundation/prd.md:65,84-85,104`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/context/foundation/prd.md#L84-L85): US-02 AC, FR-006 with the Socrates note, NFR "Trwałość danych"
- [`context/foundation/roadmap.md:27-28,51,62,160-178,191`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/context/foundation/roadmap.md#L168-L178): milestone "Done when", S-07 row, Stream D, S-06 and S-07 bodies, Handoff
- [`context/foundation/test-plan.md:52-57,170`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/787aa1f1bbd5cc6d6fab1441ac471acfe37399fa/context/foundation/test-plan.md#L52-L57): risks 1–6 (none covers accidental deletion or orphans); admin out of scope
- G `context/changes/garment-lifecycle/plan.md:46-52`: What We're NOT Doing (tags in edit, checkbox, S-07 unchanged, file gaps)
- G `context/changes/garment-lifecycle/plan.md:296-402`: Phase 3, outfit edit and delete (`OutfitEditForm` `:314`, `_store_outfit` guard `:324`, `outfit_delete` `:326-329`, `delete.html` `:351-356`, registry `:366-367`)
- G `context/changes/garment-lifecycle/plan.md:605-613`: close-out; "S-07 is not changed" at `:611`
- W `privatemedia/models.py:77-113`: `stored_private_image`, `discard_private_image` (the only code that deletes files)
- W `outfits/views.py:163-174`, W `templates/outfits/photo_remove.html:1-19`: the only existing confirmation-page precedent
- W `context/changes/outfit-photo/plan.md:42,463`: photo cleanup on outfit delete handed to S-07 (S-06 takes it over)

## Architecture Insights

- **Rules live in models and signal receivers, not views.** Tag cleanup already covers every outfit deletion path, so S-07 has nothing to add there.
- **Only `privatemedia` deletes files, and only when a UI action calls it explicitly.** Every admin, ORM and cascade path leaves bytes behind. This is a deliberate, repeatedly recorded "known gap" (`user-accounts`, `private-media-gate`, S-04, S-06), not an S-07 matter.
- **Destructive actions: no JS, a GET confirmation plus a POST (S-04), and small reversible actions as a bare `require_POST`.** A checkbox or typed-name confirmation fits these rules; undo does not.
- **The privacy registry verifies more than 404s.** A change to the payload of a destructive route (a confirmation field) must go into its `foreign_payload`, or the scenario proves nothing.

## Historical Context (from prior changes)

- `context/changes/compose-outfit/plan.md:34`: outfit edit and delete deferred to S-07.
- `context/changes/compose-outfit/plan-brief.md:58`: accepted that an `outfit-N` name can be reused after S-07 deletes an outfit.
- `context/changes/outfit-tags/plan.md:12,38`: the warning when deleting a tagged outfit and outfit edit deferred to S-07.
- `context/changes/user-accounts/plan.md:50,89`: no account deletion; "CASCADE removes rows, never bytes".
- `context/changes/private-media-gate/plan.md:42`: orphan cleanup deferred to S-06, which narrows it to UI paths (G `plan.md:52`).
- W `context/changes/outfit-photo/plan.md:42,463`: "outfit deletion is S-07" plus the `RESTRICT` gap.
- G `context/changes/garment-lifecycle/plan-brief.md:27,75`: the developer's choice to put full outfit edit and delete in S-06; "S-07 zostaje otwarty … `/10x-plan outfit-lifecycle` musi to uwzględnić".
- `context/foundation/lessons.md`: roadmap changes go to Jira (OG-8); done means every check passes on the PR deploy.

## Related Research

- G `context/changes/garment-lifecycle/research.md`: §6 "Quick-fix paths, and the overlap with S-07" (the boundary options that led to widening S-06)
- `context/changes/testing-cross-user-privacy/research.md:144-147`: S-06/S-07 write paths anticipated; `OutfitForm` needs an `instance`

## Open Questions

1. **Is a confirmation page enough to close the S-07 risk** (`roadmap.md:177`)? Or add an outfit preview (1b) and/or a checkbox (1a) to S-06 Phase 3? Either is the developer's call during the S-06 plan review.
2. **Close S-07 as `done` in the S-06 close-out (variant i), or remove it from the graph (variant ii)?** Both require changing the "S-07 is not changed" rule in G `plan.md:51,611` and propagating to Jira OG-8.
3. **Should *Edit outfit* close missing slots** when garments are added? This is an S-06 question, but it directly shapes how "outfit edit" feels, which is S-07's original concern.
4. **Leftover files after admin, ORM and account deletion:** add an entry to the roadmap's *Parked* section (with the threshold for revisiting, e.g. volume usage or user-facing account deletion), or leave it as the "known gap" in the plans?
5. The orphan-size estimate (0.25–0.6 MB) is not measured. If question 4 matters, check actual file sizes on the Railway volume.

## Follow-up: Decision (2026-09-14)

- **Resolves Open Question 2 with variant (i).** No separate `/10x-plan outfit-lifecycle` is run. When the S-06 `garment-lifecycle` PR passes its PR-environment checks, its close-out sets S-07 to `done` with the note "delivered by `garment-lifecycle` PR #N (FR-006 in Phase 3)". After the merge, OG-8 moves to Done together with OG-7.
- **What was updated:** G `context/changes/garment-lifecycle/plan.md`, namely the Overview, What We're NOT Doing, the Phase 5 PR body and the Phase 5 close-out, and `plan-brief.md`, namely the S-06/S-07 boundary decision, Scope, the Phase 5 row and Open Risks. Neither change is committed yet. Another session had already left uncommitted edits to both files (Phase 0 and merge instead of rebase); the S-07 edits are targeted and don't overlap them.
- **Hardening the delete page (1a/1b) was not chosen.** The confirmation page with the tag warning stays the only safeguard. Open Question 1 is closed as "no change". Questions 3–5 remain for the S-06 plan review and for *Parked*.
- `roadmap.md` and Jira are not changed now. The flip happens in the S-06 close-out, per the lessons ("Done means all checks pass on the PR deploy"; propagate to Jira).
