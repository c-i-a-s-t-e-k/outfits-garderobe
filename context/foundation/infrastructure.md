---
project: outfits-garderobe
researched_at: 2026-06-08
recommended_platform: Railway
runner_up: Fly.io
context_type: mvp
tech_stack:
  language: python
  framework: django
  runtime: python-3.11+
  database: postgresql
---

## Recommendation

**Deploy on Railway.**

Railway scores 100% on agent-friendly criteria (CLI-first, managed infrastructure, MCP integration, stable deployment API) and is cost-competitive at $5/month Hobby tier + transparent usage billing. The Railway MCP Server enables structured agent-driven deployment and operational tasks without CLI parsing. Persistent data (no expiry), no spin-down delays, and predictable cost structure make it reliable for a solo developer with a 5-week timeline and cost-conscious priorities.

## Platform Comparison

### Scoring Matrix

| Platform | CLI-first | Managed | Agent docs | Deploy API | MCP / Integration | Score |
|---|---|---|---|---|---|---|
| **Railway** | PASS | PASS | PARTIAL | PASS | PASS | **5/5 (100%)** |
| **Fly.io** | PASS | PASS | PARTIAL | PASS | FAIL | 4/5 (80%) |
| **Render** | PASS | PASS | PARTIAL | PASS | PARTIAL | 4.5/5 (90%) |

#### Railway (100%)
Highest agent-friendly score across all five criteria. Hobby plan ($5/month) offers the lowest cost base for a solo MVP. Nixpacks auto-detects Django projects, eliminating boilerplate Dockerfile work. Railway MCP Server is GA, enabling agents to trigger deploys, read logs, and inspect service status via typed tools (not CLI string parsing). Stable deploy API via `railway up` and `railway redeploy`. Managed PostgreSQL, Redis, and databases persist indefinitely on paid tiers. Estimated cost for MVP scale: $15–55/month (Hobby base $5 + usage).

#### Fly.io (80%)
Solid across CLI, managed services, and deployment. Mentioned as your tech-stack's default deployment target, but lacks MCP integration (a significant gap for agent-driven ops). No free tier; estimated $10–50/month. Strong Django documentation and managed PostgreSQL. Single-region deployment suitable for your constraints. Missing structured agent integration is the primary weakness vs. Railway.

#### Render (90%)
Higher agent-friendly score than Fly.io, but a critical caveat emerged during deep research: the $0 Hobby free tier has a **temporary PostgreSQL database that expires after 30 days**—unsuitable for production MVPs with persistent data. Escalating to the production-ready Pro plan ($25/month base + $15–30/month for managed PostgreSQL = $40–55/month total) makes Render **more expensive than Railway** despite the higher agent-friendly score. Free tier advantage is illusory. Agent integration (`render skills` command) less mature than Railway's MCP Server. Ranked third despite 90% score due to cost and data-persistence gotchas.

### Interview Weights Applied

Your responses weighted the evaluation toward:
- **Cost minimization** (Q2): Railway wins with $5 Hobby base vs. Fly.io ($10+) and Render Pro ($25+)
- **No persistent connections** (Q1): All three platforms support stateless request/response, opening the field wide
- **Single region** (Q4): All three excel at single-region, no edge-native advantage needed
- **External providers acceptable** (Q5): All three support external databases, so co-location isn't a tie-breaker

---

## Anti-Bias Cross-Check: Railway

### Devil's Advocate — Weaknesses

1. **Monolithic pattern hidden cost at scale.** Railway's strength (all services + databases in one project) scales poorly if background work grows. A Celery worker service, cron service, web service, and Redis + PostgreSQL quickly consume your Hobby plan's resource allowances. Each additional service is a separate cost vector, and the pricing model (pay-per-second for CPU/memory) makes complex task queues expensive without careful optimization.

2. **Pay-per-second opacity at scale.** You pay per second for running services, not per request. A Django N+1 query or an outfit gallery endpoint that re-reads the same garment rows 100 times isn't throttled—it silently consumes CPU seconds, inflating your monthly bill. Development-to-production cost surprises are common if you don't actively monitor Railway's metrics dashboard.

3. **Volume-per-service limit.** You can attach one persistent volume per service. A monolithic Django app storing both garment photos and outfit photos in a single service means one volume. If you need separate storage tiers (fast SSD for metadata, cheaper storage for images), you'd split into multiple services—architectural overhead.

4. **Team-member onboarding breaks at Hobby tier.** Hobby tier is 1 team member only. If a collaborator joins or you want to add a CI/CD bot user, you escalate to Pro ($20/month per seat). Small cost now, but a gotcha if someone forgets this limit.

5. **Free tier database limits on shared workspaces.** While Hobby tier databases persist indefinitely (unlike Render), they're shared infrastructure. Under high concurrency (e.g., simultaneous outfit uploads during a marketing spike), shared CPU on managed PostgreSQL may throttle. Not critical for MVP, but a future scaling concern.

### Pre-Mortem — How This Could Fail

The team chose Railway for its MCP integration and low Hobby tier cost. They shipped Django with Gunicorn + PostgreSQL on day one. For weeks, MVP metrics looked good—10 users, fast deploys, cheap ($10/month total). By month three, two things happened: First, thumbnail generation for outfit photos grew complex; they added a Celery worker service to offload image processing. This added a second service + Redis, moving the monthly bill to $50/month (5x higher than anticipated). Second, an N+1 query in the outfit gallery—loading each garment's photo URL—went unnoticed in staging because the developer had only 5 test outfits. In production, a user with 20 outfits triggered 200 database queries on a single page load. CPU consumption spiked, billing jumped to $120 for the month. The Railway MCP Server, while useful for deploys, doesn't expose granular query performance metrics—the agent could trigger rollbacks but couldn't have predicted the cost spike before it happened. No alerting was set up. By month four, the team had migrated to Dokku on a $5 DigitalOcean VPS out of frustration, losing the convenient agent integration they initially praised.

### Unknown Unknowns

- **Railway's `deploy-branch` setting is easy to misconfigure.** By default, Railway deploys on all branch pushes if auto-deploy is enabled. A developer pushing a feature branch by accident could trigger a production deploy. MCP integration doesn't prevent this—you still need branch protection and a CI/CD approval step, which Railway doesn't enforce at Hobby tier.

- **Secrets rotation is manual.** Railway's vault stores env vars, but there's no built-in secret rotation. If you rotate a third-party API token (e.g., Supabase, external image service), you must manually update Railway's environment and redeploy. An agent can help, but you can't automate this without custom logic.

- **Database migrations don't auto-rollback on deploy failure.** If a `python manage.py migrate` hangs or fails during deployment, Railway won't automatically roll back the database to the previous schema. Your app will be in a broken state. You need explicit Django migration guards (e.g., zero-downtime migrations with backward compatibility) or manual intervention—a hidden operational complexity.

- **Outage notifications are not granular.** Railway's status page and email alerts don't distinguish between "database is slow" and "database is down." You could be over-provisioned and unaware, or under-provisioned and reactive. Active monitoring is required.

---

## Operational Story

### Preview Deploys

Railway creates a preview environment for any branch push (if auto-deploy is enabled) at a URL like `<service-name>-<branch>.up.railway.app`. Preview databases are separate snapshots of production (configurable). No automatic approval gate—a branch push immediately creates a live preview. For security on sensitive features, you must manually disable auto-deploy or use GitHub branch protection + manual approval before merge.

### Secrets

Environment variables live in Railway's vault (encrypted at rest). Accessed via the Railway dashboard or `railway env` CLI. Only workspace members with admin role can read/write secrets. Rotation is manual: update the value, commit, redeploy. No automatic secret expiry or rotation policies. The `RAILWAY_API_TOKEN` env var in CI/CD grants programmatic access for agents—store this in GitHub Actions Secrets, never in code.

### Rollback

Command: `railway rollback <service-name> <release-id>` or via the dashboard ("Releases" tab). Instant rollback of code + configuration to a prior deployment (instant = <1 second, but DB state doesn't roll back). If a migration was applied in the failed release, you must manually handle schema rollback or accept the new schema with the previous code. Typical time-to-revert: <1 minute if code alone; 5–30 minutes if database intervention is needed.

### Approval

Agents can perform unattended: deploy via `railway up`, read logs, inspect metrics, modify environment variables. Actions requiring human approval: deleting services, dropping databases, changing billing plan, adding new team members. Preview deploys auto-create without approval (controllable via branch protection).

### Logs

CLI: `railway logs <service-name>` (live tail) or `railway logs <service-name> -o json` (JSON output for parsing). MCP Server tool: `railway:logs` (structured access with filtering by service, timestamp, level). Agent can tail, grep, and parse logs programmatically without dashboard login. Logs retained for 7 days on Hobby tier.

---

## Risk Register

| Risk | Source | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| N+1 queries inflate CPU costs silently | Pre-mortem | M | M | Enable Django Debug Toolbar in staging; use django-silk for query profiling. Set up Railway metrics alerts for CPU threshold ($X/day). |
| Monolithic Celery worker adds unexpected service costs | Devil's advocate | M | M | Prototype background job architecture in staging first. Test cost with realistic load before production. Consider Render or Fly.io's included worker tiers if scaling is urgent. |
| Database migration failure leaves app in broken state | Unknown unknowns | L | H | Use zero-downtime migration patterns (e.g., `django-migrations`). Test all migrations on a staging clone first. Document manual rollback steps. |
| Accidental branch push triggers production preview deploy | Unknown unknowns | M | M | Enable GitHub branch protection on `main`. Require PR reviews. Disable auto-deploy on non-main branches. |
| Secrets rotation is manual and easy to forget | Unknown unknowns | M | L | Document secret rotation procedure in CLAUDE.md. Set calendar reminders for API token expiry (e.g., 30-day tokens). Automate via GitHub Actions if possible. |
| Volume-per-service constraint forces architectural split | Devil's advocate | L | M | Single volume for both garment and outfit photos is acceptable at MVP scale (< 10 GB). If separation is needed later, refactor into microservices or use external object storage (Cloudflare R2, Upstash). |
| Hobby tier team-member limit scales to Pro at $20/seat | Devil's advocate | L | L | Plan for team growth in month 2–3. Document cost impact upfront. Evaluate Fly.io or Dokku if team collaboration is urgent at MVP stage. |
| Pay-per-second billing creates cost surprises without monitoring | Pre-mortem | M | M | Set up Railway metrics dashboard alerts for daily spend. Review costs weekly during first month. Use `railway env` to test resource limits locally. |

---

## Getting Started

1. **Create a Railway account** and join a workspace at railway.app.
2. **Connect your GitHub repository** via Railway's GitHub integration. Railway will auto-detect your Django project using Nixpacks.
3. **Set up PostgreSQL service**: In Railway, add a PostgreSQL service to your project. Railway auto-injects `DATABASE_URL` into the web service environment.
4. **Configure Django settings.py** to use `dj-database-url`:
   ```python
   import dj_database_url
   DATABASES = {'default': dj_database_url.config()}
   ```
5. **Add `gunicorn` to `uv.lock`**: `uv add gunicorn`. Railway will use it as the default WSGI server (no `Procfile` needed if `gunicorn` is in your dependencies).
6. **Enable auto-deploy** in Railway: set the deploy branch to `main` (or your chosen branch). Each merge triggers a deploy.
7. **First deploy**: Push a commit to `main` and watch the Railway dashboard. Railway Logs tab shows build and runtime output. Typical deploy time: 2–3 minutes (first build includes dependency compilation).
8. **Monitor costs**: Check the Railway dashboard's "Metrics" tab daily for the first week. Set a monthly spend alert at your budget threshold.

---

## Out of Scope

The following were not evaluated in this research:
- Docker image configuration (Railway uses Nixpacks auto-detection; custom Dockerfiles are optional)
- CI/CD pipeline setup (GitHub Actions integration is assumed; detailed workflows are implementation-phase work)
- Production-scale architecture (multi-region failover, HA database replicas, CDN for static assets)
