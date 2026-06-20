from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.purchase import PurchaseItem, PurchaseOrder, PurchaseStatus
from app.repositories.base import BaseRepository


class PurchaseOrderRepository(BaseRepository[PurchaseOrder]):
    def __init__(self, session: AsyncSession):
        super().__init__(session, PurchaseOrder)

    async def get_with_items(self, purchase_id: UUID, tenant_id: UUID) -> Optional[PurchaseOrder]:
        """Get a purchase order with its line items."""
        stmt = (
            select(PurchaseOrder)
            .where(PurchaseOrder.id == purchase_id, PurchaseOrder.tenant_id == tenant_id)
            .options(selectinload(PurchaseOrder.items))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_supplier(
        self,
        tenant_id: UUID,
        supplier_id: UUID,
        skip: int = 0,
        limit: int = 20,
        status: Optional[PurchaseStatus] = None,
    ) -> Tuple[List[PurchaseOrder], int]:
        """List purchase orders for a specific supplier with pagination."""
        stmt = select(PurchaseOrder).where(
            PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.supplier_id == supplier_id
        )
        
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get items
        stmt = stmt.order_by(PurchaseOrder.purchase_date.desc()).offset(skip).limit(limit).options(selectinload(PurchaseOrder.items))
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def list_all(
        self,
        tenant_id: UUID,
        skip: int = 0,
        limit: int = 20,
        status: Optional[PurchaseStatus] = None,
    ) -> Tuple[List[PurchaseOrder], int]:
        """List all purchase orders for a tenant with pagination."""
        stmt = select(PurchaseOrder).where(PurchaseOrder.tenant_id == tenant_id)
        
        if status:
            stmt = stmt.where(PurchaseOrder.status == status)

        # Count total
        count_stmt = select(func.count()).select_from(stmt.subquery())
        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar() or 0

        # Get items
        stmt = stmt.order_by(PurchaseOrder.purchase_date.desc()).offset(skip).limit(limit).options(selectinload(PurchaseOrder.items))
        result = await self.session.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def create_with_items(
        self, tenant_id: UUID, data: Dict[str, Any], items_data: List[Dict[str, Any]]
    ) -> PurchaseOrder:
        """Create a purchase order and its line items in one transaction."""
        po = PurchaseOrder(tenant_id=tenant_id, **data)
        self.session.add(po)
        await self.session.flush()

        for item_data in items_data:
            item = PurchaseItem(purchase_order_id=po.id, **item_data)
            self.session.add(item)
        
        await self.session.flush()
        return po
