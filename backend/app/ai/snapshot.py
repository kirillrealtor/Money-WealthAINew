"""Financial snapshot injected into the system prompt (tenant-scoped)."""
from __future__ import annotations

from dataclasses import dataclass

from .tools import exec_get_account_balances, exec_get_cash_flow


@dataclass
class FinancialSnapshot:
    net_worth: float
    total_debt: float
    monthly_income: float
    monthly_spend: float
    savings_rate: float | None
    has_linked_accounts: bool
    is_demo_data: bool = False


async def get_financial_snapshot(user_id: str, tenant_id: str) -> FinancialSnapshot:
    balances = await exec_get_account_balances(user_id, tenant_id, {})
    cash = await exec_get_cash_flow(user_id, tenant_id, {"months": 3})

    months = cash["months"]
    income = round(sum(m["income"] for m in months) / len(months), 2) if months else 0.0
    spend = round(sum(m["expense"] for m in months) / len(months), 2) if months else 0.0
    savings_rate = round((income - spend) / income * 100, 1) if income > 0 else None
    from app import db
    async with db.with_tenant(tenant_id, user_id) as conn:
        is_demo = bool(await conn.fetchval("SELECT is_demo FROM users WHERE user_id=$1", user_id))

    return FinancialSnapshot(
        net_worth=balances["net_worth"],
        total_debt=balances["total_debt"],
        monthly_income=income,
        monthly_spend=spend,
        savings_rate=savings_rate,
        has_linked_accounts=bool(balances["accounts"]),
        is_demo_data=is_demo,
    )
