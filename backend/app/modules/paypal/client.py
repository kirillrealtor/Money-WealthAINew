"""Small sandbox-only REST client. Provider errors never expose credentials or payer data."""
from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.errors import ApiError

BASE_URL = "https://api-m.sandbox.paypal.com"


async def request(method: str, path: str, *, body: dict[str, Any] | None = None,
                  request_id: str | None = None) -> dict[str, Any]:
    if not settings.paypal_client_id or not settings.paypal_client_secret:
        raise ApiError("PAYPAL_UNAVAILABLE")
    try:
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=25) as client:
            auth = await client.post(
                "/v1/oauth2/token", data={"grant_type": "client_credentials"},
                auth=(settings.paypal_client_id, settings.paypal_client_secret),
            )
            auth.raise_for_status()
            headers = {"Authorization": f"Bearer {auth.json()['access_token']}",
                       "Prefer": "return=representation"}
            if request_id:
                headers["PayPal-Request-Id"] = request_id
            response = await client.request(method, path, json=body, headers=headers)
            response.raise_for_status()
            return dict(response.json())
    except (httpx.HTTPError, KeyError, ValueError) as err:
        raise ApiError("PAYPAL_ERROR") from err
