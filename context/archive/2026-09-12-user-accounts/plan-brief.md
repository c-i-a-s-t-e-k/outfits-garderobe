# Konto użytkownika — rejestracja, logowanie, wylogowanie i zmiana hasła — Plan Brief

> Full plan: `context/changes/user-accounts/plan.md`
> Change identity: `context/changes/user-accounts/change.md`
> Roadmap item: S-01, milestone M-1, stream B
> Research: `context/changes/user-accounts/brevo-onboarding.md` (Brevo onboarding, 2026-09-12)

## What & Why

A visitor can register with an email address, confirm it, log in, log out and change their password; anyone not logged in lands on the login page rather than on content. This is roadmap slice **S-01**, the head of the whole dependency graph — until accounts exist, no other slice has anyone's data to show. It satisfies PRD **FR-001**, **FR-002** and the *Access Control* section, and it resolves roadmap Open Question #1 as **email + password, no OAuth in M-1**.

Two things ride along because nothing else can carry them: this is the first slice with a visible interface, so it creates the base template and stylesheet every later view inherits; and `settings.py:43` explicitly parks HSTS here — *"HSTS is left to S-01, which owns the auth flow."*

## Starting Point

The repo has no user interface at all: `TEMPLATES['DIRS']` is empty, `STATICFILES_DIRS` is unset, and no `.html` file exists. Identity is stock `auth.User`, already referenced by a `PrivateImage` FK from F-01. There is no email configuration anywhere. Three things surfaced during research: `privatemedia`'s `@login_required` currently redirects to Django's default `/accounts/login/`, **a URL that does not exist** — so F-01's anonymous case passes only in the loosest sense; `CompressedManifestStaticFilesStorage` is live with `collectstatic` running at nixpacks *build* time, so the first bad `{% static %}` reference breaks the deploy rather than a page; and both dev and production hold F-01's test accounts, one of them (`stranger`) with a blank email.

## Desired End State

Someone new registers with their email, receives a confirmation link that actually arrives in their inbox, clicks it, logs in, and lands on their (empty) wardrobe. They can change their password, log out, and — having forgotten it — get themselves back in by email without anyone's help. Every screen is legible on a 360-pixel phone, which is where the PRD says this product is actually used.

## Key Decisions Made

| Decision | Choice | Why (1 sentence) | Source |
| --- | --- | --- | --- |
| User model | Keep `auth.User`, email written into `username` | Avoids a swap against live production data; allauth's own `account_emailaddress` table supplies the real unique constraint that plain `auth.User` would have lacked. | Plan |
| External login | Email + password only | Roadmap Open Question #1 resolved — FR-001 is satisfied either way, and OAuth adds provider setup for no new capability in the end-to-end flow. | Plan |
| Password recovery | Reset by email, in this slice | Without it a forgotten password is unrecoverable; FR-002 alone would have left that hole open. | Plan |
| Auth machinery | django-allauth 65.19 | One library covers registration, verification, reset and change; verified to support Django 6.0 and, account-only, to add just `asgiref`. | Plan |
| Email provider | Brevo, verified single sender | The only common free tier that reaches arbitrary recipients without owning a domain — this project is on a `*.up.railway.app` hostname. | Plan |
| Email transport | Brevo HTTP API via `django-anymail[brevo]`, 10 s timeout | Railway Hobby blocks outbound SMTP, so the originally planned SMTP relay cannot connect from the container. | Research |
| Sender identity | Dedicated Gmail mailbox, no own domain; From rewritten to `…@brevosend.com` | Working in one session at zero cost; moving to a domain later touches only Brevo and `DEFAULT_FROM_EMAIL`. `@duck.com` is excluded (DMARC `p=quarantine`). | Plan (research leaned domain) |
| Onboarding | Its own phase (4), before production, no code | A human-at-the-browser step whose output Phase 5's settings require at boot. | Plan |
| Secret handling | Developer alone writes the API key to `.env` and Railway; agent checks print no values; key not sealed | Keeps the key out of the transcript; sealed values are hidden from `railway run`, which the validity check needs. | Plan |
| Onboarding "done" | Keys present and valid in both places (`GET /v3/account` 200, sender active) + one real send (201, delivered) | Presence alone would pass an SMTP key or a mistyped sender and break Phase 5 on its first signup. | Plan |
| Email verification | Mandatory before first login | Turns a mistyped address into an immediate visible failure rather than a silent lockout discovered the day recovery is needed. | Plan |
| Styling | Vendored Pico.css v2.1.1 + a short project stylesheet | Classless CSS styles semantic HTML, so allauth's plain templates come out right with one override file and no class vocabulary to invent — structurally resists the design-system sprawl the roadmap flags as S-01's main risk. | Plan |
| Entry point | `/` is a pure redirect; `/wardrobe/` is the reserved destination | Settles the URL shape now so S-02 and S-03 fill a page in rather than relocate one. | Plan |
| Enumeration | `ACCOUNT_PREVENT_ENUMERATION = False` | Chosen for a clear "already registered" message over allauth's silent-success default. | Plan |
| Existing accounts | Deleted, superuser re-created | Leaves one class of account rather than two; the pre-allauth rows cannot log in through the new flow anyway. | Plan |
| Hardening | HSTS at 1h, `check --deploy` guard, "Remember me" | Discharges the parked HSTS debt at a max-age a mistake can outlive, and pins the deploy config the way F-01 pinned media storage. | Plan |
| Test scope | Smoke tests only | Explicit scope decision by the developer; see Open Risks. | Plan |

## Scope

**In scope:** the `templates/` and `static/` foundation with Pico.css and `base.html`; django-allauth with email login, mandatory verification and password reset; an account adapter writing the email into `username`; `/` and `/wardrobe/` routing; `LOGIN_URL` (which repairs `privatemedia`'s dangling redirect); HSTS, session lifetime and a `check --deploy` guard; a guided Brevo onboarding (account, Gmail sender, v3 API key, credentials in local `.env` and on Railway); Brevo over its HTTP API in production; deletion of the F-01 test accounts in both environments.

**Out of scope:** any custom user model; OAuth and social login; garments, outfits, tags and the real wardrobe; profile fields, avatars and account deletion; MFA, login-by-code and session-management UI; changes to allauth's default rate limits; any design system, component library or build step; changes to `privatemedia`'s model, view or tests; an own sending domain, sealed Railway variables, Brevo webhooks.

## Architecture / Approach

allauth sits on top of the stock `auth.User`. The `username` column is never shown to anyone: a small account adapter writes the confirmed email into it, keeping the column populated and unique without a model swap. Email uniqueness is enforced by allauth's own table, which has a real database constraint. Templates flow through one file — `templates/allauth/layouts/base.html` extends our `base.html` — and because Pico styles semantic elements rather than classes, that single override styles every account screen without touching allauth's markup. Routing is thin: `/` reads authentication state and redirects; `/wardrobe/` is the login-gated destination, holding a placeholder until S-03. Development uses a console email backend; production uses anymail's Brevo backend over HTTPS, with its API key and sender read from the environment with no fallback, the same fail-loudly-at-boot pattern `SECRET_KEY` and `MEDIA_ROOT` already follow.

## Phases at a Glance

| Phase | What it delivers | Key risk |
| --- | --- | --- |
| 1. Presentation foundation | `templates/`, `static/`, Pico.css, `base.html`, settings wiring | The first real `{% static %}` under manifest storage — a bad reference fails the Railway *build*, not a page |
| 2. allauth wired up | Dependency, `ACCOUNT_*` settings, `/accounts/` routes, adapter, layout override, console email | allauth's default derives `username` from the email's local part, not the full address — the adapter must override it |
| 3. Routing and placeholder | `/` redirect, `/wardrobe/`, `LOGIN_URL`, dev account reset, smoke tests | Login redirects are what repair F-01's gate; getting them wrong re-breaks a shipped guarantee |
| 4. Brevo onboarding | Brevo account, verified Gmail sender, v3 API key; `BREVO_API_KEY` + `DEFAULT_FROM_EMAIL` proven valid locally and on Railway; one real send | Leaking the key into the transcript, or a wrong key type (SMTP/v2) that only fails once code ships |
| 5. Production | anymail Brevo backend, HSTS, `check --deploy` guard, production account reset | The only irreversible phase — HSTS cannot be recalled, and deleting accounts orphans files that `CASCADE` will not clean up |

**Prerequisites:** none — S-01 has no upstream roadmap dependency and ran in parallel with F-01. Phase 4 needs a browser, a password manager and Railway access to the `outfits-garderobe` service; Phase 5 needs Phase 4's credentials in place.
**Estimated effort:** ~5 sessions, one per phase; Phase 2 is the substantial one, Phase 4 is a short guided session.

## Open Risks & Assumptions

- **Smoke-only testing leaves this slice's access boundaries unproven.** S-01 is where "only your data" is defined for the entire product, and the suite will not assert it beyond the redirect chain. Mitigated slightly by testing that `privatemedia`'s anonymous redirect resolves to a real login page — enough to catch a `LOGIN_URL` regression, not enough to catch an authorization one. Accepted deliberately; worth revisiting before launch.
- **`ACCOUNT_PREVENT_ENUMERATION = False` affects password reset too, not just signup.** The reset form will also reveal whether an address has an account. In a product whose stated guardrail is privacy, that is a real disclosure; allauth offers a `'strict'` middle setting if the trade looks worse in practice than on paper.
- **Mail is sent synchronously inside the request.** Signup and reset block on an HTTPS call to Brevo's API — well under a couple of seconds normally, up to the 10-second anymail timeout during a Brevo outage. The fix is a background worker, which the roadmap has deliberately not funded.
- **Brevo's free tier is a shared sending pool, and the From is rewritten.** Until an own domain is authenticated, recipients see `…@<id>.brevosend.com` instead of the Gmail sender, plus a "Sent with Brevo" sticker. Reset mail may land in spam; the failure is silent from the app's side — the send succeeds and the user never sees it.
- **The Railway API key is not sealed.** Anyone with project access can read it in the dashboard; sealing would hide it but also from `railway run`, which the validity check uses. Revisit once Phase 5 is live.
- **Brevo's manual account validation is unconfirmed.** New accounts may need a validation form before the API accepts sends; the symptom is 401/403 with a correct v3 key.
- **HSTS is irreversible for its own max-age.** Shipping at one hour with no preload and no subdomains keeps a mistake survivable; raising it is a later, separate decision that is easy to forget.
- **Deleting the production accounts retires F-01's acceptance evidence.** Its impl-review record remains the documentation. The orphaned files under `/data/media/private/` must be swept by hand — `CASCADE` removes rows, never bytes.
- **Assumes a mailbox is available for production testing** that is not the Brevo sender address itself, since a message from and to the same address is a weak test of deliverability.

## Success Criteria (Summary)

- A brand-new user registers, confirms by email, logs in, and reaches their wardrobe — entirely on a phone, without help.
- A user who has forgotten their password gets back into their account unaided, via a link that arrives in a real inbox.
- Nobody who is not logged in can reach any content, including a private photo, and lands on a real login page instead.
