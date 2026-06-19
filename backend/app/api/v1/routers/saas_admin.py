"""
app/api/v1/routers/saas_admin.py
──────────────────────────────────────────────────────────────────────────────
API router for Super Admin operations.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func

from app.core.dependencies import SuperadminUser, DbSession
from app.models.tenant import Tenant, User
from app.models.supplier import Supplier
from app.schemas.saas_admin import TenantListResponse, TenantAdminView, PlatformStatsResponse, ToggleTenantRequest
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/saas-admin", tags=["SaaS Admin"])

@router.get("/tenants", response_model=TenantListResponse)
async def list_tenants(
    admin: SuperadminUser,
    db: DbSession,
):
    """List all registered tenants (Super Admin only)."""
    stmt = select(Tenant).order_by(Tenant.created_at.desc())
    result = await db.execute(stmt)
    tenants = result.scalars().all()
    
    data = [
        TenantAdminView(
            id=str(t.id),
            name=t.name,
            slug=t.slug,
            is_active=t.is_active,
            created_at=t.created_at,
        ) for t in tenants
    ]
    return TenantListResponse(data=data, total=len(data))

@router.post("/tenants/{tenant_id}/toggle", response_model=SuccessResponse)
async def toggle_tenant_status(
    tenant_id: uuid.UUID,
    req: ToggleTenantRequest,
    admin: SuperadminUser,
    db: DbSession,
):
    """Suspend or Activate a tenant."""
    stmt = select(Tenant).where(Tenant.id == tenant_id)
    result = await db.execute(stmt)
    tenant = result.scalar_one_or_none()
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
        
    tenant.is_active = req.is_active
    await db.commit()
    
    action = "activated" if req.is_active else "suspended"
    return SuccessResponse(message=f"Tenant {tenant.name} has been {action}")

@router.get("/stats", response_model=PlatformStatsResponse)
async def get_platform_stats(
    admin: SuperadminUser,
    db: DbSession,
):
    """Get global platform statistics."""
    total_tenants = await db.scalar(select(func.count()).select_from(Tenant))
    active_tenants = await db.scalar(select(func.count()).select_from(Tenant).where(Tenant.is_active == True))
    total_users = await db.scalar(select(func.count()).select_from(User))
    total_suppliers = await db.scalar(select(func.count()).select_from(Supplier))
    
    return PlatformStatsResponse(
        total_tenants=total_tenants or 0,
        active_tenants=active_tenants or 0,
        total_users=total_users or 0,
        total_suppliers=total_suppliers or 0,
    )
