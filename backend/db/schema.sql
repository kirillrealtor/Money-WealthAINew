-- =====================================================================
-- NOTE: This file is the ANNOTATED REFERENCE for the full data design.
-- The EXECUTABLE source of truth is db/migrations/*.sql (run via
-- `python -m scripts.migrate`). Keep this in sync when migrations change the schema.
-- =====================================================================
--
-- AI Financial Advisor — Consolidated Production Schema (Aurora Postgres)
-- Target: 100K active users, multi-tenant, live Plaid.
--
-- Improvements over blueprint v3.0:
--   * All scattered tables consolidated (sync_jobs, token_usage,
--     ai_response_feedback, notification_preferences, is_duplicate col)
--   * transactions PARTITIONED BY RANGE (date) — required at this scale
--   * Row-Level Security wired for tenant isolation
--   * Explicit indexes for every hot query path
--   * updated_at triggers
-- Run order matters: extensions -> core -> plaid -> planning -> ai -> ops
-- =====================================================================

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()

-- ---------------------------------------------------------------------
-- updated_at helper
-- ---------------------------------------------------------------------
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

-- =====================================================================
-- CORE / TENANCY
-- =====================================================================
CREATE TABLE tenants (
  tenant_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name           VARCHAR(255) NOT NULL,
  slug           VARCHAR(100) UNIQUE NOT NULL,
  plan           VARCHAR(50) NOT NULL DEFAULT 'retail',   -- 'retail' | 'white_label'
  persona_config JSONB DEFAULT '{}'::jsonb,
  theme_config   JSONB DEFAULT '{}'::jsonb,
  api_key_hash   VARCHAR NOT NULL,                        -- SHA-256 of partner API key
  webhook_secret VARCHAR,                                 -- HMAC secret for partner webhooks
  is_active      BOOLEAN NOT NULL DEFAULT true,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- A built-in tenant for retail/direct users so every row has a tenant_id.
INSERT INTO tenants (tenant_id, name, slug, plan, api_key_hash)
VALUES ('00000000-0000-0000-0000-000000000001', 'Retail (Direct)', 'retail', 'retail', 'n/a');

CREATE TABLE users (
  user_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id       UUID NOT NULL REFERENCES tenants(tenant_id) ON DELETE CASCADE,
  email           VARCHAR(255) NOT NULL,
  password_hash   VARCHAR NOT NULL,                       -- bcrypt cost=12
  full_name       VARCHAR(255),
  phone           VARCHAR(20),
  advisor_persona VARCHAR(50) NOT NULL DEFAULT 'balanced',-- strict|balanced|supportive
  tier            VARCHAR(20) NOT NULL DEFAULT 'free',    -- free|plus|premium
  locale          VARCHAR(10) NOT NULL DEFAULT 'en-US',
  display_currency VARCHAR(5) NOT NULL DEFAULT 'USD',
  onboarding_step INTEGER NOT NULL DEFAULT 0,
  is_verified     BOOLEAN NOT NULL DEFAULT false,
  last_login_at   TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (tenant_id, email)                               -- email unique per tenant
);
CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE TRIGGER trg_users_updated BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE user_sessions (
  session_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id      UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  token_hash   VARCHAR NOT NULL,                          -- SHA-256 of refresh token
  ip_address   INET,
  user_agent   TEXT,
  expires_at   TIMESTAMPTZ NOT NULL,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sessions_user ON user_sessions(user_id);
CREATE INDEX idx_sessions_token ON user_sessions(token_hash);

-- =====================================================================
-- PLAID INTEGRATION
-- =====================================================================
CREATE TABLE plaid_items (
  item_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  access_token_enc BYTEA NOT NULL,                        -- AES-256-GCM envelope (KMS)
  item_status      VARCHAR(50) NOT NULL DEFAULT 'good',   -- good|error|pending_expiration
  institution_id   VARCHAR(100),
  institution_name VARCHAR(255),
  cursor           TEXT,                                  -- transactions/sync cursor
  last_sync_at     TIMESTAMPTZ,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_items_user ON plaid_items(user_id);

CREATE TABLE plaid_accounts (
  account_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id           UUID NOT NULL REFERENCES plaid_items(item_id) ON DELETE CASCADE,
  plaid_account_id  VARCHAR(100) NOT NULL UNIQUE,
  name              VARCHAR(255),
  official_name     VARCHAR(255),
  type              VARCHAR(50),                           -- depository|investment|credit|loan
  subtype           VARCHAR(50),
  balance_current   NUMERIC(14,2),
  balance_available NUMERIC(14,2),
  balance_limit     NUMERIC(14,2),
  currency_code     VARCHAR(5) NOT NULL DEFAULT 'USD',
  synced_at         TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_accounts_item ON plaid_accounts(item_id);

-- Transactions: PARTITIONED BY MONTH. Create partitions ahead via a job.
CREATE TABLE transactions (
  transaction_id       UUID NOT NULL DEFAULT gen_random_uuid(),
  account_id           UUID NOT NULL,
  plaid_transaction_id VARCHAR(100) NOT NULL,
  amount               NUMERIC(12,2) NOT NULL,            -- + debit, - credit (Plaid convention)
  iso_currency_code    VARCHAR(5) NOT NULL DEFAULT 'USD',
  date                 DATE NOT NULL,
  authorized_date      DATE,
  merchant_name        VARCHAR(255),
  plaid_category       VARCHAR(100),
  category             VARCHAR(100),                      -- normalized
  subcategory          VARCHAR(100),
  is_recurring         BOOLEAN NOT NULL DEFAULT false,
  is_duplicate         BOOLEAN NOT NULL DEFAULT false,    -- soft-dup flag
  pending              BOOLEAN NOT NULL DEFAULT false,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (transaction_id, date),
  UNIQUE (plaid_transaction_id, date)
) PARTITION BY RANGE (date);

-- Example partitions (automate creation 1 month ahead in a cron job):
CREATE TABLE transactions_2026_05 PARTITION OF transactions
  FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
CREATE TABLE transactions_2026_06 PARTITION OF transactions
  FOR VALUES FROM ('2026-06-01') TO ('2026-07-01');
CREATE TABLE transactions_2026_07 PARTITION OF transactions
  FOR VALUES FROM ('2026-07-01') TO ('2026-08-01');

-- Indexes are created on the parent and inherited by partitions.
CREATE INDEX idx_tx_account_date ON transactions(account_id, date DESC);
CREATE INDEX idx_tx_category_date ON transactions(category, date DESC);

-- =====================================================================
-- FINANCIAL PLANNING
-- =====================================================================
CREATE TABLE budgets (
  budget_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id       UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  category      VARCHAR(100) NOT NULL,
  monthly_limit NUMERIC(10,2) NOT NULL CHECK (monthly_limit > 0),
  alert_at_pct  INTEGER NOT NULL DEFAULT 80,
  is_active     BOOLEAN NOT NULL DEFAULT true,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, category)
);

CREATE TABLE goals (
  goal_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id        UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  title          VARCHAR(255) NOT NULL,
  description    TEXT,
  target_amount  NUMERIC(14,2) NOT NULL CHECK (target_amount > 0),
  current_amount NUMERIC(14,2) NOT NULL DEFAULT 0,
  target_date    DATE NOT NULL,
  monthly_target NUMERIC(10,2),
  priority       INTEGER NOT NULL DEFAULT 1,
  status         VARCHAR(50) NOT NULL DEFAULT 'active',   -- active|paused|completed
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_goals_user ON goals(user_id, status);
CREATE TRIGGER trg_goals_updated BEFORE UPDATE ON goals
  FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE goal_milestones (
  milestone_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  goal_id       UUID NOT NULL REFERENCES goals(goal_id) ON DELETE CASCADE,
  milestone_pct INTEGER NOT NULL,                         -- 25|50|75|100
  achieved_at   TIMESTAMPTZ,
  notified      BOOLEAN NOT NULL DEFAULT false
);

-- =====================================================================
-- PORTFOLIO / DEBT
-- =====================================================================
CREATE TABLE portfolio_holdings (
  holding_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id        UUID NOT NULL REFERENCES plaid_accounts(account_id) ON DELETE CASCADE,
  plaid_security_id VARCHAR(100),
  ticker            VARCHAR(20),
  name              VARCHAR(255),
  quantity          NUMERIC(18,6),
  cost_basis        NUMERIC(14,2),
  institution_price NUMERIC(14,4),
  institution_value NUMERIC(14,2),
  asset_class       VARCHAR(50),                          -- equity|fixed_income|cash|alternative
  sector            VARCHAR(100),
  synced_at         TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_holdings_account ON portfolio_holdings(account_id);

CREATE TABLE debt_accounts (
  debt_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id      UUID NOT NULL REFERENCES plaid_accounts(account_id) ON DELETE CASCADE,
  balance         NUMERIC(14,2),
  apr             NUMERIC(6,4),                           -- 0.2499 = 24.99%
  minimum_payment NUMERIC(10,2),
  last_payment_at DATE,
  debt_type       VARCHAR(50),                            -- credit_card|student_loan|auto|personal
  synced_at       TIMESTAMPTZ
);

-- =====================================================================
-- AI CONVERSATION + QUALITY
-- =====================================================================
CREATE TABLE chat_sessions (
  chat_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  module     VARCHAR(50),                                 -- general|budget|portfolio|goals|debt
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  ended_at   TIMESTAMPTZ
);
CREATE INDEX idx_chat_user ON chat_sessions(user_id, started_at DESC);

CREATE TABLE chat_messages (
  message_id  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  chat_id     UUID NOT NULL REFERENCES chat_sessions(chat_id) ON DELETE CASCADE,
  role        VARCHAR(20) NOT NULL,                       -- user|assistant|tool
  content     TEXT NOT NULL,
  tool_name   VARCHAR(100),
  tool_input  JSONB,
  tool_result JSONB,
  provider    VARCHAR(20),                                -- claude|gpt4o|gemini
  prompt_version VARCHAR(20),
  tokens_used INTEGER,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_chat ON chat_messages(chat_id, created_at);

CREATE TABLE financial_memory (                           -- conversation summarization
  chat_id        UUID PRIMARY KEY REFERENCES chat_sessions(chat_id) ON DELETE CASCADE,
  summary        JSONB NOT NULL,                          -- FinancialMemory object
  turns_compressed INTEGER NOT NULL DEFAULT 0,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE ai_response_feedback (
  feedback_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  message_id     UUID NOT NULL REFERENCES chat_messages(message_id) ON DELETE CASCADE,
  user_id        UUID NOT NULL REFERENCES users(user_id),
  rating         SMALLINT NOT NULL CHECK (rating IN (1, -1)),
  issue_type     VARCHAR(50),                             -- wrong_numbers|not_helpful|compliance_concern|too_long|other
  free_text      TEXT,
  prompt_version VARCHAR(20),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_feedback_created ON ai_response_feedback(created_at DESC);

CREATE TABLE token_usage (                                -- per-user daily AI spend / budgets
  user_id  UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  date     DATE NOT NULL,
  tokens   BIGINT NOT NULL DEFAULT 0,
  provider VARCHAR(20),
  PRIMARY KEY (user_id, date)
);

-- =====================================================================
-- DATA PIPELINE / OPS
-- =====================================================================
CREATE TABLE sync_jobs (                                  -- Plaid sync idempotency + resume
  sync_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id              UUID REFERENCES users(user_id) ON DELETE CASCADE,
  item_id              UUID NOT NULL REFERENCES plaid_items(item_id) ON DELETE CASCADE,
  status               VARCHAR(20) NOT NULL DEFAULT 'pending', -- pending|running|completed|failed|partial
  cursor               TEXT,
  transactions_synced  INTEGER NOT NULL DEFAULT 0,
  retry_count          INTEGER NOT NULL DEFAULT 0,
  error_message        TEXT,
  started_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at         TIMESTAMPTZ
);
CREATE INDEX idx_syncjobs_item_status ON sync_jobs(item_id, status);

CREATE TABLE alerts (
  alert_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  type       VARCHAR(100) NOT NULL,
  title      VARCHAR(255),
  body       TEXT,
  severity   VARCHAR(20) NOT NULL DEFAULT 'info',         -- info|warning|critical
  is_read    BOOLEAN NOT NULL DEFAULT false,
  sent_via   VARCHAR(50)[],
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_alerts_user ON alerts(user_id, created_at DESC);

CREATE TABLE notification_preferences (
  user_id           UUID PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
  push_enabled      BOOLEAN NOT NULL DEFAULT true,
  email_enabled     BOOLEAN NOT NULL DEFAULT true,
  sms_opt_in        BOOLEAN NOT NULL DEFAULT false,       -- explicit (TCPA)
  budget_alerts     BOOLEAN NOT NULL DEFAULT true,
  goal_alerts       BOOLEAN NOT NULL DEFAULT true,
  bank_error_alerts BOOLEAN NOT NULL DEFAULT true,
  unusual_tx_alerts BOOLEAN NOT NULL DEFAULT true,
  weekly_digest     BOOLEAN NOT NULL DEFAULT true,
  monthly_report    BOOLEAN NOT NULL DEFAULT true,
  marketing_emails  BOOLEAN NOT NULL DEFAULT false,
  quiet_hours_start TIME NOT NULL DEFAULT '22:00',
  quiet_hours_end   TIME NOT NULL DEFAULT '08:00',
  timezone          VARCHAR(50) NOT NULL DEFAULT 'America/New_York',
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE audit_logs (
  log_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID REFERENCES users(user_id),
  tenant_id   UUID REFERENCES tenants(tenant_id),
  action      VARCHAR(100) NOT NULL,
  resource    VARCHAR(100),
  resource_id UUID,
  ip_address  INET,
  metadata    JSONB,
  timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_audit_user_time ON audit_logs(user_id, timestamp DESC);
CREATE INDEX idx_audit_tenant_time ON audit_logs(tenant_id, timestamp DESC);

-- =====================================================================
-- ROW-LEVEL SECURITY (tenant isolation)
-- App sets: SELECT set_config('app.current_tenant_id', '<uuid>', true);
-- =====================================================================
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation_users ON users
  USING (tenant_id = current_setting('app.current_tenant_id', true)::uuid);

-- Apply equivalent policies (joined through users) to child tables in
-- migrations once tenancy goes live; kept minimal here for clarity.
