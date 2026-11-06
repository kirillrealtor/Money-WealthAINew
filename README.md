[![CI](https://github.com/kirillrealtor/Money-WealthAINew/actions/workflows/ci.yml/badge.svg)](https://github.com/kirillrealtor/Money-WealthAINew/actions/workflows/ci.yml)

# MoneyWealth AI

An AI-native personal finance platform. Users connect real bank accounts — read-only,
via Plaid — and receive grounded guidance on budgets, goals, debt payoff, and
portfolio health, alongside an AI advisor that cites the data behind every figure.

**Previous deployment (not verified for this branch):** https://moneywealth-ai.vercel.app

A monorepo holding a Python/FastAPI backend and a Next.js/TypeScript frontend,
coordinated through the backend's generated OpenAPI contract.

## Architecture

Current workflow: local Next.js frontend -> local Docker/FastAPI backend ->
PostgreSQL + Redis, with private stdio MCP financial tools. The former AWS
deployment has been retired. Railway is the next hosting target, after local
verification and recovery of the team's integration credentials.

The diagram below describes the historical AWS deployment, not an active service.

```
Browser ──► Vercel (Next.js 16 + BFF) ──► AWS ECS Fargate (FastAPI)
              │                              │            │
              │                    Aurora PostgreSQL   Upstash Redis
              │                    (RDS Proxy, FORCE   (rate limits,
              │                     RLS)                AI token budgets)
              │                              + Plaid · Groq/Claude (egress)
              └─ same-origin only; nonce CSP, httpOnly refresh cookie
```

Three properties define the design:

- **BFF security model.** The browser talks only to Next.js; route handlers proxy to
  the backend server-side. The access token stays in memory, the refresh token in a
  first-party httpOnly cookie, and CSP is nonce-based. `API_BASE_URL` is server-only.
- **Tenant and per-user isolation.** Postgres FORCE Row-Level Security, with the
  application connecting as a non-owner `app_user` (`NOBYPASSRLS`). Admin cross-tenant
  reads go through narrow, audited `SECURITY DEFINER` functions only.
- **Grounded AI.** Every quantitative answer must call a tenant-scoped tool for live
  data. An output validator rejects ungrounded numbers, missing compliance framing,
  and secret or SQL leakage; an input layer blocks prompt injection, jailbreaks, and
  crisis signals.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router, RSC, BFF), React 19, TypeScript 5, Tailwind 4, TanStack Query, Radix, zod, motion, posthog-js |
| Backend | Python 3.11, FastAPI, asyncpg (raw parameterized SQL — no ORM), Pydantic v2, JWT |
| Data | Aurora PostgreSQL 16 (Serverless v2, FORCE RLS), Redis, durable `sync_jobs` queue |
| AI | Groq (Llama 3.3 70B) / Anthropic Claude — grounded agentic tool-calling with a safety eval harness |
| Integrations | Plaid (transactions, liabilities, investments), Stripe (billing) |
| Infrastructure | ECS Fargate, Aurora, RDS Proxy, ECR, SSM, CloudWatch, Upstash Redis, Vercel, Terraform |
| Quality | ruff, mypy, pytest · ESLint, Vitest with Testing Library, Playwright with axe |

## Repository layout

```
.
├── backend/              Python · FastAPI · asyncpg · Redis   (API + AI orchestration)
│   ├── app/                application code (auth, plaid, ai, budgets, goals, admin, …)
│   ├── db/migrations/      SQL schema — source of truth (FORCE RLS, SECURITY DEFINER fns)
│   ├── tests/ + tests/evals/  unit + integration + AI safety eval harness
│   ├── deploy/             ECS task-definition template
│   └── docs/               architecture, security, DR, production deployment
├── frontend/             TypeScript · Next.js 16 · React 19 · Tailwind 4
│   └── src/                app (BFF) · components · design tokens · Vitest/Playwright
├── infra/terraform/      Infrastructure as Code — the scalable AWS target stack
├── .github/workflows/    CI (lint/type/test/AI-eval) + auto-deploy (backend ECS, frontend Vercel)
├── DEPLOY.md             legacy runbook (superseded — see DEVOPS_HANDOFF.md)
├── DEVOPS_HANDOFF.md     authoritative deploy guide (ECS + Aurora)
└── docker-compose.yml    local Postgres + Redis
```

## Quick start

### Run the backend in Docker

Install and start Docker Desktop with Linux containers, then from the repository root:

```powershell
# Create local configuration and install development dependencies; preserve existing .env values.
powershell -ExecutionPolicy Bypass -File setup.ps1 -SkipServices
docker compose up -d --build --wait
# After all services are healthy, populate the dedicated synthetic demo profile.
docker compose exec app python -m scripts.seed_demo
powershell -ExecutionPolicy Bypass -File start-dev.ps1 frontend
```

Open http://localhost:3100. Sign in as `demo@fathom.app` using `DEMO_PASSWORD`
from `backend/.env`. The backend is at http://localhost:3000 and readiness is
http://localhost:3000/health/ready. New local configuration uses simulated AI;
real AI, Plaid and PayPal sandbox operations require the team's credentials.
Stop a separately running native backend before starting Docker so port 3000 is free.
Use `docker compose logs app` to inspect startup and `docker compose down` to stop
containers while preserving the database volume. Docker startup, readiness, seeding,
and the local browser demo were verified on November 5, 2026 with actual PostgreSQL
and Redis containers. The full backend suite passed all 140 tests against those services.

### Run the backend natively with Docker datastores

For the current hackathon branch on Windows, run
`powershell -ExecutionPolicy Bypass -File setup.ps1`, then start the two services with
`start-dev.ps1 backend` and `start-dev.ps1 frontend` in separate terminals.
See [SUBMISSION.md](SUBMISSION.md) for judge instructions, external credentials,
synthetic-data disclosure, and the remaining live verification gates.
The advisor now uses [actual private stdio MCP](backend/docs/MCP.md).

**1. Datastores** (from the repository root):

```bash
docker compose up -d postgres redis    # Postgres :5433, Redis :6380
```

**2. Backend** (`backend/`):

```bash
cp .env.example .env
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python -m scripts.migrate                            # apply db/migrations/*.sql
uvicorn app.main:app --reload --port 3000            # http://localhost:3000/docs
```

**3. Frontend** (`frontend/`):

```bash
npm install
echo "API_BASE_URL=http://localhost:3000" > .env.local
npm run dev                                          # http://localhost:3100
```

See [backend/README.md](backend/README.md) and [frontend/README.md](frontend/README.md)
for detail.

## Testing and CI

On Windows, use `powershell -ExecutionPolicy Bypass -File test-backend.ps1`
for backend integration tests. It creates/reuses `financial_advisor_test` and Redis
database 1 without modifying `.env` or stopping the running app. This isolation is
required when the demo's Plaid sync worker is enabled; otherwise it can consume test jobs.

```bash
# backend
cd backend && ruff check . && mypy app && pytest     # + python -m scripts.run_evals
# frontend
cd frontend && npm run lint && npm test && npm run build
```

CI (`.github/workflows/ci.yml`) runs lint, type-check, tests, an AI-safety eval gate,
and a dependency scan on every push and pull request. Merges to `main` deploy the
frontend to Vercel, and the backend to ECS once AWS secrets are configured.

## Deployment

The former AWS backend is no longer hosted there. See [RAILWAY_HANDOFF.md](RAILWAY_HANDOFF.md)
for the prepared, undeployed Railway configuration and migration checklist. First verify the local Docker
stack; deployment to Railway is the next phase. Existing AWS Terraform and
[DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md) are historical references. Do not provision
that stack as part of local setup. The team is recovering the existing API keys
and environment configuration; avoid replacing their integration credentials.

## Status

Hackathon branch additions: actual MCP server/client, synthetic development seed,
Windows setup scripts, and PayPal sandbox purchase planning/checkout. Live provider
and PayPal sandbox verification are still required before claiming submission readiness.
The historical deployment notes below are not proof that the current hosted backend is reachable.

- Backend phases 0–6 complete: authentication, Plaid, grounded AI advisor with its
  safety stack, budgets, goals, debt and portfolio, proactive alerts, and
  reliability and observability.
- Frontend complete: marketing site, authenticated application (10 surfaces), admin
  console, light and dark themes, unit and end-to-end tests.
- AWS/Vercel deployment configuration exists; the hosted backend and this branch's
  deployment still need verification.
- Submission gates: live AI through MCP, actual PayPal sandbox approval/capture,
  working judge access. Production launch additionally
  requires its own keys, infrastructure and legal review.

## Documentation

PayPal hackathon checkout setup and demo: [PAYPAL_SETUP.md](PAYPAL_SETUP.md).
For recovered credentials and the exact Docker reload/live-check sequence, see
[KEYS_HANDOFF.md](KEYS_HANDOFF.md).

| Document | Purpose |
|---|---|
| [DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md) | Deploy guide — ECS, Aurora, SSM, Vercel |
| [backend/docs/](backend/docs/) | Architecture, security, disaster recovery, production deployment |
| [infra/terraform/README.md](infra/terraform/README.md) | Terraform apply and out-of-band database setup |
| [EMAIL_SETUP.md](EMAIL_SETUP.md) | Email delivery — Resend, SMTP, SendGrid |
| [DEPLOY.md](DEPLOY.md) | Legacy runbook, superseded by DEVOPS_HANDOFF.md |

---

Educational information; not financial advice.
