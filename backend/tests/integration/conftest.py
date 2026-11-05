"""Integration fixtures. Skip the whole module if Postgres isn't reachable so
unit-only runs (no datastores) stay green."""
from __future__ import annotations

import socket
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport


def _db_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 5433), timeout=1):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(not _db_reachable(), reason="Postgres not reachable on localhost:5433")


async def _clear_rate_limits() -> None:
    """Wipe fixed-window rate-limit counters so cross-test accumulation can't
    trip a production limit (all ASGI requests share one client host, hence one
    bucket). Uses a fresh connection bound to the current test's event loop so it
    never hits the shared singleton's 'event loop is closed' issue. Best-effort."""
    import redis.asyncio as aioredis

    from app.config import settings

    try:
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        keys = await r.keys("rl:*")
        if keys:
            await r.delete(*keys)
        await r.aclose()
    except Exception:  # noqa: BLE001 - test hygiene; never fail a test on this
        pass


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    # Import here so the skip above applies before any DB wiring.
    from app import db
    from app.main import app
    from app.redis_client import close_redis

    await db.init_pool()
    await _clear_rate_limits()
    try:
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as c:
            yield c
    finally:
        # Each pytest-asyncio test owns a new loop. Dispose pooled Redis sockets
        # before it closes so the next test cannot silently fail open on a stale loop.
        await close_redis()
        await db.close_pool()
