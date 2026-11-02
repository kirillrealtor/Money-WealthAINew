# Email & auth env setup

Sign-in is controlled by **`AUTH_MODE`**: `password` (email + password) or
`magic_link` (passwordless one-time link via email). The backend and frontend
**must use the same mode**.

Email delivery is config-driven (`backend/app/modules/auth/mailer.py`). Set env
vars (and one SSM secret for production Resend) — no code changes when switching.

---

## Env vars reference

| Variable | Where | Password mode | Magic-link mode |
|---|---|---|---|
| `AUTH_MODE` | backend | `password` | `magic_link` |
| `NEXT_PUBLIC_AUTH_MODE` | frontend | `password` | `magic_link` |
| `MAIL_TRANSPORT` | backend | `console` (dev) or `resend` / `smtp` / `sendgrid` (prod) | **`resend`** (or `console` for dev — links in logs) |
| `RESEND_API_KEY` | backend | Optional (only if sending real mail) | **Required** when `MAIL_TRANSPORT=resend` |
| `MAIL_FROM` | backend | Any valid sender for your transport | `MoneyWealth AI <onboarding@resend.dev>` (test) or `no-reply@yourdomain.com` (prod) |
| `WEB_APP_URL` | backend | Frontend origin (verify + reset links) | Frontend origin (sign-in links) |
| `MAGIC_LINK_TTL_MINUTES` | backend | Ignored | Link expiry (default `15`) |

Shared (both modes): `API_BASE_URL` (frontend, server-only), `NEXT_PUBLIC_APP_URL`
(frontend public origin), JWT secrets, Aurora/SSM database URLs, Redis.

Check active mode at runtime: `GET /api/v1/auth/config` → `{ "auth_mode": "..." }`.

---

## Password mode (`AUTH_MODE=password`)

Signup, login, forgot password, and email verification. **Default for production**
until a custom domain is verified in Resend (magic-link can then email any user).

### Local dev

**`backend/.env`**

```env
AUTH_MODE=password
MAIL_TRANSPORT=console
WEB_APP_URL=http://localhost:3100
MAIL_FROM="MoneyWealth AI <no-reply@localhost>"
```

With `MAIL_TRANSPORT=console`, verification and reset links are **printed in the
backend terminal** — no Resend account needed.

**`frontend/.env.local`**

```env
API_BASE_URL=http://localhost:3000
NEXT_PUBLIC_APP_URL=http://localhost:3100
NEXT_PUBLIC_AUTH_MODE=password
```

Restart backend and frontend. Use `/signup` and `/login`.

### Production (ECS + Vercel)

**Backend (ECS task env)** — see [`backend/deploy/task-definition.json`](backend/deploy/task-definition.json):

```env
AUTH_MODE=password
MAIL_TRANSPORT=resend
MAIL_FROM=MoneyWealth AI <onboarding@resend.dev>
WEB_APP_URL=https://zenaiautomation.com/moneywealthai
```

**Backend (SSM secret):** `RESEND_API_KEY` → `/moneywealth/RESEND_API_KEY`

**Frontend (Vercel env):**

```env
NEXT_PUBLIC_AUTH_MODE=password
API_BASE_URL=<your backend URL>
NEXT_PUBLIC_APP_URL=https://moneywealth-ai.vercel.app
```

For real outbound mail to **any** address, verify a domain in Resend and set
`MAIL_FROM` to e.g. `MoneyWealth AI <no-reply@yourdomain.com>`.

---

## Magic-link mode (`AUTH_MODE=magic_link`)

Passwordless sign-in: user enters email → clicks one-time link → logged in.
Uses **Resend** when `MAIL_TRANSPORT=resend`.

### Local dev

**`backend/.env`**

```env
AUTH_MODE=magic_link
MAIL_TRANSPORT=resend
RESEND_API_KEY=re_...
MAIL_FROM=MoneyWealth AI <onboarding@resend.dev>
WEB_APP_URL=http://localhost:3100
MAGIC_LINK_TTL_MINUTES=15
```

For offline dev without Resend, use `MAIL_TRANSPORT=console` — the link appears
in backend logs (same as password-mode verify emails).

**`frontend/.env.local`**

```env
API_BASE_URL=http://localhost:3000
NEXT_PUBLIC_APP_URL=http://localhost:3100
NEXT_PUBLIC_AUTH_MODE=magic_link
```

Restart both servers. Sign in at `/login` (email only — no password field).

### Production (ECS + Vercel)

**Backend (ECS task env):**

```env
AUTH_MODE=magic_link
MAIL_TRANSPORT=resend
MAIL_FROM=MoneyWealth AI <no-reply@yourdomain.com>
WEB_APP_URL=https://zenaiautomation.com/moneywealthai
MAGIC_LINK_TTL_MINUTES=15
```

**Backend (SSM secret):** `RESEND_API_KEY` → `/moneywealth/RESEND_API_KEY`

**Frontend (Vercel env):**

```env
NEXT_PUBLIC_AUTH_MODE=magic_link
API_BASE_URL=<your backend URL>
NEXT_PUBLIC_APP_URL=https://moneywealth-ai.vercel.app
```

---

## Resend setup

1. Create a free account at [resend.com](https://resend.com).
2. **API Keys** → Create → **Sending access** → copy `re_...`.
3. Put the key in `backend/.env` locally or SSM in production (see below).

### Test sender (`onboarding@resend.dev`)

No custom domain required.

| | Test sender | Verified domain |
|---|---|---|
| `MAIL_FROM` | `MoneyWealth AI <onboarding@resend.dev>` | `no-reply@yourdomain.com` |
| Who receives mail | **Only the email on your Resend account** | Any real address |
| Good for | Local dev, demo, staging | Production |

If the API returns “Check your email” but nothing arrives, sign in with the
**same email as your Resend account**, or verify a domain.

### Store API key in AWS (one-time)

```powershell
aws ssm put-parameter --name /moneywealth/RESEND_API_KEY --type SecureString `
  --value "re_YOUR_KEY" --overwrite --region us-east-1
```

Redeploy the backend after changing ECS env or SSM.

Confirm in CloudWatch logs: `email sent` with `transport=resend` (not
`DEV email (not sent)`).

---

## Switching modes

1. Set `AUTH_MODE` on the backend and `NEXT_PUBLIC_AUTH_MODE` on the frontend to
   the **same** value.
2. Adjust `MAIL_TRANSPORT` / `RESEND_API_KEY` as in the tables above.
3. Redeploy backend and frontend.
4. Existing users keep their accounts; only the sign-in UI and active API routes
   change (wrong-mode endpoints return 404).

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Backend won't start: `MAIL_TRANSPORT=resend requires RESEND_API_KEY` | Set `RESEND_API_KEY` in `.env` or SSM |
| Login shows password field but backend expects magic link (or vice versa) | Align `AUTH_MODE` and `NEXT_PUBLIC_AUTH_MODE` |
| Password signup works but no verify email | `MAIL_TRANSPORT=console` — check backend logs; or configure Resend |
| Magic-link “succeeds” but no email | Resend test sender — use your Resend account email, or verify a domain |
| Link goes to wrong site | Set `WEB_APP_URL` to your public frontend URL |
| `resend status 403/422` in logs | Invalid API key, or recipient not allowed on test sender |
| Still see link in server logs only | `MAIL_TRANSPORT` is still `console` — set `resend` and redeploy |

---

## Alternative mail transports

SMTP (Gmail / Amazon SES) and SendGrid remain supported:

```env
MAIL_TRANSPORT=smtp
SMTP_HOST=...
SMTP_USERNAME=...
SMTP_PASSWORD=...
```

```env
MAIL_TRANSPORT=sendgrid
SENDGRID_API_KEY=...
```

Resend is the recommended default for magic-link and production password-mode
email (verify + reset).
