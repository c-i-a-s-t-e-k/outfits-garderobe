---
date: 2026-09-13T19:20:17+02:00
researcher: Claude (Opus 5) with ciastek
git_commit: 29fe28a188af1e19990282800a62fda024beff99
branch: feat/teasting-cross-user-privacy
repository: c-i-a-s-t-e-k/outfits-garderobe
topic: "Cross-user privacy contract: every read and write entry point, how ownership is derived, how media is served, and what a route-enumerating check can hook into (test-plan Phase 1, risks #1 and #2)"
tags: [research, codebase, privacy, ownership, privatemedia, garments, outfits, url-routing, test-plan-phase-1]
status: complete
last_updated: 2026-09-13
last_updated_by: Claude (Opus 5)
---

# Research: Cross-user privacy contract (test-plan Phase 1)

**Date**: 2026-09-13T19:20:17+02:00
**Researcher**: Claude (Opus 5) with ciastek
**Git Commit**: `29fe28a` (master = this branch) plus `f7c81bf` (`feat/compose-outfit`, PR #2, open, mergeable)
**Branch**: feat/teasting-cross-user-privacy
**Repository**: c-i-a-s-t-e-k/outfits-garderobe

## Research Question

Ground test-plan §3 Phase 1, *Cross-user privacy contract*, against current code. It covers:

- **Risk #1**: a photo or record reaches another user or an anonymous visitor.
- **Risk #2**: a write that trusts a foreign id from the request.

The §2 *Risk Response Guidance* says to ground:

- every entry point that returns photos or owner data (gate, lists, grids, detail, forms with choices);
- how ownership is derived;
- how media files are named and served in dev vs prod;
- every write path and where posted ids are checked against the owner;
- the M2M assignment path;
- what a route-enumerating check can hook into.

**Scope (agreed with the developer):** master plus the `outfits` app from PR #2 (`feat/compose-outfit`, worktree `../outfits-garderobe-compose-outfit`). Each finding is tagged **[master]** or **[PR #2]**.

## Summary

1. **Ownership comes from `request.user` and nothing else.** No app view reads an owner, photo id or owner-scoped object from the URL or POST without filtering by `owner=request.user` in the same query. The patterns are:
   - the gate: `filter(pk=pk, owner=request.user)`;
   - lists and the grid: `filter(owner=request.user)`;
   - detail: `get_object_or_404(..., pk=pk, owner=request.user)`;
   - the compose picker: form `queryset` scoped by owner.

   No view uses a plain `Model.objects.get(pk=...)`.
2. **Authentication and ownership are separate layers, and the tests treat them that way.** Every owner-scoped app view has `@login_required`; the owner filter sits inside the query, not in the decorator. On master the authenticated app surface is 3 views (4 with the `wardrobe` placeholder); PR #2 raises it to 6.
3. **Writes have two layers.** A form limits what can be chosen, and a model rule refuses foreign links on any ORM path:
   - `Garment.clean()` refuses another user's photo **[master]**;
   - an `m2m_changed` `pre_add` receiver refuses another user's garment in an outfit, from both sides of the relation **[PR #2]**.

   `garment_add` accepts **no** ids from the request at all. `owner` and `photo` are set on the server.
4. **Two-user tests already exist per slice, and most check the page body, not just the status.** What's missing is anything **cross-cutting**:
   - no test lists routes, so a new owner-scoped view is covered only if its slice author remembers;
   - a few edges are untested (see *Gaps*).
5. **A route-enumerating check is feasible and has hooks to use.** A probe (throwaway, scratchpad only) walked `get_resolver()` on PR #2 and found **70 routes**:
   - 8 in project modules;
   - ~50 Django admin (§7 exclusion);
   - 17 allauth (§7 exclusion, except anonymous → login).

   `login_required` leaves a `login_url` attribute on the wrapped view, so a test can find project routes without a login guard. The project already has a `_flatten` helper for walking the resolver.
6. **No media URL form gets past the gate** (probed as a stranger):
   - conditional GET with the owner's `ETag` or `Last-Modified` → 404, not 304;
   - HEAD → 404; POST → 404;
   - uppercase or undashed UUID → 404 at the resolver;
   - missing trailing slash → 301 to the gated URL;
   - `ImageField.url` (`/media/private/<hex>.png`) → 404.

   Nothing serves `MEDIA_ROOT` in dev or prod, and config-guard tests pin that.
7. **Sequencing hazard.** PR #2 replaces master's `wardrobe` placeholder, the landing redirects and `test_smoke.py` expectations. Phase 1 tests written on this branch before PR #2 merges would target routes that are about to change.

## Detailed Findings

### 1. Entry-point inventory (read side, Risk #1)

URL tree: [master] `outfits_garderobe/urls.py:29-45`; [PR #2] adds `wardrobe/` → `outfits.views.wardrobe` and `include('outfits.urls')` under the same prefix (`outfits_garderobe/urls.py:37-39` on PR #2).

| Route | Name | View | Auth | Ownership derivation | Branch |
|---|---|---|---|---|---|
| `health/` | — | `outfits_garderobe.urls.health` | none (public by design) | returns a constant | master |
| `` | `home` | `accounts.views.home` | none: reads auth state and redirects | — | master (PR #2 retargets to `wardrobe`) |
| `wardrobe/` | `wardrobe` | `accounts.views.wardrobe` placeholder (`accounts/views.py:29-36`) | `@login_required` | no data | master |
| `wardrobe/` | `wardrobe` | `outfits.views.wardrobe` (`outfits/views.py:18-27`) | `@login_required` | `Outfit.objects.filter(owner=request.user)` + `Garment...filter(owner=request.user).count()` | PR #2 |
| `wardrobe/compose/` | `outfits:compose` | `outfits.views.outfit_compose` (`outfits/views.py:30-48`) | `@login_required` | owner-scoped garment count; `OutfitForm(owner=request.user)` | PR #2 |
| `wardrobe/<uuid:pk>/` | `outfits:detail` | `outfits.views.outfit_detail` (`outfits/views.py:51-58`) | `@login_required` | `get_object_or_404(..., pk=pk, owner=request.user)` | PR #2 |
| `garments/` | `garments:list` | `garments.views.garment_list` (`garments/views.py:12-17`) | `@login_required` | `Garment.objects.filter(owner=request.user)` | master |
| `garments/add/` | `garments:add` | `garments.views.garment_add` (`garments/views.py:20-30`) | `@login_required` | no read of existing objects; owner set server-side | master |
| `media/<uuid:pk>/` | `privatemedia:image` | `privatemedia.views.serve_private_image` (`privatemedia/views.py:46-73`) | `@login_required` | `PrivateImage.objects.filter(pk=pk, owner=request.user).first()` (`privatemedia/views.py:25`) | master |
| `admin/…` (~50) | `admin:*` | Django admin | staff (`admin_view`) | none: staff sees all users | out of scope (§7) |
| `accounts/…` (17) | `account_*` | allauth | mixed | allauth's own | out of scope (§7), except the anonymous → login rule |

Where photos appear in HTML (all use the gate URL built from `photo_id`, never `.url`):

- `templates/garments/list.html:19` [master]: `garment.photo_url`
- `templates/outfits/compose.html:37` [PR #2]: `option.data.value.instance.photo_url`, one per picker checkbox; the choice list comes from the owner-scoped queryset
- `templates/outfits/detail.html:13` [PR #2]
- `templates/outfits/wardrobe.html:32,36` [PR #2]: preview collage, up to 4 per tile
- `garments/models.py:114-117`: `Garment.photo_url` reverses `privatemedia:image` from `photo_id`
- `privatemedia/models.py:67-74`: `PrivateImage.get_absolute_url()` does the same

Owner data other than photos, as rendered:

- garment `display_type` and `description` (list, picker, detail);
- outfit `name` (grid tile `aria-label`, detail `<title>`/`<h1>`);
- garment and outfit UUIDs (picker checkbox `value`, tile `href`);
- `user.email` in the nav (`templates/base.html:60`), which is always the requester's own.

These are the "body markers" a test can assert are absent for a stranger.

**Denials look the same everywhere.** A stranger and a nonexistent id both get 404. The gate adds that a denial carries no `ETag`/`Last-Modified`, because the validator functions return `None` for a row the requester doesn't own (`privatemedia/views.py:30-43`). There is no custom `404.html`; the suite runs with `DEBUG=False` (`outfits_garderobe/settings_test.py`), so the body is Django's default page.

### 2. How ownership is modelled

Every owner-scoped model has a direct `owner` FK to `AUTH_USER_MODEL`, `on_delete=CASCADE`, with a `(owner, -created)` index:

- `PrivateImage.owner`: `privatemedia/models.py:31-35`
- `Garment.owner`: `garments/models.py:36-40`. `Garment.photo` is a `OneToOneField(PrivateImage, on_delete=RESTRICT)` (`garments/models.py:45-49`).
- `Outfit.owner` [PR #2]: `outfits/models.py:49-53`. `Outfit.garments` is an M2M to `Garment` (`outfits/models.py:57`).

Other facts:

- **UUID primary keys** on all three models (`privatemedia/models.py:30`, `garments/models.py:35`, `outfits/models.py:48`), so ids can't be enumerated. The test plan lists this as a reason likelihood is Medium, not a control in its own right.
- **Stored file names carry no information**: `upload_to_uuid` → `private/<uuid4 hex>.<ext>` (`privatemedia/models.py:15-19`). The client's filename is kept only as metadata (`original_filename`).
- **Validation on every save path**: `PrivateImage.save()`, `Garment.save()` and `Outfit.save()` all call `full_clean()` (`privatemedia/models.py:55-65`, `garments/models.py:76-81`, `outfits/models.py:80-85`). So rules in `clean()` hold on plain `objects.create()`.
- **Garment → photo owner rule**: `Garment.clean()` raises if `photo.owner_id != owner_id` (`garments/models.py:103-106`). It only applies once both are set, because a ModelForm runs `clean()` before the view assigns them.
- **Outfit → garment owner rule** [PR #2]: `outfits/signals.py:16-27`. It raises `ValidationError` on `pre_add` from either side: forward (garment ids) or reverse (outfit ids). It's connected in `OutfitsConfig.ready()` (`outfits/apps.py:8-11`). It covers `.add()`, `.set()` and the admin form, but not `through.objects.bulk_create()` (a raw ORM path, no request reaches it).

### 3. Write paths (Risk #2)

| Write path | What the request can carry | Where foreign ids are refused | Branch |
|---|---|---|---|
| `garments:add` POST | `photo` (file), `type`, `type_other`, `description`: `GarmentForm.Meta.fields` (`garments/forms.py:25-27`) | nothing to refuse. `owner` and `photo` aren't form fields; `_store_garment` sets `garment.owner = owner` and `garment.photo = image` from `request.user` and the new upload (`garments/views.py:33-41`). The model rule (`garments/models.py:105`) is the backstop. | master |
| `outfits:compose` POST | `name`, `garments` (list of UUIDs) | 1) `OutfitForm.__init__` sets `self.fields['garments'].queryset = Garment.objects.filter(owner=owner)` (`outfits/forms.py:31-36`), so a foreign id fails as *invalid choice* before anything is stored; 2) `m2m_changed` guard at `form.save_m2m()` (`outfits/views.py:81`, `outfits/signals.py`) | PR #2 |
| `outfits:compose` name uniqueness | `name` | scoped to the owner in the form (`outfits/forms.py:38-42`) and in the DB (`UniqueConstraint(Lower('name'), 'owner')`, `outfits/models.py:64-69`); another user's name doesn't collide | PR #2 |
| gate | none (GET-only use; POST → 404, probed) | — | master |
| admin add/change | any field | staff only; `raw_id_fields` avoids cross-user select lists (`garments/admin.py:14`, `outfits/admin.py:14`); the M2M guard applies | out of scope (§7) |

**Write paths that don't exist yet** (from roadmap, test-plan §2 #2), each a future owner-scoped view:

- S-04: upload an outfit photo;
- S-05: add or remove a tag, filter by tag;
- S-06: edit or delete a garment;
- S-07: edit or delete an outfit.

Every one needs the object loaded with an owner filter. The current `OutfitForm.__init__(self, data=None, *, owner)` takes no `instance` (`outfits/forms.py:31`), so S-07's edit form will change this signature.

### 4. Media naming and serving, dev vs prod

- **The gate is the only byte path**: `privatemedia/views.py:1`; `FileResponse(..., as_attachment=False)` after the owner lookup; `Cache-Control: private, max-age=0, must-revalidate`, placed above `@condition` so 304s carry it too (`privatemedia/views.py:46-51`). A missing file on disk is a 404 plus a log line (`privatemedia/views.py:63-71`).
- **The route takes only a UUID**: `media/<uuid:pk>/` (`privatemedia/urls.py:14`). No filename or path segment, so path traversal can't happen.
- **`MEDIA_URL = 'media/'`** (`outfits_garderobe/settings.py:212`) shares the gate's prefix, but `ImageField.url` gives `/media/private/<hex>.<ext>`, which no pattern matches. `test_get_absolute_url_is_the_gate_and_image_url_is_dead` pins this (`privatemedia/tests/test_gate.py:93-106`).
- **`MEDIA_ROOT`**: in DEBUG, `$MEDIA_ROOT` or `BASE_DIR/'media'`; outside DEBUG it's required from the environment, in prod `/data/media` on the Railway volume (`outfits_garderobe/settings.py:205-208`; roadmap F-01).
- **WhiteNoise** serves only `STATIC_ROOT` (`staticfiles/`) plus, under DEBUG, the finders (`STATICFILES_DIRS = [BASE_DIR/'static']`, `settings.py:191`); `WHITENOISE_ROOT` is unset. **No `static()` helper** in the URLconf (comment at `outfits_garderobe/urls.py:41-43`).
- **Config guards already pin this**, in `privatemedia/tests/test_storage_config.py`:
  - `MEDIA_ROOT` outside `STATIC_ROOT` (`:26-33`);
  - no pattern uses `django.views.static.serve` or a `document_root` kwarg (`:36-38`);
  - the same check with the URLconf re-imported under `DEBUG=True` (`:41-57`);
  - `WHITENOISE_ROOT` doesn't cover `MEDIA_ROOT` (`:65-79`).
- **Unguarded edge (low):** nothing checks that `MEDIA_ROOT` stays out of `STATICFILES_DIRS`. Under DEBUG, WhiteNoise's finders and runserver would serve it at `/static/…`. The current default (`BASE_DIR/'media'`) is safe. This sits on the #1/#4 boundary, probably Phase 2 territory.
- **Probe results** (stranger logged in, owner's image, PR #2 tree):

  | Request | Result |
  |---|---|
  | `GET` with owner's `If-None-Match` | 404 (not 304) |
  | `GET` with owner's `If-Modified-Since` | 404 |
  | `HEAD` | 404 |
  | `POST` | 404 |
  | uppercase UUID | 404 (resolver; `uuid` converter is lowercase-only) |
  | 32-hex UUID without dashes | 404 |
  | no trailing slash | 301 → gated URL (then 404) |
  | `image.url` (`/media/private/<hex>.png`) | 404 |

  Existing tests cover the plain stranger 404, anonymous → login, identical 404 bodies without validator headers, and 304 for the owner. They **don't** cover the stranger-with-validator-headers case or HEAD.

### 5. Existing cross-user test coverage

Test base: **101 tests** on master, **147** on PR #2 (collected 2026-09-13). Shared fixtures in `conftest.py:6-25`: `temp_media_root` (opt-in), `owner`, `stranger`. Both users are plain `create_user(username=...)` rows with no email and no allauth `EmailAddress`. That's fine with `force_login`, but they don't match real accounts (the email-as-username accounts in `accounts/tests/test_smoke.py:24-33`).

Per-slice two-user tests that exist:

| Surface | Test | What it asserts | Body-checked? |
|---|---|---|---|
| gate | `privatemedia/tests/test_gate.py:59` `test_second_user_gets_404` | status 404 | status only; the body is the generic 404, and `:78-90` proves both 404s are byte-identical |
| gate | `:65` anonymous → `LOGIN_URL`; `accounts/tests/test_smoke.py:121-129` follows it to a rendered login page | redirect target | — |
| gate | `:78` `test_the_two_404s_are_indistinguishable` | same content, no `ETag`/`Last-Modified` | yes |
| garment list | `garments/tests/test_views.py:59` | stranger's page has neither description nor `photo_url` of owner's garments | yes |
| garment photo | `garments/tests/test_views.py:77` | owner fetches the tile `src` (200); stranger gets 404 | status |
| garment list/add | `garments/tests/test_views.py:51` | anonymous GET → login | — |
| garment model | `garments/tests/test_model.py:94` `test_photo_of_another_user_is_rejected` | model rule | DB |
| compose | `outfits/tests/test_views.py:50,58` [PR #2] | anonymous GET → login; anonymous POST → login **and no `Outfit` stored** | DB |
| picker | `:69` [PR #2] | foreign garment's `photo_url`, description and pk absent from the page | yes |
| compose foreign id | `:158` [PR #2] | 200 with `garments` error, no `Outfit`, `foreign.outfits.count() == 0` | DB re-read |
| detail | `:237` [PR #2] | owner sees every garment `photo_url`; stranger 404; random UUID 404 | owner body; stranger status |
| grid | `:271` [PR #2] | stranger's grid has none of owner's outfit names, detail URLs, garment `photo_url`s | yes |
| M2M guard | `outfits/tests/test_model.py:122,135` [PR #2] | foreign add raises from both sides; link table empty | DB |
| outfit names | `outfits/tests/test_model.py:63,97` [PR #2] | another user's names don't affect default naming or uniqueness | DB |

**Test helpers are duplicated.** `_garment(user)` in `garments/tests/test_views.py:34-38` and `make_garment(user)` in `outfits/tests/test_model.py:28-33` [PR #2] both build a `PrivateImage` and a `Garment`. `outfits/tests/test_views.py:19` imports `make_garment` from another test module. A cross-cutting privacy test would need a shared factory (e.g. in `conftest.py`). The add-garment impl-review already moved `owner`/`stranger` there for the same reason (`context/changes/add-garment/reviews/impl-review.md:151-153`).

### 6. Gaps against the Risk Response Guidance

These are the risk-#1/#2 behaviours the guidance names that no test currently proves.

**Risk #1**
- **No route-enumerating check.** Nothing fails when a new project route is added without a two-user test. This is the central Phase 1 deliverable and doesn't exist in any form.
- **Anonymous POST to `garments:add` isn't tested** (only GET, `garments/tests/test_views.py:51`). Compose has it [PR #2].
- **Gate: stranger with the owner's validator headers, and HEAD**, aren't pinned (probed OK today).
- **Detail stranger denial checks status only.** It's safe today because the 404 body is Django's generic page; a custom `404.html` or a view that renders a "not found" template with context would break that assumption silently.
- **Garment photos inside the compose picker, detail and grid** aren't fetched through the gate by a stranger. Tests assert the URLs are absent from the stranger's page, and the gate test proves a stranger can't fetch a photo in general; no test ties a photo URL rendered for the owner on those pages to a stranger fetch.

**Risk #2**
- **`garments:add` ignoring posted `owner`/`photo`/`id` fields** isn't pinned. The protection is structural (fields aren't in `Meta.fields`); a later edit that switches to `fields = '__all__'` or adds `owner` to the form wouldn't fail any test.
- **An invalid compose POST with a foreign id re-renders the picker.** No test asserts that the re-render still lacks the foreign garment's photo, description or pk. By construction it can't appear, since the form's queryset is owner-scoped.
- **No write paths exist yet for edit, delete or tag** (S-04 to S-07), so there's nothing to test today. Phase 1's value there is the pattern and the enumeration net that forces each of those slices to register its routes.

### 7. What a route-enumerating check can hook into

- **Walking the resolver**: `privatemedia/tests/test_storage_config.py:12-17` already has `_flatten(patterns)` over `get_resolver().url_patterns`. The probe extended it to carry the prefix and namespace. On PR #2 it lists 70 routes.
- **Telling project routes from third-party ones**: `pattern.callback.__module__`. Project modules are `outfits_garderobe.urls`, `accounts.views`, `garments.views`, `outfits.views`, `privatemedia.views`. Admin callbacks are `django.contrib.admin.*`, `django.contrib.auth.admin`, `django.contrib.contenttypes.views`, `django.views.generic.base`. allauth callbacks are `allauth.account.views`. Namespaces also partition cleanly: `admin`, `garments`, `outfits`, `privatemedia`, un-namespaced `account_*`.
- **Spotting a login guard**: Django 6.0.8's `user_passes_test` (and therefore `login_required`) sets `_view_wrapper.login_url` and `redirect_field_name` on the wrapper ("Attributes used by LoginRequiredMiddleware", `.venv/.../django/contrib/auth/decorators.py`, just before `return wraps(view_func)(_view_wrapper)`). Probe results: the 6 owner-scoped project views on PR #2 have it; `health` and `home` don't. A class-based view using `LoginRequiredMixin` would **not** carry the attribute (it would show `view_class`). No project view is class-based today.
- **Default-deny alternative (production code, not a test)**: Django ≥5.1 ships `LoginRequiredMiddleware` plus `@login_not_required` (`decorators.py`, `login_not_required` sets `view_func.login_required = False`). With it, `health`/`home` and allauth's anonymous screens would need explicit opt-out. That's a design choice for `/10x-plan`. Either way it only handles authentication, not ownership, which the test plan says a test must prove.
- **Building a URL for a parametrized route**: route patterns expose `pattern.pattern.converters` (e.g. `{'pk': UUIDConverter}`). A check can require every owner-scoped route with a `<uuid:…>` segment to have a registered factory that makes an owner's object and returns kwargs. It can also require every owner-scoped route without params (lists, grid, compose) to have registered "owner markers" to look for in a stranger's body.
- **Registry shape implied by the code**: three kinds of project route exist today. The route set is small, so an explicit allowlist or registry that fails on any unregistered project route stays cheap.
  1. **public** (`health`, `home`);
  2. **owner-scoped read** (`wardrobe`, `garments:list`, `outfits:detail`, `privatemedia:image`);
  3. **owner-scoped write** (`garments:add`, `outfits:compose`).

## Code References

Master (`29fe28a`):
- [`outfits_garderobe/urls.py:29-45`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/outfits_garderobe/urls.py#L29-L45) - root URLconf; the gate is included last; `static()` warning
- [`privatemedia/views.py:15-27`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/privatemedia/views.py#L15-L27) - `_owned_image`: one pk+owner query, cached on the request
- [`privatemedia/views.py:46-73`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/privatemedia/views.py#L46-L73) - gate decorators order and the 404 on missing file
- [`privatemedia/models.py:15-19`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/privatemedia/models.py#L15-L19) - UUID storage names
- [`privatemedia/models.py:67-74`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/privatemedia/models.py#L67-L74) - `get_absolute_url` is the gate; `.url` is dead
- [`privatemedia/urls.py:14`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/privatemedia/urls.py#L14) - `media/<uuid:pk>/`
- [`garments/models.py:103-117`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/garments/models.py#L103-L117) - photo-owner rule; `photo_url`
- [`garments/views.py:12-41`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/garments/views.py#L12-L41) - owner-scoped list; add sets owner/photo server-side
- [`garments/forms.py:25-27`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/garments/forms.py#L25-L27) - `Meta.fields` excludes owner/photo
- [`accounts/views.py:13-36`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/accounts/views.py#L13-L36) - `home` redirect; `wardrobe` placeholder (replaced by PR #2)
- [`outfits_garderobe/settings.py:194-220`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/outfits_garderobe/settings.py#L194-L220) - `MEDIA_ROOT`/`MEDIA_URL` rules
- [`outfits_garderobe/settings.py:278`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/outfits_garderobe/settings.py#L278) - `LOGIN_URL` as a path (tests compare against it)
- [`conftest.py:6-25`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/conftest.py#L6-L25) - `temp_media_root`, `owner`, `stranger`
- [`privatemedia/tests/test_gate.py:59-106`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/privatemedia/tests/test_gate.py#L59-L106) - gate denial tests
- [`privatemedia/tests/test_storage_config.py:12-79`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/privatemedia/tests/test_storage_config.py#L12-L79) - `_flatten` resolver walk; media-serving config guards
- [`garments/tests/test_views.py:51-86`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/29fe28a188af1e19990282800a62fda024beff99/garments/tests/test_views.py#L51-L86) - anonymous and stranger garment tests

PR #2 (`f7c81bf`, `feat/compose-outfit`):
- [`outfits/views.py:18-58`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/f7c81bf/outfits/views.py#L18-L58) - grid, compose, detail; all owner-scoped
- [`outfits/forms.py:31-36`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/f7c81bf/outfits/forms.py#L31-L36) - picker queryset scoped to owner
- [`outfits/signals.py:16-27`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/f7c81bf/outfits/signals.py#L16-L27) - `m2m_changed` foreign-garment guard, both directions
- [`outfits/models.py:49-75`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/f7c81bf/outfits/models.py#L49-L75) - owner FK, M2M, per-owner unique name
- [`outfits_garderobe/urls.py:37-39`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/f7c81bf/outfits_garderobe/urls.py#L37-L39) - `wardrobe/` moves to outfits
- [`outfits/tests/test_views.py:50-293`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/f7c81bf/outfits/tests/test_views.py#L50-L293) - anonymous, picker, foreign id, detail, grid two-user tests
- [`outfits/tests/test_model.py:28-33`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/f7c81bf/outfits/tests/test_model.py#L28-L33) - `make_garment` factory (imported cross-module)
- [`outfits/tests/test_model.py:122-142`](https://github.com/c-i-a-s-t-e-k/outfits-garderobe/blob/f7c81bf/outfits/tests/test_model.py#L122-L142) - M2M guard tests

## Architecture Insights

- **"Rules on every path."** Validation lives on the model (`full_clean()` in `save()`, DB constraints, the `m2m_changed` guard). Forms narrow the choices; views never take an owner from the request. The compose-outfit plan names this pattern explicitly (`context/changes/compose-outfit/plan.md:10` on PR #2). A privacy contract test should assert the outcome over HTTP and re-read the DB, not re-test each layer.
- **One ownership answer for bytes.** Every photo is a `PrivateImage` with its own `owner`. Garments (and, later, S-04 outfit photos) point at it instead of having their own file field (`privatemedia/models.py:22-28`). A new photo-bearing view therefore can't add a new byte path unless someone deliberately writes one. The enumeration check is what would catch that.
- **The route name is the contract.** Redirects and tests reverse names (`wardrobe`, `garments:list`), not paths (`accounts/views.py:1-6`). A registry keyed by route name survives moves like PR #2's `wardrobe` relocation.
- **Every denial is the same 404.** "No such object" and "not yours" are one 404, with no validator headers. That's an existing, tested property to keep for every new owner-scoped route, not only the gate.
- **The test style already fits the guidance.** Recent tests check for absent body markers and re-read the DB (`outfits/tests/test_views.py:1-4`: "Every assertion re-reads the database rather than trusting a status code"). Phase 1 can generalise this style instead of inventing one.

## Historical Context (from prior changes)

- `context/changes/private-media-gate/plan.md:47-49`: one central `PrivateImage` so the ownership check lives in one place; UUID addressing is defence in depth; the same 404 for "doesn't exist" and "not yours".
- `context/changes/private-media-gate/plan.md:59`: never add `static()`; `MEDIA_URL` matches the gate route.
- `context/changes/private-media-gate/reviews/impl-review.md:61`: `.url` is a hard 404 everywhere, including the admin `ImageField` widget. It fails closed, but it's the "public-serving temptation" the test plan cites for Risk #1.
- `context/changes/private-media-gate/reviews/impl-review.md:140`: `WHITENOISE_ROOT` was unguarded; later pinned by `test_whitenoise_does_not_cover_media_root`.
- `context/changes/add-garment/plan.md:199,300-301`: garment slice's own ownership tests (foreign photo rejected, stranger list/photo).
- `context/changes/add-garment/reviews/impl-review.md:151-153`: `owner`/`stranger`/`temp_media_root` fixtures moved to `conftest.py` at the third app; no `autouse`, because of `test_storage_config`.
- `context/changes/user-accounts/plan.md:305,624`: the dev/prod `stranger` account (blank email) was a F-01 test artifact, deleted at the allauth cutover. Real accounts are email-as-username plus a verified `EmailAddress`.
- `context/changes/compose-outfit/plan.md:14,40` (PR #2): the slice ships its own two-account tests because Phase 1 hadn't started, and **explicitly defers "the route-enumerating privacy net across all apps" to test-plan §3 Phase 1**.
- `context/changes/compose-outfit/plan.md:27,106-110` (PR #2): why the M2M guard is a signal (M2M writes skip `save()`); it's the model-level half of Risk #2.

## Related Research

None. This is the first `research.md` under `context/changes/`; earlier changes went straight from `change.md` to `plan.md`.

## Open Questions

1. **Merge order.** Should Phase 1 implementation wait until PR #2 merges and this branch is rebased? Recommended: yes. Otherwise the enumeration check and any `wardrobe` assertions are written against a placeholder that PR #2 deletes, and PR #2 and Phase 1 conflict in `conftest.py` if a shared garment factory is added.
2. **Registry vs duplication.** How much should Phase 1 duplicate the per-slice two-user tests that already exist (gate, garment list, picker, detail, grid, foreign compose id)? Two options:
   - a cross-cutting parametrized contract (anonymous → login, stranger → 404 or absent body markers, foreign write → nothing persisted) plus deleting nothing;
   - the enumeration net plus gap tests only.

   This is a cost × signal call for `/10x-plan`.
3. **How a route declares itself.** Options: an explicit registry in the test module (fails on an unregistered project route), or a marker on the view (attribute or decorator) read by the test. The second touches production code. Both rely on the `callback.__module__` partition in §7.
4. **`LoginRequiredMiddleware`.** Should Phase 1 recommend default-deny authentication (Django ≥5.1) as a production change, or keep per-view `@login_required` and only test it? Not required by the test plan; it makes "forgot the decorator" impossible but doesn't touch ownership.
5. **Fixture realism.** Should the privacy contract use allauth-shaped users (email-as-username plus a verified `EmailAddress`), like `accounts/tests/test_smoke.py:24-33`, instead of the bare `owner`/`stranger` fixtures? `force_login` makes it irrelevant to the outcome today.
6. **`MEDIA_ROOT` vs `STATICFILES_DIRS`.** This unpinned edge (DEBUG only) belongs to Phase 2 (#4 config pins) rather than Phase 1. Confirm the split when planning.
