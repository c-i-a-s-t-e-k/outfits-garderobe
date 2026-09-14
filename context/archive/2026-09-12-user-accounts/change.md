---
change_id: user-accounts
title: Konto użytkownika — rejestracja, logowanie, wylogowanie i zmiana hasła
status: archived
created: 2026-09-12
updated: 2026-09-14
archived_at: 2026-09-14T12:11:03Z
---

## Notes

jest to S-01 z @context/foundation/roadmap.md

### Brevo onboarding (Phase 4) — 2026-09-12

- **Sender variant:** dedicated Gmail mailbox, no own domain. Verified sender in Brevo: `outfitsgarderobe@gmail.com` (Senders row name `outfits-garderobe`). This address is `DEFAULT_FROM_EMAIL` locally and on Railway.
- **Plan:** Brevo Free (300 emails/day), account confirmed.
- **Keys:** two separate v3 API keys (`xkeysib-…`) on the same Brevo account — one in the local `../.secrets/outfits-garderobe/.env`, one on Railway (`outfits-garderobe` / `production`). Either can be revoked without touching the other. Neither value was ever pasted into the session.
- **Railway:** `BREVO_API_KEY` set by the developer, `DEFAULT_FROM_EMAIL` by the agent, both with `--skip-deploys` (no deploy triggered). The key is deliberately **not sealed** — sealed values are not provided to `railway run`, which the validity probe relies on. Sealing is a separate, later decision.
- **Checks:** Railway probe `account: 200`, `active sender: 1`; local probe likewise (after adding the missing `DEFAULT_FROM_EMAIL` line to the local `.env`).
- **Test send:** `send: 201` to a non-sender mailbox. From appeared rewritten to `outfitsgarderobe@<id>.brevosend.com`, as expected for an unauthenticated free-mail sender. Landed in **Inbox**, not spam. Brevo *Transactional → Logs* shows `sent` then `delivered`.
- **Moving to an own domain later** touches only Brevo (authenticate domain, add sender) and the `DEFAULT_FROM_EMAIL` value — no code change.
- Unrelated observation: Railway deployment `a47ace49` from 2026-09-10 is `FAILED`; production still runs `fa3b69dd` (2026-09-06). Worth understanding before the Phase 5 push.

### Production deploy (Phase 5) — 2026-09-12

- **Root cause of failed deployment `a47ace49` (2026-09-10):** `96f025c` turned on `SECURE_SSL_REDIRECT`, and Railway's healthcheck probes `/health/` over plain HTTP with no `X-Forwarded-Proto`, so every attempt got a 301 and the replica "never became healthy". Production kept running `fa3b69dd` (`85d7fc4`) — i.e. nothing after F-01's close-out had actually shipped. Fixed with `SECURE_REDIRECT_EXEMPT = [r'^health/$']`, pinned by `accounts/tests/test_deploy_config.py::test_healthcheck_is_not_redirected_to_https`. Not in the original plan.
- **Deploy allow-list deviation from plan:** with HSTS on, `check --deploy` also emits `security.W005` (no INCLUDE_SUBDOMAINS) and `security.W021` (no PRELOAD). Both are deliberate per the HSTS decision and are allow-listed as `DELIBERATE_DEVIATIONS`, separately from the harness artifacts W008/W009.
- **Deployed:** `6ed120f` as deployment `4386ce37` — build `collectstatic` OK, allauth migrations `account.0001`–`0009` applied, healthcheck succeeded, no `KeyError` at boot. Live: `Strict-Transport-Security: max-age=3600`, `/` and `/wardrobe/` → login, anonymous private-media URL → login page (200), hashed Pico CSS served.
- **Manual verification (2026-09-12):** the developer confirmed 5.9–5.17 against production — signup confirmation mail delivered via Brevo with a working `https://` link, login-before-confirm refused, password reset and change, log out, *Remember me?*, private-media redirect, real phone. The first attempt went to the local `runserver` (console backend), which is why Brevo logged nothing; production was not at fault. 2.13 (reset via console link) was confirmed alongside.
- **Legacy account reset — F-01's production acceptance evidence retired deliberately.** `reset_legacy_accounts` dry run named exactly `ciastek-django-admin` (superuser) and `outsider` (blank email) plus their two files under `/data/media/private/`; `--commit` deleted 7 rows across cascades and 2 files. Before it, the single verified new-flow account was promoted to staff + superuser so `/admin/` stays reachable (not in the plan; the old superuser was the only admin). After: 1 user, 0 without `EmailAddress`, 0 `PrivateImage` rows, 0 orphaned files. F-01's evidence remains documented in `context/changes/private-media-gate/reviews/impl-review.md`.
- **Access used:** the developer's `~/.ssh/id_ed25519.pub` was registered with Railway as `ciastek-laptop-id_ed25519` for `railway ssh`. Remove with `railway ssh keys remove` if it should not persist.
- **Observability gap (open):** no `LOGGING` config, so production 500s never reach stdout, and gunicorn's access log is off. Worth a small follow-up change.
