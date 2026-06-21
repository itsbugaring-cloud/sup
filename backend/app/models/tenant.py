"""
app/models/tenant.py
──────────────────────────────────────────────────────────────────────────────
SaaS Tenant and User models.

- Tenant: Represents a client company/organization.
- User: An individual who belongs to a Tenant.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    pass


class Tenant(TimestampMixin, Base):
    """
    SaaS Tenant (Client Company).
    """
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)

    def __repr__(self) -> str:
        return f"<Tenant name={self.name!r}>"


class User(TimestampMixin, Base):
    """
    SaaS User belonging to a Tenant.
    """
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # roles: owner, admin, viewer
    role: Mapped[str] = mapped_column(String(50), nullable=False, server_default="viewer")
    
    is_superadmin: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<User email={self.email!r} role={self.role!r}>"


class TeamInvitation(TimestampMixin, Base):
    """
    SaaS Team Invitation.
    """
    __tablename__ = "team_invitations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )

    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False, server_default="viewer")
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    
    # pending, accepted, expired
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="pending")

    def __repr__(self) -> str:
        return f"<TeamInvitation email={self.email!r} role={self.role!r} status={self.status!r}>"
