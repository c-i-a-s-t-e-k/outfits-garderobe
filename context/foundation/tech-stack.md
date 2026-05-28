---
starter_id: django
package_manager: uv
project_name: outfits-garderobe
hints:
  language_family: python
  team_size: solo
  deployment_target: fly
  ci_provider: github-actions
  ci_default_flow: auto-deploy-on-merge
  bootstrapper_confidence: verified
  path_taken: standard
  quality_override: false
  self_check_answers: null
  has_auth: true
  has_payments: false
  has_realtime: false
  has_ai: false
  has_background_jobs: false
---

## Why this stack

Django is the recommended default for `(web-app, python)` and passes convention_based, popular_in_training, and well_documented quality gates. Solo developer with a 5-week timeline shipping a photo-centric wardrobe app with auth and file storage needs a batteries-included framework that covers both without extra integration work. Django ships `django.contrib.auth` (email + password, extensible to OAuth via django-allauth) and `ImageField`/`FileField` with `django-storages` for photo uploads, matching the two technology-forcing features detected in the PRD (FR-001 auth, FR-003/FR-007 file storage). PostgreSQL as the default database suits the relational outfit–garment many-to-many model. Fly.io is the card's default deployment target; GitHub Actions with auto-deploy-on-merge is the standard shape. Bootstrapper confidence is verified — scaffolding will be smooth.
