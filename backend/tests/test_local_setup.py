"""Verify configuration preservation and development-only seeding without external services."""
from __future__ import annotations

import base64
import runpy
from pathlib import Path
from typing import Any

import pytest
from dotenv import dotenv_values

from app.config import settings
from scripts.seed_demo import seed


def test_bootstrap_generates_secrets_once_and_preserves_existing_values(tmp_path: Path) -> None:
    script = Path(__file__).resolve().parents[2] / "scripts" / "bootstrap_env.py"
    namespace = runpy.run_path(str(script))
    configure: Any = namespace["configure_backend"]
    configure.__globals__["ROOT"] = tmp_path
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".env.example").write_text("JWT_ACCESS_SECRET=placeholder\nPLAID_ENC_KEY=\n", encoding="utf-8")
    configure()
    target = backend / ".env"
    first = target.read_bytes()
    values = dotenv_values(target)
    assert len(values["JWT_ACCESS_SECRET"] or "") >= 32
    assert len(base64.b64decode(values["PLAID_ENC_KEY"] or "")) == 32
    assert values["ADVISOR_PROVIDER"] == "mock"
    configure()
    assert target.read_bytes() == first
    target.write_text(target.read_text() + "\nPAYPAL_CLIENT_ID=keep-this-test-value\n", encoding="utf-8")
    (backend / ".env.example").write_text("PAYPAL_CLIENT_ID=replacement\nNEW_SETTING=new\n", encoding="utf-8")
    configure()
    values = dotenv_values(target)
    assert values["PAYPAL_CLIENT_ID"] == "keep-this-test-value"
    assert values["NEW_SETTING"] == "new"


async def test_seed_refuses_production_before_writing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "env", "production")
    with pytest.raises(RuntimeError, match="local database"):
        await seed()


async def test_seed_refuses_remote_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "env", "development")
    monkeypatch.setattr(settings, "database_url", "postgres://user:password@remote.example.com/wealth")
    with pytest.raises(RuntimeError, match="local database"):
        await seed()
