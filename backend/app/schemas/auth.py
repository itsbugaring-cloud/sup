"""
app/schemas/auth.py
──────────────────────────────────────────────────────────────────────────────
Pydantic schemas for authentication (login, tokens, current user).
"""

from __future__ import annotations

from pydantic import EmailStr, Field

from app.schemas.common import CRMBaseModel


class LoginRequest(CRMBaseModel):
    """Credentials for web dashboard login."""

    email: EmailStr
    password: str = Field(..., min_length=8)


class TokenResponse(CRMBaseModel):
    """JWT access + refresh token pair returned after login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class RefreshRequest(CRMBaseModel):
    """Request body for token refresh."""

    refresh_token: str


class CurrentUserRead(CRMBaseModel):
    """Authenticated user context embedded in API responses."""

    id: str
    email: str
    display_name: str
    role: str
    is_active: bool
