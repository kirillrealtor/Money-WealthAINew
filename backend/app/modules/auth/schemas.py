"""Pydantic request/response models for the auth API."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SignupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    full_name: str | None = Field(default=None, max_length=255)
    captcha_token: str | None = None


class SignupResponse(BaseModel):
    user_id: str
    message: str = "Account created. Check your email to verify."


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=200)
    captcha_token: str | None = None


class MagicLinkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    captcha_token: str | None = None


class GoogleAuthRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id_token: str = Field(min_length=1, max_length=8192)


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    captcha_token: str | None = None


class ForgotPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    captcha_token: str | None = None


class ResetPasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    user_id: str


class MessageResponse(BaseModel):
    message: str


class AuthConfigResponse(BaseModel):
    auth_mode: Literal["password", "magic_link"]


class MeResponse(BaseModel):
    is_demo: bool = False
    user_id: str
    email: EmailStr
    full_name: str | None
    tier: str
    advisor_persona: str
    is_verified: bool
    onboarding_step: int
