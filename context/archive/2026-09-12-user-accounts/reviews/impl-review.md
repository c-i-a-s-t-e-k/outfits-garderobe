<!-- IMPL-REVIEW-REPORT -->
# Implementation Review: Konto użytkownika — rejestracja, logowanie, wylogowanie i zmiana hasła

- **Plan**: `context/changes/user-accounts/plan.md`
- **Scope**: Full plan — Phases 1–5 of 5 (commits 79ad4d4..64fa8d0)
- **Date**: 2026-09-12
- **Verdict**: NEEDS ATTENTION → triaged 2026-09-12: 6 fixed, 1 accepted, 1 skipped (F3)
- **Findings**: 0 critical, 4 warnings, 4 observations

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| Plan Adherence | WARNING |
| Scope Discipline | WARNING |
| Safety & Quality | WARNING |
| Architecture | PASS |
| Pattern Consistency | PASS |
| Success Criteria | WARNING |

## Evidence gathered

Automated criteria, re-run by the reviewer on 2026-09-12 against HEAD `64fa8d0`:

- `uv run pytest`: 52 passed. `accounts/tests/test_deploy_config.py`: 5 passed. `privatemedia/tests/`: 23 passed.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 33 files already formatted.
- `uv run pip-audit`: no known vulnerabilities.
- Run with `DEBUG=True` and a dummy `SECRET_KEY`: `manage.py check` found no issues, `migrate --check` found nothing unapplied, and `makemigrations --check` detected no changes. The manifest holds hashed `vendor/pico.min.94cbb1d0170a.css` and `css/app.faae855d118d.css`.
- `manage.py check --deploy` under production-like environment variables (dummy values) reports only `security.W005` and `security.W021`, which matches the documented `DELIBERATE_DEVIATIONS`.
- `git grep -nE 'xkeysib-[0-9a-f]{32}'` found nothing.
- Railway presence check: `BREVO_API_KEY: true` and `DEFAULT_FROM_EMAIL: true`. Live deployment `4386ce37` is `SUCCESS`.
- Production probes, GET only:
  - `/health/` returns 200.
  - `Strict-Transport-Security: max-age=3600`.
  - `/` and `/wardrobe/` redirect (302) to `/accounts/login/`.
  - An anonymous `/media/<uuid>/` redirects (302) to `/accounts/login/?next=…`.
  - The `csrftoken` cookie is `Secure`.

Documented deviations checked and found sound:

- **Reset predicate:** "no `EmailAddress` row" instead of "no verified one", which protects pending signups.
- **Pico build:** the default build instead of classless. The plan contradicted itself here, since `.container` needs the default build.
- **`SECURE_REDIRECT_EXEMPT = [r'^health/$']`:** matches only `/health/`, which is Railway's `healthcheckPath`.
- **W005/W021:** allow-listed because HSTS is on.
- **`extra_head`/`extra_body` blocks** in `base.html`.

## Findings

### F1 — `reset_legacy_accounts` stays in the repo as a footgun

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: accounts/management/commands/reset_legacy_accounts.py:63
- **Detail**: The production run is done and was handled safely: the new-flow account was promoted before `--commit`, and 0 orphans were verified afterwards. The command itself, however, is unsafe to run again.
  1. It deletes any `createsuperuser`/admin-created account, because those have no `EmailAddress` row, and `README.md:47` tells operators to use `createsuperuser`.
  2. `--commit` re-selects users instead of deleting the set the dry run showed, so the two can differ. A signup caught between allauth's user save and its `EmailAddress` save also matches.
  3. The comment at lines 102-105 claims a crash leaves files "which this command finds again on its next run". That is false: files are found only through `PrivateImage` rows that are already deleted, and a rerun exits at line 65. This was confirmed by execution.
  4. `storage.delete` ignores missing files, so `removed` counts files that were never there. Run somewhere without the volume, it deletes rows and reports success.
  5. The docstring's "neither can log in through the new flow" is wrong for a legacy user who has an email address. Logging in creates an `EmailAddress` row and takes them out of the selection.
- **Fix A ⭐ Recommended**: Delete the command and its test module. It was a one-off cutover tool, and both environments have now run it.
  - Strength: Removes the whole class of accidental re-runs. Git history and `change.md` keep the record, and no later slice depends on it.
  - Tradeoff: If another pre-allauth account ever turns up, it has to be restored from history.
  - Confidence: HIGH — `change.md` records 0 users without `EmailAddress` in production, and the plan scoped the command to exactly two runs.
  - Blind spot: Whether the developer wants it kept as a template for a future cleanup command.
- **Fix B**: Harden it:
  - skip `is_staff` and `is_superuser` accounts unless `--include-staff` is passed;
  - make `--commit` require the IDs from the dry run;
  - refuse to commit when `MEDIA_ROOT` or any listed file is missing;
  - count missing files separately;
  - fix the comment and docstring;
  - add tests for a superuser, a missing file, and a legacy user who has an email.
  - Strength: Keeps a reusable tool with honest guarantees.
  - Tradeoff: More code and tests maintained for an operation that should never recur.
  - Confidence: MEDIUM — the agent's execution probes confirm each gap, but hardening adds surface area.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A. The command and `accounts/tests/test_reset_legacy_accounts.py` were removed with `git rm`; the suite now passes 45 tests (52 minus the 7 removed) and ruff is clean. The historical record stays in `change.md` and the plan.

### F2 — Signup can 500 on a `username` collision

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Safety & Quality
- **Location**: accounts/adapter.py:49 (guard belongs in accounts/forms.py:26)
- **Detail**: allauth checks email uniqueness against `EmailAddress` and `User.email`, never against `User.username`. The adapter writes username = email, and that column is unique. Both reproduced scenarios end in an `IntegrityError` (a 500) instead of a form error:
  - A user adds and verifies a second address at `/accounts/email/`, makes it primary, and removes the original. A new signup with the original address then fails.
  - A `createsuperuser` account has `username=admin@x.com` and a blank email. A signup with `admin@x.com` then fails.

  Case is not a problem: allauth lowercases the email before this point.
- **Fix**: In `SignupForm.clean()`, add an `email`-field error ("already registered") when `User.objects.filter(username__iexact=email)` exists, and add a regression test in `test_smoke.py`.
- **Decision**: FIXED. `accounts/forms.py` `clean()` now refuses an address already stored as a username, using allauth's own `email_taken` message. Regression test: `test_signup_refuses_an_email_already_taken_as_a_username`; it fails with `IntegrityError` without the fix and passes with it. Full suite: 46 passed.

### F3 — allauth rate limits key on Railway's proxy address, not the client

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Safety & Quality
- **Location**: outfits_garderobe/settings.py (no `ALLAUTH_TRUSTED_PROXY_COUNT` / `ALLAUTH_TRUSTED_CLIENT_IP_HEADER`)
- **Detail**: `allauth/core/internal/httpkit.py:get_client_ip` falls back to `REMOTE_ADDR` when neither setting is set, and both default to off. Behind Railway's edge, `REMOTE_ADDR` is the proxy's address, so the per-IP limits are shared by every visitor:
  - `login_failed` 10/m
  - `signup` 20/m
  - `reset_password` 20/m

  A single client can therefore lock everyone out of login, signup and reset. The same limit is the only brake on email enumeration, which `ACCOUNT_PREVENT_ENUMERATION = False` deliberately allows. This makes the limits work rather than changing them, so it does not conflict with the plan's "no change to rate limits".
- **Fix**: Check which client-IP header Railway's edge sends (log `X-Forwarded-For` / `X-Real-IP` once in production), then set `ALLAUTH_TRUSTED_PROXY_COUNT = 1` (or `ALLAUTH_TRUSTED_CLIENT_IP_HEADER`) outside DEBUG, with a comment.
  - Strength: One setting, and it is the configuration allauth documents for this case.
  - Tradeoff: A wrong proxy count lets clients spoof their IP through `X-Forwarded-For`, and allauth raises `ImproperlyConfigured` when the header is shorter than the count.
  - Confidence: MED — the allauth source was read directly, but Railway's header shape is unverified.
  - Blind spot: The exact `X-Forwarded-For` chain Railway produces. There is also no `LOGGING` config today, so capturing it needs a temporary log line or a debug endpoint.
- **Decision**: SKIPPED

### F4 — The deploy guard cannot detect loss of SSL redirect or the proxy header

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: accounts/tests/test_deploy_config.py:25-38
- **Detail**: `settings_test.py` forces `SECURE_SSL_REDIRECT = False`, and the guard allow-lists W008. As a result, deleting `SECURE_SSL_REDIRECT = True` from `settings.py` still passes every test. `SECURE_PROXY_SSL_HEADER`, whose loss means a redirect loop on Railway, and `SECURE_REDIRECT_EXEMPT`, whose loss means a failed healthcheck like deployment `a47ace49`, are not pinned by any Django check. The guard therefore misses the exact regression class that caused this change's unplanned incident.
- **Fix**: Add a test that imports `outfits_garderobe.settings` directly (it runs the non-DEBUG branch under the test env stubs) and asserts `SECURE_SSL_REDIRECT is True`, `SECURE_PROXY_SSL_HEADER == ('HTTP_X_FORWARDED_PROTO', 'https')`, `SECURE_REDIRECT_EXEMPT == [r'^health/$']` and the anymail `EMAIL_BACKEND`.
- **Decision**: FIXED. Added `test_production_transport_settings_are_pinned` in `accounts/tests/test_deploy_config.py`, which reads `outfits_garderobe.settings` directly. Mutation check: deleting `SECURE_SSL_REDIRECT = True` from `settings.py` makes it fail, and restoring the line makes it pass. Full suite: 47 passed.

### F5 — Unplanned production operations left standing

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Scope Discipline
- **Location**: context/changes/user-accounts/change.md (Production deploy notes)
- **Detail**: Neither step was in the plan, and both are documented in `change.md`:
  - The only verified new-flow account was promoted to staff and superuser before the reset.
  - The developer's `~/.ssh/id_ed25519.pub` was registered with Railway as `ciastek-laptop-id_ed25519` for `railway ssh`, and is still registered.

  The promotion was the right call, because the plan's `/admin/` escape hatch would otherwise have been deleted. That also means the plan's claim that `/admin/` "stays reachable for the old superuser across the whole cutover" was incomplete. Separately, commit 79ad4d4 removed a 48-line block from `CLAUDE.md`; this was out of plan but author-approved.
- **Fix**: Decide whether to keep the Railway SSH key; if not, run `railway ssh keys remove ciastek-laptop-id_ed25519`.
- **Decision**: ACCEPTED. The developer keeps the Railway SSH key `ciastek-laptop-id_ed25519` registered. The superuser promotion and the `CLAUDE.md` edit stand as documented.

### F6 — Progress SHAs attribute checks to commits that don't contain them

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Success Criteria
- **Location**: context/changes/user-accounts/plan.md:683, 743-752
- **Detail**: Two SHAs in Progress point at the wrong place. This is not rubber-stamping: `change.md` records who confirmed each item and when.
  - 2.13 is stamped `73e01e9`, but that commit's message says 2.13 was deferred. It was confirmed on 2026-09-12 together with Phase 5.
  - 5.9–5.18 are stamped `6ed120f`, but they were verified after the deploy. The 5.18 reset ran before `64fa8d0` and is recorded there.
- **Fix**: Point 2.13 and 5.9–5.18 at `64fa8d0`, where their evidence is recorded, or accept as is.
- **Decision**: FIXED. The SHAs for 2.13 and 5.9–5.18 in `plan.md` now point at `64fa8d0`.

### F7 — Vendored Pico build isn't recorded

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: static/vendor/README.md:10
- **Detail**: The plan specified the *classless* build. The default `pico.min.css` was shipped instead, correctly, because `<main class="container">` and `.site-header` need it; the p1 commit message says so. The vendor README only gives the URL, though, so the next upgrade could "fix" it back to classless.
- **Fix**: Add one line to `static/vendor/README.md`: "default build, not classless — `base.html` uses `.container`."
- **Decision**: FIXED. `static/vendor/README.md` now records that this is the default build, not classless, and why.

### F8 — Stale references in code comments and CLAUDE.md

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Adherence
- **Location**: outfits_garderobe/settings.py:249; CLAUDE.md ("No Django apps exist yet…")
- **Detail**:
  - `settings.py:249` says the setting repairs `privatemedia/views.py:54`, but `@login_required` is on line 46.
  - `CLAUDE.md` still says no domain apps exist, although `privatemedia` and `accounts` both do.
  - The plan's Testing Strategy lists "unit tests" for the adapter, but the behaviour is covered by signup integration tests (`test_smoke.py:134`, `:150`). The coverage is adequate and only the wording is off.
- **Fix**: Correct the line reference to `:46` and update the CLAUDE.md sentence to name `privatemedia` and `accounts`.
- **Decision**: FIXED. `settings.py:249` now points at `privatemedia/views.py:46`, and `CLAUDE.md` names the `privatemedia` and `accounts` apps. The Testing Strategy wording was left as is, since coverage is adequate.
