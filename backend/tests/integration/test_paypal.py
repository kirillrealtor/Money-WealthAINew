"""Real Postgres ownership/RLS test; payment network calls are never made."""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest

from app import db
from app.config import settings
from app.errors import ApiError
from app.modules.paypal import service
from app.modules.paypal.schemas import AssessmentRequest
from tests.integration.auth_helpers import create_user
from tests.integration.conftest import _db_reachable

pytestmark = pytest.mark.skipif(not _db_reachable(), reason="Postgres not reachable on localhost:5433")


async def test_purchase_is_private_to_user_even_within_same_tenant(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner, owner_token = await create_user(client, f"paypal-owner-{uuid4()}@example.com")
    other, other_token = await create_user(client, f"paypal-other-{uuid4()}@example.com")
    tenant = settings.default_tenant_id
    async with db.with_tenant(tenant) as conn:
        await conn.execute("UPDATE users SET is_verified=true WHERE user_id=ANY($1::uuid[])", [owner, other])

    async def balances(*args: Any) -> dict[str, Any]:
        return {"accounts": [{"type": "depository", "currency": "USD", "balance": 10000}]}
    async def cash(*args: Any) -> dict[str, Any]:
        return {"months": [{"expense": 1000}]}
    monkeypatch.setattr(service, "exec_get_account_balances", balances)
    monkeypatch.setattr(service, "exec_get_cash_flow", cash)
    purchase = await service.assess(owner, tenant, AssessmentRequest(description="Demo", amount=Decimal("100")))
    path = f"/api/v1/paypal/purchases/{purchase['purchase_id']}"
    assert (await client.get(path, headers={"authorization": f"Bearer {owner_token}"})).status_code == 200
    assert (await client.get(path, headers={"authorization": f"Bearer {other_token}"})).status_code == 404
    assert (await client.post(path + "/capture", headers={"authorization": f"Bearer {other_token}"})).status_code == 404
    # Intentionally omit an application user_id filter: the DB policy must still isolate the row.
    async with db.with_tenant(tenant, other) as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM paypal_purchases WHERE purchase_id=$1",
                                   purchase["purchase_id"]) == 0
    async with db.with_tenant(str(uuid4()), owner) as conn:
        assert await conn.fetchval("SELECT COUNT(*) FROM paypal_purchases WHERE purchase_id=$1",
                                   purchase["purchase_id"]) == 0


async def test_order_and_capture_retries_use_saved_database_state(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _ = await create_user(client, f"paypal-retry-{uuid4()}@example.com")
    tenant = settings.default_tenant_id

    async def balances(*args: Any) -> dict[str, Any]:
        return {"accounts": [{"type": "depository", "currency": "USD", "balance": 10000}]}
    async def cash(*args: Any) -> dict[str, Any]:
        return {"months": [{"expense": 1000}]}
    monkeypatch.setattr(service, "exec_get_account_balances", balances)
    monkeypatch.setattr(service, "exec_get_cash_flow", cash)
    purchase = await service.assess(
        user, tenant, AssessmentRequest(description="Synthetic test", amount=Decimal("149")),
    )
    purchase_id = purchase["purchase_id"]
    calls: list[tuple[str, str, dict[str, Any]]] = []
    completed = False
    # The test DB is intentionally reusable; provider fixture IDs must not collide across runs.
    order_id, capture_id = "SYNTHETIC-" + uuid4().hex, "CAPTURE-" + uuid4().hex

    async def provider(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        nonlocal completed
        calls.append((method, path, kwargs))
        if path == "/v2/checkout/orders":
            assert kwargs["body"]["purchase_units"][0]["amount"]["value"] == "149.00"
            return {"id": order_id, "links": [{"rel": "payer-action",
                    "href": f"https://www.sandbox.paypal.com/checkoutnow?token={order_id}"}]}
        if method == "GET" and not completed:
            return {"id": order_id, "status": "APPROVED"}
        completed = True
        return {"id": order_id, "status": "COMPLETED", "purchase_units": [{
            "reference_id": purchase_id, "payments": {"captures": [{"id": capture_id, "status": "COMPLETED",
                "amount": {"currency_code": "USD", "value": "149.00"}}]},
        }]}
    monkeypatch.setattr(service.client, "request", provider)
    order = await service.create_order(user, tenant, purchase_id, True)
    assert order["order_id"] == order_id
    await service.create_order(user, tenant, purchase_id, True)
    assert len(calls) == 1
    assert calls[0][2]["request_id"] == purchase_id
    result = await service.capture_order(user, tenant, purchase_id)
    assert result["status"] == "COMPLETED" and result["capture_id"] == capture_id
    previous = len(calls)
    assert (await service.capture_order(user, tenant, purchase_id))["status"] == "COMPLETED"
    assert len(calls) == previous
    # Tampering is not accepted through a create-order amount parameter; the API accepts only a saved purchase ID.
    async with db.with_tenant(tenant, user) as conn:
        await conn.execute("UPDATE paypal_purchases SET created_at=NOW()-INTERVAL '2 hours' WHERE purchase_id=$1",
                           purchase_id)
        row = await conn.fetchval("SELECT amount FROM paypal_purchases WHERE purchase_id=$1", purchase_id)
        assert row == Decimal("149.00")


async def test_expired_database_assessment_blocks_provider_calls(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _ = await create_user(client, f"paypal-expired-{uuid4()}@example.com")
    async with db.with_tenant(settings.default_tenant_id, user) as conn:
        purchase_id = str(await conn.fetchval(
            """INSERT INTO paypal_purchases (user_id,tenant_id,description,amount,assessment,created_at)
               VALUES ($1,$2,'Synthetic expired',100,'{"recommendation":"ok"}',NOW()-INTERVAL '2 hours')
               RETURNING purchase_id""", user, settings.default_tenant_id,
        ))
    async def unexpected(*args: Any, **kwargs: Any) -> dict[str, Any]:
        pytest.fail("Expired assessments must not call PayPal")
    monkeypatch.setattr(service.client, "request", unexpected)
    with pytest.raises(ApiError, match="expired"):
        await service.create_order(user, settings.default_tenant_id, purchase_id, True)
