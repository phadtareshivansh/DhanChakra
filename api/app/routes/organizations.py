from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from typing import Optional, List
from uuid import UUID, uuid4
from datetime import datetime

from sqlalchemy import text, select, update
from ..config import settings
from ..deps import get_neo4j_session, get_db_session, get_current_user
from ..models.schemas import Organization, Membership, User, OrganizationCreate, MembershipCreate, MembershipUpdate
from ..services import auth_service

router = APIRouter(prefix="/api/v1", tags=["organizations"])


# ----------------------------------------------------------------------------
# Organization
# ----------------------------------------------------------------------------

@router.post("/organizations", response_model=Organization, status_code=status.HTTP_201_CREATED)
async def create_organization(
    org: OrganizationCreate,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Create a new organization. The creator becomes the platform admin."""
    org_id = str(uuid4())
    org_obj = Organization(
        id=org_id,
        name=org.name,
        display_name=org.display_name,
        is_active=True,
    )
    # Store in Postgres for now; the org_id will be propagated to Neo4j nodes.
    async with db as session:
        await session.execute(
            text(
                """
                INSERT INTO organizations (id, name, display_name, created_at, is_active)
                VALUES (:id, :name, :display_name, :created_at, :is_active)
                """
            ),
            {
                "id": org_id,
                "name": org.name,
                "display_name": org.display_name,
                "created_at": datetime.utcnow(),
                "is_active": True,
            },
        )
        await session.commit()
    return org_obj


@router.get("/organizations", response_model=List[Organization])
async def list_organizations(
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """List all organizations the user belongs to."""
    async with db as session:
        result = await session.execute(
            text("SELECT id, name, display_name, created_at, is_active FROM organizations WHERE is_active = True")
        )
        rows = result.mappings().all()
    return [Organization(**r) for r in rows]


@router.get("/organizations/{org_id}", response_model=Organization)
async def get_organization(
    org_id: str,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Get a specific organization."""
    async with db as session:
        result = await session.execute(
            text("SELECT id, name, display_name, created_at, is_active FROM organizations WHERE id = :id"),
            {"id": org_id},
        )
        row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Organization not found")
    return Organization(**row)


# ----------------------------------------------------------------------------
# Membership
# ----------------------------------------------------------------------------

@router.post("/organizations/{org_id}/memberships", status_code=status.HTTP_201_CREATED)
async def invite_member(
    org_id: str,
    membership: MembershipCreate,
    db=Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    """Invite a user to an organization. Org admins and platform admins can invite."""
    # TODO: add org role check
    mem_id = str(uuid4())
    async with db as session:
        await session.execute(
            text(
                """
                INSERT INTO memberships (id, user_id, organization_id, role, invited_by, invited_at, is_active)
                VALUES (:id, :user_id, :org_id, :role, :invited_by, :invited_at, :is_active)
                """
            ),
            {
                "id": mem_id,
                "user_id": current_user.get("sub"),
                "org_id": org_id,
                "role": membership.role,
                "invited_by": current_user.get("sub"),
                "invited_at": datetime.utcnow(),
                "is_active": True,
            },
        )
        await session.commit()
    return {"id": mem_id, "detail": "Invitation sent"}