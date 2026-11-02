# Backend Architecture — AI Financial Advisor

**Target:** 100K active users (WAA), production AWS, live Plaid.
**Stack decision:** **Python (FastAPI)** for the backend application + AI orchestration; **TypeScript (Next.js)** for the frontend. Aurora PostgreSQL (asyncpg). Containerized service for the AI/agentic loop, with thin serverless/edge in front. Redis for state/rate-limits. SQS for async work. Python also remains the home for any heavy quant/ML work (evals, Monte Carlo modeling, embeddings).

> Note: sections below that reference Vercel serverless functions describe the original blueprint; our implementation runs the service plane as Python containers (ECS Fargate) with FastAPI. The two-plane reasoning still applies.

This document is the backend design notes. Schema lives in `db/schema.sql`; the executable source of truth is `db/migrations/*.sql` (run via `python -m scripts.migrate`).

---

## 1. Why not pure Vercel serverless

The blueprint says "Vercel serverless functions." At 100K active users with an **agentic LLM loop** (multiple Claude round-trips per turn, each holding context for 10–30s), pure serverless hurts in two specific ways:

1. **DB connection exhaustion.** Every warm function instance opens a Postgres connection and holds it across the whole agentic turn. Aurora caps connections; you hit the wall well before 100K users.
2. **Long-held compute.** Paying for a function to sit open while Claude thinks is expensive and bumps into platform timeouts.

**Decision:** Split the backend into two planes.

```
┌─────────────────────────────────────────────────────────────┐
│  EDGE / API PLANE  (Vercel or AWS API Gateway + Lambda)       │
│  - Auth, JWT validation, rate limiting, CORS                  │
│  - Thin CRUD: budgets, goals, accounts read, settings        │
│  - Webhook receivers (Plaid, Stripe) -> enqueue to SQS        │
│  - Tenant resolution (X-Tenant-ID / subdomain)               │
└───────────────┬──────────────────────────────────────────────┘
                │ internal call / queue
┌───────────────┴──────────────────────────────────────────────┐
│  SERVICE PLANE  (ECS Fargate — persistent Node containers)    │
│  - AI Advisor service: agentic Claude loop + MCP tools        │
│  - Sync workers: Plaid transactions/investments/liabilities   │
│  - Alert engine, notification dispatcher, digest generator    │
│  - Holds pooled DB connections via RDS Proxy                  │
└───────────────────────────────────────────────────────────────┘
```

Same TypeScript codebase, deployed two ways. Framework: **Fastify** (lean, fast, great for the service plane) or **NestJS** if you want batteries-included structure. Recommendation: Fastify + a clean module layout; NestJS adds ceremony you don't need yet.

---

## 2. Mandatory infrastructure (not "Phase 3")

These are required at *launch* for 100K, not later:

| Component | Why it's required now |
|---|---|
| **RDS Proxy** (or PgBouncer) | Connection pooling between the fleet and Aurora. Without it the agentic loop kills the DB. |
| **Aurora Serverless v2** (0.5–16 ACU autoscale), Multi-AZ | Right scaling shape for spiky AI load; Multi-AZ gives the 30s failover the DR plan promises. |
| **ElastiCache Redis** (Multi-AZ) | AI health/degradation state shared across instances, rate-limit counters, alert dedup, chat session cache. |
| **SQS** (3 queues + DLQs) | `plaid-sync`, `alerts`, `notifications`. Decouples slow work from request path. |
| **Secrets Manager** | All keys (Anthropic, Plaid, DB, NextAuth). Never env vars in prod. |
| **KMS** | Envelope encryption for Plaid access tokens; Aurora at-rest key. |
| **S3** | Statement PDFs, audit-log archives (7yr), white-label assets. |
| **EventBridge** | Scheduled jobs: daily budget alert engine, weekly digests, soft-dup cleanup, health checks. |

---

## 3. Service modules (the service plane)

| Module | Responsibility | Key dependencies |
|---|---|---|
| **Auth** | Signup, login, email verify, JWT + refresh rotation, session table | bcrypt(12), Redis (rate limit) |
| **Plaid Sync** | Link token, public-token exchange, idempotent `transactions/sync`, investments, liabilities | KMS, SQS, Aurora, Plaid webhooks |
| **AI Advisor** | Agentic Claude loop, MCP tool execution, output validation, conversation summarization, token budgeting | Anthropic SDK, Aurora, Redis |
| **Budget** | CRUD, categorization, velocity/forecast calc | Aurora |
| **Goals** | CRUD, reverse-engineering math, milestone tracking | Aurora |
| **Debt** | Snowball/avalanche calc, DTI, refinance flags | Aurora |
| **Portfolio** | Holdings aggregation, allocation, sector/concentration | Aurora, market data |
| **Alert Engine** | Daily per-user budget/goal/anomaly checks → notifications | EventBridge, SQS |
| **Notifications** | Channel routing (push/email/sms/in-app), dedup, prefs, TCPA opt-out | SES/SendGrid, Twilio, FCM |
| **Tenancy** | Tenant resolution, RLS context set, partner API keys, usage metering | Aurora RLS |

---

## 4. The AI core — the part that must be right

This is the differentiator, so it gets the most rigor. Rules, all enforced server-side:

1. **No ungrounded numbers.** Any quantitative answer must be preceded by an MCP tool call. Enforced by `output-validator` (`NUMBERS_WITHOUT_TOOL_GROUNDING` → reject + retry once).
2. **Tool results are bounded.** MCP tools return *aggregates*, never raw transaction lists. Per-tool token budgets (`tool-result-limiter`). This is what keeps you from $1.50/turn blowups at 100K.
3. **Compliance framing is non-negotiable** and lives in the system prompt + a regex/LLM-judge validator. Investment topics without an educational disclaimer get rejected.
4. **Prompt injection + jailbreak + crisis detection** run on every inbound message before it reaches Claude.
5. **Conversation summarization** kicks in past ~15K tokens so power users don't blow the context window or your bill.
6. **Provider fallback** (Claude → GPT-4o → Gemini) behind one `callAdvisorLLM` interface, same MCP tool JSON. Auto-trips on >20% Claude error rate over 2 min.

Model IDs to use: primary `claude-opus-4-8` (or `claude-sonnet-4-6` for cost/latency on high-volume chat), classifier `claude-haiku-4-5-20251001`. *Validate current model IDs/pricing against the Claude API reference before wiring — do not hardcode from memory.*

---

## 5. Scaling specifics for 100K active users

| Concern | Design |
|---|---|
| **Transactions table volume** | 100K users × 24mo history ≈ tens of millions of rows. **Partition `transactions` by month (range)**. Indexes per partition. |
| **DB connections** | RDS Proxy; service plane pool sized to ACU, not to instance count. |
| **AI cost control** | Per-tier daily token budget (free 10K / plus 100K / premium 500K), tracked in `token_usage`, enforced before each turn. Cache common deterministic answers in Redis. |
| **Read scaling** | Aurora reader endpoint for dashboards/analytics; writer for sync + mutations. |
| **Rate limits** | 100 req/min/user general, 10 AI req/min/user, in Redis. Per-tenant ceilings for white-label. |
| **Hot path latency** | Dashboard p95 < 500ms (reader + Redis cache). AI first token < 3s via streaming. |
| **Background fan-out** | Alert engine and digests run via EventBridge → SQS, processed by worker fleet with concurrency caps (see queue config in schema doc). |

---

## 6. Security posture (launch requirements)

- Plaid access tokens: **AES-256-GCM envelope encryption** (KMS data key) before column storage (`BYTEA`).
- Passwords: bcrypt cost 12. Sessions: store SHA-256 of refresh token only.
- Parameterized queries only. Zod validation on every endpoint.
- No PII in logs (mask email/phone; user_id UUID only). No financial data in client-facing errors.
- Aurora in private VPC, no public endpoint. WAF in front of API Gateway. TLS 1.3.
- Row-Level Security for tenant isolation (`app.current_tenant_id` set per request).

---

## 7. What I'm explicitly deferring even on the "full build"

You said full blueprint — agreed, but *sequenced*. These ship after the core loop is proven end-to-end, because building them first delays having anything testable:

- i18n / multi-currency / RTL (Section 29) → after US launch
- A/B testing framework (Section 28.3) → once you have traffic to test
- Full 3-provider fallback → start Claude-only behind the `callAdvisorLLM` interface, add providers when reliability data justifies it
- White-label partner dashboard UI → tenancy *schema* goes in now; partner UI later
- SOC 2 audit → prep hooks (audit_logs, access logging) in now; formal audit at Series A as the doc says
