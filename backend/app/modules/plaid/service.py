
"""Plaid business logic: link token, token exchange (encrypt + store), list,
disconnect. All DB access is tenant-scoped via db.with_tenant (RLS enforced).
Access tokens are encrypted at rest and only decrypted in-memory for API calls.
"""
from __future__ import annotations

from typing import Any

from app import db
from app.audit import audit
from app.encryption import decrypt, encrypt
from app.errors import ApiError
from app.integrations.plaid_client import get_plaid
from app.logging_conf import logger

from .dedup import split_accounts
from .sync import to_money
from .worker import enqueue_sync


async def create_link_token(user_id: str, environment: str = "sandbox") -> dict[str, Any]:
    plaid = get_plaid(environment)
    result = await plaid.create_link_token(user_id)
    await audit("plaid.link_token_created", user_id=user_id, resource="plaid_item")
    return {"link_token": result["link_token"], "expiration": result.get("expiration")}


async def _discard_plaid_item(plaid: Any, access_token: str) -> None:
    """Supprime chez Plaid un Item rejeté, sans masquer l'erreur principale."""
    try:
        await plaid.item_remove(access_token)
    except ApiError as err:
        logger.warning(
            "plaid item_remove failed for rejected duplicate",
            error_message=str(err),
        )


async def exchange_public_token(
    user_id: str,
    tenant_id: str,
    public_token: str,
    ip: str | None,
    environment: str = "sandbox",
) -> dict[str, Any]:
    plaid = get_plaid(environment)

    exchanged = await plaid.exchange_public_token(public_token)
    access_token: str = exchanged["access_token"]
    plaid_item_id: str = exchanged["item_id"]

    item_info = await plaid.get_item(access_token)
    institution_id = (item_info.get("item") or {}).get("institution_id")

    accounts_resp = await plaid.get_accounts(access_token)
    accounts = accounts_resp.get("accounts", [])

    token_enc = encrypt(access_token, aad=user_id)

    item_id = None
    new_accounts: list[dict[str, Any]] = accounts
    skipped = 0

    async with db.with_tenant(tenant_id) as conn:
        # Sérialise les liaisons simultanées d'un même utilisateur.
        await conn.execute(
            "SELECT pg_advisory_xact_lock(hashtext($1::text))",
            f"plaid_link:{user_id}",
        )

        existing = await conn.fetch(
            """SELECT a.plaid_account_id, a.persistent_account_id, a.mask,
                      a.type, a.subtype, a.name, i.institution_id
                 FROM plaid_accounts a
                 JOIN plaid_items i ON i.item_id = a.item_id
                WHERE i.user_id = $1 AND i.environment = $2""",
            user_id,
            environment,
        )

        new_accounts, dup_accounts = split_accounts(
            [dict(r) for r in existing],
            accounts,
            institution_id,
        )
        skipped = len(dup_accounts)

        if not (accounts and not new_accounts):
            item_id = await conn.fetchval(
                """INSERT INTO plaid_items
                       (user_id, tenant_id, plaid_item_id, access_token_enc,
                        item_status, institution_id, environment)
                   VALUES ($1, $2, $3, $4, 'good', $5, $6)
                   ON CONFLICT (plaid_item_id) DO UPDATE
                       SET access_token_enc = EXCLUDED.access_token_enc,
                           item_status = 'good',
                           institution_id = EXCLUDED.institution_id,
                           environment = EXCLUDED.environment
                   RETURNING item_id""",
                user_id,
                tenant_id,
                plaid_item_id,
                token_enc,
                institution_id,
                environment,
            )

            for acc in new_accounts:
                bal = acc.get("balances") or {}

                await conn.execute(
                    """INSERT INTO plaid_accounts
                           (item_id, tenant_id, plaid_account_id, name,
                            official_name, type, subtype, mask,
                            persistent_account_id, balance_current,
                            balance_available, balance_limit, currency_code,
                            synced_at)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,NOW())
                       ON CONFLICT (plaid_account_id) DO UPDATE
                           SET balance_current = EXCLUDED.balance_current,
                               balance_available = EXCLUDED.balance_available,
                               balance_limit = EXCLUDED.balance_limit,
                               mask = EXCLUDED.mask,
                               persistent_account_id = EXCLUDED.persistent_account_id,
                               synced_at = NOW()""",
                    item_id,
                    tenant_id,
                    acc["account_id"],
                    acc.get("name"),
                    acc.get("official_name"),
                    acc.get("type"),
                    acc.get("subtype"),
                    acc.get("mask"),
                    acc.get("persistent_account_id"),
                    to_money(bal.get("current")),
                    to_money(bal.get("available")),
                    to_money(bal.get("limit")),
                    bal.get("iso_currency_code") or "USD",
                )

    if item_id is None:
        # Appel réseau hors transaction : on libère l'Item créé chez Plaid.
        await _discard_plaid_item(plaid, access_token)

        await audit(
            "plaid.link_duplicate_rejected",
            user_id=user_id,
            tenant_id=tenant_id,
            resource="plaid_item",
            ip_address=ip,
            metadata={
                "institution_id": institution_id,
                "accounts": len(accounts),
            },
        )

        raise ApiError("CONFLICT", message="This bank is already linked.")

    await audit(
        "plaid.item_linked",
        user_id=user_id,
        tenant_id=tenant_id,
        resource="plaid_item",
        resource_id=str(item_id),
        ip_address=ip,
        metadata={
            "institution_id": institution_id,
            "accounts": len(new_accounts),
            "skipped": skipped,
        },
    )

    await enqueue_sync(str(item_id), tenant_id, user_id)

    return {
        "item_id": str(item_id),
        "institution_name": None,
        "accounts_linked": len(new_accounts),
        "accounts_skipped": skipped,
    }


async def list_items(user_id: str, tenant_id: str) -> list[dict[str, Any]]:
    # Single query (LEFT JOIN) instead of N+1 (one accounts fetch per item):
    # items and their accounts come back in one round-trip, then grouped in-app.
    # ORDER BY keeps items newest-first and accounts stable within each item.
    async with db.with_tenant(tenant_id) as conn:
        rows = await conn.fetch(
            """SELECT i.item_id, i.institution_name, i.item_status, i.last_sync_at,
                      a.account_id, a.name AS account_name, a.type AS account_type,
                      a.subtype, a.balance_current, a.currency_code
                 FROM plaid_items i
                 LEFT JOIN plaid_accounts a ON a.item_id = i.item_id
                WHERE i.user_id = $1
                ORDER BY i.created_at DESC, a.created_at""",
            user_id,
        )

    result: list[dict[str, Any]] = []
    by_item: dict[Any, dict[str, Any]] = {}

    for r in rows:
        item = by_item.get(r["item_id"])

        if item is None:
            item = {
                "item_id": str(r["item_id"]),
                "institution_name": r["institution_name"],
                "item_status": r["item_status"],
                "last_sync_at": r["last_sync_at"],
                "accounts": [],
            }
            by_item[r["item_id"]] = item
            result.append(item)

        # LEFT JOIN yields a null account row for items with no accounts yet.
        if r["account_id"] is not None:
            item["accounts"].append(
                {
                    "account_id": str(r["account_id"]),
                    "name": r["account_name"],
                    "type": r["account_type"],
                    "subtype": r["subtype"],
                    "balance_current": r["balance_current"],
                    "currency_code": r["currency_code"],
                }
            )

    return result


async def disconnect_item(
    user_id: str,
    tenant_id: str,
    item_id: str,
    ip: str | None,
) -> None:
    async with db.with_tenant(tenant_id) as conn:
        row = await conn.fetchrow(
            """SELECT access_token_enc, environment
                 FROM plaid_items
                WHERE item_id = $1 AND user_id = $2""",
            item_id,
            user_id,
        )

        if not row:
            raise ApiError("NOT_FOUND")

    # Best-effort revoke at Plaid, then delete locally (cascade) regardless.
    if row["environment"] == "synthetic":
        raise ApiError(
            "CONFLICT",
            message="Synthetic demo accounts are managed by the development seed command.",
        )

    try:
        access_token = decrypt(bytes(row["access_token_enc"]), aad=user_id)
        await get_plaid(row["environment"]).item_remove(access_token)
    except ApiError as err:
        logger.warning(
            "plaid item_remove failed; deleting locally anyway",
            error_message=str(err),
        )

    async with db.with_tenant(tenant_id) as conn:
        await conn.execute(
            "DELETE FROM plaid_items WHERE item_id = $1 AND user_id = $2",
            item_id,
            user_id,
        )

    await audit(
        "plaid.item_disconnected",
        user_id=user_id,
        tenant_id=tenant_id,
        resource="plaid_item",
        resource_id=item_id,
        ip_address=ip,
    )
