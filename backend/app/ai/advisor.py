"""Advisor turn orchestration: safety -> grounded agentic loop ->
validation -> persistence -> usage accounting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app import db
from app.audit import audit
from app.errors import ApiError
from app.logging_conf import logger

from .budget import record_usage
from .health import record_validation_failure
from .mcp_client import financial_mcp
from .prompts import PROMPT_VERSION, build_system_prompt
from .provider import AdvisorProvider, get_provider
from .safety import CRISIS_RESPONSE, detect_crisis, detect_jailbreak, sanitize_input
from .validator import CORRECTION_INSTRUCTION, validate_output

_REFUSAL = (
    "I can help with educational analysis of your finances, but I can't act on that request. "
    "Ask me about your budget, cash flow, balances, or goals and I'll dig in."
)
_FALLBACK = (
    "I'm having trouble giving a safe, grounded answer to that right now. Could you rephrase, "
    "or ask about a specific part of your finances?"
)


@dataclass
class TurnResult:
    chat_id: str
    message_id: str
    response: str
    tool_calls_made: list[str]
    provider: str
    tokens_used: int


async def run_turn(
    *,
    user_id: str,
    tenant_id: str,
    first_name: str | None,
    persona: str,
    tier: str,
    chat_id: str | None,
    message: str,
    module: str | None,
    ip: str | None = None,
    provider: AdvisorProvider | None = None,
) -> TurnResult:
    # 1. Input safety (prompt injection / length).
    san = sanitize_input(message)
    if not san.safe:
        await audit("ai.input_rejected", user_id=user_id, tenant_id=tenant_id, ip_address=ip,
                    metadata={"reason": san.reason})
        raise ApiError("VALIDATION_ERROR", message="Your message could not be processed.")

    chat_id = await _ensure_chat(user_id, tenant_id, chat_id, module)

    # 2. Crisis protocol — bypass the LLM entirely (no budget consumed).
    if detect_crisis(message):
        mid = await _persist(chat_id, tenant_id, message, CRISIS_RESPONSE, provider="crisis_protocol", tokens=0)
        await audit("ai.crisis_protocol", user_id=user_id, tenant_id=tenant_id)
        return TurnResult(chat_id, mid, CRISIS_RESPONSE, [], "crisis_protocol", 0)

    # 3. Jailbreak classifier (cheap, gated) — refuse before calling the LLM.
    if await detect_jailbreak(message):
        mid = await _persist(chat_id, tenant_id, message, _REFUSAL, provider="refused", tokens=0)
        await audit("ai.jailbreak_refused", user_id=user_id, tenant_id=tenant_id)
        return TurnResult(chat_id, mid, _REFUSAL, [], "refused", 0)

    # 4. Grounded agentic loop. Usage is recorded after a successful turn.
    # 5. Build context: history + live snapshot + persona/compliance system prompt.
    history = await _load_history(chat_id, tenant_id)
    # One private MCP subprocess per turn binds identity once, before any model-generated tool inputs exist.
    async with financial_mcp(user_id, tenant_id) as mcp:
        snapshot = await mcp.snapshot()
        system = build_system_prompt(first_name=first_name, persona=persona, snapshot=snapshot)
        if snapshot.is_demo_data:
            system += ("\nThis profile uses synthetic demonstration finances, "
                       "not a real Plaid connection. Say so clearly.")
        messages: list[dict[str, Any]] = [*history, {"role": "user", "content": message}]

        prov = provider or get_provider()

        # 6. Run the grounded agentic loop.
        result = await prov.run(system=system, messages=messages, tools=mcp.tools, execute_tool=mcp.execute)
        # Grounding evidence comes from completed MCP calls, not the provider's claims about attempted calls.
        result.tool_calls_made = list(mcp.successful_calls)

        # 7. Validate; retry once with a correction, else safe fallback.
        final_text = result.text
        val = validate_output(final_text, tool_calls_made=result.tool_calls_made)
        if not val.valid:
            logger.warning("advisor output rejected", service="ai-advisor", reason=val.reason)
            await record_validation_failure()
            await audit("ai.output_rejected", user_id=user_id, tenant_id=tenant_id, metadata={"reason": val.reason})
            retry_msgs = [*messages, {"role": "user", "content": CORRECTION_INSTRUCTION.format(reason=val.reason)}]
            retry = await prov.run(
                system=system, messages=retry_msgs, tools=mcp.tools, execute_tool=mcp.execute
            )
            result.input_tokens += retry.input_tokens
            result.output_tokens += retry.output_tokens
            result.tool_calls_made = list(mcp.successful_calls)
            retry_ok = validate_output(retry.text, tool_calls_made=result.tool_calls_made).valid
            final_text = retry.text if retry_ok else _FALLBACK

    # 8. Persist the turn and record usage.
    mid = await _persist(chat_id, tenant_id, message, final_text, provider=result.provider,
                         tokens=result.total_tokens, model=result.model)
    logger.info("advisor turn complete", service="ai-advisor", provider=result.provider,
                input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                tool_calls=result.tool_calls_made)
    await record_usage(user_id, tenant_id, result.total_tokens, result.provider)
    return TurnResult(chat_id, mid, final_text, result.tool_calls_made, result.provider, result.total_tokens)


# --------------------------------------------------------------------------
# Persistence (chat_sessions / chat_messages are user-scoped, not RLS tables)
# --------------------------------------------------------------------------
async def _ensure_chat(user_id: str, tenant_id: str, chat_id: str | None, module: str | None) -> str:
    async with db.with_tenant(tenant_id) as conn:
        if chat_id:
            owner = await conn.fetchval("SELECT user_id FROM chat_sessions WHERE chat_id = $1", chat_id)
            if owner is None:
                raise ApiError("NOT_FOUND")
            if str(owner) != user_id:  # RLS scopes the tenant; this scopes the user within it
                raise ApiError("FORBIDDEN")
            return chat_id
        return str(await conn.fetchval(
            "INSERT INTO chat_sessions (user_id, tenant_id, module) VALUES ($1, $2, $3) RETURNING chat_id",
            user_id, tenant_id, module,
        ))


async def _load_history(chat_id: str, tenant_id: str) -> list[dict[str, Any]]:
    from app.config import settings

    async with db.with_tenant(tenant_id) as conn:
        rows = await conn.fetch(
            """SELECT role, content FROM chat_messages
                WHERE chat_id = $1 AND role IN ('user', 'assistant')
                ORDER BY created_at DESC LIMIT $2""",
            chat_id, settings.advisor_history_turns * 2,
        )
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


async def _persist(
    chat_id: str, tenant_id: str, user_message: str, assistant_message: str,
    *, provider: str, tokens: int, model: str | None = None,
) -> str:
    async with db.with_tenant(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO chat_messages (chat_id, tenant_id, role, content) VALUES ($1, $2, 'user', $3)",
            chat_id, tenant_id, user_message,
        )
        return str(await conn.fetchval(
            """INSERT INTO chat_messages (chat_id, tenant_id, role, content, provider, prompt_version, tokens_used)
               VALUES ($1, $2, 'assistant', $3, $4, $5, $6) RETURNING message_id""",
            chat_id, tenant_id, assistant_message, provider, PROMPT_VERSION, tokens,
        ))
