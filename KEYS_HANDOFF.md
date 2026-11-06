# When the recovered keys arrive

Use the team's private handoff channel and local/hosting environment settings.
Never put actual values into `.env.example`, Git, screenshots, test fixtures or Devpost.
Preserve existing database URLs and encryption keys when they belong to existing data.

## Local credential checks recorded November 6, 2026

- Backend configuration validated, the container was recreated, and PostgreSQL/Redis readiness passed.
- Plaid sandbox Link token creation returned HTTP 200 with a sandbox token. This
  verifies the initial credential/API path, not completed bank linking or transaction sync.
  Pushkar can own the full Plaid sandbox integration checks.
- The xAI model-list endpoint returned HTTP 403; the response referred to credits
  and team permissions. The account owner must check billing/credit balance, API-key
  permissions, and an available current model ID. `grok-beta` is still the local
  configured default and has not been verified as available to this account.
- `ADVISOR_PROVIDER` remains explicitly `mock` until a live provider is validated.
  Adding a key does not automatically switch a provider selected as `mock`.
- PayPal sandbox credentials are configured and OAuth authentication passed.
  The user completed buyer approval and capture for USD 10.00. A subsequent
  read-only Orders API check independently confirmed both order and capture as
  `COMPLETED` with the expected USD 10.00 amount. No real money moved.
- After enabling the live sync worker, use `test-backend.ps1` for backend tests.
  Its dedicated local test database and Redis namespace keep test jobs isolated
  from the app worker. All **143 backend tests passed** using that isolation.

No key values, Link tokens or account identifiers are included in these notes.

## Minimum configuration for live verification

| Capability | Backend settings | Notes |
|---|---|---|
| Live AI | `ADVISOR_PROVIDER` and one matching provider key | Choose `claude`, `groq`, `gemini` or `grok`. Set a model available to that account. Leaving the provider as `mock` keeps responses simulated even after adding a key. |
| Plaid sandbox | `PLAID_CLIENT_ID`, `PLAID_SANDBOX_SECRET`, `PLAID_ENC_KEY`, `PLAID_ENV=sandbox` | Keep the original encryption key if reusing encrypted access tokens. Enable `SYNC_WORKER_ENABLED=true` for the single-container demo. |
| PayPal sandbox | `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | Seller REST app plus a separate personal sandbox buyer login. The integration never calls PayPal's live API. |
| Local sign-in | Existing generated JWT settings, `AUTH_MODE=password`, `MAIL_TRANSPORT=console` | No external email keys are required for the seeded local user. |

These are separate integrations: Plaid credentials cannot substitute for PayPal,
and a coding-tool subscription does not provide the app's AI API credentials.

## Reload Docker correctly

After editing `backend/.env`, run from the repository root:

```powershell
docker compose up -d --force-recreate --no-deps --wait app
```

Compose reads `env_file` when it creates a container. `docker compose restart app`
only restarts the existing container and does **not** import changed `.env` values.
Do not delete the database volume to refresh keys.

If changing frontend `NEXT_PUBLIC_*` settings, rebuild and restart the frontend;
those values are compiled into the browser bundle. Keep frontend and backend auth
modes consistent. A provider-key change alone needs no frontend rebuild.

## Live acceptance sequence

1. Check http://localhost:3000/health/ready. Both datastore checks must be `ok`.
2. Ask the advisor about the seeded balances. Verify the displayed provider is the
   selected live provider, no simulated-response label appears, and MCP tools ran.
   Seeded finances are still synthetic even when a live AI model analyzes them.
3. Run `docker compose exec app python -m scripts.run_evals` after selecting the
   live provider. This intentionally makes real model calls and can consume credits.
   A skipped suite or a mock provider is not evidence of live-model quality.
4. If showing Plaid in the final demo, use a separate verified sandbox test profile,
   link the sandbox institution and confirm accounts and transactions actually sync.
   Do not present seeded records as proof of bank linking.
5. In Purchase planner, assess a small USD test purchase. Check its figures against
   the actual tool outputs, then approve using the personal PayPal sandbox buyer.
6. On return, select Confirm sandbox payment. Record a completed order/capture and
   verify the same transaction in the seller sandbox activity. Check cancellation
   and pending handling; never describe a redirect alone as payment success.
7. Record which provider/model and data source were used, update the submission
   checklist, and rehearse the video script before preparing Railway deployment.

Full Railway environment and database-role instructions: [RAILWAY_HANDOFF.md](RAILWAY_HANDOFF.md).
