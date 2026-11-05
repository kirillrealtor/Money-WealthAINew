"""Actual stdio child process + PostgreSQL; no live AI or banking credentials required."""
from __future__ import annotations

import json
from uuid import uuid4

import anyio
import httpx
import pytest

from app import db
from app.ai.mcp_client import financial_mcp
from app.config import settings
from app.errors import ApiError
from tests.integration.auth_helpers import create_user
from tests.integration.conftest import _db_reachable

pytestmark = pytest.mark.skipif(not _db_reachable(), reason="Postgres not reachable on localhost:5433")


async def test_stdio_tools_and_snapshot_are_scoped_to_parent_identity(client: httpx.AsyncClient) -> None:
    owner, _ = await create_user(client, f"mcp-owner-{uuid4()}@example.com")
    other, _ = await create_user(client, f"mcp-other-{uuid4()}@example.com")
    tenant = settings.default_tenant_id
    async with db.with_tenant(tenant, owner) as conn:
        item = await conn.fetchval(
            """INSERT INTO plaid_items (user_id,tenant_id,access_token_enc,institution_name)
               VALUES ($1,$2,$3,'Synthetic MCP test') RETURNING item_id""", owner, tenant, b"synthetic",
        )
        await conn.execute(
            """INSERT INTO plaid_accounts (item_id,tenant_id,plaid_account_id,name,type,balance_current)
               VALUES ($1,$2,$3,'Synthetic Checking','depository',1234.56)""", item, tenant, str(uuid4()),
        )
    async with financial_mcp(owner, tenant) as mcp:
        assert (await mcp.snapshot()).net_worth == 1234.56
        content, error = await mcp.execute("get_account_balances", {})
        assert not error and json.loads(content)["net_worth"] == 1234.56
        _, rejected = await mcp.execute("get_account_balances", {"user_id": other})
        assert rejected
    async with financial_mcp(other, tenant) as mcp:
        content, error = await mcp.execute("get_account_balances", {})
        assert not error and json.loads(content)["accounts"] == []
    async with financial_mcp(owner, str(uuid4())) as mcp:
        content, error = await mcp.execute("get_account_balances", {})
        assert not error and json.loads(content)["accounts"] == []


async def test_stdio_cancellation_releases_capacity(client: httpx.AsyncClient) -> None:
    user, _ = await create_user(client, f"mcp-cancel-{uuid4()}@example.com")
    # Cancellation must close the JSON-RPC session and child transport before returning the slot.
    with anyio.move_on_after(0.01):
        async with financial_mcp(user, settings.default_tenant_id):
            await anyio.sleep_forever()
    async with financial_mcp(user, settings.default_tenant_id) as mcp:
        assert len(mcp.tools) == 9


async def test_turn_deadline_closes_session_and_queue_is_bounded(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, _ = await create_user(client, f"mcp-deadline-{uuid4()}@example.com")
    monkeypatch.setattr(settings, "mcp_max_concurrent", 1)
    monkeypatch.setattr(settings, "mcp_queue_timeout_s", 0.01)
    async with financial_mcp(user, settings.default_tenant_id):
        with pytest.raises(ApiError) as queued:
            async with financial_mcp(user, settings.default_tenant_id):
                pytest.fail("A second child must not exceed the configured process limit")
        assert queued.value.code == "SERVICE_BUSY"
    monkeypatch.setattr(settings, "mcp_turn_timeout_s", 0.01)
    with pytest.raises(ApiError) as timed_out:
        async with financial_mcp(user, settings.default_tenant_id):
            await anyio.sleep_forever()
    assert timed_out.value.code == "MCP_UNAVAILABLE"
    # Both a queue rejection and a timed-out turn must release capacity for the next turn.
    monkeypatch.setattr(settings, "mcp_turn_timeout_s", 120)
    async with financial_mcp(user, settings.default_tenant_id) as mcp:
        assert len(mcp.tools) == 9
