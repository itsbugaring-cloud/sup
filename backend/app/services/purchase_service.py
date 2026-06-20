import logging
from typing import Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditAction, AuditActorType
from app.models.purchase import PurchaseOrder, PurchaseStatus
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.purchase_repository import PurchaseOrderRepository
from app.repositories.supplier_repository import SupplierRepository
from app.schemas.purchase import PurchaseOrderCreate, PurchaseOrderUpdate

logger = logging.getLogger(__name__)


class PurchaseService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PurchaseOrderRepository(session)
        self.supplier_repo = SupplierRepository(session)
        self.audit_repo = AuditLogRepository(session)

    async def create_purchase(
        self,
        tenant_id: UUID,
        actor_id: UUID,
        actor_name: str,
        data: PurchaseOrderCreate,
        ip_address: Optional[str] = None,
    ) -> PurchaseOrder:
        """Create a new purchase order with its items."""
        # Verify supplier exists and belongs to tenant
        supplier = await self.supplier_repo.get_by_id(data.supplier_id, tenant_id)
        if not supplier:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Supplier not found",
            )

        # Prepare data
        po_data = data.model_dump(exclude={"items"})
        items_data = [item.model_dump() for item in data.items]

        # Calculate total amount if not provided but items have total_price
        if po_data.get("total_amount") is None and items_data:
            total = sum(item.get("total_price") or 0 for item in items_data)
            po_data["total_amount"] = total if total > 0 else None

        # Create PO
        po = await self.repo.create_with_items(tenant_id, po_data, items_data)
        await self.session.commit()
        await self.session.refresh(po)

        # Audit Log
        await self.audit_repo.log_action(
            tenant_id=tenant_id,
            action=AuditAction.UPDATE_SUPPLIER,  # Using existing enum or should we add one?
            entity_type="PURCHASE_ORDER",
            entity_id=str(po.id),
            actor_id=actor_id,
            actor_type=AuditActorType.USER,
            actor_display_name=actor_name,
            ip_address=ip_address,
            details={"action": "created_purchase_order", "supplier_id": str(supplier.id), "item_count": len(items_data)},
        )
        await self.session.commit()

        # Fetch with items for response
        return await self.repo.get_with_items(po.id, tenant_id)

    async def get_purchase(self, tenant_id: UUID, purchase_id: UUID) -> PurchaseOrder:
        """Get a single purchase order by ID."""
        po = await self.repo.get_with_items(purchase_id, tenant_id)
        if not po:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Purchase order not found",
            )
        return po

    async def update_purchase_status(
        self,
        tenant_id: UUID,
        purchase_id: UUID,
        actor_id: UUID,
        actor_name: str,
        new_status: PurchaseStatus,
        ip_address: Optional[str] = None,
    ) -> PurchaseOrder:
        """Update the status of a purchase order."""
        po = await self.get_purchase(tenant_id, purchase_id)
        
        old_status = po.status
        if old_status == new_status:
            return po

        po = await self.repo.update(po, {"status": new_status})
        await self.session.commit()

        # Audit Log
        await self.audit_repo.log_action(
            tenant_id=tenant_id,
            action=AuditAction.UPDATE_SUPPLIER,
            entity_type="PURCHASE_ORDER",
            entity_id=str(po.id),
            actor_id=actor_id,
            actor_type=AuditActorType.USER,
            actor_display_name=actor_name,
            ip_address=ip_address,
            details={"action": "updated_status", "old_status": old_status.value, "new_status": new_status.value},
        )
        await self.session.commit()

        return po

    async def list_purchases_by_supplier(
        self,
        tenant_id: UUID,
        supplier_id: UUID,
        skip: int = 0,
        limit: int = 20,
        status: Optional[PurchaseStatus] = None,
    ) -> Tuple[list[PurchaseOrder], int]:
        """List purchases for a specific supplier."""
        return await self.repo.list_by_supplier(tenant_id, supplier_id, skip, limit, status)

    async def list_all_purchases(
        self,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 20,
        status: Optional[PurchaseStatus] = None,
    ) -> Tuple[list[PurchaseOrder], int]:
        """List all purchases."""
        return await self.repo.list_all(tenant_id, skip, limit, status)
