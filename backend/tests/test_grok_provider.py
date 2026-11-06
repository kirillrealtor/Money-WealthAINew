"""Provider failures are simulated; these tests never call xAI or consume credits."""
from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from openai import APIConnectionError, PermissionDeniedError, RateLimitError

from app.ai.grok_provider import GrokProvider
from app.config import settings
from app.errors import ApiError


@pytest.mark.parametrize("failure", ["forbidden", "rate_limit", "connection"])
async def test_grok_outage_is_sanitized(
    failure: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
) -> None:
    # Deliberately put a fake secret in the SDK error to prove neither API nor logs echo it.
    secret = "xai-test-secret-must-not-be-logged"
    request = httpx.Request("POST", "https://api.x.ai/v1/chat/completions")
    if failure == "forbidden":
        error = PermissionDeniedError(secret, response=httpx.Response(403, request=request), body=None)
    elif failure == "rate_limit":
        error = RateLimitError(secret, response=httpx.Response(429, request=request), body=None)
    else:
        error = APIConnectionError(message=secret, request=request)
    monkeypatch.setattr(settings, "grok_api_key", "xai-placeholder-for-offline-test")
    provider = GrokProvider()
    monkeypatch.setattr(provider._client.chat.completions, "create", AsyncMock(side_effect=error))
    execute = AsyncMock()
    try:
        with pytest.raises(ApiError) as caught:
            await provider.run(system="test", messages=[{"role": "user", "content": "test"}],
                               tools=[], execute_tool=execute)
        assert caught.value.code == "AI_UNAVAILABLE"
        assert secret not in str(caught.value)
        assert secret not in capsys.readouterr().out
        execute.assert_not_called()
    finally:
        await provider._client.close()
