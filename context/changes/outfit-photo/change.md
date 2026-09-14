---
change_id: outfit-photo
title: Outfit photo
status: implemented
created: 2026-09-14
updated: 2026-09-14
archived_at: null
---

## Notes

- Jira OG-5, roadmap S-04. Built in worktree `/home/ciastek/Projects/.worktrees/outfit-photo` on `feat/outfit-photo`, from `origin/master` at `787aa1f`.
- 2026-09-14: the developer moved the production database to an EU region — database reads and writes are much faster than before.
- 2026-09-14: PR deploy — https://github.com/c-i-a-s-t-e-k/outfits-garderobe/pull/7, Railway environment `outfits-garderobe-pr-7` (`c1d8d9dc-7a12-4713-ad32-a2d20330ced6`). The status check went green on deployment `775a7c46-f9d5-45dd-801f-7558e74f233b`, and its pre-deploy `migrate` applied `outfits.0003_outfit_photo` on Postgres. Browser checks ran on deployment `412deb81-450b-4ed5-86af-7d83665959c0`.
  - Checks run:
    - 4.1–4.3 locally: 294 passed, no pending migrations, deploy guard.
    - 4.7: `/health/` returned 200.
    - 4.8–4.10 in headless Chromium at 360 px: compose → outfit page → upload with "Uploading…", a disabled button and one POST → photo upright and whole (1200×1600) → 3:4 photo tile. Replace: the old URL returns 404, and the old file is gone from `/data/media` (checked over `railway ssh`). Remove went through the confirmation page, and the file was deleted. The tile went back to the collage. A second account got 404 on the outfit page, remove page and photo URL, and 403 on a foreign upload POST, and its wardrobe was empty.
    - The developer then repeated the flow on a real phone, and it worked.
  - Deviations:
    - The base branch check needed no rebase (`origin/master` still at `787aa1f`).
    - With the developer's approval, `ALLOWED_HOSTS=${{RAILWAY_PUBLIC_DOMAIN}}` and `CSRF_TRUSTED_ORIGINS=https://${{RAILWAY_PUBLIC_DOMAIN}}` were set on the PR-7 environment only. Before that, `/health/` returned 400.
    - Two verified accounts were seeded over `railway ssh` with `manage.py shell`. The ssh shell lacks the runtime `LD_LIBRARY_PATH`, so pillow-heif failed to import until the value was copied from PID 1. Gunicorn is unaffected.
    - The agent's 360 px check used a synthetic 12 MP EXIF-rotated JPEG; the real-phone photo check was done by the developer.
    - Automating the host variables and account seeding is tracked in Jira OG-13.
  - 4.11 (merge + production `/health/`) happens after this close-out lands, so it stays unchecked in Progress.
