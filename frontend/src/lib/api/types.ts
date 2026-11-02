/** Response models mirroring the backend (budgets, goals). Money is a decimal
 *  STRING from the API — never parse to float for storage/compare. */

export type Budget = {
  budget_id: string;
  category: string;
  monthly_limit: string;
  spent: string;
  pct_used: number;
  remaining: string;
  alert_at_pct: number;
  is_active: boolean;
};

export type Goal = {
  goal_id: string;
  title: string;
  description: string | null;
  target_amount: string;
  current_amount: string;
  target_date: string; // ISO date
  monthly_target: string | null;
  progress_pct: number;
  on_track: boolean;
  status: "active" | "paused" | "completed";
  priority: number;
};

export type Notification = {
  alert_id: string;
  type: string;
  title: string | null;
  body: string | null;
  severity: string;
  is_read: boolean;
  created_at: string;
};

export type NotificationList = { items: Notification[]; unread_count: number };

export type Preferences = {
  push_enabled: boolean;
  email_enabled: boolean;
  sms_opt_in: boolean;
  budget_alerts: boolean;
  goal_alerts: boolean;
  bank_error_alerts: boolean;
  unusual_tx_alerts: boolean;
  weekly_digest: boolean;
  monthly_report: boolean;
  marketing_emails: boolean;
  quiet_hours_start: string; // "HH:MM:SS"
  quiet_hours_end: string;
  timezone: string;
};

export type Debt = {
  debt_id: string;
  debt_type: string | null;
  balance: string | null;
  apr: string | null;
  minimum_payment: string | null;
  months_at_minimum: number | null;
  above_typical_rate: boolean;
};

export type DebtSummary = {
  debts: Debt[];
  total_debt: string;
  total_minimum_payment: string;
  debt_to_income: number | null;
  note: string | null;
};

export type PayoffMethod = {
  payoff_order: string[];
  months_to_payoff: number;
  total_interest: string;
  feasible: boolean;
};

export type PayoffComparison = {
  avalanche: PayoffMethod;
  snowball: PayoffMethod;
  interest_saved_with_avalanche: string;
  note: string | null;
};

export type Holding = {
  name: string | null;
  asset_class: string | null;
  value: string | null;
  unrealized_gain_loss: string | null;
};

export type PortfolioSummary = {
  total_value: string;
  unrealized_gain_loss: string;
  allocation_pct: Record<string, number>;
  sector_exposure_pct: Record<string, number>;
  concentration_flags: string[];
  top_holdings: Holding[];
  note: string | null;
};

/** The 14 Plaid categories the backend accepts (BudgetCreate.category Literal). */
export const PLAID_CATEGORIES = [
  "FOOD_AND_DRINK",
  "SHOPPING",
  "ENTERTAINMENT",
  "TRANSPORTATION",
  "TRAVEL",
  "TRANSFER",
  "FEES",
  "TAXES",
  "LOANS_AND_MORTGAGES",
  "BANK_FEES",
  "FINANCIAL",
  "PERSONAL_FINANCE",
  "UNCATEGORIZED",
  "PERSONAL",
] as const;

/** Tightest money column is NUMERIC(10,2); the backend caps inputs here. */
export const MONEY_MAX = 99_999_999.99;

export function categoryLabel(c: string): string {
  return c
    .toLowerCase()
    .split("_")
    .map((w) => w[0]?.toUpperCase() + w.slice(1))
    .join(" ");
}
