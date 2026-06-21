"""
app/api/v1/routers/auth.py
──────────────────────────────────────────────────────────────────────────────
Authentication and Tenant Registration router for SaaS.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status, Request

from app.core.dependencies import TenantRepo, UserRepo
from app.core.rate_limit import limiter
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.auth import LoginRequest, TokenResponse
from app.schemas.common import CRMBaseModel, SuccessResponse

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterTenantRequest(CRMBaseModel):
    company_name: str
    company_slug: str
    email: str
    password: str
    display_name: str


@router.post(
    "/register",
    summary="Register a new Tenant and Owner Account",
    response_model=SuccessResponse[TokenResponse],
    status_code=status.HTTP_201_CREATED,
)
@limiter.limit("3/minute")
async def register_tenant(
    request: Request,
    req: RegisterTenantRequest,
    tenant_repo: TenantRepo,
    user_repo: UserRepo,
) -> SuccessResponse[TokenResponse]:
    # Check if user already exists
    existing_user = await user_repo.get_by_email(req.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create Tenant
    tenant = await tenant_repo.create(
        name=req.company_name,
        slug=req.company_slug,
        is_active=True,
    )

    # Create Owner User
    user = await user_repo.create(
        tenant_id=tenant.id,
        email=req.email,
        hashed_password=hash_password(req.password),
        display_name=req.display_name,
        role="owner",
        is_active=True,
    )

    # Issue JWT Token
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={
            "tenant_id": str(tenant.id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_superadmin": user.is_superadmin,
        },
    )

    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token="not_implemented",
            expires_in=3600,
        ),
        message="Tenant registered successfully",
    )


@router.post(
    "/login",
    summary="Authenticate user and return JWT token",
    response_model=SuccessResponse[TokenResponse],
)
@limiter.limit("5/minute")
async def login(
    request: Request,
    req: LoginRequest,
    user_repo: UserRepo,
) -> SuccessResponse[TokenResponse]:
    user = await user_repo.get_by_email(req.email)
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Issue JWT Token
    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={
            "tenant_id": str(user.tenant_id),
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "is_superadmin": user.is_superadmin,
        },
    )

    return SuccessResponse(
        data=TokenResponse(
            access_token=access_token,
            refresh_token="not_implemented",
            expires_in=3600,
        ),
        message="Login successful",
    )
