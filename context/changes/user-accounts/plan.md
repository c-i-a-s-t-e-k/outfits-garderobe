# Konto użytkownika — rejestracja, logowanie, wylogowanie i zmiana hasła — Implementation Plan

## Overview

This change gives the project its first accounts and its first user interface. A visitor can register with an email address, confirm it, log in, log out and change their password; an anonymous visitor reaching any application URL lands on the login page rather than on content.

It is roadmap item **S-01** (milestone M-1, stream B), it unblocks **S-02** (`add-garment`) and transitively everything after it, and it satisfies PRD **FR-001**, **FR-002** and the *Access Control* section.

Two things ride along because nothing else can carry them. First, this is the first slice with a visible interface, so it creates the base template and the stylesheet every later view inherits — the roadmap names sprawl here as S-01's principal risk, and the design decision below is chosen specifically to contain it. Second, `outfits_garderobe/settings.py:43` explicitly parks HSTS for this change: *"HSTS is left to S-01, which owns the auth flow."*

## Current State Analysis

- **There is no user interface of any kind.** `TEMPLATES['DIRS']` is `[]` with `APP_DIRS` on (`outfits_garderobe/settings.py:76-89`), and no `.html` file exists in the repository. There is no `templates/` directory and no `static/` source directory; `STATICFILES_DIRS` is unset. The only collected static files are Django admin's.
- **`@login_required` currently redirects into a void.** `privatemedia/views.py:46` gates the private media view, but `LOGIN_URL` is never set, so Django falls back to `/accounts/login/` — a route that does not exist. F-01's manual check 2.12 ("opening the same URL logged out lands on the login flow") passes only in the loosest sense today. This change is what makes it true.
- **`CompressedManifestStaticFilesStorage` is live** (`settings.py:169`) and `collectstatic` runs in the nixpacks **build** phase (`nixpacks.toml:12`), not at deploy. Under manifest storage a `{% static %}` reference to a missing file raises at render time, and a missing manifest turns every page into a 500. F-01's plan predicted this: *"S-01 will meet it."* No template has ever exercised it.
- **Identity is stock `auth.User`.** `privatemedia/migrations/0001_initial.py` carries `swappable_dependency(settings.AUTH_USER_MODEL)` and a real FK. Dev holds two rows — superuser `ciastek` (`jezowdominik@duck.com`) and `stranger` with a **blank** email, an F-01 test artifact — each with a `PrivateImage`. Production holds the equivalent accounts plus files on the Railway volume, created as F-01's acceptance evidence.
- **No email infrastructure exists.** `EMAIL_BACKEND` is unset (so Django defaults to SMTP against `localhost:25`, which silently fails), and `.env.example` names no mail variables. Railway provides no mail service.
- **`manage.py check --deploy` reports exactly one substantive issue:** `security.W004` (no `SECURE_HSTS_SECONDS`). `security.W009` also fires under the test settings because `settings_test.py:16` uses a 38-character key; that is a test-harness artifact, not a production defect.
- **Transport hardening is otherwise done.** `settings.py:44-48` already sets `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` and `SECURE_PROXY_SSL_HEADER` outside DEBUG, and `settings_test.py:28` disables only the redirect.
- **Conventions to match.** `ruff` with single quotes and a 100-character line length, `E/F/I/UP/B/DJ` rules (`pyproject.toml:26-32`). Tests live under `<app>/tests/` and run against `outfits_garderobe.settings_test`. `privatemedia` is the house style: thin views, module docstrings that explain *why*, and a settings-guard test suite (`privatemedia/tests/test_storage_config.py`).

## Desired End State

A visitor at `/` is redirected to `/accounts/login/`. Registering with an email and password sends a confirmation mail; the account cannot be used until the link is clicked. After confirming and logging in, the visitor lands on `/wardrobe/`. They can change their password, log out, and — having forgotten it — receive a working reset link by email in production. Every one of these screens is legible on a 360-pixel-wide phone. An anonymous request for a private photo now redirects to a real login page instead of a dead URL, and `manage.py check --deploy` reports no issues beyond a documented allow-list.

Verify by: `uv run pytest` (all smoke tests green), then, against production, registering a brand-new account with a real mailbox, confirming it from that mailbox, logging in, changing the password, logging out, and completing a password reset end to end from the emailed link.

### Key Discoveries:

- **django-allauth 65.19.3** (released 2026-09-11) declares support for Django **6.0 and 6.1**. Installed without the `socialaccount` extra it adds one transitive dependency, `asgiref`, which Django already requires. `requests` and `oauthlib` arrive only with the social extra we are not taking.
- **Account-only allauth no longer needs `django.contrib.sites` or `SITE_ID`** in 65.x. It builds absolute URLs for email from `request.get_host()` plus `ACCOUNT_DEFAULT_HTTP_PROTOCOL`, whose default is `'http'`.
- **One template override styles the whole account flow.** allauth's shipped templates are deliberately unstyled semantic markup, and the documented hook is `allauth/layouts/base.html` (with `entrance.html` and `manage.html` extending it). Because Pico.css styles semantic elements rather than classes, overriding that single file to extend our `base.html` is sufficient — no allauth template needs to be copied or re-classed.
- **`ACCOUNT_SESSION_REMEMBER` already defaults to `None`, which means "ask the user"**, so the login form renders a *Remember me?* checkbox with no configuration. Only `SESSION_COOKIE_AGE` needs deciding.
- **`ACCOUNT_LOGOUT_ON_GET` defaults to `False`.** Logging out is a POST. A plain `<a href="{% url 'account_logout' %}">` renders a confirmation page instead of logging out.
- **`ACCOUNT_SIGNUP_FIELDS` defaults to `['username*', 'email', 'password1*', 'password2*']`** and `ACCOUNT_LOGIN_METHODS` to `{'username'}`. Both must be set for email-based identity, and the docs warn they must agree with each other.
- **allauth's docs confirm the enumeration trade-off we are taking deliberately:** with `mandatory` verification, allauth *can* fully prevent enumeration at signup. Setting `ACCOUNT_PREVENT_ENUMERATION = False` is therefore an explicit, informed exchange of that property for a clearer error message.
- **Pico.css v2.1.1** is the current release (2025-03-15).
- `django.contrib.sessions` is already installed and `ACCOUNT_*` needs no session-engine change — allauth only forbids the `signed_cookies` engine, which this project does not use.

## What We're NOT Doing

- **No custom user model.** Identity stays `auth.User` with the email written into `username`. Weighed and declined: see *Key Decisions* in the brief.
- **No OAuth or social login.** Roadmap Open Question #1 is hereby resolved as email + password for milestone M-1. The `socialaccount` extra is not installed.
- **No wardrobe, garments, outfits or tags.** `/wardrobe/` is a placeholder; S-02 and S-03 fill it.
- **No profile fields, avatars, display names, or account deletion.** FR-001 and FR-002 ask for four operations and no more.
- **No multi-factor authentication, login-by-code, or session management UI**, all of which allauth offers and none of which the PRD requests.
- **No change to allauth's default rate limits.** The shipped defaults are appropriate at MVP scale.
- **No design system.** One vendored stylesheet plus a short project stylesheet. No component library, no utility classes, no build step, no Node in the nixpacks build.
- **No changes to `privatemedia`'s model, view or tests.** This change only supplies the login page its `@login_required` was already pointing at.
- **No thorough test suite.** Smoke coverage only, by explicit decision — recorded as a risk below rather than silently absorbed.

## Implementation Approach

The slice is built dev-first and shipped last, mirroring how F-01 was run: three phases that touch only the working tree, then one production phase.

The presentation layer comes first and alone, because it is the only part that can break the Railway build. Manifest storage plus build-time `collectstatic` means a bad `{% static %}` reference fails the deploy rather than a page — proving that path with one stylesheet, before any auth code exists, keeps the two risks from arriving together.

allauth then lands on top of stock `auth.User`. `username` is not a field the user ever sees: an account adapter writes the confirmed email into it, so the column stays populated and unique without a model swap and without allauth's default of deriving a username from the email's local part. Email uniqueness is enforced by allauth's own `account_emailaddress` table, which carries a real unique constraint — the property the plain-`auth.User` route would otherwise have lacked.

Routing is deliberately thin. `/` holds no content; it is a redirect that reads authentication state. `/wardrobe/` is the login-gated destination, reserved now so S-02 and S-03 fill a page in rather than move it. Setting `LOGIN_URL` to allauth's login route is what repairs `privatemedia`'s dangling redirect, at no cost.

Production comes last because it is where the two irreversible things live: a real mail sender, and the deletion of the existing accounts. Everything before it is reversible in the working tree.

## Critical Implementation Details

**`username` must be populated, and allauth's default will not do what we chose.** With `username` absent from `ACCOUNT_SIGNUP_FIELDS`, allauth's `DefaultAccountAdapter.populate_username()` generates one from the email's *local part* (`jezowdominik`), not the full address. Our decision was the full email. Override `populate_username` on a custom adapter to assign the address itself. Two constraints bound this: `User.username` is `max_length=150`, and `UnicodeUsernameValidator` permits `[\w.@+-]`, which covers every character legal in an email — so ordinary addresses fit, but a longer one must be rejected rather than silently truncated into a collision. Reject it in the **signup form**, not the adapter: `populate_username` runs during save, after validation, so raising there produces a 500 rather than a field error, and allauth's email field accepts Django's 254-character default.

**The `check --deploy` guard cannot assert an empty issue list.** Under `settings_test`, `security.W009` fires on the 38-character test key (`settings_test.py:16`) and `security.W004` is what this change fixes. Assert against a named, commented allow-list of check IDs so the guard fails on a *new* issue rather than on the harness.

**HSTS is irreversible for the duration of its own max-age.** Browsers cache the header; a mistake cannot be recalled, only waited out. Ship `SECURE_HSTS_SECONDS = 3600`, without `SECURE_HSTS_PRELOAD` and without `INCLUDE_SUBDOMAINS`, verify in production, and raise it in a later change. Note that Railway terminates TLS at the edge — `SECURE_PROXY_SSL_HEADER` is already set (`settings.py:48`), which is what lets Django emit the header at all.

**Verification links will be `http://` unless told otherwise.** With no `sites` framework, allauth composes email URLs from `ACCOUNT_DEFAULT_HTTP_PROTOCOL`, which defaults to `'http'`. Combined with `SECURE_SSL_REDIRECT`, an unset value produces a link that redirects on click — and, once HSTS is live, one that some browsers refuse outright. Set it to `'https'` outside DEBUG.

**Ordering: the production account reset must follow the production deploy, not precede it.** Deleting the accounts first would leave the environment with no way in until the new registration flow is live. The old superuser can still reach `/admin/` throughout, because `ModelBackend` stays in `AUTHENTICATION_BACKENDS` — that is the escape hatch that makes the sequence safe.

**Deleting a user cascades to their photos but not to their files.** `PrivateImage.owner` is `on_delete=CASCADE` (`privatemedia/models.py:30-34`), so the rows vanish while the bytes remain on the Railway volume under `/data/media/private/`. Enumerate and remove the orphans explicitly; nothing else will.

## Phase 1: Presentation foundation

### Overview

Create the project's first templates and stylesheet, and prove that a real `{% static %}` reference survives manifest storage and the build-time `collectstatic`. No authentication code lands in this phase — the point is to isolate the one failure mode that breaks deploys rather than pages.

### Changes Required:

#### 1. Settings — template and static discovery

**File**: `outfits_garderobe/settings.py`

**Intent**: Let Django find project-level templates and static sources, neither of which it currently looks for. `DIRS` must precede `APP_DIRS` in precedence so that Phase 2's allauth override actually wins.

**Contract**: `TEMPLATES[0]['DIRS'] = [BASE_DIR / 'templates']`; a new `STATICFILES_DIRS = [BASE_DIR / 'static']`. `STATIC_ROOT` and `STORAGES` are untouched. Add a comment recording that `STATICFILES_DIRS` must never point at `STATIC_ROOT`.

#### 2. Vendored stylesheet

**File**: `static/vendor/pico.min.css`

**Intent**: Provide sane, responsive defaults for semantic HTML — forms, buttons, typography, spacing — without inventing a class vocabulary that later slices would have to learn and extend.

**Contract**: Pico.css **v2.1.1**, classless build, committed to the repository rather than loaded from a CDN — an external stylesheet on every page load is a third-party dependency in the render path and cannot be hashed by manifest storage. Record the version in a sibling `static/vendor/README.md` so the next upgrade is not archaeology.

#### 3. Project stylesheet

**File**: `static/css/app.css`

**Intent**: Hold only what Pico does not: the site header layout, and anything specific to this product. Deliberately small — this file is the one most at risk of becoming the design system the roadmap warns about.

**Contract**: Targets the base template's landmark elements. No CSS framework, no preprocessor, no build step, no `@import` of remote resources.

#### 4. Base template

**File**: `templates/base.html`

**Intent**: The single layout every page in the product will extend, including — via Phase 2's override — every allauth screen.

**Contract**: A complete HTML document with `<meta name="viewport" content="width=device-width, initial-scale=1">`, both stylesheets via `{% static %}`, a `<main class="container">` wrapper, and blocks `title` and `content`. It renders `django.contrib.messages` (already installed, `settings.py:58`), because allauth reports every account action through them and they would otherwise be invisible. Navigation is added in Phase 3, when there are authenticated routes to point at.

### Success Criteria:

#### Automated Verification:

- System checks pass: `uv run python manage.py check`
- `collectstatic` succeeds under manifest storage with the new sources: `uv run python manage.py collectstatic --noinput`
- The full existing suite still passes: `uv run pytest`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- The hashed filenames for `pico.min.css` and `app.css` appear in `staticfiles/staticfiles.json`
- `git status` shows `staticfiles/` still ignored and only the intended sources staged

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 2: allauth wired up

### Overview

Install django-allauth and configure email-based accounts with mandatory verification, on top of the existing `auth.User`. At the end of this phase every account screen exists, is styled, and works in development against a console email backend.

### Changes Required:

#### 1. Dependency

**File**: `pyproject.toml`, `uv.lock`

**Intent**: Add allauth without the social-provider extra, which is the difference between one transitive dependency and five.

**Contract**: `uv add "django-allauth>=65.19,<66"`. Explicitly **not** `django-allauth[socialaccount]`.

#### 2. Settings — application wiring

**File**: `outfits_garderobe/settings.py`

**Intent**: Register the app, its middleware and its authentication backend. `ModelBackend` must remain first so the Django admin keeps working through the production cutover.

**Contract**: `INSTALLED_APPS` gains `'allauth'` and `'allauth.account'`. `MIDDLEWARE` gains `'allauth.account.middleware.AccountMiddleware'` at the end. A new `AUTHENTICATION_BACKENDS` lists `django.contrib.auth.backends.ModelBackend` then `allauth.account.auth_backends.AuthenticationBackend`. `django.contrib.sites` is **not** added and `SITE_ID` is **not** set — allauth 65.x account-only does not use them.

#### 3. Settings — account behaviour

**File**: `outfits_garderobe/settings.py`

**Intent**: Express the four product decisions — email is the identity, confirmation is required, duplicate signups say so plainly, and the session lifetime is the user's choice — as configuration rather than as code.

**Contract**:

```python
ACCOUNT_LOGIN_METHODS = {'email'}
ACCOUNT_SIGNUP_FIELDS = ['email*', 'password1*', 'password2*']
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'
ACCOUNT_PREVENT_ENUMERATION = False  # deliberate: see plan-brief
ACCOUNT_ADAPTER = 'accounts.adapter.AccountAdapter'
ACCOUNT_SIGNUP_FORM_CLASS = 'accounts.forms.SignupForm'
```

`ACCOUNT_SESSION_REMEMBER` is deliberately left unset; its default of `None` already renders the *Remember me?* checkbox. Each non-obvious value carries a comment in the house style — particularly `ACCOUNT_PREVENT_ENUMERATION`, which trades away a privacy property and must not read as an oversight to a future reviewer.

#### 4. Development email backend

**File**: `outfits_garderobe/settings.py`

**Intent**: Make confirmation and reset links readable during development without a mail provider. An unset `EMAIL_BACKEND` defaults to SMTP on `localhost:25`, which fails silently and would make mandatory verification look broken.

**Contract**: Under `DEBUG`, `EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'`. The production branch is Phase 4; leave a comment saying so rather than a half-configured SMTP block.

#### 5. The `accounts` app

**File**: `accounts/` (`__init__.py`, `apps.py`, `adapter.py`, `forms.py`)

**Intent**: House the two pieces of behaviour allauth cannot be configured into — writing the full email address into `User.username`, and refusing an address too long to fit there.

**Contract**: `adapter.py` holds a `DefaultAccountAdapter` subclass overriding `populate_username(request, user)` to assign `user.email`. `forms.py` holds the signup form wired through `ACCOUNT_SIGNUP_FORM_CLASS`, rejecting an address longer than `User.username`'s `max_length` of 150 as a **field error**. The split matters: `populate_username` runs during save, after form validation, so raising there would be an unhandled exception — a 500 on a public form — and allauth's email field accepts Django's 254-character default, so addresses in the 151–254 range do reach it. The adapter keeps its own length assertion as a non-user-facing invariant. `AppConfig.default_auto_field` matches `privatemedia/apps.py:7`. No models, and therefore no migration.

#### 6. URL routing for accounts

**File**: `outfits_garderobe/urls.py`

**Intent**: Mount allauth's routes at the prefix Django's own `LOGIN_URL` default already assumes.

**Contract**: `path('accounts/', include('allauth.urls'))`, placed above the `privatemedia` catch-all include so route resolution is unambiguous. The existing `/health/`, `/admin/` and `privatemedia` entries are untouched.

#### 7. allauth layout override

**File**: `templates/allauth/layouts/base.html`

**Intent**: Pull every allauth screen — login, signup, confirmation, password change, password reset — inside our own layout, in one file.

**Contract**: Extends `base.html` and maps allauth's `content` block into ours. This single template is sufficient because Pico styles semantic elements: allauth's markup needs no class attributes added. Do not copy allauth's individual templates into the project; overriding them wholesale is the maintenance burden this hook exists to avoid.

### Success Criteria:

#### Automated Verification:

- allauth's migrations apply cleanly: `uv run python manage.py migrate`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- System checks pass: `uv run python manage.py check`
- The existing suite still passes: `uv run pytest`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`
- allauth introduces no vulnerable dependency: `uv run pip-audit`

#### Manual Verification:

- Registering at `/accounts/signup/` creates a user whose `username` equals the full email address
- The confirmation email appears in the console, and following its link marks the address verified
- Logging in before confirming is refused; logging in after confirming succeeds
- The login form shows a *Remember me?* checkbox
- Password change at `/accounts/password/change/` works and the old password stops working
- The password reset flow completes end to end using the console-printed link
- Registering a second time with the same address gives a plain "already registered" error, not a silent success
- Every account screen inherits `base.html` and is usable at 360px
- Logging out requires a POST — a bare GET to the logout URL shows a confirmation page

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 3: Routing and the wardrobe placeholder

### Overview

Give the application its entry point, reserve the URL the wardrobe will occupy, repair the redirect `privatemedia` has been pointing at nothing, reset the development accounts, and write the smoke suite.

### Changes Required:

#### 1. Root and wardrobe routes

**File**: `accounts/views.py`, `outfits_garderobe/urls.py`

**Intent**: `/` carries no content of its own — it reads authentication state and sends the visitor onward. `/wardrobe/` is the authenticated destination, reserved now so S-02 and S-03 fill a page in rather than relocate one.

**Contract**: A root view redirecting anonymous visitors to `settings.LOGIN_URL` and authenticated ones to `wardrobe`; a `@login_required` wardrobe view rendering a placeholder. Routes `path('', ..., name='home')` and `path('wardrobe/', ..., name='wardrobe')`. Both live in `accounts` for now; S-03 will move the wardrobe into its own app, and the URL name is the contract that survives that move.

#### 2. Wardrobe placeholder template

**File**: `templates/wardrobe.html`

**Intent**: Tell a newly registered user, honestly, that there is nothing here yet.

**Contract**: Extends `base.html`. Deliberately minimal — S-03 replaces its body wholesale, and anything invested here is thrown away.

#### 3. Navigation in the base template

**File**: `templates/base.html`

**Intent**: Give authenticated users a visible way to reach their account and to log out — the UI half of FR-002.

**Contract**: A header showing, when `user.is_authenticated`, the account email plus links to password change and a **POST** log-out form (`ACCOUNT_LOGOUT_ON_GET` is `False`); when anonymous, links to log in and register. The log-out form carries `{% csrf_token %}`.

#### 4. Settings — login redirects

**File**: `outfits_garderobe/settings.py`

**Intent**: Point Django's authentication machinery at the routes that now exist. This is what repairs `privatemedia/views.py:46`, whose `@login_required` has been redirecting to a non-existent URL since F-01.

**Contract**: `LOGIN_URL = '/accounts/login/'`, `LOGIN_REDIRECT_URL = 'wardrobe'`, `LOGOUT_REDIRECT_URL = 'account_login'`. The two redirect targets are named routes so S-03 repoints the landing page by changing one string. `LOGIN_URL` is deliberately the **path**, not the `account_login` name: `privatemedia/tests/test_gate.py:83` asserts `Location.startswith(settings.LOGIN_URL)`, which compares against a URL and fails outright if this setting holds a route name. The path is fixed by the `accounts/` include prefix we control, so nothing is lost. Add a comment recording both that dependency and the tie back to the `privatemedia` gate, so a future edit sees what breaks.

#### 5. Account-reset management command

**File**: `accounts/management/commands/reset_legacy_accounts.py`

**Intent**: Make the riskiest step in this plan a reviewable artifact rather than a console session. The same command serves development here and production in Phase 4, where the operation is irreversible and cascades into files on a mounted volume.

**Contract**: Deletes `auth.User` rows that have no verified allauth `EmailAddress` — the pre-allauth accounts — and removes the files their `PrivateImage` rows orphan. **Defaults to a dry run**: it prints the users and the exact file paths it would remove and changes nothing unless explicitly told to commit. The file sweep has to be code regardless of how the deletion is triggered, because `on_delete=CASCADE` (`privatemedia/models.py:32`) removes rows and never bytes. Selecting on "no verified `EmailAddress`" rather than on a hardcoded username list is what makes it safe to run twice and safe to run in production.

#### 6. Development account reset

**File**: none — a local operation

**Intent**: Remove the pre-allauth users so development exercises only accounts created through the real flow. Neither existing row can log in through the new path anyway: `stranger` has no email at all, and neither has an `EmailAddress` record.

**Contract**: Run the command above in dry-run mode, confirm it names exactly the two known rows, then run it for real. Create a fresh superuser and register a normal account through `/accounts/signup/`. Development data only — production is Phase 4.

#### 7. Smoke test suite

**File**: `accounts/tests/__init__.py`, `accounts/tests/test_smoke.py`

**Intent**: Assert that every account URL resolves and that the redirect chain behaves for both authentication states. Scoped to smoke coverage by explicit decision.

**Contract**: Follows `privatemedia/tests/` conventions — `pytestmark = pytest.mark.django_db`, fixtures over setup methods. Covers: each allauth screen returns 200 for the appropriate actor; `/` redirects anonymous visitors to login and authenticated ones to `/wardrobe/`; `/wardrobe/` redirects an anonymous visitor rather than rendering; and the `privatemedia` gate's anonymous redirect now resolves to a real login page. That last assertion is the one that would otherwise let a future `LOGIN_URL` change silently re-break F-01.

### Success Criteria:

#### Automated Verification:

- The full suite passes, old and new: `uv run pytest`
- The new smoke suite passes on its own: `uv run pytest accounts/tests/`
- The `privatemedia` suite is unaffected: `uv run pytest privatemedia/tests/`
- System checks pass: `uv run python manage.py check`
- Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`

#### Manual Verification:

- Visiting `/` while logged out lands on the login page; while logged in, on `/wardrobe/`
- Registering, confirming and logging in reaches `/wardrobe/` without a manual URL entry
- The header log-out button ends the session and returns to the login page
- Requesting a private media URL while logged out lands on the real login page, not a 404
- The whole flow — register, confirm, log in, change password, log out — is usable at 360px width
- The local database contains only accounts created through the new flow, and no orphaned files remain under the development `MEDIA_ROOT`
- The `reset_legacy_accounts` dry run names exactly the expected rows and files before anything is deleted

**Implementation Note**: After completing this phase and all automated verification passes, pause here for manual confirmation from the human that the manual testing was successful before proceeding to the next phase.

---

## Phase 4: Production — real email, transport hardening, account reset

### Overview

Make password reset actually deliver, enable HSTS, guard the deploy configuration with a test, and retire the F-01 evidence accounts. This is the only phase with irreversible steps, which is why it is last.

### Changes Required:

#### 1. Settings — production email

**File**: `outfits_garderobe/settings.py`, `outfits_garderobe/settings_test.py`, `.env.example`

**Intent**: Send real mail through Brevo's SMTP relay, which verifies a single sender *address* rather than a whole domain — the only common free tier that reaches arbitrary recipients from a Railway hostname we do not own.

**Contract**: Outside `DEBUG`, Django's stock SMTP backend configured from the environment: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, plus `DEFAULT_FROM_EMAIL`. Read credentials with `os.environ[...]` rather than `os.getenv` with a default, matching how `SECRET_KEY` (`settings.py:26`) and the production `MEDIA_ROOT` (`settings.py:152`) already fail loudly at boot instead of running degraded — a silently unset mail password means every reset link is lost. `.env.example` gains the new keys with placeholder values and no secrets.

`settings_test.py` **must** gain the same keys in its existing `os.environ.setdefault` block (`settings_test.py:16-19`) in this phase, not later. The suite runs with `DEBUG=False`, so it executes this very branch; without the stubs the settings module raises `KeyError: 'EMAIL_HOST_PASSWORD'` at import and the entire suite fails to collect — every automated criterion below included. This is the same reason that block already stubs `SECRET_KEY` and `MEDIA_ROOT`.

#### 2. Settings — absolute URLs in email

**File**: `outfits_garderobe/settings.py`

**Intent**: Without the `sites` framework, allauth composes confirmation and reset links from this setting. Left at its `'http'` default, every emailed link would be redirected on click and, once HSTS is live, refused outright by some browsers.

**Contract**: `ACCOUNT_DEFAULT_HTTP_PROTOCOL = 'https'` outside `DEBUG`, `'http'` under it.

#### 3. Settings — HSTS

**File**: `outfits_garderobe/settings.py`

**Intent**: Discharge the debt `settings.py:43` assigned to this change, without creating an unrecallable mistake.

**Contract**: `SECURE_HSTS_SECONDS = 3600` inside the existing `if not DEBUG:` block. `SECURE_HSTS_PRELOAD` and `SECURE_HSTS_INCLUDE_SUBDOMAINS` are deliberately **not** set; replace the "left to S-01" comment with one recording that the max-age is intentionally short pending production verification, and that raising it is a later, separate decision.

#### 4. Settings — session lifetime

**File**: `outfits_garderobe/settings.py`

**Intent**: Give the *Remember me?* checkbox a defined meaning. A user standing at their wardrobe with a phone should not re-authenticate on every visit; the same cookie is the only credential guarding every private photo.

**Contract**: An explicit `SESSION_COOKIE_AGE` of two weeks, with a comment naming both sides of that trade-off. `SESSION_EXPIRE_AT_BROWSER_CLOSE` stays at its default — allauth sets it per-login from the checkbox.

#### 5. Deploy-configuration guard

**File**: `accounts/tests/test_deploy_config.py`

**Intent**: Turn a settings regression into a failing test, the same trick `privatemedia/tests/test_storage_config.py` plays for media storage.

**Contract**: Runs Django's `check --deploy` checks under production-like settings and asserts the resulting IDs against a named allow-list. Two IDs are allow-listed, each with a comment naming the harness artifact that causes it: `security.W009` (the 38-character key at `settings_test.py:16`) and `security.W008` (`settings_test.py:28` forces `SECURE_SSL_REDIRECT = False`, because leaving it on would turn every test-client request into a 301 before it reached a view). `security.W004` must **not** be allow-listed, since this phase fixes it. Verified against the current tree: the deployment checks emit exactly these three IDs today. The assertion is on specific IDs, never on an empty list — otherwise the harness's own artifacts make it unpassable.

#### 6. Railway environment

**File**: none — platform configuration

**Intent**: Supply the mail credentials the application now requires at boot.

**Contract**: Set `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` and `DEFAULT_FROM_EMAIL` on the `outfits-garderobe` service, from a Brevo account with the sender address verified. Imperative and outside the repository, exactly as F-01's volume was. `DEFAULT_FROM_EMAIL` must match the verified sender or Brevo rejects the message.

#### 7. Production account reset

**File**: none — runs the Phase 3 command against production

**Intent**: Retire the F-01 evidence accounts so production holds only accounts created through the real flow.

**Contract**: **After** the deploy is healthy and a fresh account has been registered and confirmed end to end — never before, or the environment has no way in. Run `reset_legacy_accounts` against production in its default dry-run mode first, read the list of users and orphaned paths beneath `/data/media/private/` it reports, and only then re-run it to commit. Note in `change.md` that F-01's production acceptance evidence was retired here deliberately, and that the impl-review record at `context/changes/private-media-gate/reviews/impl-review.md` remains its documentation.

### Success Criteria:

#### Automated Verification:

- The deploy-configuration guard passes: `uv run pytest accounts/tests/test_deploy_config.py`
- The full suite passes: `uv run pytest`
- Linting passes: `uv run ruff check .`
- Formatting is clean: `uv run ruff format --check .`
- No vulnerable dependencies: `uv run pip-audit`
- The deployment reaches a healthy state — `/health/` returns 200 after deploy
- Deploy logs show `collectstatic` and `migrate` completing without error

#### Manual Verification:

- A response from production carries a `Strict-Transport-Security` header with the expected max-age
- Registering a brand-new production account delivers a confirmation email to a real mailbox, and the link is `https://` and works
- Logging in before confirming is refused in production, as it is locally
- A full password reset completes from the emailed link
- Password change and log out work against production
- *Remember me?* unchecked ends the session on browser close; checked, it survives
- Requesting a private media URL while logged out lands on the production login page
- The whole flow is usable on a real phone, not just a narrowed desktop window
- After the account reset, production holds only accounts created through the new flow, and no orphaned files remain beneath `/data/media/private/`

**Implementation Note**: This is the final phase. Confirm all manual verification before considering S-01 complete and advancing the roadmap item to `done`.

---

## Testing Strategy

Scoped to smoke coverage by explicit decision, recorded in *Open Risks* below.

### Unit Tests:

- The account adapter writes the full email address into `username`
- The adapter refuses an address longer than `User.username`'s 150-character limit

### Integration Tests:

- Each allauth screen — login, signup, password change, password reset — returns 200 for the appropriate actor
- `/` redirects anonymous visitors to login and authenticated ones to `/wardrobe/`
- `/wardrobe/` redirects an anonymous visitor instead of rendering
- The `privatemedia` gate's anonymous redirect resolves to a real login page
- `check --deploy` reports nothing outside the documented allow-list

### Manual Testing Steps:

1. Register with a fresh address; confirm the email arrives and that logging in before clicking it is refused.
2. Confirm the address, log in, and verify the landing page is `/wardrobe/`.
3. Change the password; verify the old one stops working.
4. Log out via the header; verify the session ends and the login page returns.
5. Complete a password reset from a real mailbox.
6. Attempt to register the same address twice; verify the plain "already registered" error.
7. Walk the whole flow on a phone at 360px, checking for horizontal scrolling.
8. While logged out, request a private media URL; verify it lands on the login page.

## Performance Considerations

Nothing here approaches the PRD's five-second budget. The one operation with real latency is sending mail: an SMTP handshake inside the request-response cycle means signup and password-reset submissions block on Brevo. At MVP scale that is a second or two, well inside budget — but it is synchronous, and a Brevo outage turns signup into a timeout rather than an error page. Background sending is the fix, and it needs a worker the roadmap has deliberately not funded; revisit if signup latency becomes visible.

Pico.css adds roughly 80KB uncompressed, served once with a hashed filename under whitenoise's compression and immutable caching.

## Migration Notes

allauth's own migrations create `account_emailaddress` and `account_emailconfirmation`; no existing table is altered and no project model changes, so `makemigrations` produces nothing.

The delicate part is data, not schema. Pre-allauth users have no `EmailAddress` record, and with `ACCOUNT_LOGIN_METHODS = {'email'}` they cannot log in through the new flow at all — `stranger` has no email address, and neither account has a verified one. They are deleted rather than backfilled: development in Phase 3, production in Phase 4 and only after a fresh account has proven the flow. `ModelBackend` remains first in `AUTHENTICATION_BACKENDS` throughout, so `/admin/` stays reachable for the old superuser across the whole cutover — that is the property that makes the sequence recoverable at every step.

Deleting a user cascades to `PrivateImage` rows but leaves their files on disk. Both resets therefore pair the deletion with an explicit sweep of the orphaned bytes.

## References

- Change identity: `context/changes/user-accounts/change.md`
- Roadmap item S-01: `context/foundation/roadmap.md`
- PRD FR-001, FR-002, *Access Control*: `context/foundation/prd.md`
- Prior slice, for structure and conventions: `context/changes/private-media-gate/plan.md`
- The gate this change repairs the redirect for: `privatemedia/views.py:46`
- The settings-guard pattern reused in Phase 4: `privatemedia/tests/test_storage_config.py`
- The HSTS debt this change discharges: `outfits_garderobe/settings.py:43`
- django-allauth quickstart and configuration: https://docs.allauth.org/en/latest/installation/quickstart.html, https://docs.allauth.org/en/latest/account/configuration.html
- allauth template override hook: https://docs.allauth.org/en/latest/common/templates.html

## Progress

> Convention: `- [ ]` pending, `- [x]` done. Append ` — <commit sha>` when a step lands. Do not rename step titles. See `references/progress-format.md`.

### Phase 1: Presentation foundation

#### Automated

- [x] 1.1 System checks pass: `uv run python manage.py check` — 79ad4d4
- [x] 1.2 `collectstatic` succeeds under manifest storage with the new sources — 79ad4d4
- [x] 1.3 The full existing suite still passes: `uv run pytest` — 79ad4d4
- [x] 1.4 Linting passes: `uv run ruff check .` — 79ad4d4
- [x] 1.5 Formatting is clean: `uv run ruff format --check .` — 79ad4d4

#### Manual

- [x] 1.6 Hashed filenames for both stylesheets appear in `staticfiles/staticfiles.json` — 79ad4d4
- [x] 1.7 `git status` shows `staticfiles/` ignored and only intended sources staged — 79ad4d4

### Phase 2: allauth wired up

#### Automated

- [x] 2.1 allauth's migrations apply cleanly: `uv run python manage.py migrate`
- [x] 2.2 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- [x] 2.3 System checks pass: `uv run python manage.py check`
- [x] 2.4 The existing suite still passes: `uv run pytest`
- [x] 2.5 Linting passes: `uv run ruff check .`
- [x] 2.6 Formatting is clean: `uv run ruff format --check .`
- [x] 2.7 allauth introduces no vulnerable dependency: `uv run pip-audit`

#### Manual

- [x] 2.8 Registration creates a user whose `username` equals the full email address
- [x] 2.9 The confirmation email appears in the console and its link verifies the address
- [x] 2.10 Login before confirming is refused; after confirming it succeeds
- [x] 2.11 The login form shows a *Remember me?* checkbox
- [x] 2.12 Password change works and the old password stops working
- [ ] 2.13 The password reset flow completes via the console-printed link
- [x] 2.14 A duplicate signup gives a plain "already registered" error
- [x] 2.15 Every account screen inherits `base.html` and is usable at 360px
- [x] 2.16 Logging out requires a POST — a bare GET shows a confirmation page

### Phase 3: Routing and the wardrobe placeholder

#### Automated

- [ ] 3.1 The full suite passes, old and new: `uv run pytest`
- [ ] 3.2 The new smoke suite passes on its own: `uv run pytest accounts/tests/`
- [ ] 3.3 The `privatemedia` suite is unaffected: `uv run pytest privatemedia/tests/`
- [ ] 3.4 System checks pass: `uv run python manage.py check`
- [ ] 3.5 Nothing is left unmigrated: `uv run python manage.py makemigrations --check --dry-run`
- [ ] 3.6 Linting passes: `uv run ruff check .`
- [ ] 3.7 Formatting is clean: `uv run ruff format --check .`

#### Manual

- [ ] 3.8 `/` lands on login when logged out, on `/wardrobe/` when logged in
- [ ] 3.9 Register → confirm → log in reaches `/wardrobe/` without manual URL entry
- [ ] 3.10 The header log-out button ends the session and returns to login
- [ ] 3.11 A private media URL requested while logged out lands on the real login page
- [ ] 3.12 The whole flow is usable at 360px width
- [ ] 3.13 The local database holds only accounts from the new flow, with no orphaned media files
- [ ] 3.14 `reset_legacy_accounts` dry-run names exactly the expected rows and files before anything is deleted

### Phase 4: Production — real email, transport hardening, account reset

#### Automated

- [ ] 4.1 The deploy-configuration guard passes: `uv run pytest accounts/tests/test_deploy_config.py`
- [ ] 4.2 The full suite passes: `uv run pytest`
- [ ] 4.3 Linting passes: `uv run ruff check .`
- [ ] 4.4 Formatting is clean: `uv run ruff format --check .`
- [ ] 4.5 No vulnerable dependencies: `uv run pip-audit`
- [ ] 4.6 The deployment reaches a healthy state — `/health/` returns 200 after deploy
- [ ] 4.7 Deploy logs show `collectstatic` and `migrate` completing without error

#### Manual

- [ ] 4.8 A production response carries `Strict-Transport-Security` with the expected max-age
- [ ] 4.9 A new production registration delivers a confirmation email with a working `https://` link
- [ ] 4.10 Login before confirming is refused in production
- [ ] 4.11 A full password reset completes from the emailed link
- [ ] 4.12 Password change and log out work against production
- [ ] 4.13 *Remember me?* governs whether the session survives browser close
- [ ] 4.14 A private media URL requested while logged out lands on the production login page
- [ ] 4.15 The whole flow is usable on a real phone
- [ ] 4.16 Production holds only accounts from the new flow, with no orphaned files under `/data/media/private/`
