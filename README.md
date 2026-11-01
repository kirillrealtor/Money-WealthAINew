# MoneyWealth AI

An AI-native personal finance platform. Connect real bank accounts (read-only, via
Plaid) and get grounded guidance on budgets, goals, debt payoff, and portfolio
health — plus an AI advisor that cites the data it used and never invents numbers.

**Live:** https://moneywealth-ai.vercel.app

Monorepo: a Python/FastAPI backend and a Next.js/TypeScript frontend, coordinated
through the backend's auto-generated OpenAPI contract.

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

Three decisions shape the system:

<<<<<<< Updated upstream
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
├── backend/AURORA_MIGRATION_PROGRESS.txt  Aurora cutover log (complete)
└── docker-compose.yml    local Postgres + Redis
```
=======
- **BFF security model.** The browser only talks to Next.js; route handlers proxy to
  the backend server-side. Access token in memory, refresh token in a first-party
  httpOnly cookie, strict nonce-based CSP. `API_BASE_URL` is server-only.
- **Tenant + per-user isolation.** Postgres FORCE Row-Level Security; the app connects
  as a non-owner `app_user` (`NOBYPASSRLS`). Admin cross-tenant reads go through narrow
  audited `SECURITY DEFINER` functions only.
- **Grounded AI.** Every quantitative answer must call a tenant-scoped tool for live
  data. An output validator rejects ungrounded numbers, missing compliance framing, and
  secret/SQL leaks; an input layer blocks prompt-injection, jailbreaks, and crisis
  signals.
>>>>>>> Stashed changes

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router, RSC, BFF), React 19, TypeScript 5, Tailwind 4, TanStack Query, Radix, zod, motion, posthog-js |
| Backend | Python 3.12, FastAPI, asyncpg (raw parameterized SQL — no ORM), Pydantic v2, JWT |
| Data | Aurora PostgreSQL 16 (Serverless v2, FORCE RLS), Redis, durable `sync_jobs` queue |
| AI | Groq (Llama 3.3 70B) / Anthropic Claude — grounded agentic tool-calling + safety evals |
| Integrations | Plaid (transactions, liabilities, investments), Stripe (billing) |
| Infra | ECS Fargate · Aurora · RDS Proxy · ECR · SSM · CloudWatch · Upstash Redis · Vercel · Terraform |
| Quality | ruff, mypy, pytest · ESLint, Vitest + Testing Library, Playwright + axe |

## Repository layout

```
backend/            Python · FastAPI · asyncpg · Redis (API + AI orchestration)
  app/                auth, plaid, ai, budgets, goals, debt, portfolio, admin, …
  db/migrations/      SQL schema — source of truth (FORCE RLS, SECURITY DEFINER fns)
  tests/              unit + integration + AI safety eval harness
  docs/               architecture, security, DR, production deployment
frontend/           TypeScript · Next.js 16 · React 19 · Tailwind 4
  src/                app (BFF), components, design tokens, Vitest/Playwright
infra/terraform/    Infrastructure as Code — the scalable AWS target stack
.github/workflows/  CI (lint, type, test, AI-eval) + auto-deploy
docker-compose.yml  local Postgres + Redis
```

## Quick start

**1. Datastores** (from repo root):

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

## Testing & CI

```bash
# backend
cd backend && ruff check . && mypy app && pytest     # + python -m scripts.run_evals
# frontend
cd frontend && npm run lint && npm test && npm run build
```

CI (`.github/workflows/ci.yml`) runs lint, type-check, tests, an AI-safety eval gate,
and a dependency scan on every push/PR. Merges to `main` auto-deploy the frontend to
Vercel (and the backend to ECS once AWS secrets are set).

## Deployment

<<<<<<< Updated upstream
Live today on **AWS (ECS Fargate + Aurora PostgreSQL + RDS Proxy + SSM) + Upstash Redis + Vercel**.
Infrastructure is **Terraform** in [infra/terraform/](infra/terraform/).
Deploy runbook: [DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md). Aurora cutover log:
[backend/AURORA_MIGRATION_PROGRESS.txt](backend/AURORA_MIGRATION_PROGRESS.txt).
=======
Live on AWS (ECS Fargate + Aurora + RDS Proxy + SSM) + Upstash Redis + Vercel.
Infrastructure is Terraform in [infra/terraform/](infra/terraform/); the runbook is
[DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md).
>>>>>>> Stashed changes

## Status

- Backend Phases 0–6 complete: auth, Plaid, grounded AI advisor + safety,
  budgets/goals/debt/portfolio, proactive alerts, reliability and observability.
- Frontend complete: marketing site, authenticated app (10 surfaces), admin console,
  light/dark themes, unit + e2e tests.
- Deployed to AWS + Vercel with CI/CD and IaC.
- Remaining for launch: production Plaid and Stripe keys, counsel-reviewed legal
  pages, stable HTTPS via load balancer.

## Documentation

| Doc | Purpose |
|---|---|
| [DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md) | Authoritative deploy guide (ECS, Aurora, SSM, Vercel) |
| [backend/docs/](backend/docs/) | Architecture, security, DR, production deployment |
| [infra/terraform/README.md](infra/terraform/README.md) | Terraform apply + out-of-band DB setup |
| [EMAIL_SETUP.md](EMAIL_SETUP.md) | Email delivery (Resend/SMTP/SendGrid) |
| [DEPLOY.md](DEPLOY.md) | Legacy runbook (superseded) |

---

Educational information, not financial advice.
