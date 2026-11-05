"""Standardized error contract (Architecture / blueprint 20.3).

Every error across every endpoint returns this exact shape so API consumers -
including white-label partners - get no surprises.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from app.context import get_trace_id

API_ERRORS: dict[str, dict[str, Any]] = {
    "MCP_UNAVAILABLE": {"status": 503, "message": "Financial tools are temporarily unavailable. Please retry."},
    "PAYPAL_UNAVAILABLE": {"status": 503, "message": "PayPal sandbox is not configured."},
    "PAYPAL_ERROR": {"status": 502, "message": "PayPal could not confirm this request. Retry shortly."},
    "UNAUTHORIZED": {"status": 401, "message": "Invalid or expired authentication token."},
    "FORBIDDEN": {"status": 403, "message": "You do not have permission to access this resource."},
    "CAPTCHA_REQUIRED": {"status": 403, "message": "Captcha verification is required or failed."},
    "NOT_FOUND": {"status": 404, "message": "The requested resource does not exist."},
    "CONFLICT": {"status": 409, "message": "The resource already exists."},
    "VALIDATION_ERROR": {"status": 422, "message": "Request validation failed. See details."},
    "PAYLOAD_TOO_LARGE": {"status": 413, "message": "Request body exceeds the maximum allowed size."},
    "RATE_LIMITED": {"status": 429, "message": "Too many requests. See Retry-After header."},
    "AI_UNAVAILABLE": {"status": 503, "message": "AI provider temporarily unavailable. Retry in 60s."},
    "SERVICE_BUSY": {"status": 503, "message": "Service is busy. Please retry shortly."},
    "PLAID_ERROR": {"status": 502, "message": "Banking data provider returned an error."},
    "BILLING_UNAVAILABLE": {"status": 503, "message": "Billing is not configured. Try again later."},
    "INTERNAL_ERROR": {"status": 500, "message": "An unexpected error occurred. Reference request_id in support."},
}


class ApiError(Exception):
    """Throwable error carrying an API error type; caught by the global handler."""

    def __init__(self, code: str, details: Any | None = None, message: str | None = None) -> None:
        self.code = code
        self.details = details
        self.message = message or API_ERRORS[code]["message"]
        super().__init__(self.message)


def error_payload(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": get_trace_id()}
    if details is not None:
        body["details"] = details
    return body


def error_response(code: str, details: Any | None = None, headers: dict[str, str] | None = None) -> JSONResponse:
    spec = API_ERRORS[code]
    return JSONResponse(
        status_code=spec["status"],
        content=error_payload(code, spec["message"], details),
        headers=headers,
    )


def register_exception_handlers(app: Any) -> None:
    from fastapi.exceptions import RequestValidationError

    @app.exception_handler(ApiError)
    async def _api_error_handler(_req: Request, exc: ApiError) -> JSONResponse:
        spec = API_ERRORS[exc.code]
        return JSONResponse(
            status_code=spec["status"],
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_req: Request, exc: RequestValidationError) -> JSONResponse:
        # SECURITY: Pydantic includes the raw `input` (and `url`/`ctx`) in each
        # error — for a password field that would echo the password back to the
        # client and into logs. Return only the field location, type, and message.
        safe = [
            {"loc": e.get("loc"), "type": e.get("type"), "msg": e.get("msg")}
            for e in exc.errors()
        ]
        return error_response("VALIDATION_ERROR", details=safe)

    @app.exception_handler(Exception)
    async def _unhandled_handler(_req: Request, exc: Exception) -> JSONResponse:
        from app.logging_conf import logger

        logger.error("unhandled error", service="api", error_type="UNHANDLED", error_message=str(exc))
        return error_response("INTERNAL_ERROR")
