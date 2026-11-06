"""Gemini provider — OpenAI-compatible tool-calling loop behind the same
AdvisorProvider interface as Claude.
"""
from __future__ import annotations

import json
from typing import Any

from openai import APIError, AsyncOpenAI

from app.config import settings
from app.errors import ApiError
from app.logging_conf import logger

from .provider import AdvisorResult, ToolExecutor

_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        if not settings.gemini_configured:
            raise ApiError("AI_UNAVAILABLE")
        # Keep upstream outages inside the MCP turn deadline. The UI can offer a
        # retry instead of hiding multiple long SDK retries behind one request.
        self._client = AsyncOpenAI(api_key=settings.gemini_api_key, base_url=_GEMINI_BASE_URL,
                                   timeout=30, max_retries=0)
        self._model = settings.gemini_model

    async def run(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        execute_tool: ToolExecutor,
    ) -> AdvisorResult:
        oai_tools = [
            {"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": t["input_schema"]}}
            for t in tools
        ]
        convo: list[dict[str, Any]] = [{"role": "system", "content": system}, *messages]
        tool_calls: list[str] = []
        in_tok = out_tok = 0

        for _round in range(settings.advisor_max_tool_rounds + 1):
            try:
                resp = await self._client.chat.completions.create(
                    model=self._model, messages=convo, tools=oai_tools,  # type: ignore[arg-type]
                    max_tokens=settings.advisor_max_tokens,
                )
            except APIError as error:
                # Model retirement, quota denials and network failures should produce
                # a clear unavailable response. Never log SDK bodies: they can echo
                # request contents or credentials into the shared provider logs.
                logger.warning("gemini provider unavailable", service="ai-advisor",
                               status_code=getattr(error, "status_code", None))
                raise ApiError("AI_UNAVAILABLE") from None
            if resp.usage:
                in_tok += resp.usage.prompt_tokens
                out_tok += resp.usage.completion_tokens
            msg = resp.choices[0].message

            if not msg.tool_calls:
                return AdvisorResult(
                    text=msg.content or "", provider=self.name, model=self._model,
                    tool_calls_made=tool_calls, input_tokens=in_tok, output_tokens=out_tok,
                )

            convo.append({
                "role": "assistant", "content": msg.content or "",
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            })
            for tc in msg.tool_calls:
                tool_calls.append(tc.function.name)
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                content, _is_error = await execute_tool(tc.function.name, args)
                convo.append({"role": "tool", "tool_call_id": tc.id, "content": content})

        logger.warning("gemini tool rounds exhausted", service="ai-advisor", tool_calls=tool_calls)
        return AdvisorResult(
            text="I wasn't able to complete that analysis. Could you rephrase or narrow the question?",
            provider=self.name, model=self._model, tool_calls_made=tool_calls,
            input_tokens=in_tok, output_tokens=out_tok,
        )
