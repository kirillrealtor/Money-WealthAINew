# Railway handoff: prepared, not deployed

Finish local validation first. This document and `backend/railway.json` prepare the
next deployment; they do not create resources, incur hosting charges or publish the app.
The team is recovering existing API credentials. Preserve the existing Plaid encryption
key if reusing its encrypted bank tokens; use fresh secrets only for a fresh database.

## Services and source configuration

Create a Railway project with PostgreSQL, Redis and the backend service when hosting
is authorized. Keep the frontend on Vercel initially; changing both hosting layers at
once is unnecessary for this prototype.

For the backend service:

- Repository/branch: `datphandp333/Money-WealthAINew`, reviewed feature branch or its merged commit.
- Root directory: `/backend`.
- Config file path: `/backend/railway.json`.
- Builder: checked-in Dockerfile. It runs as an unprivileged container user and
  binds `0.0.0.0` to Railway's injected `PORT`.
- Pre-deploy: `python -m scripts.migrate`, limited to 300 seconds.
- Readiness: `/health/ready`, requiring both PostgreSQL and Redis, with a 120-second timeout.
- Begin with one replica. Each API process limits concurrent private MCP children to two.

The stdio MCP child runs inside the backend container. It requires no separately
exposed port or public MCP endpoint. Do not replace the Docker command with multiple
workers until the database connection and child-process limits have been reviewed.

## Database preparation before first app deployment

Use a **fresh dedicated database** unless the team explicitly chooses an existing one.
Do not point local synthetic seeding or test suites at hosted production data.

1. Set `MIGRATION_DATABASE_URL` to the owner connection for the new database.
2. Run the migration command once using the built backend image, with that owner
   URL available. This creates schema, policies and the `app_user` role.
3. In an owner-authenticated `psql` session, run `\password app_user` and assign a
   unique strong password. Never use the migration's local-development default
   `app_user` password on a hosted database.
4. Set the backend's `DATABASE_URL` to the same database using `app_user` and its
   new password. URL-encode special characters in connection strings.
5. Confirm `app_user` is neither superuser nor BYPASSRLS:

   ```sql
   SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = 'app_user';
   ```

   Both privilege flags must be false. Do not run the app using the managed database's
   owner/superuser connection: that would defeat the intended isolation model.

6. Keep the owner URL for deployment migrations; the running application's queries
   must use the non-owner app URL. The pre-deploy step applies subsequent migrations.

Do not run the AWS-specific `bootstrap_aurora_roles` script on Railway. Its `mwadmin`
role and AWS Secrets Manager assumptions do not apply here.

## Backend environment checklist

| Setting | Value/source |
|---|---|
| `ENV` | `production` |
| `DATABASE_URL` | Non-owner `app_user` connection on Railway's private network |
| `MIGRATION_DATABASE_URL` | Owner connection used by migration command |
| `REDIS_URL` | Railway Redis connection |
| `JWT_ACCESS_SECRET`, `JWT_REFRESH_SECRET` | Existing deployment secrets when preserving sessions, otherwise freshly generated secrets |
| `ALLOWED_HOSTS` | Exact generated backend hostname; keep `TRUST_ANY_HOST=false` |
| `WEB_APP_URL` | Actual public frontend HTTPS origin; controls PayPal/email return links |
| `ADVISOR_PROVIDER` | The actual selected provider, with its API key and available model |
| `PLAID_ENV` | `sandbox` for the hackathon |
| `PLAID_CLIENT_ID`, `PLAID_SANDBOX_SECRET`, `PLAID_ENC_KEY` | Team's recovered sandbox configuration |
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | Seller sandbox app credentials |
| `MAIL_TRANSPORT` | Configured real email transport for public onboarding; console links are only a local workflow |
| `SYNC_WORKER_ENABLED` | `true` for a single-instance sandbox demo that imports Plaid transactions |
| `MCP_MAX_CONCURRENT` | Start at `2` |

Use private-network database/Redis endpoints. Do not add backend secrets to Vercel's
`NEXT_PUBLIC_*` variables or copy a local `.env` into the container image.

Generate the backend public HTTPS domain, then set the frontend's **server-only**
`API_BASE_URL` to it. Set `NEXT_PUBLIC_APP_URL` to the frontend origin and make
`NEXT_PUBLIC_AUTH_MODE` match backend `AUTH_MODE`. Redeploy the frontend after changing
these values. No cross-origin browser-to-backend requests are needed through the BFF.

## Acceptance before recording or sharing judge access

- `/health/ready` returns ready with both datastore checks `ok`.
- App queries connect as `app_user`; database isolation tests pass in a separate test database.
- A verified test user can sign in after a full browser reload.
- Real Plaid sandbox linking/sync works if included in the demonstration.
- A live AI answer calls financial tools through MCP and matches the actual figures.
- PayPal sandbox approval returns to the correct frontend and a completed capture is verified.
- Cancellation/pending/error states remain truthful; the AI cannot capture payments.
- Test access, hosting availability through judging, and any required account access are arranged.

The development-only seed command intentionally refuses production or remote databases.
Use a dedicated staging-data plan if hosted synthetic finances are desired; do not
disable its guards to populate production.

## Rollback

Keep the last known working commit and environment configuration. Redeploy that
commit if application behavior regresses. Migrations are forward-only: inspect schema
compatibility before rolling code back, and do not delete database volumes or reverse
migrations blindly. Keep database backups before schema-changing releases.

Official references:
- https://docs.railway.com/config-as-code
- https://docs.railway.com/config-as-code/reference
- https://docs.railway.com/deployments/pre-deploy-command
- https://railway.com/railway.schema.json
