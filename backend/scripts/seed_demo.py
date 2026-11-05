"""Idempotent synthetic demo data. Local development databases only; never calls Plaid.

Usage: python -m scripts.seed_demo
Credentials: demo@fathom.app / DEMO_PASSWORD from .env (default WealthDemo123!).
Rerunning resets this dedicated demo profile's sample finances, not other users.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from app import db
from app.config import settings
from app.crypto import hash_password

EMAIL = "demo@fathom.app"


def demo_id(name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"moneywealth-demo:{settings.default_tenant_id}:{name}"))


async def seed() -> str:
    if settings.env != "development" or urlparse(settings.database_url).hostname not in {
        "localhost", "127.0.0.1", "::1", "postgres",
    }:
        raise RuntimeError("Demo seeding requires ENV=development and a local database.")
    user_id, item_id = demo_id("user"), demo_id("item")
    password = settings.demo_password
    if len(password) < 12:
        raise RuntimeError("DEMO_PASSWORD must have at least 12 characters.")
    hashed = hash_password(password)
    async with db.with_tenant(settings.default_tenant_id, user_id) as conn:
        existing = await conn.fetchrow("SELECT user_id,is_demo FROM users WHERE email=$1", EMAIL)
        if existing and (not existing["is_demo"] or str(existing["user_id"]) != user_id):
            raise RuntimeError("Demo email belongs to a non-demo user; refusing to modify it.")
        await conn.execute(
            """INSERT INTO users (user_id,tenant_id,email,password_hash,full_name,is_verified,onboarding_step,is_demo)
               VALUES ($1,$2,$3,$4,'Synthetic Demo User',true,3,true)
               ON CONFLICT (user_id) DO UPDATE SET password_hash=$4, is_verified=true""",
            user_id, settings.default_tenant_id, EMAIL, hashed,
        )
        # No real token exists. This item has no sync jobs or webhook identifier.
        await conn.execute(
            """INSERT INTO plaid_items
               (item_id,user_id,tenant_id,access_token_enc,institution_name,item_status,environment)
               VALUES ($1,$2,$3,$4,'Synthetic Demo - not connected to Plaid','synthetic','synthetic')
               ON CONFLICT (item_id) DO NOTHING""",
            item_id, user_id, settings.default_tenant_id, b"synthetic-no-access-token",
        )
        for name, kind, subtype, balance in [
            ("Checking", "depository", "checking", "4500.00"),
            ("Savings", "depository", "savings", "7500.00"),
            ("Credit card", "credit", "credit card", "1500.00"),
            ("Investments", "investment", "brokerage", "6000.00"),
        ]:
            await conn.execute(
                """INSERT INTO plaid_accounts
                   (account_id,item_id,tenant_id,plaid_account_id,name,type,subtype,balance_current,currency_code,synced_at)
                   VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'USD',NOW())
                   ON CONFLICT (account_id) DO UPDATE SET balance_current=$8,synced_at=NOW()""",
                demo_id(name), item_id, settings.default_tenant_id, f"synthetic-{demo_id(name)}",
                f"Synthetic {name}", kind, subtype, balance,
            )
        # Only remove this script's own synthetic transactions; use DB-relative dates.
        await conn.execute("DELETE FROM transactions WHERE account_id=$1 AND plaid_transaction_id LIKE 'synthetic-%'",
                           demo_id("Checking"))
        for month in range(3):
            for category, amount in [("INCOME", "-5200.00"), ("FOOD_AND_DRINK", "600.00"),
                                     ("RENT_AND_UTILITIES", "1400.00"), ("TRANSPORTATION", "200.00")]:
                await conn.execute(
                    """INSERT INTO transactions
                       (account_id,tenant_id,plaid_transaction_id,amount,date,category,merchant_name)
                       VALUES ($1,$2,$3,$4,(date_trunc('month',CURRENT_DATE)-make_interval(months=>$5))::date,
                               $6,'Synthetic demo transaction')""",
                    demo_id("Checking"), settings.default_tenant_id, f"synthetic-{user_id}-{month}-{category}",
                    amount, month, category,
                )
        await conn.execute(
            """INSERT INTO budgets (budget_id,user_id,tenant_id,category,monthly_limit)
               VALUES ($1,$2,$3,'FOOD_AND_DRINK',700)
               ON CONFLICT (user_id,category) DO UPDATE SET monthly_limit=700""",
            demo_id("budget"), user_id, settings.default_tenant_id,
        )
        await conn.execute(
            """INSERT INTO goals
               (goal_id,user_id,tenant_id,title,target_amount,current_amount,target_date,monthly_target)
               VALUES ($1,$2,$3,'Synthetic emergency fund',15000,7500,CURRENT_DATE+365,625)
               ON CONFLICT (goal_id) DO UPDATE SET target_date=CURRENT_DATE+365,current_amount=7500""",
            demo_id("goal"), user_id, settings.default_tenant_id,
        )
        await conn.execute(
            """INSERT INTO debt_accounts (debt_id,account_id,tenant_id,balance,apr,minimum_payment,debt_type)
               VALUES ($1,$2,$3,1500,0.1999,50,'credit_card')
               ON CONFLICT (debt_id) DO UPDATE SET balance=1500""",
            demo_id("debt"), demo_id("Credit card"), settings.default_tenant_id,
        )
        await conn.execute(
            """INSERT INTO portfolio_holdings
               (holding_id,account_id,tenant_id,ticker,name,quantity,cost_basis,institution_price,
                institution_value,asset_class,sector)
               VALUES ($1,$2,$3,'DEMO','Synthetic diversified fund',60,5400,100,6000,'equity','diversified')
               ON CONFLICT (holding_id) DO UPDATE SET institution_value=6000""",
            demo_id("holding"), demo_id("Investments"), settings.default_tenant_id,
        )
        await conn.execute(
            """INSERT INTO notification_preferences (user_id,tenant_id,email_enabled,push_enabled)
               VALUES ($1,$2,false,false) ON CONFLICT (user_id) DO NOTHING""", user_id, settings.default_tenant_id,
        )
    return user_id


async def main() -> None:
    await db.init_pool()
    try:
        await seed()
        print(f"Synthetic demo ready: {EMAIL}. Password: DEMO_PASSWORD in backend/.env (default WealthDemo123!).")
    finally:
        await db.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
