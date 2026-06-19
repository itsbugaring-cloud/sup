"""
app/core/dependencies.py
──────────────────────────────────────────────────────────────────────────────
FastAPI dependency injection providers.

All route handlers receive their dependencies through these functions.
This centralises all cross-cutting concerns (auth, db, repos, services).

Dependency tree:
  get_db_session          → AsyncSession
  get_current_user        → CurrentUserRead (requires JWT Bearer)
  get_supplier_repo       → SupplierRepository(db)
  get_audit_repo          → AuditLogRepository(db)
  get_doc_repo            → SupplierDocumentRepository(db)
  get_supplier_service    → SupplierService(repo, audit_repo, minio)
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db_session
from app.core.logging import get_logger
from app.core.security import decode_token
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.supplier_document_repository import SupplierDocumentRepository
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.auth import CurrentUserRead

logger = get_logger(__name__)

# ── Auth Scheme ───────────────────────────────────────────────────────────────
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)
    ] = None,
) -> CurrentUserRead:
    """
    Validate Bearer JWT and return the current authenticated user.

    Raises 401 if:
    - No Authorization header is present.
    - Token is expired, tampered, or invalid.
    - Token type is not 'access'.
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(credentials.credentials)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type — access token required",
        )

    return CurrentUserRead(
        id=payload["sub"],
        email=payload.get("email", payload["sub"]),
        display_name=payload.get("display_name", ""),
        role=payload.get("role", "viewer"),
        is_active=payload.get("is_active", True),
    )


async def get_current_admin(
    current_user: Annotated[CurrentUserRead, Depends(get_current_user)],
) -> CurrentUserRead:
    """Require the current user to have the 'admin' role."""
    if current_user.role not in ("admin", "superadmin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required",
        )
    return current_user


# ── Database Session ──────────────────────────────────────────────────────────
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ── Repository Dependencies ───────────────────────────────────────────────────
def get_supplier_repo(db: DbSession) -> SupplierRepository:
    return SupplierRepository(db)


def get_audit_repo(db: DbSession) -> AuditLogRepository:
    return AuditLogRepository(db)


def get_doc_repo(db: DbSession) -> SupplierDocumentRepository:
    return SupplierDocumentRepository(db)


# ── Annotated shorthand types for router injection ────────────────────────────
SupplierRepo = Annotated[SupplierRepository, Depends(get_supplier_repo)]
AuditRepo = Annotated[AuditLogRepository, Depends(get_audit_repo)]
DocRepo = Annotated[SupplierDocumentRepository, Depends(get_doc_repo)]
CurrentUser = Annotated[CurrentUserRead, Depends(get_current_user)]
AdminUser = Annotated[CurrentUserRead, Depends(get_current_admin)]


# ── Request Context ───────────────────────────────────────────────────────────
def get_request_id(request: Request) -> str:
    """Extract the request_id set by the middleware."""
    return request.state.request_id if hasattr(request.state, "request_id") else ""


def get_client_ip(request: Request) -> str:
    """Extract the real client IP (handles X-Forwarded-For from Nginx)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
