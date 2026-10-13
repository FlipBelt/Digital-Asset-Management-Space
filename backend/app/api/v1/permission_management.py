from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.access import AccessContext, get_access_context
from app.core.auth import require_csrf
from app.db.session import get_db
from app.schemas.permission_management import (
    PermissionAccessWrite,
    PermissionMutation,
    PermissionResourceWrite,
    PermissionRoleWrite,
)
from app.services import permission_management as service

router = APIRouter(prefix="/permission-management", tags=["permission-management"])


@router.get("/catalog")
def catalog(db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)):
    return service.catalog(db, access.user)


@router.get("/users")
def users(keyword: str = Query(default="", max_length=200), db: Session = Depends(get_db)):
    return service.list_users(db, keyword)


@router.get("/users/{user_id}")
def user(user_id: UUID, db: Session = Depends(get_db)):
    return service.user_details(db, user_id)


@router.post("/users/{user_id}/roles", dependencies=[Depends(require_csrf)])
def grant_role(
    user_id: UUID,
    payload: PermissionRoleWrite,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    return service.grant_role(db, access, user_id, payload)


@router.post("/users/{user_id}/roles/{assignment_id}/revoke", dependencies=[Depends(require_csrf)])
def revoke_role(
    user_id: UUID,
    assignment_id: UUID,
    payload: PermissionMutation,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    return service.revoke_role(db, access, user_id, assignment_id, payload)


@router.post("/users/{user_id}/access", dependencies=[Depends(require_csrf)])
def user_access(
    user_id: UUID,
    payload: PermissionAccessWrite,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    return service.set_user_access(db, access, user_id, payload)


@router.post("/users/{user_id}/resource-grants", dependencies=[Depends(require_csrf)])
def grant_resource(
    user_id: UUID,
    payload: PermissionResourceWrite,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    return service.grant_resource(db, access, user_id, payload)


@router.post(
    "/users/{user_id}/resource-grants/{grant_id}/revoke", dependencies=[Depends(require_csrf)]
)
def revoke_resource(
    user_id: UUID,
    grant_id: UUID,
    payload: PermissionMutation,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    return service.revoke_resource(db, access, user_id, grant_id, payload)
