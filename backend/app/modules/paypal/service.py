from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from app import db
from app.ai.tools import exec_get_account_balances, exec_get_cash_flow
from app.calculations.affordability import calculate_affordability
from app.config import settings
from app.errors import ApiError

from . import client
from .schemas import AssessmentRequest


def assess_finances(amount: Decimal, balances: dict[str, Any], cash: dict[str, Any]) -> dict[str, Any]:
    accounts = balances["accounts"]
    months = cash["months"]
    deposits = [a for a in accounts if a["type"] == "depository"]
    liquid = sum((Decimal(str(a["balance"])) for a in deposits
                  if a["currency"] == "USD" and a["balance"] is not None), Decimal("0"))
    # Cash-flow tools currently aggregate currencies. Refuse mixed/unknown currency data.
    complete = bool(deposits and months) and all(a["currency"] == "USD" for a in accounts)
    complete = complete and all(a["balance"] is not None for a in deposits)
    spend = (sum((Decimal(str(m["expense"])) for m in months), Decimal("0")) / len(months)
             if months else Decimal("0"))
    complete = complete and spend > 0
    result = calculate_affordability(
        purchase_amount=amount, is_recurring=False, liquid_assets=liquid, monthly_spend=spend,
    )
    return {"recommendation": result.recommendation_flag if complete else "insufficient_data",
            "liquid_assets": str(liquid.quantize(Decimal("0.01"))),
            "monthly_spend": str(spend.quantize(Decimal("0.01"))),
            "post_purchase_liquid": str((liquid - amount).quantize(Decimal("0.01"))),
            "emergency_fund_flag": result.emergency_fund_flag,
            "note": "Educational estimate using linked USD deposits and recent spending; not financial advice. "
                    "Does not reserve funds or include other sandbox purchases."}


def public_purchase(row: dict[str, Any]) -> dict[str, Any]:
    assessment = row["assessment"]
    if isinstance(assessment, str):
        assessment = json.loads(assessment)
    return {"purchase_id": str(row["purchase_id"]), "description": row["description"],
            "amount": str(row["amount"]), "currency": "USD", "assessment": assessment,
            "status": row["status"], "order_id": row["paypal_order_id"],
            "assessment_expires_at": (row["created_at"] + timedelta(hours=1)).isoformat(),
            "approval_url": row["approval_url"], "capture_id": row["capture_id"], "sandbox": True}


async def get_purchase(user_id: str, tenant_id: str, purchase_id: str) -> dict[str, Any]:
    async with db.with_tenant(tenant_id, user_id) as conn:
        row = await conn.fetchrow(
            "SELECT * FROM paypal_purchases WHERE purchase_id = $1 AND user_id = $2", purchase_id, user_id,
        )
    if not row:
        raise ApiError("NOT_FOUND")
    return public_purchase(dict(row))


async def assess(user_id: str, tenant_id: str, body: AssessmentRequest) -> dict[str, Any]:
    balances = await exec_get_account_balances(user_id, tenant_id, {})
    cash = await exec_get_cash_flow(user_id, tenant_id, {"months": 3})
    assessment = assess_finances(body.amount, balances, cash)
    async with db.with_tenant(tenant_id, user_id) as conn:
        row = await conn.fetchrow(
            """INSERT INTO paypal_purchases (user_id, tenant_id, description, amount, assessment)
               VALUES ($1,$2,$3,$4,$5::jsonb) RETURNING *""",
            user_id, tenant_id, body.description, body.amount, json.dumps(assessment),
        )
    return public_purchase(dict(row))


async def create_order(user_id: str, tenant_id: str, purchase_id: str, acknowledge: bool) -> dict[str, Any]:
    purchase = await get_purchase(user_id, tenant_id, purchase_id)
    if not acknowledge:
        raise ApiError("VALIDATION_ERROR", message="Review and acknowledge the assessment before checkout.")
    if purchase["assessment"]["recommendation"] == "insufficient_data":
        raise ApiError("VALIDATION_ERROR", message="Link USD accounts with spending history before checkout.")
    if purchase["order_id"]:
        return purchase
    if datetime.fromisoformat(purchase["assessment_expires_at"]) < datetime.now(timezone.utc):
        raise ApiError("CONFLICT", message="This assessment expired. Check affordability again before checkout.")
    # Bind amount, description and return destinations exclusively on the server.
    root = settings.web_app_url.rstrip("/") + "/app/purchases"
    order = await client.request("POST", "/v2/checkout/orders", request_id=purchase_id, body={
        "intent": "CAPTURE",
        "purchase_units": [{"reference_id": purchase_id, "custom_id": purchase_id,
                            "description": purchase["description"],
                            "amount": {"currency_code": "USD", "value": purchase["amount"]}}],
        "payment_source": {"paypal": {"experience_context": {
            "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING",
            "return_url": f"{root}?purchase_id={purchase_id}",
            "cancel_url": f"{root}?purchase_id={purchase_id}&cancelled=1",
        }}},
    })
    approval = next((link["href"] for link in order.get("links", [])
                     if link.get("rel") in ("approve", "payer-action")), None)
    if (not approval or urlparse(approval).hostname != "www.sandbox.paypal.com"
            or urlparse(approval).scheme != "https" or not order.get("id")):
        raise ApiError("PAYPAL_ERROR")
    async with db.with_tenant(tenant_id, user_id) as conn:
        await conn.execute(
            """UPDATE paypal_purchases SET paypal_order_id=$3, approval_url=$4, status='CREATED'
               WHERE purchase_id=$1 AND user_id=$2 AND paypal_order_id IS NULL""",
            purchase_id, user_id, order["id"], approval,
        )
    return await get_purchase(user_id, tenant_id, purchase_id)


def capture_details(order: dict[str, Any], purchase: dict[str, Any]) -> tuple[str, str | None]:
    if order.get("id") != purchase["order_id"]:
        raise ApiError("PAYPAL_ERROR")
    units = order.get("purchase_units", [])
    if len(units) != 1 or units[0].get("reference_id") != purchase["purchase_id"]:
        raise ApiError("PAYPAL_ERROR")
    captures = units[0].get("payments", {}).get("captures", [])
    if len(captures) != 1:
        raise ApiError("PAYPAL_ERROR")
    capture = captures[0]
    amount = capture.get("amount", {})
    if amount.get("currency_code") != "USD" or Decimal(amount.get("value", "0")) != Decimal(purchase["amount"]):
        raise ApiError("PAYPAL_ERROR")
    status = capture.get("status")
    if status not in ("COMPLETED", "PENDING"):
        raise ApiError("PAYPAL_ERROR")
    return status, str(capture["id"])


async def capture_order(user_id: str, tenant_id: str, purchase_id: str) -> dict[str, Any]:
    purchase = await get_purchase(user_id, tenant_id, purchase_id)
    if purchase["status"] == "COMPLETED":
        return purchase
    if not purchase["order_id"]:
        raise ApiError("CONFLICT", message="Create and approve the PayPal order first.")
    path = f"/v2/checkout/orders/{purchase['order_id']}"
    order = await client.request("GET", path)
    if order.get("status") == "APPROVED":
        request_id = str(uuid5(NAMESPACE_URL, "moneywealth-paypal-capture:" + purchase_id))
        order = await client.request("POST", path + "/capture", body={}, request_id=request_id)
    elif order.get("status") != "COMPLETED":
        raise ApiError("CONFLICT", message="Approve the order in PayPal before confirming payment.")
    status, capture_id = capture_details(order, purchase)
    async with db.with_tenant(tenant_id, user_id) as conn:
        await conn.execute(
            """UPDATE paypal_purchases SET status=$3, capture_id=$4
               WHERE purchase_id=$1 AND user_id=$2 AND status <> 'COMPLETED'""",
            purchase_id, user_id, status, capture_id,
        )
    return await get_purchase(user_id, tenant_id, purchase_id)
