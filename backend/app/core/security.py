"""
app/core/security.py
──────────────────────────────────────────────────────────────────────────────
JWT utilities and password hashing.

- Access tokens: Short-lived (60 min default), used for API authorization.
- Refresh tokens: Long-lived (7 days), stored server-side in Redis for revocation.
- Passwords: bcrypt via passlib.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt
import bcrypt

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# ── Password Hashing ───────────────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using bcrypt."""
    password_bytes = plain_password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against a bcrypt hash."""
    password_bytes = plain_password.encode("utf-8")
    hashed_bytes = hashed_password.encode("utf-8")
    try:
        return bcrypt.checkpw(password_bytes, hashed_bytes)
    except Exception:
        return False


# ── JWT Tokens ────────────────────────────────────────────────────────────────

def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Create a signed JWT access token.

    Args:
        subject: The token subject (user ID or email).
        extra_claims: Additional claims to embed (e.g., role, display_name).

    Returns:
        Signed JWT string.
    """
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(minutes=settings.jwt.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)

    return jwt.encode(
        payload,
        settings.jwt.JWT_SECRET_KEY,
        algorithm=settings.jwt.JWT_ALGORITHM,
    )


def create_refresh_token(subject: str) -> str:
    """
    Create a signed JWT refresh token (longer TTL).

    Refresh tokens are also stored in Redis for server-side revocation.
    """
    now = datetime.now(tz=timezone.utc)
    expire = now + timedelta(days=settings.jwt.JWT_REFRESH_TOKEN_EXPIRE_DAYS)

    payload: dict[str, Any] = {
        "sub": subject,
        "iat": now,
        "exp": expire,
        "type": "refresh",
    }

    return jwt.encode(
        payload,
        settings.jwt.JWT_SECRET_KEY,
        algorithm=settings.jwt.JWT_ALGORITHM,
    )


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises:
        JWTError: If token is expired, tampered, or invalid.
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt.JWT_SECRET_KEY,
            algorithms=[settings.jwt.JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        logger.warning("jwt_decode_failed", error=str(e))
        raise
