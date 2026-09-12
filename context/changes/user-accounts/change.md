---
change_id: user-accounts
title: Konto użytkownika — rejestracja, logowanie, wylogowanie i zmiana hasła
status: implementing
created: 2026-09-12
updated: 2026-09-12
archived_at: null
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
