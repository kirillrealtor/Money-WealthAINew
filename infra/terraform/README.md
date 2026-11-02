# MoneyWealth AI — Infrastructure as Code (Terraform)

This is the **production architecture** for the backend platform, as code.

```
Internet ─► ALB (HTTPS) ─► ECS Fargate service (N tasks, autoscaling)
                                 │  private subnets, no public IP
                                 ├─► RDS Proxy ──► Aurora PostgreSQL (Serverless v2)
                                 └─► Upstash Redis / Groq / Plaid (via NAT)
```

## What it creates
- **Network**: dedicated VPC, public + private subnets across `az_count` AZs,
  IGW, one NAT gateway per AZ.
- **Security**: 4-tier SGs — only `ALB:80/443` is public; tasks accept traffic
  *only* from the ALB; RDS Proxy accepts Postgres *only* from tasks; Aurora
  accepts Postgres *only* from the proxy.
- **Compute**: ECS Fargate cluster (Container Insights on), task definition,
  service in private subnets behind the ALB, with **target-tracking
  autoscaling** (CPU 65% / mem 75%, `min`..`max` tasks).
- **Edge**: Application Load Balancer; HTTPS listener when `acm_certificate_arn`
  is set (HTTP→HTTPS redirect), HTTP-only otherwise.
- **Data**: **Aurora PostgreSQL 16** (Serverless v2, 0.5–2 ACU default), encrypted,
  7-day backups, deletion protection in prod; master + `app_user` passwords in
  Secrets Manager; **RDS Proxy** for connection pooling.
- **Registry/secrets**: ECR repo (scan-on-push, lifecycle), SSM SecureString
  parameters (resource owned by TF, **values injected out-of-band**).
- **Observability**: CloudWatch log group + alarms (tasks-down, CPU, ALB 5xx,
  unhealthy targets, Aurora CPU/ACU) → SNS email.

## Prerequisites
- Terraform ≥ 1.6, AWS credentials with admin-ish perms.
- **ELB enabled on the account** (new accounts are gated — open a Support case
  to lift the limit; the ALB will fail to create until then).
- For HTTPS: an ACM certificate in `us-east-1` for your domain.

## Usage
```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars   # then edit
terraform init
terraform plan
terraform apply
```

## Out-of-band steps (by design — keeps secrets out of TF state)
After `apply`:

1. **Fetch passwords** from Secrets Manager:
   ```bash
   aws secretsmanager get-secret-value --secret-id moneywealth/app-user-db --query SecretString --output text
   aws secretsmanager get-secret-value --secret-id "<aurora_master_secret_arn output>" --query SecretString --output text
   ```
2. **URL-encode passwords** for connection strings (required if password contains
   `[`, `]`, `$`, `@`, etc.):
   ```bash
   python -c "from urllib.parse import quote; import sys; print(quote(sys.argv[1], safe=''))" 'RAW_PASSWORD'
   ```
3. **Set SSM parameters** (both use the **RDS Proxy** hostname — tasks cannot reach
   Aurora directly):
   ```bash
   PROXY=$(terraform output -raw rds_proxy_endpoint)
   aws ssm put-parameter --name /moneywealth/DATABASE_URL --type SecureString \
     --value "postgresql://app_user:ENCODED_PASS@${PROXY}:5432/financial_advisor?sslmode=require" --overwrite
   aws ssm put-parameter --name /moneywealth/MIGRATION_DATABASE_URL --type SecureString \
     --value "postgresql://mwadmin:ENCODED_PASS@${PROXY}:5432/financial_advisor?sslmode=require" --overwrite
   ```
4. **Run migrations** — ECS one-off task in the **moneywealth** cluster (private subnets,
   `moneywealth-task` SG), command override: `python,-m,scripts.migrate`.
5. **Bootstrap roles** — after migrations:
   - `ALTER ROLE app_user PASSWORD '<from app-user-db secret>';`
   - `ALTER ROLE mwadmin BYPASSRLS;`
   Or `python -m scripts.bootstrap_aurora_roles` (after image rebuild).
6. **First admin** — ECS one-off: `python,-m,scripts.create_admin,<email>,<pass>,super_admin`
7. **Redeploy ECS** — `aws ecs update-service ... --force-new-deployment`
8. Point Vercel `API_BASE_URL` at `terraform output alb_dns_name`.

## Hackathon cost note
Default Aurora Serverless v2 (0.5–2 ACU) + RDS Proxy + 2 NAT gateways + ECS
will consume ~$100 AWS credits in roughly 4–6 weeks if left running 24/7.
Tear down with `terraform destroy` when the demo ends, or reduce `az_count=1`
and `desired_count=1` to stretch credits.

## Follow-up to fully drop `TRUST_ANY_HOST`
Exempt `/health` routes from `TrustedHostMiddleware` in `backend/app/main.py`, then set
`ALLOWED_HOSTS` to your domain and remove `TRUST_ANY_HOST`.

## State
Local state by default. For a team, uncomment the S3 backend in `versions.tf`
(create the bucket + DynamoDB lock table first).

## Troubleshooting

### `terraform apply` failed deleting old RDS (`deletion protection`)
```bash
aws rds modify-db-cluster --db-cluster-identifier moneywealth-aurora \
  --no-deletion-protection --apply-immediately --region us-east-1
aws rds modify-db-instance --db-instance-identifier moneywealth-aurora-writer \
  --no-deletion-protection --apply-immediately --region us-east-1
terraform apply
```

### SSM parameter `ParameterAlreadyExists`
```bash
terraform import 'aws_ssm_parameter.secret[\"PLAID_SANDBOX_SECRET\"]' /moneywealth/PLAID_SANDBOX_SECRET
```

### Migration task `TimeoutError` connecting to Aurora
Use the **proxy** endpoint in SSM, not the cluster writer hostname. Confirm ECS task
networking matches the running service (moneywealth VPC, private subnets, task SG).

### Migration task URL parse error (`ValueError` on hostname)
Password contains unencoded special characters — URL-encode before putting in SSM.
