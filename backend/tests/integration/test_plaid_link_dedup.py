"""Lien Plaid : doublons bloqués, comptes légitimes acceptés, re-sync propre.
Plaid est simulé ; Postgres et Redis sont réels (locaux)."""
from __future__ import annotations

import time

import httpx
import pytest

import app.modules.plaid.service as service
import app.modules.plaid.sync as syncmod
from app import db
from app.config import settings
from app.errors import ApiError
from app.modules.plaid.sync import run_sync_for_item
from tests.integration.auth_helpers import create_user_via_magic_link
from tests.integration.conftest import _db_reachable

pytestmark = pytest.mark.skipif(not _db_reachable(), reason="Postgres not reachable on localhost:5433")
TENANT = settings.default_tenant_id
INS = "ins_test_dedup"


def _acc(aid, mask, name="Checking", typ="depository", sub="checking"):
    return {"account_id": aid, "mask": mask, "name": name, "official_name": name, "type": typ,
            "subtype": sub, "balances": {"current": 100.0, "available": 100.0, "limit": None,
                                         "iso_currency_code": "USD"}}


class FakePlaid:
    def __init__(self, item_id, accounts):
        self.item_id, self.accounts, self.removed = item_id, accounts, []

    async def exchange_public_token(self, public_token):
        return {"access_token": f"access-{self.item_id}", "item_id": self.item_id}

    async def get_item(self, token):
        return {"item": {"institution_id": INS}}

    async def get_accounts(self, token):
        return {"accounts": self.accounts}

    async def item_remove(self, token):
        self.removed.append(token)
        return {}

    async def transactions_sync(self, token, cursor, count=500):
        if cursor is not None:
            return {"added": [], "modified": [], "removed": [], "has_more": False, "next_cursor": cursor}
        aid = self.accounts[0]["account_id"]
        txs = [{"transaction_id": f"{aid}-tx{i}", "account_id": aid, "amount": 10.0 * i,
                "date": "2026-06-01", "name": "Shop", "pending": False} for i in (1, 2)]
        return {"added": txs, "modified": [], "removed": [], "has_more": False, "next_cursor": "end"}

    async def liabilities_get(self, token):
        return {"accounts": [], "liabilities": {}}

    async def investments_holdings_get(self, token):
        return {"accounts": [], "holdings": [], "securities": []}


async def _user(client) -> str:
    user_id, _ = await create_user_via_magic_link(client, f"dedup+{int(time.time()*1_000_000)}@example.com")
    return user_id


async def _link(monkeypatch, user_id, fake):
    async def _noop(*a, **kw):
        return None

    monkeypatch.setattr(service, "get_plaid", lambda *a, **kw: fake)
    monkeypatch.setattr(service, "enqueue_sync", _noop)
    return await service.exchange_public_token(user_id, TENANT, "public-x", None)


async def _counts(user_id) -> tuple[int, int]:
    async with db.with_tenant(TENANT) as conn:
        items = await conn.fetchval("SELECT count(*) FROM plaid_items WHERE user_id = $1", user_id)
        accts = await conn.fetchval(
            """SELECT count(*) FROM plaid_accounts
                WHERE item_id IN (SELECT item_id FROM plaid_items WHERE user_id = $1)""", user_id)
    return items, accts


async def test_new_bank_links_all_accounts(client: httpx.AsyncClient, monkeypatch) -> None:
    uid = await _user(client)
    res = await _link(monkeypatch, uid, FakePlaid(f"item1-{uid}", [_acc(f"{uid}-a", "0001"),
                                                                   _acc(f"{uid}-b", "0002", "Savings", sub="savings")]))
    assert res["accounts_linked"] == 2 and res["accounts_skipped"] == 0
    assert await _counts(uid) == (1, 2)


async def test_same_bank_again_is_rejected_and_cleaned_up(client: httpx.AsyncClient, monkeypatch) -> None:
    uid = await _user(client)
    await _link(monkeypatch, uid, FakePlaid(f"item1-{uid}", [_acc(f"{uid}-a", "0001")]))
    second = FakePlaid(f"item2-{uid}", [_acc(f"{uid}-a2", "0001")])  # nouveaux ids Plaid, même compte
    with pytest.raises(ApiError):
        await _link(monkeypatch, uid, second)
    assert len(second.removed) == 1          # Item orphelin supprimé chez Plaid
    assert await _counts(uid) == (1, 1)      # rien ajouté en base


async def test_same_bank_with_extra_account_adds_only_new(client: httpx.AsyncClient, monkeypatch) -> None:
    uid = await _user(client)
    await _link(monkeypatch, uid, FakePlaid(f"item1-{uid}", [_acc(f"{uid}-a", "0001")]))
    res = await _link(monkeypatch, uid, FakePlaid(
        f"item2-{uid}", [_acc(f"{uid}-a2", "0001"), _acc(f"{uid}-s2", "0002", "Savings", sub="savings")]))
    assert res["accounts_linked"] == 1 and res["accounts_skipped"] == 1
    assert await _counts(uid) == (2, 2)


async def test_distinct_account_same_institution_is_allowed(client: httpx.AsyncClient, monkeypatch) -> None:
    uid = await _user(client)
    await _link(monkeypatch, uid, FakePlaid(f"item1-{uid}", [_acc(f"{uid}-a", "0001")]))
    res = await _link(monkeypatch, uid, FakePlaid(f"item2-{uid}", [_acc(f"{uid}-c", "0002")]))
    assert res["accounts_linked"] == 1 and res["accounts_skipped"] == 0
    assert await _counts(uid) == (2, 2)


async def test_clean_single_link_resync_is_idempotent(client: httpx.AsyncClient, monkeypatch) -> None:
    uid = await _user(client)
    fake = FakePlaid(f"item1-{uid}", [_acc(f"{uid}-a", "0001")])
    res = await _link(monkeypatch, uid, fake)
    monkeypatch.setattr(syncmod, "get_plaid", lambda *a, **kw: fake)

    n1 = await run_sync_for_item(res["item_id"], TENANT, uid)
    n2 = await run_sync_for_item(res["item_id"], TENANT, uid)

    async with db.with_tenant(TENANT) as conn:
        tx = await conn.fetchval(
            """SELECT count(*) FROM transactions
                WHERE account_id IN (SELECT account_id FROM plaid_accounts WHERE item_id = $1)""",
            res["item_id"])
    assert (n1, n2, tx) == (2, 0, 2)