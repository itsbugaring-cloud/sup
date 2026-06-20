from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.purchase import PurchaseStatus
from app.schemas.common import PaginationMeta


# --- Purchase Item Schemas ---
class PurchaseItemBase(BaseModel):
    item_name: str = Field(..., max_length=255)
    quantity: float = Field(..., gt=0)
    unit: str = Field(..., max_length=50)
    price_per_unit: Optional[float] = Field(None, ge=0)
    total_price: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class PurchaseItemCreate(PurchaseItemBase):
    pass


class PurchaseItemUpdate(BaseModel):
    item_name: Optional[str] = Field(None, max_length=255)
    quantity: Optional[float] = Field(None, gt=0)
    unit: Optional[str] = Field(None, max_length=50)
    price_per_unit: Optional[float] = Field(None, ge=0)
    total_price: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


class PurchaseItemResponse(PurchaseItemBase):
    id: UUID
    purchase_order_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# --- Purchase Order Schemas ---
class PurchaseOrderBase(BaseModel):
    supplier_id: UUID
    po_number: Optional[str] = Field(None, max_length=100)
    purchase_date: Optional[datetime] = None
    status: PurchaseStatus = Field(default=PurchaseStatus.DRAFT)
    total_amount: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None
    receipt_file_url: Optional[str] = None


class PurchaseOrderCreate(PurchaseOrderBase):
    items: List[PurchaseItemCreate] = Field(default_factory=list)


class PurchaseOrderUpdate(BaseModel):
    po_number: Optional[str] = Field(None, max_length=100)
    purchase_date: Optional[datetime] = None
    status: Optional[PurchaseStatus] = None
    total_amount: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None
    receipt_file_url: Optional[str] = None


class PurchaseOrderResponse(PurchaseOrderBase):
    id: UUID
    tenant_id: UUID
    created_at: datetime
    updated_at: datetime
    items: List[PurchaseItemResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class PurchaseOrderListResponse(BaseModel):
    data: List[PurchaseOrderResponse]
    meta: PaginationMeta
