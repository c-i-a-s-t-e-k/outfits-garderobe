---
bootstrapped_at: 2026-05-28T17:16:00Z
starter_id: django
starter_name: Django
project_name: outfits-garderobe
language_family: python
package_manager: uv
cwd_strategy: native-cwd
bootstrapper_confidence: verified
phase_3_status: ok
audit_command: pip-audit --format json
---

## Hand-off

```yaml
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
```

### Why this stack

Django is the recommended default for `(web-app, python)` and passes convention_based, popular_in_training, and well_documented quality gates. Solo developer with a 5-week timeline shipping a photo-centric wardrobe app with auth and file storage needs a batteries-included framework that covers both without extra integration work. Django ships `django.contrib.auth` (email + password, extensible to OAuth via django-allauth) and `ImageField`/`FileField` with `django-storages` for photo uploads, matching the two technology-forcing features detected in the PRD (FR-001 auth, FR-003/FR-007 file storage). PostgreSQL as the default database suits the relational outfit–garment many-to-many model. Fly.io is the card's default deployment target; GitHub Actions with auto-deploy-on-merge is the standard shape. Bootstrapper confidence is verified — scaffolding will be smooth.

## Pre-scaffold verification

| Signal | Value | Severity | Notes |
| --- | --- | --- | --- |
| npm package | not run | — | non-JS starter; npm recency check skipped |
| GitHub repo | django/django last pushed 2026-05-27 | fresh | docs_url points to docs.djangoproject.com (not GitHub); looked up django/django directly |

## Scaffold log

**Resolved invocation**: `uv init --name outfits-garderobe && uv add django && uv run django-admin startproject outfits_garderobe .`
**Strategy**: native-cwd
**Exit code**: 0
**Pre-flight files-to-touch**: manage.py, outfits_garderobe/, pyproject.toml, .python-version, README.md, uv.lock, .venv/
**Files written by CLI**: 8 (manage.py, outfits_garderobe/__init__.py, outfits_garderobe/settings.py, outfits_garderobe/urls.py, outfits_garderobe/wsgi.py, outfits_garderobe/asgi.py, pyproject.toml, .python-version)
**Pre-existing files preserved**: CLAUDE.md, .gitignore, context/ (all contents)
**Post-scaffold cleanup**: removed uv-init boilerplate main.py (not needed for Django)

## Post-scaffold audit

**Tool**: `pip-audit --format json`
**Summary**: 0 CRITICAL, 0 HIGH, 0 MODERATE, 0 LOW
**Direct vs transitive**: not distinguished by this tool

No vulnerabilities found. Clean dependency tree.

Dependencies audited: asgiref 3.11.1, django 6.0.5, sqlparse 0.5.5 (plus dev dependencies: pip-audit and its transitive deps).

## Hints recorded but not acted on

| Hint | Value |
| --- | --- |
| bootstrapper_confidence | verified |
| quality_override | false |
| path_taken | standard |
| self_check_answers | null |
| team_size | solo |
| deployment_target | fly |
| ci_provider | github-actions |
| ci_default_flow | auto-deploy-on-merge |
| has_auth | true |
| has_payments | false |
| has_realtime | false |
| has_ai | false |
| has_background_jobs | false |

## Next steps

Next: a future skill will set up agent context (CLAUDE.md, AGENTS.md). For now, your project is scaffolded and verified — happy hacking.

Useful manual steps in the meantime:
- `git init` (if you have not already) to start your own repo history.
- Review any `.scaffold` siblings the conflict policy created and decide which version of each file to keep.
- Address audit findings per your project's risk tolerance — the full breakdown is in this log.
