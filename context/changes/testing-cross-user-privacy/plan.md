# Cross-user Privacy Contract Implementation Plan

## Overview

Test-plan §3 Phase 1 (risks #1 and #2). The goal is a durable, cross-cutting proof that no photo or owner record crosses accounts, on reads and on writes. A new owner-scoped route must pick up that proof automatically, before roadmap S-04 to S-07 add more views.

Delivery has two parts:

- **One production change**: default-deny authentication via Django's `LoginRequiredMiddleware`.
- **A new top-level `tests/` package organised by risk.** Each risk gets a folder, and each file in it covers one failure scenario. Files are not named after the module they exercise.

## Current State Analysis

The research (`context/changes/testing-cross-user-privacy/research.md`) is the baseline.

**Protection works today:**
- Ownership comes only from `request.user`.
- A denial is one 404, and it is identical for a stranger and for a missing id.
- Writes are refused by an owner-scoped form queryset, backed by model rules: `Garment.clean()`, and the `m2m_changed` guard on PR #2.

**Existing tests:**
- Each slice has its own two-user tests in `garments/tests/test_views.py`, `outfits/tests/test_views.py` [PR #2] and `privatemedia/tests/test_gate.py`.
- Nothing is cross-cutting. No test enumerates routes.
- Research §6 lists the gaps:
  - gate HEAD and validator headers with a stranger;
  - anonymous POST to `garments:add`;
  - posted `owner`/`photo` fields ignored;
  - a refused compose re-render without foreign markers;
  - photos rendered on the owner's pages not fetched by a stranger.

**Authentication is per view.**
- Every owner-scoped view has `@login_required`.
- A new view that forgets the decorator is caught by nothing.

**Tests live in per-app `tests/` packages** and are named after modules (`test_views.py`, `test_model.py`). The garment factory is duplicated: `_garment` in `garments/tests/test_views.py:34`, and `make_garment` in `outfits/tests/test_model.py:28`, imported across modules by `outfits/tests/test_views.py:19` [PR #2].

**Sequencing:** PR #2 (`feat/compose-outfit`) is open. It moves `wardrobe` into `outfits` and adds compose and detail. This plan targets the tree **after** PR #2 merges.

## Desired End State

**Middleware and routes**
- `LoginRequiredMiddleware` is active.
- Only `health` and `home` among project views opt out, with `@login_not_required`.
- Railway's healthcheck still gets 200.

**Test layout**
- A top-level `tests/` package contains:
  - `tests/CLAUDE.md`: the layout rule and how to add a route or scenario.
  - `tests/factories.py`: shared object builders.
  - `tests/owner_scoped_routes.py`: the registry of every guarded project route and how to seed it.
  - `tests/cross_user_visibility/` (risk #1): one file per failure scenario.
  - `tests/foreign_id_writes/` (risk #2): one file per failure scenario.

**The net**
- Adding a guarded project route without a registry entry makes `uv run pytest` fail, and names the route.
- So does registering a route that opted out of login.
- So does removing the middleware.

**Registered routes are covered automatically**, with no per-route test code:
- anonymous GET and POST go to login and store nothing;
- a stranger gets a 404 identical to a missing-id 404, or a page with none of the owner's markers;
- a stranger's write aimed at the owner's objects changes nothing in the database.

**Docs:** test-plan §6.1 describes the pattern, and §6.6 carries the phase note.

**How to verify:**
- `uv run pytest` is green.
- `uv run ruff check .` and `uv run ruff format --check .` are clean.
- The sabotage checks in the Phase 2 and Phase 3 manual verification fail as expected, then pass again once reverted.

### Key Discoveries:

- **The middleware checks one attribute.** `LoginRequiredMiddleware.process_view` does `getattr(view_func, "login_required", True)` (`.venv/.../django/contrib/auth/middleware.py`). Class-based views inherit `dispatch`'s attributes through `view.__dict__.update(cls.dispatch.__dict__)` (`django/views/generic/base.py:119`). So one attribute tells the net whether any route is guarded.
- **Probe on the PR #2 tree with Django 6.0.8 and allauth 65.19.3** (scratchpad only):
  - project views `health/` and `home` are **guarded by default**, so both need an opt-out;
  - allauth already marks login, signup, password reset, confirm-email and login-code as `login_not_required`;
  - `account_logout`, `account_email` and `account_change_password` become guarded, which is correct;
  - `admin:login` is opted out.
- **Railway fails a deploy on anything but 200 from `/health/`** (`railway.toml:18`). This is already pinned by `accounts/tests/test_deploy_config.py:84` (`test_healthcheck_is_not_redirected_to_https`), which asserts 200.
- **`home` must keep its own redirect.** It sends anonymous visitors to `LOGIN_URL` without `next` (`accounts/views.py:12-24`). The middleware would add `?next=/`, so opting out keeps today's behaviour, which `accounts/tests/test_smoke.py:78` pins.
- **A resolver walk already exists.** `_flatten` in `privatemedia/tests/test_storage_config.py:12` walks `get_resolver().url_patterns`. The net needs a version that also carries the namespace and the route's converters.
- **Project and third-party routes separate by `callback.__module__`.** Project modules: `outfits_garderobe.urls`, `accounts.views`, `garments.views`, `outfits.views`, `privatemedia.views`. Third-party: `django.contrib.*`, `django.views.generic.*`, `allauth.*` (research §7).
- **The suite runs with `DEBUG=False` and no custom `404.html`** (`outfits_garderobe/settings_test.py`). Comparing a stranger's body with a random-UUID body is therefore meaningful, and would catch a future 404 template that leaks context.
- **Denied gate responses carry no `ETag`/`Last-Modified`** (`privatemedia/views.py:30-43`). That property now extends to every parametrized owner-scoped route.
- **The existing test style is the model.** The docstring at `outfits/tests/test_views.py:1-4` [PR #2] says "Every assertion re-reads the database rather than trusting a status code". Body-marker assertions follow `garments/tests/test_views.py:59`.
- **`tests/factories.py` will be importable.** pytest's `prepend` import mode puts the rootdir on `sys.path` for packages with `__init__.py`, and pytest-django adds the `manage.py` directory. So `from tests.factories import make_garment` resolves.

## What We're NOT Doing

- **Not rewriting or deleting the per-slice two-user tests.** They stay; only their garment-factory import changes. Some scenarios end up asserted twice, on purpose.
- **No "any unclassified route" rule.** The net fails only on a guarded project route that isn't registered, and on a registered route that opted out. A new public route is caught only if it wrongly carries `@login_not_required`. Opting out is an explicit, visible act, and the middleware makes forgetting a decorator harmless.
- **Not removing the existing `@login_required` decorators.** They stay as defence in depth if the middleware is ever dropped. The pin test also guards against that.
- **Not testing Django admin or allauth mechanics** (§7). Allauth routes are outside the net. The admin redirect change (anonymous `/admin/` → `/accounts/login/?next=/admin/` instead of `/admin/login/`) is accepted without a test.
- **Not testing `through.objects.bulk_create()`** bypassing the M2M guard. It's a raw ORM path that no request reaches.
- **Not pinning `MEDIA_ROOT` outside `STATICFILES_DIRS`.** That's Phase 2 (#4 config pins).
- **Not testing S-04 to S-07 write paths.** They don't exist yet. The registry forces each slice to add its entry.
- **Not switching fixtures to allauth-shaped users.** `force_login` with the existing `owner`/`stranger` fixtures (`conftest.py`) doesn't change any outcome.
- **No CI, hooks or `pyproject.toml` `testpaths` changes.** Default discovery already collects `tests/`.

## Implementation Approach

**Precondition:** PR #2 is merged into `master` and `feat/teasting-cross-user-privacy` is rebased on it. Implementation starts only then.

**Production change first.** Phase 1 adds the middleware and the scaffold. Later phases can then rely on "guarded unless opted out" and one shared factory.

**The registry is the contract.** `tests/owner_scoped_routes.py` maps each guarded project route name to a declaration:

- its kind: owner-scoped *read* or *write*;
- a seeder that builds the owner's data and returns URL kwargs plus the markers (names, descriptions, photo URLs, pks) that must never reach another user;
- for writes, a builder for a hostile POST payload that points at the owner's objects.

The scenario files in both risk folders parametrize over the registry. The net test compares the registry with the resolver. So registering a new route is the only step needed to put it under every contract.

**Two write invariants.** Write scenarios check the database rather than the status code:

1. the owner's rows (images, garments, outfits, outfit–garment links) are unchanged;
2. no row anywhere references an object of a different owner (garment ↔ photo, outfit ↔ garment).

**Layout rule:**
- A folder under `tests/` is a test-plan §2 risk.
- A file is one failure scenario, named as a sentence that describes the protection (`test_<scenario>.py`).
- Per-app `tests/` packages keep module-level behaviour.

## Critical Implementation Details

- **Ordering.** Place `LoginRequiredMiddleware` after `AuthenticationMiddleware`, because it reads `request.user`. Add `@login_not_required` to `health` and `home` in the same commit. Without it, `test_healthcheck_is_not_redirected_to_https` and the root smoke tests go red, and a deploy would never turn healthy.
- **Net detection.** A route is "guarded" when `getattr(callback, 'login_required', True)` is not `False`. Don't use the `login_url` attribute that `@login_required` leaves behind: under default-deny an undecorated view is guarded too, and the net must still demand its registration.
- **Stranger comparison.** For a route with a `<uuid:…>` segment, compare the stranger's response for the owner's id with the stranger's response for a fresh `uuid4()`: status, body bytes, and missing validator headers. Asserting only `404` wouldn't catch a "not found" page that renders the object's name.

## Phase 1: Default-deny login and test scaffold

### Overview

Make authentication default-deny, create the `tests/` package with a shared factory module, point the slice tests at it, and pin the middleware.

### Changes Required:

#### 1. Default-deny middleware

**File**: `outfits_garderobe/settings.py`

**Intent**: Every view needs a logged-in user unless it explicitly opts out, so an owner-scoped view that forgets `@login_required` is still closed to anonymous visitors.

**Contract**: `'django.contrib.auth.middleware.LoginRequiredMiddleware'` goes in `MIDDLEWARE` after `AuthenticationMiddleware`. Its comment explains why (it reads `request.user`; public views opt out with `@login_not_required`).

#### 2. Public project views opt out

**File**: `outfits_garderobe/urls.py`, `accounts/views.py`

**Intent**: The healthcheck and the root redirect keep answering anonymous visitors exactly as they do today.

**Contract**: `health` and `home` are decorated with `django.contrib.auth.decorators.login_not_required`. Each gets a one-line comment on why it's public: Railway probe; `/` routes by auth state.

#### 3. Test package and shared factories

**File**: `tests/__init__.py`, `tests/factories.py`

**Intent**: One importable place builds owner-scoped objects, so risk-folder tests and slice tests don't copy helpers between each other.

**Contract**: `tests/factories.py` exposes:
- `make_image(user)`: a tiny in-memory PNG `PrivateImage`;
- `make_garment(user, type=GarmentType.SHIRT, **fields)`: builds its own photo;
- `make_outfit(user, garments=(), **fields)`.

Its docstring states the files need a `temp_media_root`. The existing `owner`, `stranger` and `temp_media_root` fixtures stay in the root `conftest.py`.

#### 4. Slice tests use the shared factory

**File**: `garments/tests/test_views.py`, `outfits/tests/test_model.py`, `outfits/tests/test_views.py` (plus any other importer of `make_garment` after the rebase)

**Intent**: Remove the duplicated `_garment` and the cross-module import of `make_garment`, without changing any assertion.

**Contract**: `_garment(...)` call sites and the `make_garment` definition are replaced by `from tests.factories import make_garment`. Test names and assertions are unchanged, and the collected test count stays the same.

#### 5. Middleware pin

**File**: `tests/cross_user_visibility/__init__.py`, `tests/cross_user_visibility/test_login_is_required_unless_a_view_opts_out.py`

**Intent**: Pin the default-deny layer that the Phase 2 net relies on, so removing or reordering it fails loudly.

**Contract**: Two tests:
1. `LoginRequiredMiddleware` is in `settings.MIDDLEWARE` after `AuthenticationMiddleware`.
2. Among project routes, the set of views with `login_required is False` is exactly `{health, home}`. Adding an opt-out means a deliberate edit to this test, with a reason.

### Success Criteria:

#### Automated Verification:

- Full suite passes, including the healthcheck, root-redirect and allauth smoke tests: `uv run pytest`
- Middleware pin tests pass: `uv run pytest tests/cross_user_visibility/test_login_is_required_unless_a_view_opts_out.py`
- No test module defines or cross-imports a garment factory any more: `grep -rn "def _garment\|def make_garment\|from outfits.tests" --include=*.py accounts garments outfits privatemedia` returns nothing
- Lint and format are clean: `uv run ruff check . && uv run ruff format --check .`
- Django system checks pass: `uv run python manage.py check`

#### Manual Verification:

- On `runserver`, logged out: `/health/` returns JSON 200, `/` goes to the login page, and login, signup and password reset render. `/garments/` and `/wardrobe/` go to login with `next`.
- After the next Railway deploy, the healthcheck turns green and prod serves the new build (can be deferred to the deploy that ships this change).

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: Risk #1 — cross-user visibility

### Overview

Add the route registry and the net, plus the registry-driven read contract and the gate-specific gap scenarios. Each lives in its own scenario file under `tests/cross_user_visibility/`.

### Changes Required:

#### 1. Route registry

**File**: `tests/owner_scoped_routes.py`

**Intent**: One declaration per guarded project route tells every contract test how to seed the owner's data and what must never leak. This file is the only thing a new slice edits to get coverage.

**Contract**: A mapping from route name to a small declaration:
- `kind`: `read` or `write`;
- `seed(owner) -> Seeded`: `Seeded` holds the `reverse` kwargs (empty for parameterless routes) and `markers`, a list of strings (names, descriptions, photo URLs, pks) that belong only to the owner;
- for `write` routes, `foreign_payload(seeded, requester) -> dict`: a POST body that points at the owner's objects (used in Phase 3).

It also exposes `project_routes()`. That walks the resolver and yields `(name, pattern, callback)` for callbacks whose module is in the project (the `callback.__module__` partition from Key Discoveries), keeping the namespace so names match `reverse`.

Initial entries:
- `wardrobe` (read)
- `outfits:detail` (read, uuid)
- `privatemedia:image` (read, uuid)
- `garments:list` (read)
- `garments:add` (write)
- `outfits:compose` (write)

#### 2. The net

**File**: `tests/cross_user_visibility/test_new_guarded_route_cannot_skip_the_contract.py`

**Intent**: Nobody has to remember to add a privacy test for a new owner-scoped view. The suite fails until the route is registered.

**Contract**:
- One test fails with the list of guarded project routes (`login_required` not `False`) that aren't in the registry.
- One test fails for any registered route whose view opted out of login.
- Every registry name must reverse. A stale entry fails with a clear message.

#### 3. Anonymous visitor contract

**File**: `tests/cross_user_visibility/test_anonymous_visitor_only_reaches_login.py`

**Intent**: An anonymous visitor gets nothing from any registered route: no owner data, no stored rows. This covers the anonymous `garments:add` POST gap.

**Contract**: Parametrized over the registry, and GET and POST for each route:
- the response is 302 to `settings.LOGIN_URL`;
- the body contains none of the seeded markers;
- the counts of `PrivateImage`, `Garment` and `Outfit` rows are unchanged.

#### 4. Stranger read contract

**File**: `tests/cross_user_visibility/test_stranger_sees_nothing_of_the_owner.py`

**Intent**: Authentication isn't ownership. A logged-in stranger can neither load the owner's objects nor see their data on the stranger's own pages.

**Contract**: Parametrized over registry routes (read and write GETs).
- **Routes with URL kwargs** (the owner's id): the stranger's response equals the stranger's response for a fresh `uuid4()`. Status 404, identical body bytes, no `ETag`/`Last-Modified`, no markers.
- **Parameterless routes**: status 200, and none of the owner's markers appear in the body. This covers the grid, the garment list and the compose picker choice list.

#### 5. Photos on owner pages stay owner-only

**File**: `tests/cross_user_visibility/test_photos_shown_to_the_owner_stay_owner_only.py`

**Intent**: Close the gap where no test links a photo URL rendered on the owner's page to a stranger fetching it.

**Contract**: For every `read`/`write` registry route that renders `<img src>` for the owner (grid, list, picker, detail):
- every `src` on the owner's page returns 200 for the owner;
- the same URL returns 404 for the stranger and for a logged-out client (302 to login);
- at least one `src` is collected per route, so the test can't pass vacuously.

#### 6. Media URL forms don't get past the gate

**File**: `tests/cross_user_visibility/test_media_url_variants_do_not_bypass_the_gate.py`

**Intent**: Pin the probed behaviours no test covers today.

**Contract**: With the owner's image and the stranger logged in:
- GET with the owner's `If-None-Match` → 404 (not 304), no validators;
- GET with the owner's `If-Modified-Since` → 404, no validators;
- HEAD → 404;
- POST → 404;
- uppercase UUID and dashless 32-hex → 404;
- missing trailing slash → followed to 404, never 200;
- `image.url` (`/media/private/<hex>.<ext>`) → 404.

The owner's validator values come from the owner's own 200 response, not from the implementation.

### Success Criteria:

#### Automated Verification:

- The risk #1 folder passes: `uv run pytest tests/cross_user_visibility`
- Full suite passes: `uv run pytest`
- Every registry route is exercised by the anonymous, stranger and photo contracts (no empty parametrization): `uv run pytest tests/cross_user_visibility -v` shows one case per registered route in each contract file
- Lint and format are clean: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

Run each sabotage check on a scratch edit, confirm the named test fails, then revert:
- (a) add `path('wardrobe/export/', some_view)` with no decorator → the net fails and names it;
- (b) drop `owner=request.user` from `garment_list` → the stranger contract fails;
- (c) render `{{ outfit.name }}` in a custom `templates/404.html` → the identical-404 comparison fails;
- (d) add `@login_not_required` to `garment_list` → the net fails.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Risk #2 — foreign-id writes

### Overview

Add the registry-driven write contract and the two write-path gap scenarios under `tests/foreign_id_writes/`. Each checks persisted state, not the status code.

### Changes Required:

#### 1. Database invariants helper

**File**: `tests/foreign_id_writes/__init__.py`, `tests/foreign_id_writes/conftest.py`

**Intent**: Give every write scenario the same two checks: the owner's data didn't change, and no cross-owner link exists anywhere.

**Contract**:
- A fixture or helper takes a snapshot of the owner's rows (`PrivateImage`, `Garment`, `Outfit` field values, plus outfit–garment link pairs) for comparison before and after.
- A helper asserts there is no `Garment` whose `photo.owner_id != owner_id` and no outfit–garment link whose owners differ, reading the through table directly.

#### 2. Foreign write contract

**File**: `tests/foreign_id_writes/test_write_aimed_at_another_users_objects_changes_nothing.py`

**Intent**: A write carrying another user's object id is refused and leaves the database as it was, on every registered write route.

**Contract**: Parametrized over `write` registry entries. The owner's data is seeded, the stranger is logged in, and the stranger POSTs `foreign_payload`. Assertions:
- the response isn't a success redirect (`302` to a non-login URL);
- the owner's snapshot is unchanged;
- the no-cross-owner-link invariant holds.

Payloads per entry:
- `outfits:compose`: one of the stranger's own garments plus one of the owner's, and also a variant with only the owner's garments;
- `garments:add`: a valid upload plus `owner=<owner.pk>`, `photo=<owner image pk>` and `id=<owner garment pk>`.

For `garments:add` the "not refused" outcome is allowed (the upload is valid). The assertion is then that the new garment and photo belong to the stranger, and that the owner's snapshot is unchanged.

#### 3. Posted owner fields are ignored

**File**: `tests/foreign_id_writes/test_posted_owner_and_photo_fields_are_ignored.py`

**Intent**: Pin the structural protection, so that `fields = '__all__'` or adding `owner`/`photo` to `GarmentForm` fails a test.

**Contract**: The stranger posts a valid `garments:add` with the owner's `owner`, `photo` and `id` values. Re-reading the DB shows:
- exactly one new garment, owned by the stranger;
- its photo is a new `PrivateImage` owned by the stranger (not the owner's pk);
- the owner's garment count and the photo → garment link are unchanged.

#### 4. Refused compose doesn't echo the foreign garment

**File**: `tests/foreign_id_writes/test_refused_compose_does_not_reveal_the_foreign_garment.py`

**Intent**: Close the gap where the re-rendered picker after a refused foreign-id POST isn't checked for the owner's data.

**Contract**: The stranger posts compose with one own garment plus the owner's garment id. Assertions:
- 200 with a `garments` form error;
- the body contains none of the owner garment's markers (photo URL, description, pk);
- no `Outfit` is stored.

### Success Criteria:

#### Automated Verification:

- The risk #2 folder passes: `uv run pytest tests/foreign_id_writes`
- Full suite passes: `uv run pytest`
- Lint and format are clean: `uv run ruff check . && uv run ruff format --check .`

#### Manual Verification:

Run each sabotage check on a scratch edit, confirm the named test fails, then revert:
- (a) remove the owner-scoped queryset in `OutfitForm.__init__` and disconnect the `m2m_changed` guard → the foreign write contract fails;
- (b) add `'owner'` to `GarmentForm.Meta.fields` and stop assigning the owner in the view → the posted-fields test fails.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Cookbook and test guide

### Overview

Make the pattern the canonical answer to "how do I add a test for X": a local guide in `tests/`, the test-plan cookbook entry, and a pointer from the root `CLAUDE.md`.

### Changes Required:

#### 1. Test-folder guide

**File**: `tests/CLAUDE.md`

**Intent**: Future agents and the developer know where a new test goes and how a new owner-scoped route gets covered, without re-reading this plan.

**Contract**: Short sections:
- **Layout rule.** A folder is a test-plan §2 risk. A file is one failure scenario named as a sentence. Per-app `tests/` keep module behaviour. Current risk folders: `cross_user_visibility/` (#1), `foreign_id_writes/` (#2).
- **Adding an owner-scoped route.** Write the registry entry: kind, seed, markers, and `foreign_payload` for writes. The net fails until you do. Public views need `@login_not_required` plus an edit to the opt-out pin test with a reason.
- **Adding a new scenario file.** Assert behaviour from the PRD or risk, re-read the DB, check markers are absent in the body, never assert status alone.
- **Factories and fixtures.** `tests/factories.py`, the `owner`/`stranger`/`temp_media_root` fixtures in the root `conftest.py`.
- **Run commands.** Whole suite, one risk folder, one scenario.

#### 2. Test-plan cookbook

**File**: `context/foundation/test-plan.md`

**Intent**: Replace the §6.1 placeholder with the shipped pattern, and add the Phase 1 note.

**Contract**:
- §6.1: location (`tests/cross_user_visibility/`, `tests/foreign_id_writes/`), naming rule, the registry as the one step for a new route, reference tests (the net file and the stranger contract file), and the run commands.
- §6.6: a 2–3 line note: default-deny middleware adopted; `health`/`home` opt-outs; admin anonymous redirect now goes to the allauth login.
- §§1–5 stay unchanged. The §3 status is advanced by the orchestrator.

#### 3. Root pointer

**File**: `CLAUDE.md`

**Intent**: The root guide points to where tests live and how they're organised.

**Contract**: One bullet under *Conventions & gotchas*:
- risk tests live in `tests/<risk>/`, one file per scenario (see `tests/CLAUDE.md`);
- authentication is default-deny through `LoginRequiredMiddleware`.

### Success Criteria:

#### Automated Verification:

- The guide files exist and §6.1 no longer says TBD: `test -f tests/CLAUDE.md && ! grep -n "TBD — see §3 Phase 1" context/foundation/test-plan.md`
- Full suite still passes: `uv run pytest`

#### Manual Verification:

- Reading only `tests/CLAUDE.md`, you can say which file to edit to cover a hypothetical S-07 `outfits:delete` route and which scenario files would then exercise it.

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Testing Strategy

### Unit Tests:

- Middleware pin, and the opt-out set is exactly `{health, home}`.
- Net: the registry against the resolver (unregistered guarded route, registered opted-out route, stale entry).

### Integration Tests:

All use the Django test client with two users and re-read the DB.

**Risk #1**
- Anonymous GET and POST on every registered route → login, nothing stored, no markers.
- Stranger on a parametrized route → identical to a missing-id response.
- Stranger on a parameterless route → no owner markers.
- Every `<img src>` rendered for the owner → 404 for the stranger.
- Media URL variants: validator headers, HEAD, POST, case and dash forms, no slash, `.url`.

**Risk #2**
- Foreign-id write on every registered write route → owner snapshot unchanged, no cross-owner links.
- Posted `owner`/`photo`/`id` ignored on `garments:add`.
- A refused compose re-render doesn't reveal the foreign garment.

### Manual Testing Steps:

1. Phase 1: `runserver` smoke as a logged-out visitor (health, root, allauth screens, guarded pages); Railway healthcheck green after deploy.
2. Phase 2: sabotage checks (a)–(d), each failing the named test, then reverted.
3. Phase 3: sabotage checks (a)–(b), each failing the named test, then reverted.
4. Phase 4: the S-07 thought experiment against `tests/CLAUDE.md`.

## Performance Considerations

The contracts multiply (routes × methods × actors), and each case writes a few tiny PNGs to `tmp_path`. With 6 routes that's a few dozen fast tests. If it grows noticeably past S-07, parametrize seeding per module rather than per case. No action now.

## Migration Notes

No schema changes. The middleware is a behaviour change for anonymous visitors on routes that were undecorated. Today the only such project routes are `health` and `home`, and both opt out. Rollback: remove the middleware line. The kept `@login_required` decorators still protect every owner-scoped view.

## References

- Research: `context/changes/testing-cross-user-privacy/research.md`
- Test plan: `context/foundation/test-plan.md` §2 (#1, #2), §3 Phase 1, §6.1, §7
- Existing two-user style: `garments/tests/test_views.py:59`, `outfits/tests/test_views.py:1-4,158,271` [PR #2]
- Resolver walk: `privatemedia/tests/test_storage_config.py:12`
- Healthcheck pin: `accounts/tests/test_deploy_config.py:84`; `railway.toml:18`
- Root redirect: `accounts/views.py:12-24`; `accounts/tests/test_smoke.py:78`

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Default-deny login and test scaffold

#### Automated

- [x] 1.1 Full suite passes, including the healthcheck, root-redirect and allauth smoke tests — 1e4efee
- [x] 1.2 Middleware pin tests pass — 1e4efee
- [x] 1.3 No test module defines or cross-imports a garment factory any more — 1e4efee
- [x] 1.4 Lint and format are clean — 1e4efee
- [x] 1.5 Django system checks pass — 1e4efee

#### Manual

- [x] 1.6 runserver logged-out smoke: health 200, root to login, allauth screens render, guarded pages redirect with next — 1e4efee
- [ ] 1.7 Railway healthcheck green after the deploy that ships this change

### Phase 2: Risk #1 — cross-user visibility

#### Automated

- [x] 2.1 The risk #1 folder passes — 379b52c
- [x] 2.2 Full suite passes — 379b52c
- [x] 2.3 Every registry route is exercised by the anonymous, stranger and photo contracts — 379b52c
- [x] 2.4 Lint and format are clean — 379b52c

#### Manual

- [x] 2.5 Sabotage checks (a)–(d) each fail the named test, then reverted — 379b52c

### Phase 3: Risk #2 — foreign-id writes

#### Automated

- [x] 3.1 The risk #2 folder passes — 93a0957
- [x] 3.2 Full suite passes — 93a0957
- [x] 3.3 Lint and format are clean — 93a0957

#### Manual

- [x] 3.4 Sabotage checks (a)–(b) each fail the named test, then reverted — 93a0957

### Phase 4: Cookbook and test guide

#### Automated

- [x] 4.1 The guide files exist and §6.1 no longer says TBD — 9ea8e05
- [x] 4.2 Full suite still passes — 9ea8e05

#### Manual

- [ ] 4.3 S-07 thought experiment answered from tests/CLAUDE.md alone
