"""Provide valid env so app.config passes validation under tests.

Defaults match the local docker-compose datastores (Postgres :5433 as the
non-owner app_user, Redis :6380). Integration tests use these; unit tests never
open a connection.
"""
from __future__ import annotations

import base64
import os

os.environ.setdefault("ENV", "test")
# Local setup defaults to a simulated provider. Tests must not inherit that
# choice (or paid API credentials) from a developer's .env file.
os.environ.setdefault("ADVISOR_PROVIDER", "auto")
for _provider_key in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "GROK_API_KEY", "GEMINI_API_KEY"):
    os.environ.setdefault(_provider_key, "")
os.environ.setdefault("DATABASE_URL", "postgres://app_user:app_user@localhost:5433/financial_advisor")
os.environ.setdefault("MIGRATION_DATABASE_URL", "postgres://advisor:advisor@localhost:5433/financial_advisor")
os.environ.setdefault("REDIS_URL", "redis://127.0.0.1:6380")
os.environ.setdefault("JWT_ACCESS_SECRET", "test_access_secret_at_least_32_chars_long_000")
os.environ.setdefault("JWT_REFRESH_SECRET", "test_refresh_secret_at_least_32_chars_long_00")
# AES-256 key (base64 of exactly 32 bytes) for Plaid token-encryption tests.
os.environ.setdefault("PLAID_ENC_KEY", base64.b64encode(b"test-key-32-bytes-long-aes256!!!").decode())
