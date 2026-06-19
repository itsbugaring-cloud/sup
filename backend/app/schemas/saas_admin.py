"""
app/schemas/saas_admin.py
──────────────────────────────────────────────────────────────────────────────
Pydantic schemas for Super Admin operations.
"""

from __future__ import annotations

from typing import List
from datetime import datetime
from pydantic import Field

from app.schemas.common import CRMBaseModel


class TenantAdminView(CRMBaseModel):
    """Admin view of a Tenant."""
    id: str
    name: str
    slug: str
    is_active: bool
    created_at: datetime
    
class TenantListResponse(CRMBaseModel):
    data: List[TenantAdminView]
    total: int

class PlatformStatsResponse(CRMBaseModel):
    total_tenants: int
    active_tenants: int
    total_users: int
    total_suppliers: int

class ToggleTenantRequest(CRMBaseModel):
    is_active: bool
