"""Détection des comptes Plaid déjà liés (doublons) pour un même utilisateur."""
from __future__ import annotations

from typing import Any


def _norm(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip().lower()


def is_same_account(existing: dict[str, Any], incoming: dict[str, Any], institution_id: str | None) -> bool:
    # Même plaid_account_id = rejeu du même lien : géré par ON CONFLICT, pas un doublon.
    if existing.get("plaid_account_id") == incoming.get("account_id"):
        return False

    new_pid, old_pid = incoming.get("persistent_account_id"), existing.get("persistent_account_id")
    if new_pid and old_pid:
        return new_pid == old_pid  # identifiant stable : décisif dans les deux sens

    # Repli : on ne bloque que si tout est connu des deux côtés (jamais de faux positif).
    if not institution_id or existing.get("institution_id") != institution_id:
        return False
    new_mask, old_mask = _norm(incoming.get("mask")), _norm(existing.get("mask"))
    if not new_mask or not old_mask:
        return False
    return (
        new_mask == old_mask
        and _norm(incoming.get("type")) == _norm(existing.get("type"))
        and _norm(incoming.get("subtype")) == _norm(existing.get("subtype"))
        and _norm(incoming.get("name")) == _norm(existing.get("name"))
    )


def split_accounts(
    existing: list[dict[str, Any]], incoming: list[dict[str, Any]], institution_id: str | None
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Retourne (nouveaux, doublons)."""
    new: list[dict[str, Any]] = []
    dups: list[dict[str, Any]] = []
    for acc in incoming:
        if any(is_same_account(e, acc, institution_id) for e in existing):
            dups.append(acc)
        else:
            new.append(acc)
    return new, dups