"""
app/models/__init__.py
──────────────────────────────────────────────────────────────────────────────
Re-export all ORM models so Alembic autogenerate can discover them via:

    from app.models import *

Also ensures the relationship back-references resolve correctly.
"""

from app.models.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.audit_log import AuditAction, AuditActorType, AuditLog
from app.models.supplier import Supplier, SupplierStatus
from app.models.supplier_document import DocumentType, SupplierDocument

__all__ = [
    # Base classes
    "Base",
    "TimestampMixin",
    "UUIDPrimaryKeyMixin",
    "SoftDeleteMixin",
    # Enums
    "SupplierStatus",
    "DocumentType",
    "AuditAction",
    "AuditActorType",
    # Models
    "Supplier",
    "SupplierDocument",
    "AuditLog",
]
