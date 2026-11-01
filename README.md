[![CI](https://github.com/kirillrealtor/Money-WealthAINew/actions/workflows/ci.yml/badge.svg)](https://github.com/kirillrealtor/Money-WealthAINew/actions/workflows/ci.yml)

# MoneyWealth AI

An AI-native personal finance platform. Users connect real bank accounts — read-only,
via Plaid — and receive grounded guidance on budgets, goals, debt payoff, and
portfolio health, alongside an AI advisor that cites the data behind every figure.

**Live:** https://moneywealth-ai.vercel.app

A monorepo holding a Python/FastAPI backend and a Next.js/TypeScript frontend,
coordinated through the backend's generated OpenAPI contract.

## Architecture

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
backend/            Python · FastAPI · asyncpg · Redis (API and AI orchestration)
  app/                auth, plaid, ai, budgets, goals, debt, portfolio, admin, …
  db/migrations/      SQL schema — source of truth (FORCE RLS, SECURITY DEFINER fns)
  tests/              unit, integration, and AI safety eval harness
  docs/               architecture, security, DR, production deployment
frontend/           TypeScript · Next.js 16 · React 19 · Tailwind 4
  src/                app (BFF), components, design tokens, Vitest and Playwright
infra/terraform/    infrastructure as code for the AWS target stack
.github/workflows/  CI (lint, type, test, AI eval) and auto-deploy
docker-compose.yml  local Postgres and Redis
```

## Quick start

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

Production runs on AWS (ECS Fargate, Aurora, RDS Proxy, SSM) with Upstash Redis and
Vercel. Infrastructure is provisioned by Terraform in
[infra/terraform/](infra/terraform/); the runbook is
[DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md).

## Status

- Backend phases 0–6 complete: authentication, Plaid, grounded AI advisor with its
  safety stack, budgets, goals, debt and portfolio, proactive alerts, and
  reliability and observability.
- Frontend complete: marketing site, authenticated application (10 surfaces), admin
  console, light and dark themes, unit and end-to-end tests.
- Deployed to AWS and Vercel with CI/CD and infrastructure as code.
- Outstanding for launch: production Plaid and Stripe keys, counsel-reviewed legal
  pages, and stable HTTPS via the load balancer.

## Documentation

| Document | Purpose |
|---|---|
| [DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md) | Deploy guide — ECS, Aurora, SSM, Vercel |
| [backend/docs/](backend/docs/) | Architecture, security, disaster recovery, production deployment |
| [infra/terraform/README.md](infra/terraform/README.md) | Terraform apply and out-of-band database setup |
| [EMAIL_SETUP.md](EMAIL_SETUP.md) | Email delivery — Resend, SMTP, SendGrid |
| [DEPLOY.md](DEPLOY.md) | Legacy runbook, superseded by DEVOPS_HANDOFF.md |

---

Educational information; not financial advice.
