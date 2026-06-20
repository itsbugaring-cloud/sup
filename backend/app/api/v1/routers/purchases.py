import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.routers.auth import get_current_user
from app.core.database import get_db
from app.models.purchase import PurchaseStatus
from app.models.tenant import User
from app.schemas.common import PaginationMeta
from app.schemas.purchase import (
    PurchaseOrderCreate,
    PurchaseOrderListResponse,
    PurchaseOrderResponse,
)
from app.services.purchase_service import PurchaseService

router = APIRouter(prefix="/purchases", tags=["Purchases"])


@router.post("", response_model=PurchaseOrderResponse, status_code=status.HTTP_201_CREATED)
async def create_purchase(
    request: Request,
    data: PurchaseOrderCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new purchase order with items."""
    service = PurchaseService(db)
    client_ip = request.client.host if request.client else None
    
    return await service.create_purchase(
        tenant_id=current_user.tenant_id,
        actor_id=current_user.id,
        actor_name=current_user.display_name or current_user.email,
        data=data,
        ip_address=client_ip,
    )


@router.get("/supplier/{supplier_id}", response_model=PurchaseOrderListResponse)
async def list_supplier_purchases(
    supplier_id: UUID,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[PurchaseStatus] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all purchases for a specific supplier."""
    service = PurchaseService(db)
    skip = (page - 1) * per_page
    
    items, total = await service.list_purchases_by_supplier(
        tenant_id=current_user.tenant_id,
        supplier_id=supplier_id,
        skip=skip,
        limit=per_page,
        status=status,
    )
    
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    
    meta = PaginationMeta(
        total_items=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
    
    return PurchaseOrderListResponse(data=items, meta=meta)


@router.get("", response_model=PurchaseOrderListResponse)
async def list_all_purchases(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    status: Optional[PurchaseStatus] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all purchases across all suppliers."""
    service = PurchaseService(db)
    skip = (page - 1) * per_page
    
    items, total = await service.list_all_purchases(
        tenant_id=current_user.tenant_id,
        skip=skip,
        limit=per_page,
        status=status,
    )
    
    total_pages = math.ceil(total / per_page) if total > 0 else 1
    
    meta = PaginationMeta(
        total_items=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1,
    )
    
    return PurchaseOrderListResponse(data=items, meta=meta)


@router.get("/{purchase_id}", response_model=PurchaseOrderResponse)
async def get_purchase(
    purchase_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get a specific purchase order."""
    service = PurchaseService(db)
    return await service.get_purchase(current_user.tenant_id, purchase_id)


@router.patch("/{purchase_id}/status", response_model=PurchaseOrderResponse)
async def update_purchase_status(
    request: Request,
    purchase_id: UUID,
    new_status: PurchaseStatus = Query(..., description="The new status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the status of a purchase order."""
    service = PurchaseService(db)
    client_ip = request.client.host if request.client else None
    
    return await service.update_purchase_status(
        tenant_id=current_user.tenant_id,
        purchase_id=purchase_id,
        actor_id=current_user.id,
        actor_name=current_user.display_name or current_user.email,
        new_status=new_status,
        ip_address=client_ip,
    )
