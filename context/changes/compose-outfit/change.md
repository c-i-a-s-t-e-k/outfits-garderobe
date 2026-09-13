---
change_id: compose-outfit
title: Wizualne składanie outfitu i siatka garderoby
status: implementing
created: 2026-09-13
updated: 2026-09-13
archived_at: null
---

## Notes

jest to S-03 z @context/foundation/roadmap.md — Jira: OG-4 (In progress)

- **Cel:** użytkownik może wizualnie złożyć outfit z dodanych ubrań, zapisać go i zobaczyć w siatce garderoby; outfit bez własnego zdjęcia pokazuje podgląd złożony ze zdjęć ubrań; jedno ubranie może należeć do wielu outfitów naraz.
- **PRD:** FR-005, FR-008, US-01.
- **Zależności:** S-02 (dodawanie ubrania) — done (2026-09-13).
- **Pytania otwarte:** brak.
- **Ryzyko:** wizualny wybór ubrań na ekranie 360 px — siatka miniatur i zaznaczanie łatwo stają się nieużywalne.
- **Środowisko pracy (2026-09-13):** worktree `/home/ciastek/Projects/outfits-garderobe-compose-outfit`, gałąź `feat/compose-outfit`, równolegle z inną pracą w głównym checkoucie. Dostarczenie przez PR do `master`, nie bezpośredni push.

### Production deploy (2026-09-13)

- **PR:** https://github.com/c-i-a-s-t-e-k/outfits-garderobe/pull/2 — merged 2026-09-13 18:23 UTC, merge commit `3c93cfd`. Railway PR check `outfits-garderobe - outfits-garderobe` was green before the merge.
- **Deployment:** `36cb5d2c-aac1-435a-a0c6-0acd6fe425a1` (environment `production` `3e5cef2e-a1f6-4a61-9546-26b2cc54a95b`, service `ef901136-0af7-4104-8f42-cce2a8e7e8a7`) → `SUCCESS`.
- **Checks run:** the pre-deploy log shows `Applying outfits.0001_initial... OK`; `GET /health/` → 200; anonymous `/wardrobe/`, `/wardrobe/compose/` and `/` → 302 to `/accounts/login/`.
- **Manual checks 1.8–3.13 (agent, 2026-09-13):** run in headless Chromium (Playwright, 360×780, touch) against the local dev server on :8001 from this worktree, using three local accounts (`qa-carol` staff, `qa-dave`, `qa-erin`, all `@example.com`). Garments were uploaded through `/garments/add/` and outfits composed through the form. All passed: landing on *Wardrobe* with the nav order *Wardrobe → Garments*; 2/3/4/7-garment tiles square, the 7 showing `+3` and the first four in type order; picker and grid two tiles per row with no horizontal scroll and the save bar visible; with JS off the outline and "N selected" count work (2 → 1); a 1-garment save shows the error and keeps the selection and name; the detail page shows all 7 garments; tapping a tile opens the detail page; a second account gets 404 on the detail page and on the photo gate, and sees no foreign photos in its grid or picker; a new account gets the "Add at least 2 garments" state; in admin a blank name saves as `outfit-1`.
- **Finding (1.9):** in admin, a foreign garment id is refused and nothing is stored (outfit and link-row counts unchanged; the admin transaction rolls back). But the user sees **HTTP 500** (`ValidationError at /admin/outfits/outfit/add/`) instead of a form error, because the `m2m_changed` guard raises outside form validation. Staff-only path, no data leak; a candidate for a follow-up (e.g. validating ownership in `OutfitAdmin`'s form).
- **Manual checks 4.9–4.11:** waiting on the developer — they need two logged-in production accounts (signup confirms a real e-mail).
- **Deviations from the plan:** besides the four S-03 commits, the PR also carried three docs commits made during the PR (`b0987c7`, `09ecfdc`, `b9fd04d`: CLAUDE.md and `infrastructure.md` notes on Railway PR environments). The developer made them on purpose; they are not code. This note is committed on `feat/compose-outfit` after the merge and reaches `master` in a follow-up PR (with `/10x-archive`).
