---
change_id: outfit-tags
title: Outfit tags
status: implemented
created: 2026-09-13
updated: 2026-09-14
archived_at: null
---

## Notes

<!-- Free-form notes for this change: links, ad-hoc context, decisions that don't belong in research/frame/plan. -->

- 2026-09-13: folder renamed from `outfits-tags` to `outfit-tags` to match the roadmap Change ID (S-05), branch `feat/outfit-tags` and Jira OG-6.
- 2026-09-14: PR deploy — https://github.com/c-i-a-s-t-e-k/outfits-garderobe/pull/5, Railway environment `outfits-garderobe-pr-5` (`c46701c7-bac3-4ad9-87cf-c0ef1713174b`), deployment `8847f364-3939-48b3-a5d8-d67bdf788236`: status check green, pre-deploy `migrate` applied `outfits.0002_tag` on Postgres.
  - Deviations from the plan:
    - Rebasing onto `master` also carried `cce90e9` (S-03 roadmap close-out, committed on local `master` and never pushed) and the new lesson "Done means all checks pass on the PR deploy".
    - The privacy net had no notion of a POST-only route. `OwnerScopedRoute` gained `post_only`, which makes the photo scenario require GET → 405 and the stranger scenario probe with POST. The foreign-write snapshot and cross-owner check now cover tags and outfit–tag links. Verified by dropping `owner=request.user` from each tag view: 3 contract cases went red each time.
  - PR-environment browser checks (4.10–4.12) were skipped by the developer's decision. Setting `ALLOWED_HOSTS=${{RAILWAY_PUBLIC_DOMAIN}}` and `CSRF_TRUSTED_ORIGINS=https://${{RAILWAY_PUBLIC_DOMAIN}}` on the PR environment made `/health/` return 200 there. But signup has mandatory e-mail verification, and seeding verified accounts over `railway ssh` was not permitted in the agent session, so no signed-in check could run.
- 2026-09-14: slice closed out by the developer's decision, before merge. Manual checks 4.10–4.12 are skipped on both the PR environment and production. Post-merge rows 4.7–4.9 stay unchecked in Progress, because this close-out lands in PR #5 before the merge happens. The substance of 4.8 (`migrate` applying `outfits.0002_tag` on Postgres) was already verified on the PR deploy. Roadmap S-05 → `done`, and S-07 (`outfit-lifecycle`) is ready for `/10x-plan`. Jira: OG-6 → Done, OG-8 → Ready.
