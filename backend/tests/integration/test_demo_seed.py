from __future__ import annotations

import httpx
import pytest

from app import db
from app.config import settings
from scripts.seed_demo import seed
from tests.integration.conftest import _db_reachable

pytestmark = pytest.mark.skipif(not _db_reachable(), reason="Postgres not reachable on localhost:5433")


async def test_demo_seed_is_idempotent_and_labeled(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Only this dedicated local demo profile can be reset; production/remote guards have unit coverage.
    monkeypatch.setattr(settings, "env", "development")
    first = await seed()
    assert await seed() == first
    async with db.with_tenant(settings.default_tenant_id, first) as conn:
        assert await conn.fetchval("SELECT is_demo FROM users WHERE user_id=$1", first)
        assert await conn.fetchval(
            "SELECT COUNT(*) FROM plaid_items WHERE user_id=$1 AND environment='synthetic'", first,
        ) == 1
        assert await conn.fetchval(
            "SELECT COUNT(*) FROM plaid_accounts WHERE item_id IN (SELECT item_id FROM plaid_items WHERE user_id=$1)",
            first,
        ) == 4
        assert await conn.fetchval(
            """SELECT COUNT(*) FROM transactions WHERE account_id IN
               (SELECT account_id FROM plaid_accounts WHERE item_id IN
                (SELECT item_id FROM plaid_items WHERE user_id=$1))""", first,
        ) == 12
