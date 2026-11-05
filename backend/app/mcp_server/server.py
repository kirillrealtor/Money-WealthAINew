from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from typing import Any
from uuid import UUID

import structlog
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.lowlevel.helper_types import ReadResourceContents
from mcp.server.stdio import stdio_server
from pydantic import AnyUrl

from app import db
from app.ai.snapshot import get_financial_snapshot
from app.ai.tools import EXECUTORS, TOOL_DEFINITIONS


def create_server(user_id: str, tenant_id: str) -> Server[None]:
    # Fail before connecting if the parent supplied invalid/missing identity.
    user_id, tenant_id = str(UUID(user_id)), str(UUID(tenant_id))

    @asynccontextmanager
    async def lifespan(_server: Server[None]) -> AsyncIterator[None]:
        await db.init_pool(min_size=1, max_size=2)
        try:
            yield None
        finally:
            await db.close_pool()

    server: Server[None] = Server("moneywealth-financial-tools", version="1.0.0", lifespan=lifespan)

    @server.list_tools()  # type: ignore[no-untyped-call]
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(name=t["name"], description=t["description"],
                           inputSchema={**t["input_schema"], "additionalProperties": False},
                           annotations=types.ToolAnnotations(readOnlyHint=True, destructiveHint=False))
                for t in TOOL_DEFINITIONS]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
        executor = EXECUTORS.get(name)
        if executor is None:
            return types.CallToolResult(isError=True, content=[types.TextContent(type="text", text="Unknown tool")])
        try:
            result = await executor(user_id, tenant_id, arguments)
            # Normalize Decimal values without leaking objects or SQL error messages.
            result = json.loads(json.dumps(result, default=str))
            return types.CallToolResult(isError=False, structuredContent=result,
                                        content=[types.TextContent(type="text", text=json.dumps(result))])
        except Exception:
            return types.CallToolResult(isError=True,
                                        content=[types.TextContent(type="text", text="Financial tool failed")])

    @server.list_resources()  # type: ignore[no-untyped-call]
    async def list_resources() -> list[types.Resource]:
        return [types.Resource(uri=AnyUrl("wealth://snapshot"), name="Financial snapshot", mimeType="application/json")]

    @server.read_resource()  # type: ignore[no-untyped-call]
    async def read_resource(uri: AnyUrl) -> list[ReadResourceContents]:
        if str(uri) != "wealth://snapshot":
            raise ValueError("Unknown resource")
        try:
            snapshot = await get_financial_snapshot(user_id, tenant_id)
            return [ReadResourceContents(content=json.dumps(asdict(snapshot)), mime_type="application/json")]
        except Exception:
            raise ValueError("Financial snapshot unavailable") from None

    return server


async def main() -> None:
    # stdout is exclusively JSON-RPC. Library/application logs belong on stderr.
    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    structlog.configure(logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
                        processors=[structlog.processors.JSONRenderer()])
    server = create_server(os.environ["WEALTH_MCP_USER_ID"], os.environ["WEALTH_MCP_TENANT_ID"])
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
