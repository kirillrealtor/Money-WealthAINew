from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest
from mcp.shared.exceptions import McpError
from mcp.shared.memory import create_connected_server_and_client_session
from pydantic import AnyUrl

from app.ai.mcp_client import FinancialMCP
from app.ai.snapshot import FinancialSnapshot
from app.config import settings
from app.errors import ApiError
from app.mcp_server import server as server_module


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Any:
    async def noop(**kwargs: Any) -> None:
        pass
    async def snapshot(*args: Any) -> FinancialSnapshot:
        return FinancialSnapshot(1000, 0, 500, 200, 60, True, True)
    monkeypatch.setattr(server_module.db, "init_pool", noop)
    monkeypatch.setattr(server_module.db, "close_pool", noop)
    monkeypatch.setattr(server_module, "get_financial_snapshot", snapshot)
    return server_module.create_server(str(uuid4()), str(uuid4()))


async def test_real_mcp_initialization_discovery_and_resource(server: Any) -> None:
    async with create_connected_server_and_client_session(server) as session:
        client = FinancialMCP(session)
        await client.initialize()
        assert len(client.tools) == 9
        assert all("user_id" not in tool["input_schema"]["properties"] for tool in client.tools)
        assert all(tool["input_schema"]["additionalProperties"] is False for tool in client.tools)
        resources = await session.list_resources()
        assert [str(r.uri) for r in resources.resources] == ["wealth://snapshot"]
        snapshot = await client.snapshot()
        assert snapshot.net_worth == 1000
        assert snapshot.is_demo_data
        unknown = await session.call_tool("capture_paypal_payment", {})
        assert unknown.isError


async def test_identity_is_bound_outside_model_arguments(monkeypatch: pytest.MonkeyPatch, server: Any) -> None:
    identities = []
    async def balances(user: str, tenant: str, arguments: dict[str, Any]) -> dict[str, Any]:
        identities.append((user, tenant))
        return {"net_worth": 1234}
    monkeypatch.setitem(server_module.EXECUTORS, "get_account_balances", balances)
    async with create_connected_server_and_client_session(server) as session:
        client = FinancialMCP(session)
        await client.initialize()
        content, error = await client.execute("get_account_balances", {})
        assert not error and json.loads(content)["net_worth"] == 1234
        assert client.successful_calls == ["get_account_balances"]
        rejected = await session.call_tool("get_account_balances", {"user_id": str(uuid4())})
        assert rejected.isError
        assert len(identities) == 1
        assert len(identities[0][0]) == 36 and len(identities[0][1]) == 36


async def test_tool_exception_never_leaks_sql_or_secrets(monkeypatch: pytest.MonkeyPatch, server: Any) -> None:
    async def broken(*args: Any) -> dict[str, Any]:
        raise RuntimeError("SELECT secret FROM users; sk-private-test-value")
    monkeypatch.setitem(server_module.EXECUTORS, "get_account_balances", broken)
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("get_account_balances", {})
        assert result.isError
        assert "SELECT" not in str(result.content)
        assert "sk-private" not in str(result.content)


async def test_invalid_inputs_do_not_execute(server: Any) -> None:
    async with create_connected_server_and_client_session(server) as session:
        result = await session.call_tool("get_spending_summary", {"period": "next_century"})
        assert result.isError
        with pytest.raises(McpError):
            await session.read_resource(AnyUrl("wealth://another-user"))


async def test_tool_timeout_maps_to_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    class SlowSession:
        async def call_tool(self, *args: Any) -> Any:
            await asyncio.sleep(10)
    monkeypatch.setattr(settings, "mcp_call_timeout_s", 0.01)
    client = FinancialMCP(SlowSession())  # type: ignore[arg-type]
    client.tools = [{"name": "get_account_balances"}]
    with pytest.raises(ApiError) as error:
        await client.execute("get_account_balances", {})
    assert error.value.code == "MCP_UNAVAILABLE"
    assert client.successful_calls == []


def test_missing_or_invalid_identity_is_rejected() -> None:
    with pytest.raises(ValueError):
        server_module.create_server("", str(uuid4()))
