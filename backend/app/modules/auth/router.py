"""Auth HTTP routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app import db
from app.config import settings
from app.deps import CurrentUser, rate_limit, require_auth, resolve_tenant
from app.errors import ApiError

from . import service
from .mailer import extract_magic_link_token, peek_last_mail_to
from .modes import require_magic_link_mode, require_password_mode
from .schemas import (
    AuthConfigResponse,
    ForgotPasswordRequest,
    GoogleAuthRequest,
    LoginRequest,
    MagicLinkRequest,
    MeResponse,
    MessageResponse,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    TokenResponse,
)
from .service import AuthCtx

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

REFRESH_COOKIE = "refresh_token"

MAGIC_LINK_MESSAGE = "If an account exists for this email, a sign-in link has been sent."


def _ctx(request: Request) -> AuthCtx:
    return AuthCtx(
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        httponly=True,
        secure=settings.is_prod,
        samesite="strict",
        domain=settings.cookie_domain,
        path="/api/v1/auth",
        max_age=settings.refresh_token_ttl,
    )


@router.get("/config", response_model=AuthConfigResponse)
async def auth_config() -> AuthConfigResponse:
    return AuthConfigResponse(auth_mode=settings.auth_mode)


@router.post("/signup", response_model=SignupResponse, status_code=201,
             dependencies=[Depends(rate_limit("auth_signup", 10)), Depends(require_password_mode)])
async def signup(body: SignupRequest, request: Request, tenant_id: str = Depends(resolve_tenant)) -> SignupResponse:
    user_id = await service.signup(
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        tenant_id=tenant_id,
        captcha_token=body.captcha_token,
        ctx=_ctx(request),
    )
    return SignupResponse(user_id=user_id)


@router.post("/login", response_model=TokenResponse,
             dependencies=[Depends(rate_limit("auth_login", 20)), Depends(require_password_mode)])
async def login(body: LoginRequest, request: Request, response: Response,
                tenant_id: str = Depends(resolve_tenant)) -> TokenResponse:
    pair = await service.login(
        email=body.email,
        password=body.password,
        tenant_id=tenant_id,
        captcha_token=body.captcha_token,
        ctx=_ctx(request),
    )
    _set_refresh_cookie(response, pair.refresh_token)
    return TokenResponse(access_token=pair.access_token, user_id=pair.user_id)


@router.post("/magic-link", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("auth_magic_link", 5)), Depends(require_magic_link_mode)])
async def magic_link(body: MagicLinkRequest, request: Request,
                     tenant_id: str = Depends(resolve_tenant)) -> MessageResponse:
    await service.request_magic_link(
        email=body.email, tenant_id=tenant_id, captcha_token=body.captcha_token, ctx=_ctx(request)
    )
    return MessageResponse(message=MAGIC_LINK_MESSAGE)


@router.get("/verify-email", response_model=TokenResponse,
            dependencies=[Depends(rate_limit("auth_verify", 30))])
async def verify_email(token: str, request: Request, response: Response) -> TokenResponse:
    pair = await service.verify_email(token, _ctx(request))
    _set_refresh_cookie(response, pair.refresh_token)
    return TokenResponse(access_token=pair.access_token, user_id=pair.user_id)


@router.post("/google", response_model=TokenResponse,
             dependencies=[Depends(rate_limit("auth_google", 20))])
async def google(body: GoogleAuthRequest, request: Request, response: Response,
                 tenant_id: str = Depends(resolve_tenant)) -> TokenResponse:
    pair = await service.google_auth(id_token=body.id_token, tenant_id=tenant_id, ctx=_ctx(request))
    _set_refresh_cookie(response, pair.refresh_token)
    return TokenResponse(access_token=pair.access_token, user_id=pair.user_id)


@router.post("/resend-verification", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("auth_resend", 3)), Depends(require_password_mode)])
async def resend_verification(body: ResendVerificationRequest, request: Request,
                              tenant_id: str = Depends(resolve_tenant)) -> MessageResponse:
    await service.resend_verification(
        email=body.email, tenant_id=tenant_id, captcha_token=body.captcha_token, ctx=_ctx(request)
    )
    return MessageResponse(message="If an unverified account exists for this email, a new link has been sent.")


@router.post("/forgot-password", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("auth_forgot", 5)), Depends(require_password_mode)])
async def forgot_password(body: ForgotPasswordRequest, request: Request,
                          tenant_id: str = Depends(resolve_tenant)) -> MessageResponse:
    await service.request_password_reset(
        email=body.email, tenant_id=tenant_id, captcha_token=body.captcha_token, ctx=_ctx(request)
    )
    return MessageResponse(message="If an account exists for this email, a reset link has been sent.")


@router.post("/reset-password", response_model=MessageResponse,
             dependencies=[Depends(rate_limit("auth_reset_pw", 10)), Depends(require_password_mode)])
async def reset_password(body: ResetPasswordRequest, request: Request) -> MessageResponse:
    await service.reset_password(body.token, body.password, _ctx(request))
    return MessageResponse(message="Password updated. You can now log in.")


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: Request, response: Response) -> TokenResponse:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise ApiError("UNAUTHORIZED")
    pair = await service.refresh(raw, _ctx(request))
    _set_refresh_cookie(response, pair.refresh_token)
    return TokenResponse(access_token=pair.access_token, user_id=pair.user_id)


@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response) -> MessageResponse:
    await service.logout(request.cookies.get(REFRESH_COOKIE))
    response.delete_cookie(REFRESH_COOKIE, path="/api/v1/auth", domain=settings.cookie_domain)
    return MessageResponse(message="Logged out.")


@router.get("/me", response_model=MeResponse,
            dependencies=[Depends(rate_limit("read", settings.rate_limit_read_per_min))])
async def me(user: CurrentUser = Depends(require_auth)) -> MeResponse:
    async with db.with_tenant(user.tenant_id, user.user_id) as conn:
        row = await conn.fetchrow(
            """SELECT user_id, email, full_name, tier, advisor_persona, is_verified, onboarding_step, is_demo
                 FROM users WHERE user_id = $1""",
            user.user_id,
        )
    if not row:
        raise ApiError("NOT_FOUND")
    return MeResponse(
        user_id=str(row["user_id"]),
        email=row["email"],
        full_name=row["full_name"],
        tier=row["tier"],
        advisor_persona=row["advisor_persona"],
        is_verified=row["is_verified"],
        onboarding_step=row["onboarding_step"],
        is_demo=row["is_demo"],
    )


@router.get("/dev/peek-magic-link", include_in_schema=False,
            dependencies=[Depends(require_magic_link_mode)])
async def dev_peek_magic_link(email: str) -> dict[str, str]:
    if settings.is_prod:
        raise ApiError("NOT_FOUND")
    mail = peek_last_mail_to(email)
    if mail is None:
        raise ApiError("NOT_FOUND", message="No magic link found for this email.")
    token = extract_magic_link_token(mail)
    if token is None:
        raise ApiError("NOT_FOUND", message="Could not parse magic link token.")
    return {"token": token}
