-- Colonnes pour détecter un même compte relié deux fois (nouvel Item Plaid).
ALTER TABLE plaid_accounts ADD COLUMN IF NOT EXISTS mask VARCHAR(10);
ALTER TABLE plaid_accounts ADD COLUMN IF NOT EXISTS persistent_account_id VARCHAR(100);
CREATE INDEX IF NOT EXISTS idx_accounts_persistent
  ON plaid_accounts(persistent_account_id) WHERE persistent_account_id IS NOT NULL;