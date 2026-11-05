"""Centralized, validated configuration.

In production, secrets (DATABASE_URL, JWT secrets, API keys) are injected from
AWS Secrets Manager into the environment at container start. This loader stays
the same; only the source of the env vars changes.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    port: int = 3000
    log_level: Literal["debug", "info", "warning", "error", "critical"] = "info"

    # App connects as the non-owner app_user role (RLS enforced).
    database_url: str
    # Migrations run as the owner/superuser (creates roles, FORCE RLS, DDL).
    # Falls back to database_url if unset (e.g. single-role environments).
    migration_database_url: str | None = None
    redis_url: str

    jwt_access_secret: str = Field(min_length=32)
    jwt_refresh_secret: str = Field(min_length=32)
    access_token_ttl: int = 900
    refresh_token_ttl: int = 2_592_000
    bcrypt_rounds: int = Field(default=12, ge=10, le=15)
    jwt_issuer: str = "financial-advisor"
    jwt_audience: str = "financial-advisor-api"
    # Admin tokens use a DISTINCT audience so a user token can never reach an
    # admin route (and vice-versa), even though they share the signing secret.
    admin_jwt_audience: str = "financial-advisor-admin"
    admin_access_token_ttl: int = 1800  # 30 min — admin sessions are short-lived

    # password = email + password (+ optional verify/reset emails).
    # magic_link = passwordless sign-in via emailed one-time link (Resend).
    auth_mode: Literal["password", "magic_link"] = "password"

    # ---- Social login (Google "Continue with Google") ----
    # Public OAuth client id (…apps.googleusercontent.com). Leave unset to keep
    # the Google sign-in endpoint returning a clean "not configured" error.
    google_client_id: str | None = None

    app_base_url: str = "http://localhost:3000"
    cookie_domain: str = "localhost"
    default_tenant_id: str = "00000000-0000-0000-0000-000000000001"

    # Security: comma-separated allowlist for Host header (anti host-injection);
    # "*" only acceptable in dev. Max request body size in bytes.
    allowed_hosts: str = "*"
    # Explicit opt-in to accept any Host header in production. Only set when the
    # service has no stable hostname (e.g. a load-balancer-less container with a
    # dynamic public IP) AND Host-derived URLs aren't trusted — the app builds
    # links from WEB_APP_URL, not the Host header, so injection risk is contained.
    trust_any_host: bool = False
    max_body_bytes: int = 1_000_000
    # Comma-separated CORS origins (credentialed). Empty = no cross-origin.
    cors_origins: str = ""

    # ---- Email ----
    # console = log instead of sending (dev). smtp = any SMTP provider (Gmail,
    # Amazon SES SMTP endpoint, Mailgun, ...). sendgrid = SendGrid HTTP API.
    # resend = Resend HTTP API (passwordless magic-link emails).
    magic_link_ttl_minutes: int = Field(default=15, ge=5, le=60)
    # ---- Billing (Stripe) ----
    # All server-only. Price IDs come from the Stripe dashboard (one per
    # plan x interval). Leave blank to keep billing endpoints returning a clean
    # "not configured" error (display-only tiers).
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_price_plus_monthly: str | None = None
    stripe_price_plus_annual: str | None = None
    stripe_price_premium_monthly: str | None = None
    stripe_price_premium_annual: str | None = None
    # Where Stripe Checkout / the Customer Portal send the user back (frontend).
    web_app_url: str = "http://localhost:3100"

    # Hackathon checkout is deliberately sandbox-only. Never expose these to the browser.
    paypal_client_id: str | None = None
    paypal_client_secret: str | None = None
    demo_password: str = Field(default="WealthDemo123!", min_length=12)
    mcp_max_concurrent: int = Field(default=2, ge=1, le=8)
    mcp_queue_timeout_s: float = Field(default=5, gt=0)
    mcp_call_timeout_s: float = Field(default=15, gt=0)
    mcp_turn_timeout_s: float = Field(default=120, gt=0)

    mail_transport: Literal["console", "smtp", "sendgrid", "resend"] = "console"
    mail_from: str = "no-reply@financialadvisor.local"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True  # STARTTLS on port 587 (set False only for :25 relays)
    sendgrid_api_key: str | None = None
    resend_api_key: str | None = None

    @model_validator(mode="after")
    def _check_prod_hardening(self) -> Settings:
        # A wildcard Host allowlist is fine in dev but enables Host-header
        # injection in production (poisoned reset links, cache poisoning), so
        # fail at startup rather than ship a permissive instance. CORS is left
        # unchecked on purpose: the first-party Next BFF is same-origin, so an
        # empty CORS_ORIGINS is the correct production default.
        if self.env == "production" and "*" in self.allowed_hosts_list and not self.trust_any_host:
            raise ValueError(
                "ALLOWED_HOSTS must be an explicit comma-separated allowlist in production "
                "(not '*'), unless TRUST_ANY_HOST=true is set deliberately"
            )
        return self

    @model_validator(mode="after")
    def _check_mail_transport(self) -> Settings:
        # Fail at startup, not at first signup: a half-configured transport
        # would otherwise surface as users who never get their verify email.
        if self.mail_transport == "smtp" and not self.smtp_host:
            raise ValueError("MAIL_TRANSPORT=smtp requires SMTP_HOST")
        if self.mail_transport == "sendgrid" and not self.sendgrid_api_key:
            raise ValueError("MAIL_TRANSPORT=sendgrid requires SENDGRID_API_KEY")
        if self.mail_transport == "resend" and not self.resend_api_key:
            raise ValueError("MAIL_TRANSPORT=resend requires RESEND_API_KEY")
        return self

    # Cloudflare Turnstile (bot/captcha). Disabled by default so local dev and
    # tests run without a key; enable + set the secret in staging/production.
    turnstile_enabled: bool = False
    turnstile_secret_key: str | None = None
    # Require captcha on login only after this many recent failures (step-up).
    login_captcha_after_fails: int = 3

    rate_limit_general_per_min: int = 100
    # Per-user limit for cheap authenticated reads (dashboards). High enough not
    # to bother real UIs, low enough to cap scraping/abuse on unmetered GETs.
    rate_limit_read_per_min: int = 120

    # ---- Background sync worker (durable queue; see migration 010) ----
    # Production runs a dedicated worker fleet: `python -m scripts.worker`.
    # Set true to also run one worker in-process with the API (single-node/dev).
    sync_worker_enabled: bool = False
    sync_worker_batch: int = 10            # jobs claimed per poll
    sync_worker_concurrency: int = 5       # concurrent syncs per worker
    sync_worker_poll_interval_s: float = 1.0
    sync_job_max_retries: int = 5          # requeue a failing job up to N times
    sync_job_stale_seconds: int = 900      # requeue jobs orphaned by a crash after this

    # ---- Plaid (banking data) ----
    plaid_env: Literal["sandbox", "development", "production"] = "sandbox"
    plaid_client_id: str | None = None
    plaid_sandbox_secret: str | None = None
    plaid_development_secret: str | None = None
    plaid_products: str = "transactions"  # comma-separated: transactions,auth,investments,liabilities
    plaid_country_codes: str = "US"
    plaid_redirect_uri: str | None = None
    plaid_webhook_url: str | None = None
    # AES-256-GCM key (base64 of 32 raw bytes) used to encrypt Plaid access
    # tokens at rest. In production this is sourced from KMS/Secrets Manager.
    plaid_enc_key: str | None = None
    plaid_enc_key_version: int = 1

    # ---- AI advisor ----
    # Provider selection: 'auto' prefers Claude, then Gemini, then Grok, falls back to Groq.
    # Set 'groq' to force the free/cheap path; 'claude' to force Claude.
    advisor_provider: Literal["auto", "claude", "groq", "grok", "gemini", "mock"] = "auto"
    anthropic_api_key: str | None = None
    # Groq (OpenAI-compatible, free tier) — good for dev/load-testing the plumbing.
    # NOTE: open models are weaker at compliance framing; run evals before trusting
    # them as the production advisor brain (see docs/PHASE3_PENDING.md).
    groq_api_key: str | None = None
    groq_model: str = "llama-3.3-70b-versatile"
    grok_api_key: str | None = None
    grok_model: str = "grok-beta"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    # Default to Opus 4.8 for financial-reasoning quality. At high volume, set
    # ADVISOR_MODEL=claude-sonnet-4-6 to cut cost (~$3/$15 vs $5/$25 per 1M).
    advisor_model: str = "claude-opus-4-8"
    classifier_model: str = "claude-haiku-4-5"  # cheap model for jailbreak checks
    advisor_max_tokens: int = 1500
    advisor_max_tool_rounds: int = 5            # cap agentic loop (cost/runaway guard)
    advisor_history_turns: int = 10             # chat turns loaded for context
    advisor_thinking: bool = False              # adaptive thinking off by default (latency/cost)
    # Per-tier daily token budgets (input+output) enforced before each turn.
    token_budget_free: int = 10_000
    token_budget_plus: int = 100_000
    token_budget_premium: int = 500_000

    @property
    def stripe_configured(self) -> bool:
        return bool(self.stripe_secret_key)

    def stripe_price_id(self, plan: str, interval: str) -> str | None:
        return {
            ("plus", "monthly"): self.stripe_price_plus_monthly,
            ("plus", "annual"): self.stripe_price_plus_annual,
            ("premium", "monthly"): self.stripe_price_premium_monthly,
            ("premium", "annual"): self.stripe_price_premium_annual,
        }.get((plan, interval))

    @property
    def plaid_configured(self) -> bool:
        return bool(
            self.plaid_client_id
            and (self.plaid_sandbox_secret or self.plaid_development_secret)
            and self.plaid_enc_key
        )

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)

    @property
    def grok_configured(self) -> bool:
        return bool(self.grok_api_key)

    @property
    def gemini_configured(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def ai_configured(self) -> bool:
        return (
            self.anthropic_configured
            or self.groq_configured
            or self.grok_configured
            or self.gemini_configured
        )

    @property
    def plaid_products_list(self) -> list[str]:
        return [p.strip() for p in self.plaid_products.split(",") if p.strip()]

    @property
    def plaid_country_codes_list(self) -> list[str]:
        return [c.strip() for c in self.plaid_country_codes.split(",") if c.strip()]

    @property
    def is_prod(self) -> bool:
        return self.env == "production"

    @property
    def allowed_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()] or ["*"]

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from env


settings = get_settings()
