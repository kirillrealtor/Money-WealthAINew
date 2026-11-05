# PayPal sandbox demo

The Purchase planner at `/app/purchases` checks a one-time USD purchase against
linked deposits and recent spending, offers an AI explanation using the existing
advisor tools, and lets the user approve a PayPal sandbox payment. These are demo
purchases: no real money moves, no goods are delivered, and no bank funds are moved.

## Configure the sandbox

1. Sign in at https://developer.paypal.com/dashboard/ and select **Apps & Credentials**.
2. Select **Sandbox**, then use or create a REST app associated with your sandbox
   **business** (seller) account. Copy its client ID and secret.
3. Under **Testing Tools > Sandbox Accounts**, locate or create a **personal**
   buyer account. Use its sandbox email/password at checkout, not the seller login.
4. Copy `backend/.env.example` to `backend/.env` if you have no local environment
   file. Ask the team for existing database, Redis, Plaid sandbox and AI configuration.
   Preserve any existing environment file.
5. Set these variables in `backend/.env`:

   ```dotenv
   PAYPAL_CLIENT_ID=your_sandbox_app_client_id
   PAYPAL_CLIENT_SECRET=your_sandbox_app_secret
   WEB_APP_URL=http://localhost:3100
   ```

   Set `WEB_APP_URL` to the actual frontend URL when deploying. PayPal credentials
   belong only on the backend. Do not commit `.env` or paste secrets into chat.

6. Start Postgres and Redis, then run `python -m scripts.migrate` from `backend/`.
   Migration `019_paypal_purchases.sql` creates the order table and ownership policies.
7. Restart the backend. Configure one real AI provider and Plaid sandbox as described
   in the existing README. The AI explanation needs a working AI provider.
8. Start the frontend on port 3100: `npm run dev`.
   Its server-only `API_BASE_URL` must point to the backend (default port 3000).

Official setup references:
- https://developer.paypal.com/api/get-started/
- https://developer.paypal.com/sandbox-testing/accounts
- https://developer.paypal.com/api/make-api-requests

## Rehearse the working demo

1. Sign in with a verified app account. Use the explicitly labeled local synthetic
   demo profile (`python -m scripts.seed_demo`) or link Plaid sandbox USD accounts
   and wait for transactions to sync. Missing data deliberately blocks checkout.
2. Open **Purchase planner**, enter a description and USD price, and check affordability.
3. Review the remaining cash and emergency-fund warning. Select **Explain this purchase**
   to show the live AI response and the financial tools it called. Do not describe the
   deterministic estimate as an AI response or use the mock provider as proof of live AI.
4. Acknowledge the estimate, then continue to PayPal sandbox. Approve using the
   personal sandbox buyer account.
5. On return, select **Confirm sandbox payment**. Success requires PayPal's capture
   to be COMPLETED, with the expected USD amount and purchase reference. Pending
   captures are shown as pending. The return URL alone never confirms payment.
6. Confirm the order/capture IDs in the UI and seller sandbox activity.
7. Exercise cancellation, insufficient history, an AI-provider outage, and retrying
   payment confirmation. A completed payment should not be captured twice.

## Boundaries and deployment

- This integration always calls `api-m.sandbox.paypal.com`; it has no live mode.
- Amount and description come from the saved server assessment, not capture inputs.
- Unused assessments expire after one hour; check affordability again if expired.
- The AI explanation uses private stdio MCP; see `backend/docs/MCP.md`.
- Order creation and capture use stable PayPal request IDs; saved orders belong to
  the authenticated user and tenant, enforced by queries and FORCE RLS.
- The estimate uses available linked data, not a guarantee of affordability. It
  does not reserve funds or deduct earlier sandbox purchases from bank balances.
- Payment state is reconciled when confirming the purchase. There is no webhook
  settlement/refund workflow or real merchant fulfillment in this demo.
- Stripe subscription billing is independent of this sandbox purchase feature.
- Apply the migration and backend environment variables before deploying the UI.

## Submission checklist still to finish

- Run against the team's actual database/Redis and execute integration tests.
- Verify a live AI explanation and a real PayPal sandbox buyer approval/capture.
- Make the repository public with an open-source license chosen by the team.
- Document judge access, tools used, and work completed during the hackathon.
- Record a public YouTube demonstration under three minutes and enter it on Devpost.
- Submit by November 12, 2026, 12:00 PM PST (2:00 PM America/Chicago).
