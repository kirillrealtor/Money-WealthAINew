"""Per-turn stdio MCP client; no direct-execution fallback and no public listener."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path
from typing import Any
from weakref import WeakKeyDictionary

import anyio
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from pydantic import AnyUrl

from app.config import settings
from app.errors import ApiError
from app.logging_conf import logger

from .snapshot import FinancialSnapshot

_limiters: WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = WeakKeyDictionary()
# Separate limiters per event loop avoid reusing a semaphore bound to a closed test/server loop.


class FinancialMCP:
    def __init__(self, session: ClientSession) -> None:
        self.session = session
        self.tools: list[dict[str, Any]] = []
        self.successful_calls: list[str] = []

    async def initialize(self) -> None:
        try:
            with anyio.fail_after(settings.mcp_call_timeout_s):
                await self.session.initialize()
                discovered = await self.session.list_tools()
            self.tools = [{"name": t.name, "description": t.description or "", "input_schema": t.inputSchema}
                          for t in discovered.tools]
            if len(self.tools) != 9:
                raise ValueError("Unexpected financial tool catalog")
        except Exception as err:
            raise ApiError("MCP_UNAVAILABLE") from err

    async def snapshot(self) -> FinancialSnapshot:
        try:
            with anyio.fail_after(settings.mcp_call_timeout_s):
                resource = await self.session.read_resource(AnyUrl("wealth://snapshot"))
            content = resource.contents[0]
            if not isinstance(content, types.TextResourceContents):
                raise ValueError("Unexpected snapshot format")
            return FinancialSnapshot(**json.loads(content.text))
        except Exception as err:
            raise ApiError("MCP_UNAVAILABLE") from err

    async def execute(self, name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
        started = time.monotonic()
        success = False
        try:
            if name not in {t["name"] for t in self.tools}:
                return json.dumps({"error": "unknown tool"}), True
            with anyio.fail_after(settings.mcp_call_timeout_s):
                result = await self.session.call_tool(name, arguments)
            success = not result.isError
            if not success:
                return json.dumps({"error": "invalid input or financial tool unavailable"}), True
            if result.structuredContent is None:
                raise ValueError("Missing structured tool result")
            content = json.dumps(result.structuredContent)
            if len(content) > 48000:
                raise ValueError("Financial tool result exceeds limit")
            self.successful_calls.append(name)
            return content, False
        except Exception as err:
            raise ApiError("MCP_UNAVAILABLE") from err
        finally:
            logger.info("mcp tool completed", service="mcp", tool=name if name in {t["name"] for t in self.tools}
                        else "unknown", success=success, latency_ms=round((time.monotonic() - started) * 1000))


@asynccontextmanager
async def financial_mcp(user_id: str, tenant_id: str) -> AsyncIterator[FinancialMCP]:
    loop = asyncio.get_running_loop()
    limiter = _limiters.setdefault(loop, asyncio.Semaphore(settings.mcp_max_concurrent))
    try:
        with anyio.fail_after(settings.mcp_queue_timeout_s):
            await limiter.acquire()
    except TimeoutError as err:
        raise ApiError("SERVICE_BUSY") from err
    try:
        async with AsyncExitStack() as stack:
            # ExitStack unwinds session -> transport -> subprocess in reverse order on errors and cancellation.
            # Explicitly transfer the parent's validated configuration. Never pass identity as tool input.
            env = {"ENV": settings.env, "DATABASE_URL": settings.database_url, "REDIS_URL": settings.redis_url,
                   "JWT_ACCESS_SECRET": settings.jwt_access_secret, "JWT_REFRESH_SECRET": settings.jwt_refresh_secret,
                   "ALLOWED_HOSTS": settings.allowed_hosts, "TRUST_ANY_HOST": str(settings.trust_any_host).lower(),
                   "WEALTH_MCP_USER_ID": user_id, "WEALTH_MCP_TENANT_ID": tenant_id, "PYTHONUTF8": "1",
                   "PATH": os.environ.get("PATH", "")}
            parameters = StdioServerParameters(command=sys.executable, args=["-m", "app.mcp_server.server"],
                                               cwd=str(Path(__file__).resolve().parents[2]), env=env)
            try:
                streams = await stack.enter_async_context(stdio_client(parameters))
                session = await stack.enter_async_context(ClientSession(*streams))
                client = FinancialMCP(session)
                await client.initialize()
            except Exception as err:
                raise ApiError("MCP_UNAVAILABLE") from err
            # Bound model/tool work. The outer ExitStack closes the session and transport on leaving this scope.
            with anyio.fail_after(settings.mcp_turn_timeout_s):
                yield client
    except TimeoutError as err:
        raise ApiError("MCP_UNAVAILABLE") from err
    except BaseExceptionGroup as group:
        # SDK task groups wrap errors raised inside a session. Unwrap a single
        # original exception so API errors (and existing provider behavior) survive cleanup.
        error: BaseException = group
        while isinstance(error, BaseExceptionGroup) and len(error.exceptions) == 1:
            error = error.exceptions[0]
        if isinstance(error, TimeoutError):
            raise ApiError("MCP_UNAVAILABLE") from error
        if isinstance(error, BaseExceptionGroup):
            raise ApiError("MCP_UNAVAILABLE") from error
        raise error from None
    finally:
        limiter.release()
