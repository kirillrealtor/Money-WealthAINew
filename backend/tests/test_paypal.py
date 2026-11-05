from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from app.config import settings
from app.errors import ApiError
from app.modules.paypal import client, service
from app.modules.paypal.schemas import AssessmentRequest


def test_assessment_uses_deposits_and_flags_emergency_floor() -> None:
    balances = {"accounts": [
        {"type": "depository", "currency": "USD", "balance": 4000},
        {"type": "investment", "currency": "USD", "balance": 50000},
    ]}
    result = service.assess_finances(Decimal("1500"), balances, {"months": [{"expense": 1000}]})
    assert result["recommendation"] == "caution"
    assert result["post_purchase_liquid"] == "2500.00"
    assert result["liquid_assets"] == "4000.00"


@pytest.mark.parametrize("accounts,months", [
    ([], []),
    ([{"type": "depository", "currency": "EUR", "balance": 10000}], [{"expense": 100}]),
    ([{"type": "depository", "currency": "USD", "balance": None}], [{"expense": 100}]),
    ([{"type": "depository", "currency": "USD", "balance": 10000}], []),
])
def test_missing_or_non_usd_data_is_never_approved(accounts: list[Any], months: list[Any]) -> None:
    result = service.assess_finances(Decimal("100"), {"accounts": accounts}, {"months": months})
    assert result["recommendation"] == "insufficient_data"


@pytest.mark.parametrize("amount", ["0", "-1", "1.001", "NaN", "Infinity", "100000000"])
def test_invalid_amounts(amount: str) -> None:
    with pytest.raises(ValidationError):
        AssessmentRequest(description="Purchase", amount=amount)


def purchase() -> dict[str, Any]:
    return {"purchase_id": "00000000-0000-0000-0000-000000000002", "order_id": "ORDER123",
            "amount": "100.00", "description": "Headphones", "status": "CREATED",
            "assessment": {"recommendation": "ok"}}


def captured() -> dict[str, Any]:
    return {"id": "ORDER123", "status": "COMPLETED", "purchase_units": [{
        "reference_id": purchase()["purchase_id"], "payments": {"captures": [{
            "id": "CAPTURE123", "status": "COMPLETED", "amount": {"currency_code": "USD", "value": "100.00"},
        }]},
    }]}


def test_capture_requires_exact_amount_currency_and_reference() -> None:
    assert service.capture_details(captured(), purchase()) == ("COMPLETED", "CAPTURE123")
    for field, value in [("value", "1.00"), ("currency_code", "EUR")]:
        order = captured()
        order["purchase_units"][0]["payments"]["captures"][0]["amount"][field] = value
        with pytest.raises(ApiError):
            service.capture_details(order, purchase())
    order = captured()
    order["purchase_units"][0]["reference_id"] = "another-purchase"
    with pytest.raises(ApiError):
        service.capture_details(order, purchase())


async def test_order_requires_explicit_acknowledgement(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get(*args: Any) -> dict[str, Any]:
        return purchase()
    monkeypatch.setattr(service, "get_purchase", get)
    with pytest.raises(ApiError, match="acknowledge"):
        await service.create_order("user", "tenant", "purchase", False)


async def test_capture_replay_never_calls_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get(*args: Any) -> dict[str, Any]:
        return {**purchase(), "status": "COMPLETED"}
    async def unexpected(*args: Any, **kwargs: Any) -> dict[str, Any]:
        pytest.fail("completed payment must not be captured twice")
    monkeypatch.setattr(service, "get_purchase", get)
    monkeypatch.setattr(client, "request", unexpected)
    assert (await service.capture_order("user", "tenant", "purchase"))["status"] == "COMPLETED"


async def test_unapproved_order_is_not_captured(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []
    async def get(*args: Any) -> dict[str, Any]:
        return purchase()
    async def request(method: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append(method)
        return {"status": "CREATED"}
    monkeypatch.setattr(service, "get_purchase", get)
    monkeypatch.setattr(client, "request", request)
    with pytest.raises(ApiError, match="Approve"):
        await service.capture_order("user", "tenant", "purchase")
    assert calls == ["GET"]


async def test_rest_client_uses_sandbox_and_stable_idempotency(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "paypal_client_id", "test-client")
    monkeypatch.setattr(settings, "paypal_client_secret", "test-secret")
    requests = []
    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/v1/oauth2/token":
            return httpx.Response(200, json={"access_token": "test-token"})
        return httpx.Response(201, json={"id": "ORDER123"})
    real_client = httpx.AsyncClient
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(respond),
    ))
    assert await client.request("POST", "/v2/checkout/orders", body={}, request_id="stable") == {"id": "ORDER123"}
    assert all(r.url.host == "api-m.sandbox.paypal.com" for r in requests)
    assert requests[1].headers["PayPal-Request-Id"] == "stable"
    assert requests[1].headers["Authorization"] == "Bearer test-token"


async def test_provider_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "paypal_client_id", "test-client")
    monkeypatch.setattr(settings, "paypal_client_secret", "test-secret")
    real_client = httpx.AsyncClient
    monkeypatch.setattr(client.httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(lambda r: httpx.Response(401, text="private provider error")),
    ))
    with pytest.raises(ApiError) as error:
        await client.request("POST", "/v2/checkout/orders", body={})
    assert error.value.code == "PAYPAL_ERROR"
    assert "private" not in str(error.value)


async def test_create_order_uses_saved_price_and_stable_request_id(monkeypatch: pytest.MonkeyPatch) -> None:
    stored = {**purchase(), "order_id": None,
              "assessment_expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()}
    calls: list[dict[str, Any]] = []
    async def get(*args: Any) -> dict[str, Any]:
        return stored
    async def request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        calls.append(kwargs)
        return {"id": "ORDER123", "links": [{"rel": "payer-action",
                "href": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER123"}]}
    class Connection:
        async def execute(self, sql: str, *args: Any) -> None:
            assert args[:2] == (stored["purchase_id"], "user")
            stored.update(order_id=args[2], approval_url=args[3], status="CREATED")
    @asynccontextmanager
    async def scoped(tenant: str, user: str) -> Any:
        assert (tenant, user) == ("tenant", "user")
        yield Connection()
    monkeypatch.setattr(service, "get_purchase", get)
    monkeypatch.setattr(client, "request", request)
    monkeypatch.setattr(service.db, "with_tenant", scoped)
    result = await service.create_order("user", "tenant", stored["purchase_id"], True)
    assert result["order_id"] == "ORDER123"
    assert calls[0]["request_id"] == stored["purchase_id"]
    assert calls[0]["body"]["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "100.00"}
    await service.create_order("user", "tenant", stored["purchase_id"], True)
    assert len(calls) == 1


async def test_expired_assessment_cannot_start_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    async def get(*args: Any) -> dict[str, Any]:
        return {**purchase(), "order_id": None,
                "assessment_expires_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    monkeypatch.setattr(service, "get_purchase", get)
    with pytest.raises(ApiError, match="expired"):
        await service.create_order("user", "tenant", "purchase", True)


def test_pending_capture_is_not_completed() -> None:
    order = captured()
    order["purchase_units"][0]["payments"]["captures"][0]["status"] = "PENDING"
    assert service.capture_details(order, purchase()) == ("PENDING", "CAPTURE123")
