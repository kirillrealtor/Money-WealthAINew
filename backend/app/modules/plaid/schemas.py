"""Pydantic models for the Plaid API surface."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


accounts_skipped: int = 0

class LinkTokenResponse(BaseModel):
    link_token: str
    expiration: str | None = None


class ExchangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    public_token: str = Field(min_length=1, max_length=500)


class AccountSummary(BaseModel):
    account_id: str
    name: str | None
    type: str | None
    subtype: str | None
    balance_current: Decimal | None
    currency_code: str | None


class ItemSummary(BaseModel):
    item_id: str
    institution_name: str | None
    item_status: str
    last_sync_at: datetime | None
    accounts: list[AccountSummary]


class ExchangeResponse(BaseModel):
    item_id: str
    institution_name: str | None
    accounts_linked: int


class MessageResponse(BaseModel):
    message: str
