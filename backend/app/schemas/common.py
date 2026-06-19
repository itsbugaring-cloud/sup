"""
app/schemas/common.py
──────────────────────────────────────────────────────────────────────────────
Reusable Pydantic base models and response envelopes.

Design principles:
  - All responses are wrapped in a consistent envelope (success/error).
  - Pagination is standardised — every list endpoint uses PaginatedResponse.
  - Base model enforces `from_attributes=True` for ORM mode compatibility.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class CRMBaseModel(BaseModel):
    """
    Base model for all CRM Pydantic schemas.

    Enables:
    - `from_attributes=True` → ORM model → Pydantic serialisation.
    - `populate_by_name=True` → allows both alias and field name.
    - `use_enum_values=True` → serialise enums as their values (strings).
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )


class SuccessResponse(BaseModel, Generic[T]):
    """
    Standard success envelope for single-item responses.

    Usage:
        return SuccessResponse(data=supplier, message="Supplier created")
    """

    success: bool = True
    message: str = "OK"
    data: T


class PaginationMeta(BaseModel):
    """Pagination metadata included in all list responses."""

    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=200)
    total_items: int = Field(ge=0)
    total_pages: int = Field(ge=0)
    has_next: bool
    has_prev: bool


class PaginatedResponse(BaseModel, Generic[T]):
    """
    Standard paginated list response envelope.

    Usage:
        return PaginatedResponse(
            data=suppliers,
            meta=PaginationMeta(page=1, per_page=20, total_items=100, ...)
        )
    """

    success: bool = True
    data: list[T]
    meta: PaginationMeta


class ErrorDetail(BaseModel):
    """Structured error detail for validation errors."""

    field: str | None = None
    message: str
    code: str | None = None


class ErrorResponse(BaseModel):
    """Standard error envelope returned on all 4xx/5xx responses."""

    success: bool = False
    message: str
    errors: list[ErrorDetail] | None = None
    request_id: str | None = None


class TaskResponse(BaseModel):
    """Response for async background job submission."""

    task_id: str
    status: str = "queued"
    message: str = "Task has been queued for processing"
    estimated_seconds: int | None = None


class PaginationParams(BaseModel):
    """Query parameter model for paginated list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    per_page: int = Field(
        default=20, ge=1, le=200, description="Items per page (max 200)"
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.per_page
