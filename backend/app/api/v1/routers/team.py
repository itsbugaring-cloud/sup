"""
app/api/v1/routers/team.py
──────────────────────────────────────────────────────────────────────────────
Team Management and Invitations API.
"""

import uuid
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.core.dependencies import AdminUser, CurrentUser, UserRepo
from app.models.tenant import TeamInvitation, User
from app.schemas.common import SuccessResponse
from app.schemas.team import (
    TeamInviteRequest,
    TeamInviteResponse,
    TeamInviteAcceptRequest,
    TeamMemberRead,
)
from app.core.security import hash_password

router = APIRouter(prefix="/team", tags=["team"])

@router.post(
    "/invite",
    summary="Invite a new team member",
    response_model=SuccessResponse[TeamInviteResponse],
)
async def invite_member(
    req: TeamInviteRequest,
    current_user: AdminUser,
    db: AsyncSession = get_db,
    user_repo: UserRepo = UserRepo,
) -> SuccessResponse[TeamInviteResponse]:
    """Admin only. Generates an invitation token for a new team member."""
    # Check if user already exists
    existing = await user_repo.get_by_email(req.email)
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists.")
        
    # Generate token and save invite
    token = secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=3)
    
    invite = TeamInvitation(
        tenant_id=current_user.tenant_id,
        email=req.email,
        role=req.role,
        token=token,
        expires_at=expires,
        status="pending"
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)
    
    # In a real app, send an email here with the link: https://your-domain.com/accept-invite?token={token}
    
    return SuccessResponse(data=TeamInviteResponse.model_validate(invite, from_attributes=True))


@router.post(
    "/accept-invite",
    summary="Accept an invitation and create an account",
    response_model=SuccessResponse[TeamMemberRead],
)
async def accept_invite(
    req: TeamInviteAcceptRequest,
    db: AsyncSession = get_db,
    user_repo: UserRepo = UserRepo,
) -> SuccessResponse[TeamMemberRead]:
    """Public endpoint to accept an invite with a token."""
    # Find invite
    stmt = select(TeamInvitation).where(
        TeamInvitation.token == req.token,
        TeamInvitation.status == "pending"
    )
    result = await db.execute(stmt)
    invite = result.scalar_one_or_none()
    
    if not invite:
        raise HTTPException(status_code=404, detail="Invalid or expired invitation token.")
        
    if invite.expires_at < datetime.now(timezone.utc):
        invite.status = "expired"
        await db.commit()
        raise HTTPException(status_code=400, detail="Invitation has expired.")
        
    # Create user
    new_user = await user_repo.create(
        tenant_id=invite.tenant_id,
        email=invite.email,
        hashed_password=hash_password(req.password),
        display_name=req.display_name,
        role=invite.role,
        is_active=True,
    )
    
    # Mark invite as accepted
    invite.status = "accepted"
    await db.commit()
    
    return SuccessResponse(data=TeamMemberRead.model_validate(new_user, from_attributes=True))

@router.get(
    "/members",
    summary="List all team members",
    response_model=SuccessResponse[list[TeamMemberRead]],
)
async def list_members(
    current_user: CurrentUser,
    db: AsyncSession = get_db,
) -> SuccessResponse[list[TeamMemberRead]]:
    stmt = select(User).where(User.tenant_id == current_user.tenant_id)
    result = await db.execute(stmt)
    users = result.scalars().all()
    
    return SuccessResponse(data=[TeamMemberRead.model_validate(u, from_attributes=True) for u in users])
