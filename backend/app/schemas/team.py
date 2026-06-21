"""
app/schemas/team.py
──────────────────────────────────────────────────────────────────────────────
Schemas for Team Collaboration and Invitations.
"""

from typing import Optional
from datetime import datetime
import uuid
from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import CRMBaseModel

class TeamInviteRequest(CRMBaseModel):
    email: EmailStr = Field(..., description="Email of the user to invite")
    role: str = Field("viewer", description="Role: admin, staff, or viewer")

class TeamInviteResponse(CRMBaseModel):
    id: uuid.UUID
    email: str
    role: str
    status: str
    token: str
    expires_at: datetime
    
class TeamInviteAcceptRequest(CRMBaseModel):
    token: str = Field(..., description="The invitation token")
    password: str = Field(..., min_length=8, description="Password for the new account")
    display_name: str = Field(..., description="Full name of the user")

class TeamMemberRead(CRMBaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    role: str
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime]
