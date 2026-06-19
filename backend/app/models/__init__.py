"""
app/models/__init__.py
──────────────────────────────────────────────────────────────────────────────
Centralized registry for all SQLAlchemy ORM models.

Importing this module ensures all models are loaded into the Base metadata 
before Alembic generates migrations or the application runs.
Also ensures the relationship back-references resolve correctly.
"""

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin, TenantMixin
from app.models.tenant import Tenant, User
from app.models.audit_log import AuditAction, AuditActorType, AuditLog
from app.models.supplier import Supplier, SupplierStatus
from app.models.supplier_document import DocumentType, SupplierDocument
from app.models.bot_config import BotConfig

__all__ = [
    "Base",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "TenantMixin",
    "Tenant",
    "User",
    "AuditAction",
    "AuditActorType",
    "AuditLog",
    "Supplier",
    "SupplierStatus",
    "DocumentType",
    "SupplierDocument",
    "BotConfig",
]
