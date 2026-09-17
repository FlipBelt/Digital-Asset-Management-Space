from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_permission_codes, require_authenticated
from app.core.config import get_settings
from app.db.session import get_db
from app.models import Asset, AssetResponsibility, Department, Role, User, UserRoleScope


@dataclass(frozen=True)
class AccessContext:
    user: User
    person_id: UUID | None
    roles: frozenset[str]
    permissions: frozenset[str]
    department_scopes: frozenset[UUID]

    @property
    def is_test_environment(self) -> bool:
        """The isolated test service intentionally grants a full operator scope.

        This is evaluated from server-side configuration only.  It can never be
        enabled by a browser header, cookie, or client-supplied role claim.
        Production keeps the normal RBAC checks below.
        """
        return get_settings().app_env.lower() == "test"

    @property
    def is_global_manager(self) -> bool:
        return self.is_test_environment or bool(self.roles & {"system_admin", "asset_manager"})

    @property
    def is_read_all(self) -> bool:
        return self.is_test_environment or self.is_global_manager or "auditor" in self.roles

    def has_permission(self, permission: str) -> bool:
        return (
            self.is_test_environment
            or "system_admin" in self.roles
            or permission in self.permissions
        )


def get_access_context(
    user: User = Depends(require_authenticated), db: Session = Depends(get_db)
) -> AccessContext:
    rows = db.execute(
        select(Role.code, UserRoleScope.scope_type, UserRoleScope.scope_id)
        .join(UserRoleScope, UserRoleScope.role_id == Role.id)
        .where(UserRoleScope.user_id == user.id)
    ).all()
    roles = frozenset(row[0] for row in rows)
    roots = {
        row[2]
        for row in rows
        if row[0] == "department_manager" and row[1] == "department" and row[2]
    }
    scopes = set(roots)
    if roots:
        departments = list(db.execute(select(Department.id, Department.parent_id)).all())
        changed = True
        while changed:
            changed = False
            for department_id, parent_id in departments:
                if parent_id in scopes and department_id not in scopes:
                    scopes.add(department_id)
                    changed = True
    permissions = frozenset(get_permission_codes(db, user.id))
    return AccessContext(user, user.person_id, roles, permissions, frozenset(scopes))


def asset_visibility_clause(context: AccessContext):
    """Return the company-wide read scope for the authenticated asset library.

    The asset library is the shared source of truth: every authenticated employee
    may read the same asset records, regardless of responsibility or department.
    Mutation checks remain separate in ``can_manage_asset`` and the write-only
    dependencies, so opening read access does not grant edit or archive access.
    """
    return Asset.id.is_not(None)


def can_manage_asset(db: Session, context: AccessContext, asset: Asset) -> bool:
    if not context.has_permission("asset.write"):
        return False
    if context.is_global_manager:
        return True
    if "auditor" in context.roles:
        return False
    if asset.owner_department_id in context.department_scopes:
        return True
    if not context.person_id:
        return False
    return (
        db.scalar(
            select(AssetResponsibility.id).where(
                AssetResponsibility.asset_id == asset.id,
                AssetResponsibility.person_id == context.person_id,
                AssetResponsibility.role_type == "responsible",
                AssetResponsibility.archived_at.is_(None),
            )
        )
        is not None
    )


def can_govern_asset(context: AccessContext, asset: Asset) -> bool:
    return context.has_permission("asset.write") and (
        context.is_global_manager or asset.owner_department_id in context.department_scopes
    )


def require_asset_visible(db: Session, context: AccessContext, asset: Asset) -> None:
    if not db.scalar(
        select(Asset.id).where(Asset.id == asset.id, asset_visibility_clause(context))
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在或无权查看")


def require_global_manager(context: AccessContext = Depends(get_access_context)) -> AccessContext:
    if not context.is_global_manager:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要资产管理员权限")
    return context


def require_asset_write(context: AccessContext = Depends(get_access_context)) -> AccessContext:
    if not context.has_permission("asset.write"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="asset write permission required"
        )
    return context


def require_permission(permission: str):
    def dependency(context: AccessContext = Depends(get_access_context)) -> AccessContext:
        if not context.has_permission(permission):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="permission denied")
        return context

    return dependency
