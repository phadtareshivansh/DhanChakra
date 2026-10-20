"""Super Admin user management (fixed 3-slot role model).

Every route requires the 'admin' role (require_admin -> 403 otherwise). Roles
are fixed (1 admin + 2 analysts), so no request body here accepts a role: PUT
can change only email, display_name and password. The Super Admin cannot
demote or delete themselves; the admin row is never editable through these
endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException

from ..deps import get_db_session, require_admin
from ..models.schemas import AdminUserList, AdminUserOut, AdminUserUpdate, PasswordReset
from ..services import auth_service

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _out(u: dict) -> AdminUserOut:
    return AdminUserOut(
        id=u["id"],
        email=u["email"],
        display_name=u.get("display_name"),
        role=u["role"],
        created_at=u.get("created_at"),
    )


@router.get("/users", response_model=AdminUserList)
async def list_users(db=Depends(get_db_session), _admin=Depends(require_admin)):
    """The Super Admin plus the two standard-user slots."""
    return AdminUserList(users=[_out(u) for u in await auth_service.list_users(db)])


@router.put("/users/{user_id}", response_model=AdminUserOut)
async def update_user(
    user_id: str,
    body: AdminUserUpdate,
    db=Depends(get_db_session),
    admin=Depends(require_admin),
):
    # Roles are fixed: reject any attempt to smuggle a role change. AdminUserUpdate
    # has no role field, so extra keys are ignored by pydantic — but guard the
    # self-demotion/self-edit case explicitly.
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=403,
            detail={"code": "self_edit_forbidden",
                    "message": "The Super Admin cannot modify their own account here"},
        )
    try:
        updated = await auth_service.update_user(
            db, user_id,
            email=body.email,
            display_name=body.display_name,
            password=body.password,
        )
    except auth_service.UserLimitError as e:
        raise HTTPException(status_code=403, detail={"code": "admin_immutable",
                                                     "message": str(e)})
    if not updated:
        raise HTTPException(status_code=404, detail={"code": "not_found",
                                                     "message": "User not found"})
    return _out(updated)


@router.post("/users/reset-password/{user_id}")
async def reset_password(
    user_id: str,
    body: PasswordReset | None = None,
    db=Depends(get_db_session),
    admin=Depends(require_admin),
):
    if user_id == admin["id"]:
        raise HTTPException(
            status_code=403,
            detail={"code": "self_edit_forbidden",
                    "message": "The Super Admin cannot reset their own password here"},
        )
    try:
        generated = await auth_service.reset_password(
            db, user_id, body.password if body else None
        )
    except auth_service.UserLimitError as e:
        raise HTTPException(status_code=403, detail={"code": "admin_immutable",
                                                     "message": str(e)})
    if generated is None:
        # Either the user does not exist, or an explicit password was supplied.
        target = await auth_service.get_user_by_id(db, user_id)
        if not target:
            raise HTTPException(status_code=404, detail={"code": "not_found",
                                                         "message": "User not found"})
        return {"status": "ok", "user_id": user_id}
    return {"status": "ok", "user_id": user_id, "generated_password": generated}
