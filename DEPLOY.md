# Deploying MoneyWealth AI — superseded

> **This runbook is outdated.** It described manual **RDS PostgreSQL** + **AWS App Runner**.
> Production now uses **ECS Fargate + Aurora PostgreSQL (Serverless v2) + RDS Proxy**,
> provisioned by Terraform.

## Use these instead

| Doc | Purpose |
|-----|---------|
| **[DEVOPS_HANDOFF.md](DEVOPS_HANDOFF.md)** | Authoritative deploy guide (ECS, Aurora, SSM, Vercel) |
| **[infra/terraform/README.md](infra/terraform/README.md)** | Terraform apply, out-of-band DB setup, troubleshooting |

## Current architecture

```
Browser ──► Vercel (Next.js + BFF) ──► ALB ──► ECS Fargate (FastAPI)
                                              │
                                    RDS Proxy ──► Aurora PostgreSQL 16
                                              │
                                    Upstash Redis (serverless)
```

## Quick verify

```bash
curl http://<alb-dns>/health/ready
# {"status":"ready","checks":{"db":"ok","redis":"ok"}}
```

`backend/apprunner.yaml` is kept for reference only — **do not use App Runner** for new deploys.
