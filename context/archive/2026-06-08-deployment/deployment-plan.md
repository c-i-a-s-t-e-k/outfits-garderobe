# Railway Integration & Deployment Plan

## Context

The project is a freshly scaffolded Django 6 app with zero production hardening. The goal is to make it deployable on Railway (Hobby tier) with a managed PostgreSQL service. All settings are currently hardcoded for development (DEBUG=True, SQLite, hardcoded SECRET_KEY, empty ALLOWED_HOSTS). Railway expects a gunicorn-served WSGI app, env-var-driven config, and PostgreSQL.

---

## Phase 0 — Prerequisites: CLI & tooling setup

### Railway CLI

Install (choose one):
```bash
# curl — also runs `railway setup agent` which wires MCP automatically
bash <(curl -fsSL railway.com/install.sh) --agents -y

# Homebrew (macOS)
brew install railway

# npm (requires Node 16+)
npm i -g @railway/cli
```

Authenticate and link the local repo to a Railway project:
```bash
railway login          # opens browser; use --browserless if headless
railway link           # interactive: pick workspace → project → environment → service
```

`railway link` writes config to `.railway/` in the project root. Add `.railway/` to `.gitignore` — it contains local environment mappings, not secrets, but it's machine-specific.

> **Edge case — CI/headless environments:** `railway login --browserless` prints a URL + pairing code. Open the URL in any browser to complete auth. Token is stored in `~/.railway/config.json`.

- [x] Railway CLI installed
- [x] `railway login` completed
- [x] `railway link` run against the project service

---

### Railway API token (for MCP Server)

Generate a personal token at **railway.app → Account → Tokens → New Token**. Store it in your shell profile or a local `.env` (never commit it):
```bash
export RAILWAY_API_TOKEN=your_token_here
```

- [x] `RAILWAY_API_TOKEN` generated and stored locally !!Mind that for securyty porposes the .env file is outside working directory ../.secrets/outfits-garderobe/.env never try to read it just know that it exist

---

### Railway MCP Server (Claude Code integration)

Adds structured tools (`railway:deploy`, `railway:logs`, `railway:env`, etc.) so agents can operate Railway without CLI string parsing.

```bash
# Official Railway MCP Server — registers under the name "railway-mcp-server"
claude mcp add railway-mcp-server -- npx -y @railway/mcp-server
```

If the curl install above was used with `--agents`, this step may already be done. Verify:
```bash
claude mcp list
```

The MCP Server authenticates via the Railway CLI session — no separate `RAILWAY_API_TOKEN` env var required if `railway login` was already completed on the same machine.

> **Edge case — token-based auth (CI or fresh machine):** If the CLI session is not present, the MCP Server falls back to `RAILWAY_API_TOKEN`. Set it in the environment where Claude Code runs.

- [x] `claude mcp list` shows `railway-mcp-server`
- [x] Verify with a test tool call: `railway:list` or `railway:status` in an agent session

---

## Phase 1 — Production dependencies

**Files:** `pyproject.toml` (via `uv add`, not hand-edited)

Add via `uv add`:
- `gunicorn` — Railway's WSGI runner (replaces dev server)
- `whitenoise` — serves static files without a CDN or separate nginx
- `dj-database-url` — parses `DATABASE_URL` injected by Railway PostgreSQL
- `psycopg[binary]` — PostgreSQL adapter (binary wheel, no system libs needed)

- [ ] `uv add gunicorn whitenoise dj-database-url "psycopg[binary]"`

---

## Phase 2 — Settings hardening

**File:** `outfits_garderobe/settings.py`

Replace hardcoded values with env-var reads. Keep SQLite fallback for local dev (no `.env` required on a fresh clone).

```python
import os, dj_database_url

SECRET_KEY = os.environ['SECRET_KEY']          # no fallback — fail loudly if missing
DEBUG = os.getenv('DEBUG', 'False') == 'True'
ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# Static files
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Database — falls back to SQLite for local dev
DATABASES = {
    'default': dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
    )
}
```

Add WhiteNoise to MIDDLEWARE, immediately after `SecurityMiddleware`:
```python
'whitenoise.middleware.WhiteNoiseMiddleware',
```

- [ ] Replace SECRET_KEY
- [ ] Replace DEBUG
- [ ] Replace ALLOWED_HOSTS
- [ ] Add STATIC_ROOT + STATICFILES_STORAGE
- [ ] Add dj-database-url DATABASES block
- [ ] Insert WhiteNoise middleware

---

## Phase 3 — Railway config files

**New file:** `Procfile` (root)
```
web: gunicorn outfits_garderobe.wsgi:application
```
Railway's Nixpacks auto-detects this. No custom Dockerfile needed.

**New file:** `railway.toml` (root) — explicit build/deploy config beats implicit detection for reliability:
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "python manage.py migrate && gunicorn outfits_garderobe.wsgi:application"
healthcheckPath = "/"
healthcheckTimeout = 30
restartPolicyType = "on_failure"
```

> **Edge case — migration on deploy:** `migrate` runs before gunicorn starts. If migration fails, Railway aborts the deploy and keeps the previous release live. However, the DB schema may be partially applied. Use zero-downtime migration patterns for any future column drops or renames (add column → deploy → backfill → deploy → drop old column).

**New file:** `.env.example` (root) — documents required vars for any developer:
```
SECRET_KEY=change-me
DEBUG=False
ALLOWED_HOSTS=yourdomain.up.railway.app
DATABASE_URL=postgresql://...  # auto-injected by Railway PostgreSQL service
```

- [ ] Create `Procfile`
- [ ] Create `railway.toml`
- [ ] Create `.env.example`

---

## Phase 4 — Railway project setup (manual steps)

These steps require a human with Railway credentials:

1. **Create Railway account** at railway.app and start a new project.
2. **Add PostgreSQL service** — Railway injects `DATABASE_URL` automatically into the web service.
3. **Connect GitHub repo** — enable Railway's native auto-deploy on `main` branch. Railway polls GitHub directly; **no GitHub Actions workflow or external CI/CD system is used or needed.**
4. **Set environment variables** in Railway dashboard → Variables:
   - `SECRET_KEY` — generate with `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
   - `ALLOWED_HOSTS` — `<your-service>.up.railway.app`
   - `DEBUG` — `False`
   - `DATABASE_URL` — auto-set by Railway PostgreSQL; verify it's linked
5. **Disable auto-deploy on non-main branches** in Railway's GitHub integration settings to prevent accidental preview deploys. This is a Railway-side toggle — no branch protection rules or CI/CD config required.
6. **Set a monthly spend alert** in Railway billing settings at your budget threshold (Risk Register: pay-per-second opacity).

- [x] Railway account + project created
- [x] PostgreSQL service added and linked
- [x] GitHub repo connected
- [x] Env vars set
- [ ] Auto-deploy scoped to `main` only
- [ ] Spend alert configured

---

## Phase 5 — First deploy verification

- [ ] Push to `main` — watch Railway's build log for Nixpacks detection + gunicorn start
- [ ] Confirm `python manage.py migrate` ran cleanly in deploy logs
- [ ] `curl https://<service>.up.railway.app/` returns 200 (not 500)
- [ ] Check Railway Metrics tab — confirm CPU/memory within expectations

---

## Risk mitigations implemented

| Risk | Mitigation in this plan |
|---|---|
| Migration failure leaves broken state | `startCommand` chains migrate+gunicorn; deploy fails if migrate exits non-zero |
| Accidental branch deploy | Phase 4 step 5 — disable auto-deploy on non-main branches (Railway-side toggle) |
| Cost surprise | Phase 4 step 6 — spend alert on Railway billing |
| SECRET_KEY in version control | `os.environ['SECRET_KEY']` — hard fail if not set, no default |
| Static files 404 in production | WhiteNoise middleware + CompressedManifestStaticFilesStorage |

---

## Files touched

| File | Action |
|---|---|
| `pyproject.toml` / `uv.lock` | Modified (via `uv add`) |
| `outfits_garderobe/settings.py` | Modified |
| `Procfile` | Created |
| `railway.toml` | Created |
| `.env.example` | Created |

> **No `.github/workflows/` files are created.** Deploys are triggered entirely by Railway's native GitHub integration — a push to `main` triggers Railway's build pipeline directly, with no external CI runner involved.
