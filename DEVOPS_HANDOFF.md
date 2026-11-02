# MoneyWealth AI — DevOps Deployment Handoff

Authoritative deploy guide. Production database: **Amazon Aurora PostgreSQL 16**
(Serverless v2) behind **RDS Proxy**. Supersedes the older `DEPLOY.md` (App Runner +
single-instance RDS).

> **Two ways to deploy:**
> - **A. Terraform (recommended)** — `infra/terraform/` provisions the whole
>   stack *with* an Application Load Balancer (stable HTTPS endpoint, autoscaling).
>   This is the production-grade path.
> - **B. Manual CLI** — what was actually run last time (single Fargate task, no
>   LB, dynamic public IP). Faster to stand up; fine for a demo. Documented at the
>   bottom as a reference.

---

## 1. Architecture

```
Browser ──► Vercel (Next.js 16 frontend + BFF route handlers)
                       │  (server-side only; browser never calls the API directly)
                       ▼
              ALB ──► ECS Fargate  (FastAPI / Uvicorn, container port 8080)
                       │                    │
              RDS Proxy ──► Aurora PostgreSQL 16 (Serverless v2)
                       │
              Upstash Redis (serverless)
```

- ECS tasks reach the database **only through RDS Proxy** (security groups block
  direct task → Aurora connections).
- Both `DATABASE_URL` and `MIGRATION_DATABASE_URL` use the **proxy hostname**.
  URL-encode special characters in passwords (`[`, `]`, `$`, `@`, …).
- The browser only talks to Vercel (same-origin) — **no CORS**. The Next BFF
  (`/api/auth/*`, `/api/backend/[...path]`) calls the backend server-side using
  the server-only `API_BASE_URL`. Access token lives in memory; refresh token is
  an httpOnly first-party cookie (`mw_rt`).
- Backend is stateless → scale horizontally. State is Aurora + Redis.

## 2. Prerequisites

- **Accounts:** AWS, Vercel, Upstash (Redis), a GitHub repo, a domain (for HTTPS
  + email). Optional: Plaid, Groq/Anthropic (AI), Google Cloud (OAuth).
- **Tools:** Docker, AWS CLI, Vercel CLI, Terraform ≥ 1.5 (for path A), Python
  3.12 (to run DB migrations), Node 20+.
- **Repo layout:**
  - `backend/` — FastAPI app, `Dockerfile`, `db/migrations/*.sql`,
    `scripts/migrate.py`, `backend/deploy/task-definition.json`.
  - `frontend/` — Next.js app (deploys to Vercel).
  - `infra/terraform/` — full IaC (VPC, **Aurora + RDS Proxy**, ECR, ECS, ALB, autoscaling, IAM, observability).

## 3. Configuration (env vars & secrets)

The backend reads everything from env (`backend/app/config.py`). Store secrets in
**AWS SSM Parameter Store** (SecureString) and reference them from the ECS task
definition; put non-secrets as plain task env.

**Secrets (SSM SecureString):**

| Name | What |
|---|---|
| `DATABASE_URL` | App role DSN via **RDS Proxy**: `postgresql://app_user:PASS@<proxy-endpoint>:5432/financial_advisor?sslmode=require` (RLS enforced) |
| `MIGRATION_DATABASE_URL` | Owner DSN via **RDS Proxy**: `postgresql://mwadmin:PASS@<proxy-endpoint>:5432/financial_advisor?sslmode=require` (DDL only) |
| `REDIS_URL` | Upstash `rediss://...` URL |
| `JWT_ACCESS_SECRET` | random ≥ 32 chars |
| `JWT_REFRESH_SECRET` | random ≥ 32 chars |
| `PLAID_CLIENT_ID`, `PLAID_SANDBOX_SECRET`, `PLAID_ENC_KEY` | Plaid creds + a 32-byte base64 enc key |
| `GROQ_API_KEY` | AI provider key (or Anthropic) |
| `SMTP_PASSWORD` | only if email enabled — see `EMAIL_SETUP.md` |

**Non-secret task env:**

| Name | Value |
|---|---|
| `ENV` | `production` |
| `PORT` | `8080` |
| `WEB_APP_URL` | `https://zenaiautomation.com/moneywealthai` (verification/reset email links) |
| `ALLOWED_HOSTS` | the backend's public host (or `*` only if behind a trusted proxy) |
| `TRUST_ANY_HOST` | `true` **only** if there's no stable hostname (manual path); prefer `false` + a real host behind the ALB |
| `PLAID_ENV` | `sandbox` or `production` |
| `PLAID_PRODUCTS` | `transactions,liabilities,investments` |
| `SYNC_WORKER_ENABLED` | `true` (drains the durable sync_jobs queue) |
| `TOKEN_BUDGET_FREE` | e.g. `2000000` (per-user daily AI token budget; default 10k is very low) |
| `MAIL_TRANSPORT` | `resend` (magic-link emails via Resend API) |
| `MAIL_FROM` | `MoneyWealth AI <onboarding@resend.dev>` (Resend test sender; no custom domain) |
| `MAGIC_LINK_TTL_MINUTES` | `15` |
| `GOOGLE_CLIENT_ID` | only if "Continue with Google" is enabled (see §7) |

**SSM secrets (add `RESEND_API_KEY`):**

| Parameter | Purpose |
|---|---|
| `/moneywealth/RESEND_API_KEY` | Resend API key (`re_...`, Sending access). Required for magic-link email. |

Set once (never commit the value):

```powershell
aws ssm put-parameter --name /moneywealth/RESEND_API_KEY --type SecureString `
  --value "re_YOUR_KEY" --overwrite --region us-east-1
```

**Resend test sender:** `onboarding@resend.dev` works without domain verification, but Resend only delivers to the inbox of the account that owns the API key until you verify a custom domain.

**Vercel env (frontend), Production scope:**

| Name | Value |
|---|---|
| `API_BASE_URL` | **server-only** (no `NEXT_PUBLIC_`). The backend base URL — the ALB HTTPS URL (path A) or `http://<fargate-ip>:8080` (path B) |
| `NEXT_PUBLIC_APP_URL` | `https://moneywealth-ai.vercel.app` |
| `NEXT_PUBLIC_GOOGLE_CLIENT_ID` | only if Google sign-in is enabled (same value as backend `GOOGLE_CLIENT_ID`) |

## 4. Provision data stores

1. **Aurora PostgreSQL 16 (Serverless v2)** — provisioned by `infra/terraform/rds.tf`
   (default 0.5–2 ACU for hackathon cost). DB name `financial_advisor`. Includes
   **RDS Proxy**, encrypted storage, 7-day backups. Passwords in Secrets Manager:
   - Aurora master (`mwadmin`): `terraform output aurora_master_secret_arn`
   - App role (`app_user`): secret `moneywealth/app-user-db` (Terraform-generated)
2. **Upstash Redis** — create a database, copy the `rediss://` URL → `REDIS_URL`.

After `terraform apply`, complete out-of-band steps in
[infra/terraform/README.md](infra/terraform/README.md): SSM connection strings,
migrations, bootstrap SQL (`ALTER ROLE mwadmin BYPASSRLS`), first admin user.

## 5. Run database migrations

Aurora is in a **private VPC** — run migrations from an **ECS one-off task** (not
your laptop):

```bash
# Command override: python,-m,scripts.migrate
# Networking: same VPC/subnets/SG as the running service (moneywealth-task SG)
# See infra/terraform/README.md for JSON override files + aws ecs run-task
```

Or locally against **docker-compose Postgres** only (`docker compose up -d postgres redis`).

Create the first **admin** user via ECS one-off task:

```bash
# Command: python,-m,scripts.create_admin,<email>,<password>,super_admin
```

See `backend/scripts/create_admin.py`. Idempotent — re-run updates password/role.

## 6. Deploy — Path A: Terraform (recommended)

`infra/terraform/` provisions VPC/subnets, **Aurora + RDS Proxy**, ECR, ECS Fargate **behind an
ALB** (stable HTTPS, no IP churn), autoscaling, IAM, and CloudWatch.

```bash
cd infra/terraform
terraform init
terraform plan    # review; set vars (region, image tag, secret ARNs, domain/cert)
terraform apply
```

Then build & push the image and roll the service (see commands in Path B steps
2–3, but the service runs behind the ALB target group — no IP repoint needed).
Point Vercel `API_BASE_URL` at the **ALB HTTPS URL** once.

> The ALB needs the account's ELB limit available + an ACM cert for HTTPS. The
> previous account had ELB creation blocked, which is why Path B (no LB) was used.
> Resolve the limit (support request) to use this path.

## 7. Deploy the frontend (Vercel)

1. Import the repo into Vercel, root directory `frontend/`.
2. Set the Vercel env vars from §3 (Production).
3. Deploy. CI auto-deploy is wired in `.github/workflows/deploy-frontend.yml`
   (token-based; needs repo secret `VERCEL_TOKEN`).

## 8. Optional integrations

- **Email** (verification/reset links): `EMAIL_SETUP.md` — dedicated Gmail
  stopgap or Amazon SES (recommended). No code change; config only.
- **Continue with Google**: create an OAuth **Web** client in Google Cloud
  Console; authorized JS origin = the Vercel URL. Set `GOOGLE_CLIENT_ID` (backend)
  + `NEXT_PUBLIC_GOOGLE_CLIENT_ID` (Vercel). The button is hidden until set.
- **Plaid**: sandbox works out of the box; production needs Plaid approval.

## 9. CI/CD (GitHub Actions, already in repo)

- `ci.yml` — backend lint/mypy/pytest + AI-safety eval + frontend lint/test/build (on PR + main).
- `deploy-backend.yml` — build → ECR → ECS. **Deploy job is gated to manual
  dispatch** until repo secrets `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are
  set; to enable push-to-deploy, flip the `if:` in the deploy job to
  `github.ref == 'refs/heads/main'`.
- `deploy-frontend.yml` — Vercel deploy on push to main (needs `VERCEL_TOKEN`).

## 10. Verify

```bash
curl https://<backend>/health/ready           # {"status":"ready","checks":{"db":"ok","redis":"ok"}}
# Sign up → (email on) verify link logs straight into /app; (email off) link is logged server-side.
# Admin: POST /api/v1/admin/auth/login ; Plaid link flow from the dashboard.
```

---

## Appendix — Path B: Manual CLI (no load balancer)

What was run last time. Single Fargate task with a **public IP** (no ALB),
because the account couldn't create load balancers. The catch: **the IP changes
on every deploy**, so Vercel `API_BASE_URL` must be repointed each time.

```bash
# Build & push
REG=<acct>.dkr.ecr.<region>.amazonaws.com ; IMAGE=$REG/moneywealth-backend
aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin $REG
docker build --platform linux/amd64 --provenance=false -t $IMAGE:latest backend
docker push $IMAGE:latest

# Register task def (start from backend/deploy/task-definition.json: set image,
# environment, and SSM secret ARNs) then roll the service
aws ecs register-task-definition --cli-input-json file://taskdef.json --region <region>
aws ecs update-service --cluster moneywealth --service moneywealth-backend \
  --task-definition moneywealth-backend:<rev> --force-new-deployment --region <region>

# Get the new public IP → update Vercel API_BASE_URL → redeploy frontend
TASK=$(aws ecs list-tasks --cluster moneywealth --service-name moneywealth-backend \
  --desired-status RUNNING --query "taskArns[0]" --output text --region <region>)
ENI=$(aws ecs describe-tasks --cluster moneywealth --tasks $TASK --region <region> \
  --query "tasks[0].attachments[0].details[?name=='networkInterfaceId'].value|[0]" --output text)
aws ec2 describe-network-interfaces --network-interface-ids $ENI --region <region> \
  --query "NetworkInterfaces[0].Association.PublicIp" --output text
```

Security notes for Path B: the task SG opens 8080 to `0.0.0.0/0` and the backend
runs **http** (no TLS) with `TRUST_ANY_HOST=true`. Acceptable for a short-lived
demo only — **prefer Path A (ALB + HTTPS) for anything real.**

---

## What the handoff engineer must supply (fresh accounts)

New AWS account/creds, new Upstash Redis, fresh Aurora cluster (via Terraform),
SSM connection strings, fresh JWT secrets, Plaid + AI keys, a domain + ACM cert
(Path A), and the GitHub repo secrets (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`,
`VERCEL_TOKEN`).
