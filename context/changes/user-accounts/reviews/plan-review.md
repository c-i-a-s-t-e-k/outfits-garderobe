<!-- PLAN-REVIEW-REPORT -->
# Plan Review: Konto użytkownika — rejestracja, logowanie, wylogowanie i zmiana hasła

- **Plan**: `context/changes/user-accounts/plan.md`
- **Mode**: Deep
- **Date**: 2026-09-12
- **Verdict**: REVISE → all 6 findings fixed in the plan on 2026-09-12 (see Triage outcome)
- **Findings**: 2 critical, 3 warnings, 1 observation

## Verdicts

| Dimension | Verdict |
|-----------|---------|
| End-State Alignment | WARNING |
| Lean Execution | PASS |
| Architectural Fitness | PASS |
| Blind Spots | FAIL |
| Plan Completeness | WARNING |

## Grounding

9/9 paths ✓, 3/3 create-paths absent ✓, symbols ✓ (all absent as the plan claims),
brief↔plan ✓, Progress contract ✓ (4/4 phases, 53/53 criteria mapped).
Baseline: **23 tests passing** before this change.

## Claims verified as correct

Recorded so a later reader knows these were tested, not assumed:

- allauth's `AccountMiddleware` is benign — it sets `request.allauth`, wraps a request context, and rewrites a 404 on exactly `/accounts/`. It does **not** enforce email verification on existing sessions, so the 11 `client.force_login` calls in `privatemedia/tests/` are unaffected by mandatory verification.
- `DefaultAccountAdapter.populate_username(self, request, user)` is the correct hook (allauth 65.19.3, `account/adapter.py:320`), and it does derive the username from the email's local part via `generate_unique_username` — confirming the override is necessary.
- `ACCOUNT_UNIQUE_EMAIL` defaults to `True` (`account/app_settings.py:225`), so allauth's own Critical check ("Using email as a login method requires ACCOUNT_UNIQUE_EMAIL") passes without configuration.
- allauth's `settings_check` confirms `mandatory` verification requires `'email*'` in `ACCOUNT_SIGNUP_FIELDS` — which the plan specifies.
- Pico.css v2.1.1 carries **no** `sourceMappingURL` comment and no non-`data:` `url()` references, so it will not trip `CompressedManifestStaticFilesStorage` during the nixpacks build.

## Findings

### F1 — Phase 4's email config aborts the entire test suite

- **Severity**: ❌ CRITICAL
- **Impact**: 🔬 HIGH — architectural stakes; think carefully before deciding
- **Dimension**: Blind Spots
- **Location**: Phase 4 — Changes Required #1 (production email)
- **Detail**: Phase 4 reads `EMAIL_HOST_PASSWORD` and friends with `os.environ[...]`. The suite runs with `DEBUG=False` (`settings_test.py:23-28`) so it executes that same branch, and `settings_test.py` stubs only `SECRET_KEY` and `MEDIA_ROOT`. Reproduced: `KeyError: 'EMAIL_HOST_PASSWORD'` at settings import — the suite cannot collect, making criteria 4.1–4.5 unrunnable. Phase 4 listed no change to `settings_test.py`.
- **Fix A ⭐ Recommended**: Stub the `EMAIL_*` keys in `settings_test.py`'s existing `setdefault` block; add the file to Phase 4's Changes Required.
  - Strength: Two lines in the block that exists for exactly this reason; preserves the deliberate fail-loudly-at-boot property.
  - Tradeoff: A missing Railway variable still takes production down at boot.
  - Confidence: HIGH — reproduced directly.
  - Blind spot: None significant.
- **Fix B**: Read email config with `os.getenv` and degrade instead of dying.
  - Strength: Removes a real outage vector — unlike `SECRET_KEY`/`MEDIA_ROOT`, a missing mail password only breaks password reset, yet `os.environ[...]` escalates that to a total outage.
  - Tradeoff: Reset silently stops working instead of announcing itself.
  - Confidence: MEDIUM — needs a concrete startup signal.
  - Blind spot: Whether a boot crash is noticed faster than silent mail failure.
- **Decision**: FIXED via Fix A

### F2 — Phase 3's LOGIN_URL breaks a shipped F-01 test

- **Severity**: ❌ CRITICAL
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: End-State Alignment
- **Location**: Phase 3 — Changes Required #4 (login redirects)
- **Detail**: Phase 3 set `LOGIN_URL = 'account_login'` (a route name). `privatemedia/tests/test_gate.py:83` asserts `response.headers['Location'].startswith(settings.LOGIN_URL)`, and the Location is `/accounts/login/?next=/media/<uuid>/`. Verified both spellings: the path passes, the name fails. This contradicted the plan's own scope line ("No changes to `privatemedia`'s model, view or tests") and made success criterion 3.3 ("The `privatemedia` suite is unaffected") unachievable.
- **Fix A ⭐ Recommended**: Use the path — `LOGIN_URL = '/accounts/login/'`.
  - Strength: F-01's guard and the scope boundary both hold. The named-route rationale genuinely applies to `LOGIN_REDIRECT_URL`, which S-03 will change; `LOGIN_URL`'s path is fixed by an include prefix we control.
  - Tradeoff: If the allauth mount prefix ever moves, the gate's redirect breaks silently.
  - Confidence: HIGH — verified the assertion both ways.
  - Blind spot: None significant.
- **Fix B**: Keep the name and update F-01's assertion to resolve it, amending the scope line.
  - Strength: Survives a future remount; the brittleness is arguably in the test.
  - Tradeoff: Reopens a shipped, reviewed slice for robustness against a move nobody plans.
  - Confidence: HIGH — `resolve_url` handles both.
  - Blind spot: Checked — this is the only F-01 assertion making that assumption.
- **Decision**: FIXED via Fix A

### F3 — Deploy-guard allow-list omits W008

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 4 — Changes Required #5 (deploy-configuration guard)
- **Detail**: The plan allow-listed only `security.W009`. Running the deployment checks under `settings_test` emits three IDs — W008, W009, W004 — because `settings_test.py:28` forces `SECURE_SSL_REDIRECT = False`. The guard would fail on an ID the plan never mentioned.
- **Fix**: Allow-list W008 alongside W009, each with a comment naming the harness artifact that causes it.
- **Decision**: FIXED

### F4 — Phase 1's 360px check needs a view Phase 1 never builds

- **Severity**: ⚠️ WARNING
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Plan Completeness
- **Location**: Phase 1 — Manual Verification 1.7
- **Detail**: Criterion 1.7 asked for "a throwaway view rendering `base.html`" at 360px, but Phase 1 creates no view and no URL — the first route arrives in Phase 3. It asked the implementer to invent scaffolding the plan never describes or removes.
- **Fix**: Drop 1.7; Phase 2's criterion 2.15 already covers 360px on allauth's real screens.
- **Decision**: FIXED

### F5 — Destructive production step has no specified procedure

- **Severity**: ⚠️ WARNING
- **Impact**: 🔎 MEDIUM — real tradeoff; pause to reason through it
- **Dimension**: Plan Completeness
- **Location**: Phase 4 — Changes Required #7; Phase 3 — #5
- **Detail**: Both account resets said "delete the rows, then sweep the orphaned files" but named no mechanism. The riskiest, irreversible step in the plan was its least specified one — and F-01's impl-review specifically credited reviewable artifacts over console sessions.
- **Fix A ⭐ Recommended**: A `reset_legacy_accounts` management command defaulting to `--dry-run`, selecting on "no verified `EmailAddress`" rather than a hardcoded username list, printing users and exact orphaned paths; serves dev and production from one artifact.
  - Strength: Reviewable, testable, re-runnable; the file sweep needs code regardless, since `CASCADE` removes rows and never bytes.
  - Tradeoff: A command written for a one-time job that then lives in the repo.
  - Confidence: HIGH — matches the house pattern.
  - Blind spot: How the command is invoked on Railway is still unspecified.
- **Fix B**: An explicit ordered checklist in the plan, executed by hand.
  - Strength: No throwaway code.
  - Tradeoff: Hand-executed production deletion with no dry run and no record.
  - Confidence: MEDIUM.
  - Blind spot: None significant.
- **Decision**: FIXED via Fix A

### F6 — Long-email rejection lands in the adapter, producing a 500

- **Severity**: 💡 OBSERVATION
- **Impact**: 🏃 LOW — quick decision; fix is obvious and narrowly scoped
- **Dimension**: Blind Spots
- **Location**: Phase 2 — Changes Required #5; Critical Implementation Details
- **Detail**: The plan had the adapter reject addresses over `User.username`'s 150-character limit. `populate_username` runs during save, after form validation, so raising there is an unhandled exception — a 500 on a public form. allauth's signup email field accepts Django's 254-character default, so addresses in the 151–254 range reach it.
- **Fix**: Enforce the limit in a signup form via `ACCOUNT_SIGNUP_FORM_CLASS` so it surfaces as a field error; keep the adapter check as a non-user-facing invariant.
- **Decision**: FIXED

## Triage outcome

| Finding | Decision |
|---------|----------|
| F1 | FIXED via Fix A |
| F2 | FIXED via Fix A |
| F3 | FIXED |
| F4 | FIXED |
| F5 | FIXED via Fix A |
| F6 | FIXED |

Progress contract re-verified after the edits: 1 `## Progress` heading, 0 stray checkboxes,
4/4 phase names matched, all criteria counts aligned, numbering contiguous.

**Verdict after fixes: SOUND**
