"""MCP-style financial tools: Anthropic tool schemas + Pydantic input models +
tenant-scoped executors.

SECURITY MODEL (the most important property of the AI layer):
  * The LLM NEVER supplies user_id or tenant_id. Executors receive those from
    the authenticated request context and run inside db.with_tenant(), so the
    model physically cannot reach another user's or tenant's data — even under
    prompt injection.
  * LLM-provided tool inputs are validated against a Pydantic model before use,
    and only ever become SQL `$` parameters (enums/ints), never interpolated.

SCALABILITY: every tool returns BOUNDED AGGREGATES (top-N, monthly summaries) —
never raw transaction lists — keeping cost/turn bounded at scale.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app import db
from app.calculations.affordability import calculate_affordability as _affordability
from app.calculations.debt import Debt
from app.calculations.debt import calculate_debt_payoff as _payoff
from app.modules.budgets import service as budget_service
from app.modules.goals import service as goal_service

# ---------------------------------------------------------------------------
# Anthropic tool definitions (JSON schema). Descriptions are prescriptive about
# WHEN to call (better triggering on recent Opus models).
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "get_account_balances",
        "description": (
            "Retrieve current balances for the user's linked accounts. Call this "
            "before any question about liquidity, net worth, or available cash."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_types": {
                    "type": "array",
                    "items": {"type": "string", "enum": ["depository", "investment", "credit", "loan"]},
                    "description": "Filter by account type. Empty/omitted = all.",
                }
            },
        },
    },
    {
        "name": "get_spending_summary",
        "description": (
            "Get spending broken down by category for a period. Call before any "
            "question about spending habits, budgets, or category analysis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["this_month", "last_month", "last_30d", "last_90d"],
                    "description": "Time window to summarize.",
                }
            },
            "required": ["period"],
        },
    },
    {
        "name": "get_cash_flow",
        "description": (
            "Monthly income minus expenses over the last N months. Use for "
            "savings-rate, affordability, and financial-health questions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "months": {"type": "integer", "minimum": 1, "maximum": 12,
                           "description": "Months to analyze (default 3)."}
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Validated input models (reject anything the LLM hallucinates outside schema)
# ---------------------------------------------------------------------------
class ToolInput(BaseModel):
    # The protocol validates JSON schema too; this protects direct reuse of these executors.
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class BalancesInput(ToolInput):
    account_types: list[Literal["depository", "investment", "credit", "loan"]] = Field(default_factory=list)


class SpendingInput(ToolInput):
    period: Literal["this_month", "last_month", "last_30d", "last_90d"]


class CashFlowInput(ToolInput):
    months: int = Field(default=3, ge=1, le=12)


_PERIOD_DAYS = {"last_30d": 30, "last_90d": 90}

# Exclude moving-your-own-money categories (transfers, card/loan payments) so
# income — and thus savings rate — and category spend stay honest. PFC names.
_EXCL_TRANSFERS = "COALESCE(t.category, '') <> ALL(ARRAY['TRANSFER','TRANSFER_IN','TRANSFER_OUT','LOAN_PAYMENTS'])"


def _f(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float | Decimal) else None


# ---------------------------------------------------------------------------
# Executors — tenant-scoped, result-limited
# ---------------------------------------------------------------------------
async def exec_get_account_balances(user_id: str, tenant_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    args = BalancesInput.model_validate(raw)
    async with db.with_tenant(tenant_id, user_id) as conn:
        if args.account_types:
            rows = await conn.fetch(
                """SELECT pa.name, pa.type, pa.subtype, pa.balance_current, pa.currency_code
                     FROM plaid_accounts pa
                     JOIN plaid_items pi ON pa.item_id = pi.item_id
                    WHERE pi.user_id = $1 AND pa.type = ANY($2::text[])
                    ORDER BY pa.balance_current DESC NULLS LAST LIMIT 25""",
                user_id, args.account_types,
            )
        else:
            rows = await conn.fetch(
                """SELECT pa.name, pa.type, pa.subtype, pa.balance_current, pa.currency_code
                     FROM plaid_accounts pa
                     JOIN plaid_items pi ON pa.item_id = pi.item_id
                    WHERE pi.user_id = $1
                    ORDER BY pa.balance_current DESC NULLS LAST LIMIT 25""",
                user_id,
            )
    accounts = [
        {"name": r["name"], "type": r["type"], "subtype": r["subtype"],
         "balance": _f(r["balance_current"]), "currency": r["currency_code"]}
        for r in rows
    ]
    assets = sum((a["balance"] or 0) for a in accounts if a["type"] in ("depository", "investment"))
    debts = sum((a["balance"] or 0) for a in accounts if a["type"] in ("credit", "loan"))
    return {"accounts": accounts, "total_assets": round(assets, 2),
            "total_debt": round(debts, 2), "net_worth": round(assets - debts, 2),
            "note": None if accounts else "No linked accounts."}


async def exec_get_spending_summary(user_id: str, tenant_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    args = SpendingInput.model_validate(raw)
    if args.period == "this_month":
        where = "t.date >= date_trunc('month', CURRENT_DATE)"
    elif args.period == "last_month":
        where = ("t.date >= date_trunc('month', CURRENT_DATE) - INTERVAL '1 month' "
                 "AND t.date < date_trunc('month', CURRENT_DATE)")
    else:
        where = f"t.date >= CURRENT_DATE - INTERVAL '{_PERIOD_DAYS[args.period]} days'"

    async with db.with_tenant(tenant_id, user_id) as conn:
        rows = await conn.fetch(
            f"""SELECT COALESCE(t.category, 'UNCATEGORIZED') AS category, SUM(t.amount) AS total
                  FROM transactions t
                  JOIN plaid_accounts pa ON t.account_id = pa.account_id
                  JOIN plaid_items pi ON pa.item_id = pi.item_id
                 WHERE pi.user_id = $1 AND t.amount > 0 AND t.pending = false
                   AND {_EXCL_TRANSFERS} AND {where}
                 GROUP BY 1 ORDER BY 2 DESC LIMIT 10""",
            user_id,
        )
    categories = [{"category": r["category"], "amount": round(_f(r["total"]) or 0, 2)} for r in rows]
    total = round(sum(c["amount"] for c in categories), 2)
    return {"period": args.period, "total_spend": total, "top_categories": categories,
            "note": None if categories else "No spending found for this period."}


async def exec_get_cash_flow(user_id: str, tenant_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    args = CashFlowInput.model_validate(raw)
    months = max(1, min(12, args.months))
    async with db.with_tenant(tenant_id, user_id) as conn:
        rows = await conn.fetch(
            f"""SELECT to_char(date_trunc('month', t.date), 'YYYY-MM') AS month,
                       ABS(SUM(t.amount) FILTER (WHERE t.amount < 0 AND {_EXCL_TRANSFERS})) AS income,
                       SUM(t.amount) FILTER (WHERE t.amount > 0 AND {_EXCL_TRANSFERS}) AS expense
                  FROM transactions t
                  JOIN plaid_accounts pa ON t.account_id = pa.account_id
                  JOIN plaid_items pi ON pa.item_id = pi.item_id
                 WHERE pi.user_id = $1 AND t.pending = false
                   AND t.date >= date_trunc('month', CURRENT_DATE) - INTERVAL '{months - 1} months'
                 GROUP BY 1 ORDER BY 1 DESC""",
            user_id,
        )
    out = []
    for r in rows:
        income = _f(r["income"]) or 0.0
        expense = _f(r["expense"]) or 0.0
        out.append({"month": r["month"], "income": round(income, 2),
                    "expense": round(expense, 2), "net": round(income - expense, 2)})
    return {"months": out, "note": None if out else "No transaction history yet."}


# ---------------------------------------------------------------------------
# Phase 4 planning tools
# ---------------------------------------------------------------------------
TOOL_DEFINITIONS += [
    {"name": "get_budget_status",
     "description": "Get budgets with this month's spend and % used. Call for budget questions.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_goals_status", "description": "Get the user's financial goals with progress and on-track status.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_debt_summary", "description": "Get the user's debts (balance, APR, minimum payment) and total debt.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "get_portfolio_summary",
     "description": "Get holdings with allocation, sector concentration, and unrealized gain/loss. Educational only.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "calculate_affordability",
     "description": "Assess whether the user can afford a purchase given their liquidity, surplus, and debt-to-income.",
     "input_schema": {"type": "object", "properties": {
         "purchase_amount": {"type": "number"},
         "is_recurring": {"type": "boolean"},
         "monthly_payment_estimate": {"type": "number", "description": "Required if recurring."}},
         "required": ["purchase_amount", "is_recurring"]}},
    {"name": "calculate_debt_payoff",
     "description": "Compare snowball vs avalanche payoff timelines and total interest for the user's debts.",
     "input_schema": {"type": "object", "properties": {
         "extra_monthly_payment": {"type": "number", "description": "Extra paid above minimums (default 0)."}}}},
]


class AffordabilityInput(ToolInput):
    purchase_amount: float = Field(gt=0, le=99999999.99)
    is_recurring: bool
    monthly_payment_estimate: float = Field(default=0, ge=0, le=99999999.99)


class DebtPayoffInput(ToolInput):
    extra_monthly_payment: float = Field(default=0, ge=0, le=99999999.99)


async def _fetch_debts(conn: Any, user_id: str) -> list[Any]:
    rows = await conn.fetch(
        """SELECT da.debt_id, da.balance, da.apr, da.minimum_payment, da.debt_type
             FROM debt_accounts da
             JOIN plaid_accounts pa ON da.account_id = pa.account_id
             JOIN plaid_items pi ON pa.item_id = pi.item_id
            WHERE pi.user_id = $1""",
        user_id,
    )
    return list(rows)


async def exec_get_budget_status(user_id: str, tenant_id: str, _raw: dict[str, Any]) -> dict[str, Any]:
    statuses = await budget_service.list_status(user_id, tenant_id)
    return {"budgets": statuses[:25], "note": None if statuses else "No budgets set yet."}


async def exec_get_goals_status(user_id: str, tenant_id: str, _raw: dict[str, Any]) -> dict[str, Any]:
    goals = await goal_service.list_goals(user_id, tenant_id)
    return {"goals": goals[:25], "note": None if goals else "No goals set yet."}


async def exec_get_debt_summary(user_id: str, tenant_id: str, _raw: dict[str, Any]) -> dict[str, Any]:
    async with db.with_tenant(tenant_id, user_id) as conn:
        rows = await _fetch_debts(conn, user_id)
    debts = [{"type": r["debt_type"], "balance": _f(r["balance"]), "apr": _f(r["apr"]),
              "minimum_payment": _f(r["minimum_payment"])} for r in rows]
    total = round(sum((d["balance"] or 0) for d in debts), 2)
    return {"debts": debts, "total_debt": total, "note": None if debts else "No debt accounts linked."}


async def exec_get_portfolio_summary(user_id: str, tenant_id: str, _raw: dict[str, Any]) -> dict[str, Any]:
    async with db.with_tenant(tenant_id, user_id) as conn:
        rows = await conn.fetch(
            """SELECT ph.asset_class, ph.sector, ph.institution_value, ph.cost_basis
                 FROM portfolio_holdings ph
                 JOIN plaid_accounts pa ON ph.account_id = pa.account_id
                 JOIN plaid_items pi ON pa.item_id = pi.item_id
                WHERE pi.user_id = $1""",
            user_id,
        )
    total = sum((_f(r["institution_value"]) or 0) for r in rows)
    unrealized = sum(((_f(r["institution_value"]) or 0) - (_f(r["cost_basis"]) or 0)) for r in rows)
    by_class: dict[str, float] = {}
    by_sector: dict[str, float] = {}
    for r in rows:
        val = _f(r["institution_value"]) or 0
        by_class[r["asset_class"] or "unknown"] = by_class.get(r["asset_class"] or "unknown", 0) + val
        by_sector[r["sector"] or "unknown"] = by_sector.get(r["sector"] or "unknown", 0) + val
    alloc = {k: round(v / total * 100, 1) for k, v in by_class.items()} if total else {}
    top_sector = max(by_sector.items(), key=lambda kv: kv[1], default=(None, 0))
    return {
        "total_value": round(total, 2), "unrealized_gain_loss": round(unrealized, 2),
        "allocation_pct": alloc,
        "top_sector": ({"sector": top_sector[0], "pct": round(top_sector[1] / total * 100, 1)} if total else None),
        "note": None if rows else "No investment holdings linked.",
    }


async def exec_calculate_affordability(user_id: str, tenant_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    args = AffordabilityInput.model_validate(raw)
    balances = await exec_get_account_balances(user_id, tenant_id, {"account_types": ["depository"]})
    cash = await exec_get_cash_flow(user_id, tenant_id, {"months": 3})
    months = cash["months"]
    # Do not describe absent or mixed-currency data as proof that a purchase is affordable.
    if (not balances["accounts"] or not months or
            any(a["currency"] != "USD" or a["balance"] is None for a in balances["accounts"])):
        return {"recommendation_flag": "insufficient_data", "note": "Linked USD accounts and spending are required."}
    income = sum(m["income"] for m in months) / len(months) if months else 0.0
    spend = sum(m["expense"] for m in months) / len(months) if months else 0.0
    liquid = sum((a["balance"] or 0) for a in balances["accounts"])
    res = _affordability(
        purchase_amount=Decimal(str(args.purchase_amount)), is_recurring=args.is_recurring,
        monthly_payment_estimate=Decimal(str(args.monthly_payment_estimate)),
        liquid_assets=Decimal(str(liquid)), monthly_surplus=Decimal(str(income - spend)),
        monthly_spend=Decimal(str(spend)), monthly_income=Decimal(str(income)),
    )
    return {"recommendation_flag": res.recommendation_flag,
            "post_purchase_surplus": _f(res.post_purchase_surplus),
            "dti_after": _f(res.dti_after), "post_purchase_liquid": _f(res.post_purchase_liquid),
            "emergency_fund_flag": res.emergency_fund_flag}


async def exec_calculate_debt_payoff(user_id: str, tenant_id: str, raw: dict[str, Any]) -> dict[str, Any]:
    args = DebtPayoffInput.model_validate(raw)
    async with db.with_tenant(tenant_id, user_id) as conn:
        rows = await _fetch_debts(conn, user_id)
    debts = [Debt(id=str(r["debt_id"]), balance=Decimal(str(r["balance"] or 0)),
                  apr=Decimal(str(r["apr"] or 0)), minimum_payment=Decimal(str(r["minimum_payment"] or 0)))
             for r in rows if (r["balance"] or 0) > 0]
    if not debts:
        return {"note": "No debt accounts linked."}
    plans = _payoff(debts, Decimal(str(args.extra_monthly_payment)))
    return {m: {"months_to_payoff": p.months_to_payoff, "total_interest": _f(p.total_interest),
                "feasible": p.feasible} for m, p in plans.items()}


EXECUTORS = {
    "get_account_balances": exec_get_account_balances,
    "get_spending_summary": exec_get_spending_summary,
    "get_cash_flow": exec_get_cash_flow,
    "get_budget_status": exec_get_budget_status,
    "get_goals_status": exec_get_goals_status,
    "get_debt_summary": exec_get_debt_summary,
    "get_portfolio_summary": exec_get_portfolio_summary,
    "calculate_affordability": exec_calculate_affordability,
    "calculate_debt_payoff": exec_calculate_debt_payoff,
}
