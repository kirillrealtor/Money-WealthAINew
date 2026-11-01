# MoneyWealth AI — Backend

Python / FastAPI backend (async). PostgreSQL (asyncpg, FORCE RLS) + Redis.
Design notes in [docs/BACKEND_ARCHITECTURE.md](docs/BACKEND_ARCHITECTURE.md).

> **Stack note:** Backend is Python (FastAPI). Frontend is TypeScript (Next.js).
> Python is the primary application language; if/when heavy quant or ML work
> appears (evals, Monte Carlo modeling, embeddings), it stays in Python too.

**Deployed:** runs on **AWS ECS Fargate** with **Aurora PostgreSQL 16** (Serverless v2),
**RDS Proxy**, **Upstash Redis**, and secrets in **AWS SSM Parameter Store**. Image lives
in ECR; the task-definition template is in [`deploy/task-definition.json`](deploy/task-definition.json)
and the push→ECR→ECS pipeline in [`../.github/workflows/deploy-backend.yml`](../.github/workflows/deploy-backend.yml).
Infrastructure (VPC, ALB, Aurora, RDS Proxy, autoscaling) is **Terraform** in
[`../infra/terraform/`](../infra/terraform/). Runbook: [`../DEVOPS_HANDOFF.md`](../DEVOPS_HANDOFF.md).

## Status
- ✅ **Phase 0** — scaffold, config, asyncpg pool (RDS-Proxy-ready), SQL migrations, structlog, tracing, health
- ✅ **Phase 1** — auth (signup, email verify, login, JWT + rotating refresh, sessions), tenancy, rate limiting, audit log
- ✅ **Phase 1 hardening** — enforced RLS (non-owner role + FORCE RLS), brute-force throttle, anti-enumeration, bcrypt pre-hash, security headers, trusted-host, body limits, captcha, integration + RLS tests. See [docs/SECURITY.md](docs/SECURITY.md).
- ✅ **Phase 2** — Plaid data layer: link/exchange/disconnect, **encrypted access tokens (AES-256-GCM)**, idempotent transaction sync, **verified webhooks**, tenant RLS on all Plaid tables. Live calls need Plaid keys — see [docs/PHASE2_PENDING.md](docs/PHASE2_PENDING.md).
- ✅ **Phase 3** — AI advisor core: grounded **agentic loop** (Claude **or** Groq) + MCP tools (tenant-scoped, **FORCE RLS**), input safety (injection/crisis/jailbreak), output validation, **atomic** per-tier token budgets, **evals harness** (`python -m scripts.run_evals`). Live calls need `ANTHROPIC_API_KEY` or `GROQ_API_KEY` — see [docs/PHASE3_PENDING.md](docs/PHASE3_PENDING.md).
- ✅ **Phase 4** — planning: **Decimal-exact calculation engine** (debt snowball/avalanche, goal reverse-engineering, affordability) + **Budgets** and **Goals** modules (CRUD, tenant RLS) + 6 new MCP tools (budget/goals/debt/portfolio/affordability/debt-payoff) wired into the advisor.
- ✅ **Phase 4B** — Debt dashboard (summary, DTI, payoff-at-minimum, refinance flags, snowball/avalanche what-if) + Portfolio dashboard (allocation, sector exposure, concentration flags, unrealized P/L, rebalance gaps) — tenant RLS, data-only (no buy/sell directives). Open items: [docs/PHASE4_PENDING.md](docs/PHASE4_PENDING.md).
- ✅ **Phase 5** — proactive layer: alert engine (budget/goal/milestone/unusual-tx + bank-error webhook alerts), idempotent dispatcher (Redis dedup + outbox), in-app notifications + preference center (quiet hours, TCPA), batched SQS-ready runner. Channels (email/push/SMS) + SQS + digest: [docs/PHASE5_PENDING.md](docs/PHASE5_PENDING.md).
- ✅ **Phase 6 (app layer)** — reliability + observability: AI **provider auto-fallback** (Claude→Groq), **degradation tier** (`/health/ai`), **`/metrics`** (Prometheus), partition cron, k6 load test, [deployment](docs/PRODUCTION_DEPLOYMENT.md) + [DR runbook](docs/DR_RUNBOOK.md). Remaining = AWS IaC: [docs/PHASE6_PENDING.md](docs/PHASE6_PENDING.md).
- ✅ **Scale/crash audit hardening** — **bounded connection acquisition** (pool-exhaustion → fast `503 SERVICE_BUSY` instead of an indefinite hang/OOM under load), **Plaid `list_items` N+1 → single JOIN**, and **JWT verified once per request** (memoized on `request.state`, not decoded by both the rate limiter and the auth guard). Remaining 1M-scale item = SQS fan-out for the alert runner ([docs/PHASE6_PENDING.md](docs/PHASE6_PENDING.md)).
- ✅ **Dependency security pass** — `pip-audit` clean (0 known CVEs; was 18 across fastapi/starlette/pyjwt/cryptography stack), `bandit` clean (no high severity; remaining flags are audited false positives).
- ✅ **Magic-link email (Resend)** — `MAIL_TRANSPORT=resend` + `RESEND_API_KEY`. Test sender: `onboarding@resend.dev` (see [`EMAIL_SETUP.md`](../EMAIL_SETUP.md)). SMTP/SendGrid still supported as alternates.

## Quick start (local)

This package lives at `backend/` in the monorepo. `docker-compose.yml` is at the
**repo root** (one level up); run app commands from this `backend/` directory.

```bash
# from the repo root: start datastores (Postgres :5433, Redis :6380)
docker compose up -d postgres redis

# from backend/
cp .env.example .env
python -m venv .venv && source .venv/bin/activate   # (Windows: .venv\Scripts\activate)
pip install -r requirements-dev.txt
python -m scripts.migrate                      # apply db/migrations/*.sql
uvicorn app.main:app --reload --port 3000      # http://localhost:3000
```

Or run everything in containers from the repo root: `docker compose up --build`.

## Verify it's up
```bash
curl localhost:3000/health
curl localhost:3000/health/ready

# Auth flow
curl -X POST localhost:3000/api/v1/auth/signup \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"SecurePass123!"}'
# -> check server logs for the dev verification link (MAIL_TRANSPORT=console)

curl -X POST localhost:3000/api/v1/auth/login \
  -H 'content-type: application/json' \
  -d '{"email":"me@example.com","password":"SecurePass123!"}' -c cookies.txt
# -> { access_token, user_id }; refresh token set as httpOnly cookie

curl localhost:3000/api/v1/auth/me -H "authorization: Bearer <access_token>"
```

Interactive API docs: http://localhost:3000/docs (FastAPI auto-generated).

## Commands
| Command | Purpose |
|---|---|
| `uvicorn app.main:app --reload` | Hot-reload dev server |
| `python -m scripts.migrate` | Apply pending SQL migrations |
| `python -m scripts.create_admin` | Bootstrap admin user (see script docstring) |
| `python -m scripts.bootstrap_aurora_roles` | Post-migrate: sync app_user password + BYPASSRLS |
| `ruff check .` | Lint |
| `mypy app scripts` | Type-check |
| `pytest` | Unit tests |

## Layout
```
app/
  config.py            env validation (pydantic-settings)
  main.py              FastAPI factory + lifespan
  middleware.py        ASGI tracing + access log
  context.py           contextvars trace_id
  db.py                asyncpg pool, query helpers, with_tenant (RLS)
  redis_client.py  logging_conf.py  crypto.py  errors.py  audit.py
  deps.py              require_auth, resolve_tenant, rate_limit
  ai/                  advisor loop, tools (MCP), prompts, safety, validator, budget
  modules/
    auth/              tokens, mailer, schemas, service, router
    plaid/             link/exchange/sync, encrypted tokens, webhooks
    budgets/  goals/  planning/   debt, portfolio, affordability engines (Decimal-exact)
    advisor/  transactions/  notifications/  billing/  admin/
    health/
db/
  migrations/          executable schema (source of truth)
  schema.sql           annotated reference
scripts/migrate.py     migration runner
```

## Security notes (Phase 1)
- Passwords: bcrypt (rounds configurable, default 12).
- Refresh tokens: opaque, only SHA-256 hash stored; rotated on every refresh; reuse rejected.
- Access tokens: short-lived JWT (HS256), held in memory by clients.
- Tenant isolation: `X-Tenant-ID` resolution + Postgres RLS via `with_tenant()`.
- PII never logged; structured logs redact sensitive keys.
