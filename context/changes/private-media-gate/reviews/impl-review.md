<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Prywatna brama dostępu do zdjęć użytkownika

- **Plan**: `context/changes/private-media-gate/plan.md`
- **Scope**: Phases 1–3 of 3 (full plan — all Progress checkboxes `[x]`)
- **Date**: 2026-09-09
- **Verdict**: NEEDS ATTENTION → all 10 findings triaged and fixed on 2026-09-09 (see Triage outcome)
- **Findings**: 0 critical, 7 warnings, 3 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | PASS |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | WARNING |
| Success Criteria | WARNING |

## Verification performed

All automated success criteria were re-run for this review:

| Check | Result |
|---|---|
| `uv run python manage.py check` | 0 issues |
| `uv run python manage.py makemigrations --check --dry-run` | No changes detected |
| `uv run python manage.py migrate` | clean |
| `uv run python manage.py collectstatic --noinput` | 359 post-processed |
| `uv run pytest` | **16 passed** |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 19 files already formatted |
| `uv run pip-audit` | Pillow clean; Django 6.0.5 carries 9 advisories (see F7) |
| Railway volume (3.1) | `outfits-garderobe-volume` live at `/data`, 5000 MB |
| Railway deploy (3.2/3.3) | latest deployment SUCCESS; build log confirms `collectstatic` ran in the nixpacks build phase |

The gate itself was independently probed and behaves correctly: `@login_required` is the outer
decorator so an anonymous request never reaches the database; the ownership filter is a single
combined `pk`+`owner` lookup; `_owned_image` caches the row (and the negative result) on the
request, so a request makes **exactly one** `privateimage` query — the plan's "three lookups"
warning is properly addressed; and the two 404s are byte-identical with no `ETag` or
`Last-Modified` on either. The manual-verification checkboxes (2.10–2.14, 3.4–3.7) are consistent
with observable evidence in the diff and in the live Railway state.

## Findings

### F1 — `PrivateImage.image.url` resolves to a dead URL; the plan's MEDIA_URL/gate agreement is not met

- **Severity**: ⚠️ WARNING
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Plan Adherence
- **Location**: outfits_garderobe/settings.py:135, privatemedia/urls.py:14
- **Detail**: The plan's *Critical Implementation Details* required "set `MEDIA_URL` to match the gate route so `ImageField.url` and the gate agree." Only the *prefix* agrees. Verified live:
  ```
  image.name        = private/316c626e1d134256ae2614ccda3dde4d.png
  image.url         = /media/private/316c626e1d134256ae2614ccda3dde4d.png
  reverse(gate)     = /media/b236ba14-e746-41f0-b0b3-bd7c2319c8f6/
  resolve(image.url) -> Resolver404
  ```
  `FileSystemStorage.url()` builds `MEDIA_URL + storage name` (a **file path**); the gate route consumes `<uuid:pk>` (a **row id**). They never overlap, so every `.url` is a hard 404 — including the link the Django admin's own `ImageField` widget renders, which is the plan's stated manual-verification surface. It fails closed (no leak, nothing broken in production today), but `.url` is the reflex API: an S-02/S-04 developer writes `<img src="{{ garment.image.image.url }}">`, gets a broken image, and the internet's first answer to "Django media 404" is `+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` — the exact public-serving helper this whole change exists to prevent. No test covers the mismatch. Both review agents flagged this independently; one rated it CRITICAL. It is scored WARNING here because nothing is exposed or broken today, but the impact is HIGH because it fixes the accessor contract the two unblocked slices will build on.
- **Fix A ⭐ Recommended**: Add `PrivateImage.get_absolute_url()` returning `reverse('privatemedia:image', args=[self.pk])`, document it in `change.md` as the accessor S-02/S-04 must use, and add a test asserting `.url` does not resolve while `get_absolute_url()` does.
  - Strength: Gives the downstream slices one blessed accessor and pins the contract with a test, which is what let this ship unnoticed.
  - Tradeoff: `.url` still exists and still silently 404s; discipline, not enforcement.
  - Confidence: HIGH — `reverse()` on the named route is already verified working, and the route name is already documented as a load-bearing contract in `privatemedia/urls.py:3-4`.
  - Blind spot: Does not stop the admin widget from rendering its dead link.
- **Fix B**: Give the model a `PrivateImageStorage(FileSystemStorage)` whose `url()` raises `NotImplementedError` pointing at `get_absolute_url()`, so `.url` fails loudly instead of 404ing.
  - Strength: Makes the wrong path impossible rather than merely discouraged; the trap cannot be walked into.
  - Tradeoff: A custom storage class is referenced by the migration, so it becomes a migration-serialized dependency; and it will break the admin change form, which calls `.url` to render the widget — the plan's own verification surface.
  - Confidence: MEDIUM — the admin breakage is a real, likely regression that would need its own workaround.
  - Blind spot: Haven't checked which other Django internals call `.url` on an `ImageField`.
- **Decision**: FIXED via Fix A — `PrivateImage.get_absolute_url()` added (models.py), pinned by `test_get_absolute_url_is_the_gate_and_image_url_is_dead` (test_gate.py), contract recorded in `change.md`. 17 tests pass.

### F2 — Model-layer validators do not run on `objects.create()`; the module docstring's claim is false

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: privatemedia/validators.py:1, privatemedia/models.py:33
- **Detail**: `validators.py:1` reads *"Validation rules every private upload path inherits from the model layer."* Django never calls `full_clean()` on save — only `ModelForm._post_clean()` does. Verified by probe:
  ```
  [objects.create oversized]  saved OK, size = 10485761   (ceiling is 10485760)
  [objects.create non-image]  saved OK, name = private/e633363cb3d24986958691ae3f6531bd.png
  ```
  So `PrivateImage.objects.create(...)` bypasses both `validate_max_size` **and** `ImageField`'s `validate_image_file_extension`. The admin is protected (it goes through a ModelForm, which is why `test_non_image_is_rejected_despite_extension` passes) — but the plan's stated intent was "so that both S-02's and S-04's separate upload paths inherit the rule rather than each restating it in a form." They will not. Note the tests themselves use `objects.create()` (test_gate.py:45, test_model.py:73), which is precisely why the gap is invisible. If S-02 writes a plain view doing `objects.create(owner=request.user, image=request.FILES['photo'])`, there is no size ceiling — reopening the volume-exhaustion risk against the 5000 MB ceiling recorded in `change.md`.
- **Fix A ⭐ Recommended**: Call `self.full_clean()` (or run the validators explicitly) in `PrivateImage.save()` so the ceiling holds on every write path, and add a test asserting `objects.create()` with an oversized file raises.
  - Strength: Makes the docstring true and gives S-02/S-04 the inheritance the plan promised, in the one place the plan chose to centralise ownership.
  - Tradeoff: `full_clean()` on every save is broader than the two validators (it validates all fields and runs uniqueness queries); a narrower explicit call avoids that but must be kept in sync with the field's validator list.
  - Confidence: HIGH — the bypass is verified, and the fix is contained to one method.
  - Blind spot: Haven't checked whether a later bulk-import path would want to opt out.
- **Fix B**: Keep enforcement at the form layer, correct the docstring to say so, and record in `change.md` that S-02/S-04 must upload through a `ModelForm`.
  - Strength: No behaviour change, no risk to the shipped gate; matches how Django is conventionally used.
  - Tradeoff: Leaves the rule restated per-slice — exactly what the plan said it wanted to avoid — and relies on two future slices remembering.
  - Confidence: MEDIUM — correct but depends entirely on downstream discipline.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A — `self.full_clean()` added to `PrivateImage.save()`, plus `validate_image_file_extension` named explicitly on the field (migration `0002_alter_privateimage_image`). Pinned by `test_objects_create_still_enforces_the_size_ceiling` and `test_objects_create_rejects_a_dangerous_extension`. 19 tests pass.
  - **Correction found while fixing**: the review text above (following one agent's report) said `full_clean()` would restore both the size ceiling *and* the image-type check. That was wrong. `django.db.models.ImageField.default_validators` is `[]`; `validate_image_file_extension` is a **form** field default (`django/forms/fields.py:712`), and Pillow content verification lives in `forms.ImageField.to_python()`. So `full_clean()` alone restored only the size ceiling — the extension validator had to be named on the field explicitly.
  - **Residual gap (not fixed)**: Pillow *content* verification is still form-layer only. A file with valid image bytes is required by the admin, but `objects.create()` will accept non-image bytes under an image extension. Closing that needs a custom Pillow-based validator on the model field. Left for S-02 to decide, since S-02 owns the first real upload path.

### F3 — A missing file on disk raises `FileNotFoundError` → HTTP 500

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: privatemedia/views.py:54
- **Detail**: `FileResponse(image.image.open('rb'), ...)` is unguarded. Verified by probe — deleting the file while the row remains gives `FileNotFoundError [Errno 2]`, i.e. a 500. Not hypothetical for this deployment: `MEDIA_ROOT` is a Railway volume while the row lives in a *separate* Postgres volume, so a reattach, restore, or partially failed upload desynchronises the two. With `DEBUG=False` a 20-outfit grid then produces 20 × 500 plus 20 error reports.
- **Fix**: Wrap the open in `try/except (FileNotFoundError, OSError)` and `raise Http404` — which also makes a missing file indistinguishable from a missing row — logging at `warning` so silent data loss stays visible. Add a test.
- **Decision**: FIXED — `views.py` now guards the open, logs at `warning`, and raises `Http404`. Pinned by `test_missing_file_on_disk_is_a_404_not_a_500`. 20 tests pass.

### F4 — `MEDIA_ROOT` silently falls back to an ephemeral container path

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: outfits_garderobe/settings.py:134
- **Detail**: `MEDIA_ROOT = Path(os.getenv('MEDIA_ROOT', BASE_DIR / 'media'))`. If the production variable is ever unset, renamed, or typo'd, the app does not fail — it quietly writes uploads into the container layer, which Railway destroys on the next deploy. That is a silent violation of the PRD's *Trwałość danych* NFR, and it is exactly the standing requirement `change.md` records ("zostaje wymóg, żeby `MEDIA_ROOT` w środowisku produkcyjnym nadal wskazywał na ścieżkę pod montowaniem") — with nothing in code enforcing it. The file's own neighbouring pattern fails loudly: `SECRET_KEY = os.environ['SECRET_KEY']` (settings.py:26). The variable is correctly set to `/data/media` today; this is about the failure mode, not the current state.
- **Fix A ⭐ Recommended**: Require the variable when `DEBUG` is off, mirroring the `SECRET_KEY` pattern already in this file — keep the `BASE_DIR / 'media'` default only for development.
  - Strength: Uses a convention already established two lines up; turns silent data loss into a boot failure that is impossible to miss.
  - Tradeoff: A deploy with the variable missing now fails to start rather than running degraded — which is the intent, but it is a hard failure.
  - Confidence: HIGH — same mechanism as `SECRET_KEY`, already proven in this deployment.
  - Blind spot: None significant.
- **Fix B**: Add a `django.core.checks` check asserting, in production, that `MEDIA_ROOT` is an existing directory outside `BASE_DIR`.
  - Strength: Catches the subtler failure too — a variable that is *set* but points somewhere off-volume.
  - Tradeoff: More code; a system check warns rather than halts unless registered as an error.
  - Confidence: MEDIUM — depends on the check running in the deploy path (`manage.py migrate` does run checks).
  - Blind spot: Haven't verified the mount is present at `preDeployCommand` time.
- **Decision**: FIXED via Fix A — `settings.py` now requires `MEDIA_ROOT` from the environment whenever `DEBUG` is off, keeping the `BASE_DIR / 'media'` default for development only. Verified all three paths: prod-like without the variable raises `KeyError: 'MEDIA_ROOT'`; prod-like with it passes `manage.py check`; `DEBUG=True` still defaults. Railway already sets it (`/data/media`) and it is in the nixpacks build ARG list, so the build-time `collectstatic` is unaffected.
  - Required a companion change: `outfits_garderobe/settings_test.py` (new) stubs `SECRET_KEY` and `MEDIA_ROOT` before importing the real settings, with `pyproject.toml` pointing `DJANGO_SETTINGS_MODULE` at it. This also resolves gap 2 of F5 — `uv run pytest` now runs on a clean shell with no environment at all. (A root `conftest.py` was tried first and does not work: pytest-django sets Django up in `pytest_load_initial_conftests`, before rootdir conftest import.)

### F5 — The verification suite is weaker than its green checkmarks suggest

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: privatemedia/tests/test_storage_config.py:28-32
- **Detail**: Four gaps behind criteria that are all marked `[x]`:
  1. **The anti-`static()` guard cannot fail.** `test_no_url_pattern_serves_media_root_directly` asserts no pattern's callback is `django.views.static.serve`. But `django/conf/urls/static.py:24-25` returns `[]` whenever `settings.DEBUG` is false, and pytest-django runs with `DEBUG=False` — so someone adding `+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` to `urls.py` sails through green. (Residual production risk is low, since `static()` self-disables in production too, and the guard *does* still catch a hand-written `serve` route — the form that is dangerous in production. But the guard's stated purpose, pinning the config against re-exposure, is not met.) Fix: re-resolve the URLconf under `override_settings(DEBUG=True)`.
  2. **`uv run pytest` does not run cold.** `settings.py:26` reads `os.environ['SECRET_KEY']` and there is no `conftest.py` or dotenv loader, so the criterion as written (`uv run pytest`) raises `KeyError: 'SECRET_KEY'` on a clean shell — it only passes for a developer who has exported it. This will block CI. Fix: a `conftest.py` setting a test-only `SECRET_KEY`, or `DJANGO_SETTINGS_MODULE`-level env defaults.
  3. **Nothing pins the single-query optimisation.** `_owned_image`'s request cache is a deliberate optimisation the plan called out; a later refactor could silently restore three queries. `pytest-django` already ships `django_assert_num_queries`.
  4. **Nothing guards `WHITENOISE_ROOT`.** The plan's Current State Analysis established that whitenoise does not leak media only because `WHITENOISE_ROOT` is unset. It is still unset, and no test pins that — setting it to `MEDIA_ROOT` would serve every upload publicly in production, with the suite green.
- **Fix**: Add the four guards — `override_settings(DEBUG=True)` around the URLconf walk, a `conftest.py` supplying a test `SECRET_KEY`, a `django_assert_num_queries(1)` assertion on the gate request, and an assertion that `WHITENOISE_ROOT` is unset.
- **Decision**: FIXED — all four gaps closed.
  1. `test_no_url_pattern_serves_media_root_even_under_debug` reloads the root URLconf under `override_settings(DEBUG=True)`. **Mutation-tested**: appending `static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)` to `urls.py` fails this test with `^media/(?P<path>.*)$ serves files straight off disk`, while the original `test_no_url_pattern_serves_media_root_directly` still passed — confirming the original guard could never fail. `urls.py` restored afterwards.
  2. Fixed under F4 via `outfits_garderobe/settings_test.py`; `uv run pytest` now runs with no environment at all.
  3. `test_gate_makes_exactly_one_row_lookup` counts `privatemedia_privateimage` statements with `CaptureQueriesContext` (rather than `django_assert_num_queries`, which would also count the session and user lookups and be brittle).
  4. `test_whitenoise_does_not_cover_media_root` fails if `WHITENOISE_ROOT` is ever set to `MEDIA_ROOT` or any ancestor of it.
  - Suite is now 23 tests, all passing, ruff and format clean.

### F6 — Session and CSRF cookies are not marked Secure; no HTTPS redirect

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: outfits_garderobe/settings.py
- **Detail**: `uv run python manage.py check --deploy` with `DEBUG=False` reports `security.W004` (no HSTS), `W008` (`SECURE_SSL_REDIRECT` unset), `W012` (`SESSION_COOKIE_SECURE` unset), `W016` (`CSRF_COOKIE_SECURE` unset). The session cookie is now the *only* thing between an attacker and every one of a user's private photos, so one plaintext request transmits it in the clear. This is pre-existing settings hygiene rather than something the diff introduced — but this is the change that made the session cookie security-critical, and it is the change that touched `settings.py`.
- **Fix**: Gate on `not DEBUG`: `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `SECURE_SSL_REDIRECT = True`, `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` (Railway terminates TLS at the edge). HSTS can reasonably wait for S-01; the cookie flags should not.
- **Decision**: FIXED — all four added under `if not DEBUG:` in `settings.py`. `manage.py check --deploy` now reports only `security.W004` (HSTS), deliberately deferred to S-01. Required `SECURE_SSL_REDIRECT = False` in `settings_test.py`: the suite runs with `DEBUG=False`, so the redirect was turning every test-client request into a 301 before it reached a view. The cookie flags stay enabled under test since they do not affect routing.

### F7 — Django 6.0.5 carries nine known advisories

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: pyproject.toml:9, uv.lock
- **Detail**: `uv run pip-audit` reports 9 Django advisories (PYSEC-2026-197/198/199/200/201, -2090/2091/2092, -3717) fixed in 6.0.6–6.0.8, plus `sqlparse` 0.5.5 (5 advisories, incl. CVE-2026-84305) and `msgpack` 1.1.2. Criterion 2.9 was scoped narrowly to *"No new vulnerable dependencies from Pillow"* and that holds — Pillow is clean — so the checkbox is not wrong. But the audit was run as a gate on a change whose entire purpose is an authorization boundary, and it surfaced nine framework advisories that no one triaged.
- **Fix**: `uv add 'django>=6.0.8'` (and let `sqlparse`/`msgpack` follow), then re-run `uv run pytest` and `uv run pip-audit`.
- **Decision**: FIXED — Django pinned `>=6.0.8,<6.1` (resolved 6.0.8) and `sqlparse>=0.6.0` (resolved 0.6.0). All 9 Django advisories and all 5 `sqlparse` advisories are cleared; 23 tests pass, `manage.py check` clean, `makemigrations --check` detects no changes.
  - The upper bound was a deliberate choice: a bare `>=6.0.8` resolved to **6.1.1**, a feature release, which this project has too little test surface to absorb safely right now. Revisit the `<6.1` cap when S-01 has added templates and auth coverage.
  - `pip-audit` still reports `msgpack` and `pip`. Both are pip-audit's own transitive dev dependencies (`uv tree --no-dev` shows neither), so they never reach the deployed image, which installs with `uv sync --no-dev --frozen`.

### F8 — 304 responses carry no `Cache-Control: private`

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: privatemedia/views.py:55
- **Detail**: Verified by probe — the 200 carries `Cache-Control: private, max-age=0, must-revalidate`; the 304 carries no `Cache-Control` at all. The 304 is produced inside `@condition`'s pre-processing, which returns before the view body runs, so line 55 never executes on that path. Real-world risk is low (`Vary: Cookie` is present, and a shared cache would have had to store the 200 first, which *did* carry `private`), but a header this load-bearing should not depend on which code path produced the response.
- **Fix**: Move it out of the body — stack `@cache_control(private=True, max_age=0, must_revalidate=True)` between `@login_required` and `@condition` so both paths get it.
- **Decision**: FIXED — `@cache_control` now sits between `@login_required` and `@condition`, and the manual header assignment is gone from the view body. `test_repeat_fetch_is_a_304` now also asserts `private` is in the 304's `Cache-Control`.

### F9 — The collectstatic relocation left stale artifacts behind

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: .railway/railway.ts:12, plan.md (Phase 3 Automated Verification)
- **Detail**: Moving `collectstatic` from `preDeployCommand` into the nixpacks build phase (commit `35a9323`) was correct and is well explained in the `nixpacks.toml` comment — Railway runs `preDeployCommand` in a throwaway container, so the `staticfiles.json` manifest never reached the runtime image. Verified from the build log that nixpacks v1.41.0 ran the build phase and `migrate` remains the sole `preDeployCommand`. Two leftovers: (a) `.railway/railway.ts:12` still declares the *old* `preDeploy: "...collectstatic --noinput && ...migrate"` — the file is gitignored and so probably inert, but if Railway config-as-code is ever enabled it takes precedence and silently reintroduces the throwaway-container `collectstatic`; (b) the plan's Phase 3 criterion still reads "collectstatic and migrate completing **in `preDeployCommand`**", and neither `plan.md` nor `change.md` records the deviation, so the plan now reads as if nothing changed.
- **Fix**: Delete or sync `.railway/railway.ts`, and add a one-line addendum to the plan's Phase 3 recording that collectstatic moved to build time and why.
- **Decision**: FIXED — `.railway/railway.ts:12` synced to `migrate` alone, with a comment explaining why `collectstatic` must not return there. The plan's Phase 3 criterion now reads "`migrate` in `preDeployCommand`, `collectstatic` in the build phase" and carries a dated addendum recording the deviation and its cause.

### F10 — `privatemedia/apps.py` dropped `default_auto_field`

- **Severity**: 📝 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Pattern Consistency
- **Location**: privatemedia/apps.py:4-5
- **Detail**: `startapp` generates `default_auto_field = 'django.db.models.BigAutoField'`; it was removed alongside the boilerplate the plan asked to delete, and `settings.py` defines no project-level `DEFAULT_AUTO_FIELD`. Harmless today — `PrivateImage` has an explicit UUID primary key and `manage.py check` is clean — but the *next* model added to this app will emit `models.W042` and get a 32-bit `AutoField`. As the first domain app, this one sets the pattern the rest will copy.
- **Fix**: Restore `default_auto_field = 'django.db.models.BigAutoField'` in `PrivatemediaConfig`, or set `DEFAULT_AUTO_FIELD` once in `settings.py`.
- **Decision**: FIXED — `default_auto_field = 'django.db.models.BigAutoField'` restored in `PrivatemediaConfig`, with a comment noting this app sets the pattern for the next one. `makemigrations --check` detects no changes.


## Triage outcome (2026-09-09)

All ten findings were triaged in one pass and **all ten were fixed**. Nothing was skipped,
accepted as risk, or dismissed.

| ID | Decision |
|----|----------|
| F1 | FIXED (Fix A) — `get_absolute_url()` + test + `change.md` contract |
| F2 | FIXED (Fix A) — `full_clean()` in `save()` + extension validator on the field (migration 0002) |
| F3 | FIXED — guarded file open → `Http404` + warning log + test |
| F4 | FIXED (Fix A) — `MEDIA_ROOT` required when `DEBUG` is off; `settings_test.py` added |
| F5 | FIXED — all four verification gaps closed; anti-`static()` guard mutation-tested |
| F6 | FIXED — secure cookie flags, SSL redirect, proxy header under `not DEBUG` |
| F7 | FIXED — Django pinned `>=6.0.8,<6.1`; `sqlparse>=0.6.0` |
| F8 | FIXED — `@cache_control` above `@condition`; 304 now asserted |
| F9 | FIXED — `.railway/railway.ts` synced; plan addendum added |
| F10 | FIXED — `default_auto_field` restored |

### Post-fix verification

| Check | Result |
|---|---|
| `uv run pytest` (clean shell, **no** env vars) | **23 passed** — was 16, and previously could not run at all without an exported `SECRET_KEY` |
| `manage.py check` | 0 issues |
| `manage.py check --deploy` | only `security.W004` (HSTS, deferred to S-01) |
| `manage.py makemigrations --check --dry-run` | No changes detected |
| `manage.py collectstatic --noinput` | 359 post-processed |
| `uv run ruff check .` / `ruff format --check .` | clean, 21 files |
| `uv run pip-audit` | no advisories in any dependency that ships; the 4 remaining (`pip`, `msgpack`) are pip-audit's own dev deps |

### Files changed by this triage

- `outfits_garderobe/settings.py` — required `MEDIA_ROOT` outside DEBUG, transport hardening, `MEDIA_URL` comment
- `outfits_garderobe/settings_test.py` *(new)* — stubs deploy-required env for the test run
- `privatemedia/models.py` — `get_absolute_url()`, `full_clean()` in `save()`, extension validator
- `privatemedia/migrations/0002_alter_privateimage_image.py` *(new)* — validators only, no schema change
- `privatemedia/views.py` — guarded file open, `@cache_control`, logger
- `privatemedia/apps.py` — `default_auto_field`
- `privatemedia/tests/test_gate.py`, `test_model.py`, `test_storage_config.py` — 7 new tests
- `pyproject.toml`, `uv.lock` — Django and sqlparse pins, test settings module
- `.railway/railway.ts`, `plan.md`, `change.md` — documentation sync

### Not fixed — deliberately out of scope

- **Pillow content verification on the plain ORM path.** `full_clean()` enforces the size ceiling and the file extension, but verifying the *bytes* are a real image lives in `forms.ImageField.to_python()`. S-02 owns the first real upload path and should decide whether to add a Pillow-based model validator.
- **HSTS (`security.W004`).** Left to S-01, which owns the auth flow.
- **Orphan file cleanup.** Deleting a `PrivateImage` still leaves its bytes on the volume. The plan explicitly defers this to S-06 (`garment-lifecycle`).
