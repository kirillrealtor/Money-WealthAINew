# MoneyWealth AI: understand the tradeoff before you pay

Submission target: PayPal AI Hackathon, November 12, 2026, 12:00 PM PST / 2:00 PM Chicago.
Official rules: https://paypalaihackathon.devpost.com/rules

## Submission status

This is an existing project being extended for the hackathon. Local code and mock-provider
tests are not proof of a live AI call or a real PayPal sandbox payment. Complete the
live verification checklist below before submitting. The old hosted frontend is not
the judge-access path until its backend and new changes are deployed and tested.
The team confirmed the former AWS backend is retired. Current priority is the
local Docker stack and a reviewable feature branch; Railway hosting follows once
local verification and credential recovery are complete.

### Local verification recorded November 5, 2026

Broader credential-free browser coverage now includes the seeded dashboard, budget
creation/deletion, goals, accounts, debt, portfolio, settings and advisor screens,
plus public pages and settled-page accessibility scans. Admin sign-in tests require
an explicitly provisioned test administrator and are skipped when its credentials are
absent; public admin-route protection is still checked. The CI workflow is configured to run this
suite against Docker without paid provider or bank keys.

- Backend: **140 tests passed**, plus ruff and mypy. All 21 migrations applied to a
  fresh PostgreSQL 16 database; repeated synthetic seeding passed its idempotency check.
- MCP: actual stdio subprocess initialization, discovery, resource reading, tool calls,
  user/tenant isolation, cancellation, queue limits and turn deadlines were exercised.
- Frontend: **27 unit tests passed**, lint passed, and the production build passed.
- Browser: **22 checks passed**, including core finance screens, public pages,
  accessibility scans and the purchase flow through real MCP. Two protected admin
  sign-in checks are explicitly skipped until test-admin credentials are configured.
- Windows environment bootstrap and script syntax passed; rerunning bootstrap preserved
  existing environment files byte-for-byte.
- Docker verification completed: the backend image built, all three Compose services
  became healthy, and the containerized backend reported PostgreSQL and Redis ready.
  All **140 backend tests passed against actual PostgreSQL and Redis containers**.
  All **22 browser checks passed**, including the synthetic demo through the containerized
  backend and its actual Linux stdio MCP subprocess. This supersedes the earlier
  temporary `fakeredis` verification.
- No live provider key or PayPal sandbox credentials were available. No live AI response,
  actual sandbox approval/capture, hosted deployment or submission has been verified.

## Devpost description draft

**Inspiration.** A checkout tells you whether a payment can go through. It rarely tells
you what that purchase means for your emergency fund or savings plans. MoneyWealth AI
helps people understand that tradeoff before they approve a purchase.

**What it does.** Users review their finances, ask a conversational advisor questions,
and assess a one-time purchase. The advisor reads bounded financial tools through a
real Model Context Protocol connection. The purchase planner shows a deterministic
cash-buffer estimate alongside the AI explanation. The user can then approve PayPal
sandbox checkout and confirm the verified capture. The model cannot authorize payments.

**How we built it.** Next.js provides the interface and same-origin backend proxy.
FastAPI authenticates users and launches a private stdio MCP server for each advisor
turn. Nine read-only financial tools and a financial snapshot resource reuse
PostgreSQL queries scoped to the authenticated user and tenant. The backend creates
and captures PayPal sandbox Orders v2 payments using server-stored amounts and stable
request IDs. Redis supports existing rate limits and usage accounting.

**PayPal's role.** PayPal is the payment approval and capture step in the purchase
decision journey. The demonstration shows its connection to financial analysis, buyer
approval and a verified result, rather than using PayPal only to charge for this app.

**Challenges.** Converting internal function calls into actual MCP messages without
letting the model select a different user; keeping process cleanup bounded; making
checkout retries safe; and separating synthetic data from live integration evidence.

**What changed for the hackathon.** The inherited project already contained the web
app, finance modules, authentication, Plaid integration, provider adapters, and Stripe
subscription code. This branch adds actual private MCP server/client orchestration,
PayPal sandbox purchase planning/checkout, reproducible Windows setup, synthetic demo
seeding and disclosure, additional tests, and submission documentation. Confirm the
team's earlier work dates and describe only changes actually made during the event.

**What's next.** Broader forecasting, conversational budget changes, live market
context and production payment operations remain future work. This prototype does
not execute trades or move money through Plaid.

## Tools and services disclosure

| Tool/service | Role | Required for this demo |
|---|---|---|
| Official Python MCP SDK | stdio protocol server/client, financial tool discovery and execution | Yes |
| PayPal sandbox REST APIs | OAuth token, order creation, user approval, capture verification | Yes |
| One configured AI provider | Tool-calling advisor explanations | Yes for live AI evidence |
| Plaid sandbox | Optional bank-link and financial import demonstration | Only when showing actual linking |
| PostgreSQL / Redis | Financial persistence, RLS / rate limits and usage | Yes |
| Next.js / FastAPI | Interface, proxy, authentication, orchestration | Yes |
| Codex | Assisted implementation, documentation, and testing | Disclose development assistance |

Record the actual provider/model used in the recording. The local mock provider is a
scripted simulation and must not be described as live AI. Seeded finances are synthetic
records, not evidence that Plaid was connected. List any other AI coding tools the
team actually used before finalizing this disclosure.

## Judge setup and testing instructions

Prerequisites: Windows PowerShell, Git, Node.js 22+, uv, and running Docker Desktop
with Linux containers. Python 3.11 is provisioned by uv. Equivalent Python/npm/Compose
commands from the README can be used on other platforms.

1. Clone the public repository and check out the submitted commit.
2. From the root run `powershell -ExecutionPolicy Bypass -File setup.ps1`. The policy
   option applies only to this process; it does not change the system's execution policy.
   This installs dependencies, creates missing environment files, starts local Postgres
   and Redis, applies migrations and seeds a dedicated synthetic demo profile.
3. In separate terminals run `powershell -ExecutionPolicy Bypass -File start-dev.ps1 backend`
   and `powershell -ExecutionPolicy Bypass -File start-dev.ps1 frontend`.
4. Open http://localhost:3100/login. Sign in as `demo@fathom.app` using `DEMO_PASSWORD`
   from your locally generated `backend/.env`. No email provider is required locally.
5. Review the synthetic-data banner and the dashboard. Ask the advisor about balances
   or spending; even mock-provider development responses call financial tools via MCP.
6. For live AI, configure one provider key and matching `ADVISOR_PROVIDER` in the backend
   environment, choose a model available to that account, and restart the backend.
7. Follow [PAYPAL_SETUP.md](PAYPAL_SETUP.md) for seller app and separate buyer sandbox
   credentials. Configure the two backend PayPal variables and restart the backend.
8. Open Purchase planner, assess a USD purchase, request the AI explanation, acknowledge
   the estimate, approve in PayPal sandbox, then confirm payment after returning.

No third-party credentials are committed. Local setup runs without them using synthetic
finances and simulated advisor responses; a live AI and PayPal demo requires the
corresponding sandbox/provider account access. Before submitting, the team must give
judges either a working hosted build with authorized test access or clear arrangements
for any external access needed to reproduce the full recorded journey. Do not publish
production secrets to satisfy this requirement.

## Video script: 2 minutes 45 seconds

| Time | Show | Narration |
|---|---|---|
| 0:00-0:20 | Purchase planner and problem statement | A successful payment does not tell you whether a purchase fits your financial goals. |
| 0:20-0:40 | Dashboard with data-source disclosure | Explain the audience and explicitly identify synthetic or Plaid sandbox data. |
| 0:40-1:15 | Ask the live advisor about the purchase | Show its answer and successful financial tool names; explain these cross an actual private MCP connection. |
| 1:15-1:40 | Deterministic cash-buffer estimate | Explain the remaining cash, spending basis, emergency-fund warning and user acknowledgement. |
| 1:40-2:15 | PayPal sandbox approval and return | The buyer approves; the AI never authorizes payment. Hide credentials while recording. |
| 2:15-2:35 | Confirm payment and display order/capture IDs | Success is based on the verified capture, not a redirect. |
| 2:35-2:45 | Closing screen | Recap impact, MCP and PayPal roles, and educational/prototype limitations. |

Rehearse with the actual accounts. Keep the public YouTube video under three minutes;
avoid unlicensed music/assets. Never substitute mocked browser responses for a claimed
working PayPal transaction or live AI answer.

## Final release checklist

- [x] Test migrations and the full integration suite with actual PostgreSQL and Redis.
- [x] Confirm repeated setup/seed does not overwrite configuration or duplicate sample data.
- [ ] Run a live AI turn through MCP; verify its figures against tool results.
- [ ] Complete PayPal sandbox buyer approval and completed capture; verify seller activity.
- [ ] Check cancellation, pending payments, retries, missing data, MCP failure and user isolation.
- [x] Run frontend lint/tests/build and purchase browser tests against the current feature branch.
- [ ] Select and document the final judge-access path; verify it from a clean environment.
- [ ] Confirm team ownership and the MIT license; make the repository public.
- [ ] Finalize tools disclosure and existing-project changes with the team.
- [ ] Upload the public YouTube demo and enter repository/demo/video links on Devpost.
- [ ] Submit before November 12, 2026, 2:00 PM Chicago time.
