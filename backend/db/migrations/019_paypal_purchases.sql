-- Sandbox purchase assessments and PayPal orders; amounts are immutable after assessment.
CREATE TABLE paypal_purchases (
  purchase_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL REFERENCES tenants(tenant_id),
  user_id UUID NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
  description VARCHAR(127) NOT NULL,
  amount NUMERIC(10,2) NOT NULL CHECK (amount > 0),
  assessment JSONB NOT NULL,
  paypal_order_id VARCHAR(64) UNIQUE,
  approval_url TEXT,
  capture_id VARCHAR(64),
  status VARCHAR(20) NOT NULL DEFAULT 'ASSESSED'
    CHECK (status IN ('ASSESSED', 'CREATED', 'PENDING', 'COMPLETED')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_paypal_purchases_user ON paypal_purchases(tenant_id, user_id, created_at DESC);
ALTER TABLE paypal_purchases ENABLE ROW LEVEL SECURITY;
ALTER TABLE paypal_purchases FORCE ROW LEVEL SECURITY;
CREATE POLICY paypal_purchase_owner ON paypal_purchases
  USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
    AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid)
  WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
    AND user_id = NULLIF(current_setting('app.current_user_id', true), '')::uuid);
GRANT SELECT, INSERT, UPDATE ON paypal_purchases TO app_user;
