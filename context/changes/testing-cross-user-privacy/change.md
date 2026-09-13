---
change_id: testing-cross-user-privacy
title: Cross-user privacy contract tests (test-plan rollout Phase 1)
status: implemented
created: 2026-09-13
updated: 2026-09-13
archived_at: null
---

## Notes

Open a change folder for rollout Phase 1 of context/foundation/test-plan.md: "Cross-user privacy contract".
Risks covered: #1 (a user's garment/outfit photo or record becomes visible to another user or an anonymous visitor — guessed media URL, list/grid not scoped by owner, media served outside the gate), #2 (abuse: a user changes someone else's data because the server trusts an id from the request — composes an outfit from another user's garment, edits/deletes/tags another user's outfit or garment). Test types planned: integration (Django test client, two users).
Risk response intent:
- #1: prove that with two accounts, user B gets a denial/404 on every photo and every owner-scoped page of user A, anonymous requests land on login, no media URL form bypasses the gate, and a newly added owner-scoped route is covered by a route-enumerating check without someone remembering to add a test. Challenge "the view requires login, so the data is private" — authentication is not ownership. Avoid owner-only happy paths and asserting status code only while the body still contains the other user's data.
- #2: prove that a write request carrying another user's object id is refused and changes nothing in the database, and that form choice lists contain only the requester's objects. Challenge "the form only offers my garments, so ent can post any id. Avoid asserting only the HTTP status withoutre-reading persisted state.
Goal: make new owner-scoped views inherit the check before roadmap S-
After creating the folder, follow the downstream continuation rule: suggest /10x-research next.
