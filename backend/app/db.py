"""Database access layer (asyncpg).

A single shared pool. In production the connection string points at RDS Proxy,
which multiplexes these onto a small set of real Aurora connections - this is
what lets the agentic AI loop hold "connections" without exhausting Aurora
(Architecture 2). Queries use $1, $2 placeholders (asyncpg native); never
string-interpolate user input.
"""
from __future__ import annotations

import time
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

import asyncpg

from app.config import settings
from app.errors import ApiError
from app.logging_conf import logger

_pool: asyncpg.Pool | None = None

# Max time a request will wait for a free pooled connection before giving up.
# Without this, a concurrency spike (more in-flight requests than connections)
# makes callers wait *indefinitely* on pool.acquire() — requests pile up, memory
# grows, and the instance OOMs. Failing fast with a 503 sheds load instead, so a
# burst degrades gracefully (and the load balancer can retry elsewhere).
_POOL_ACQUIRE_TIMEOUT = 5.0


def _normalize_dsn(url: str) -> str:
    # asyncpg wants postgresql:// ; accept the common postgres:// alias too.
    if url.startswith("postgres://"):
        return "postgresql://" + url[len("postgres://") :]
    return url


async def init_pool(*, min_size: int = 2, max_size: int = 10) -> None:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            dsn=_normalize_dsn(settings.database_url),
            min_size=min_size,
            max_size=max_size,  # MCP children use a smaller, bounded pool.
            command_timeout=10,
        )
        logger.info("db pool initialized", service="database")


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def _require_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("DB pool not initialized; call init_pool() at startup")
    return _pool


@asynccontextmanager
async def _acquire() -> AsyncIterator[asyncpg.Connection]:
    """Acquire a pooled connection, but never wait longer than
    _POOL_ACQUIRE_TIMEOUT. On timeout, raise a clean 503 (SERVICE_BUSY) so the
    request sheds instead of hanging and exhausting the event loop / memory.
    """
    pool = _require_pool()
    try:
        # asyncpg raises asyncio.TimeoutError (an alias of builtin TimeoutError on
        # 3.11+) if no connection frees up within the timeout.
        conn = await pool.acquire(timeout=_POOL_ACQUIRE_TIMEOUT)
    except TimeoutError as err:
        logger.error("db pool acquire timeout", service="database", error_type="POOL_EXHAUSTED")
        raise ApiError("SERVICE_BUSY") from err
    try:
        yield conn
    finally:
        await pool.release(conn)


async def execute(sql: str, *params: Any) -> str:
    start = time.monotonic()
    try:
        async with _acquire() as conn:
            result = await conn.execute(sql, *params)
        logger.debug("db execute", service="database", latency_ms=_ms(start))
        return cast(str, result)
    except ApiError:
        raise
    except Exception as err:  # noqa: BLE001 - logged and re-raised
        logger.error("db execute failed", service="database", error_type="DB_QUERY_FAILED", error_message=str(err))
        raise


async def fetch(sql: str, *params: Any) -> list[asyncpg.Record]:
    start = time.monotonic()
    try:
        async with _acquire() as conn:
            rows = await conn.fetch(sql, *params)
        logger.debug("db fetch", service="database", latency_ms=_ms(start), rows=len(rows))
        return cast("list[asyncpg.Record]", rows)
    except ApiError:
        raise
    except Exception as err:  # noqa: BLE001
        logger.error("db fetch failed", service="database", error_type="DB_QUERY_FAILED", error_message=str(err))
        raise


async def fetchrow(sql: str, *params: Any) -> asyncpg.Record | None:
    start = time.monotonic()
    try:
        async with _acquire() as conn:
            row = await conn.fetchrow(sql, *params)
        logger.debug("db fetchrow", service="database", latency_ms=_ms(start))
        return row
    except ApiError:
        raise
    except Exception as err:  # noqa: BLE001
        logger.error("db fetchrow failed", service="database", error_type="DB_QUERY_FAILED", error_message=str(err))
        raise


async def fetchval(sql: str, *params: Any) -> Any:
    async with _acquire() as conn:
        return await conn.fetchval(sql, *params)


@asynccontextmanager
async def with_tenant(tenant_id: str, user_id: str | None = None) -> AsyncIterator[asyncpg.Connection]:
    """Yield a connection inside a transaction with the tenant (and optionally
    user) context set, so Row-Level Security policies apply (Architecture 6 /
    schema RLS). The set_config(..., true) makes both transaction-local - safe
    with pooling.

    Passing user_id activates the per-user RLS backstop (migration 009): rows
    must then match BOTH tenant and user. Omit it for system paths that
    legitimately span users (signup, email verification, webhook tenant
    resolution, cross-user sweeps) — the user policy no-ops when unset. Setting
    it only ever tightens access, so callers should pass user_id whenever the
    work belongs to a single authenticated user.

    Acquisition is bounded (see _acquire): under pool exhaustion this raises a
    clean 503 rather than blocking the caller indefinitely.
    """
    async with _acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.current_tenant_id', $1, true), "
                "       set_config('app.current_user_id', $2, true)",
                tenant_id, user_id or "",
            )
            yield conn


def _ms(start: float) -> int:
    return int((time.monotonic() - start) * 1000)


__all__ = [
    "init_pool",
    "close_pool",
    "execute",
    "fetch",
    "fetchrow",
    "fetchval",
    "with_tenant",
    "Sequence",
]
