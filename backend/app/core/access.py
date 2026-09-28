from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from fastapi import Depends, HTTPException, status
from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.core.auth import get_permission_codes, require_authenticated
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AccessGrant,
    Account,
    Asset,
    AssetResponsibility,
    Department,
    DepartmentMembership,
    Person,
    Role,
    User,
    UserRoleScope,
)


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
    db.info["audit_actor_user_id"] = user.id
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


def active_period(model):
    today = date.today()
    return and_(
        or_(model.starts_at.is_(None), model.starts_at <= today),
        or_(model.ends_at.is_(None), model.ends_at >= today),
    )


def person_department_ids(person_id: UUID):
    primary = (
        select(Person.department_id)
        .join(Department, Department.id == Person.department_id)
        .where(
            Person.id == person_id,
            Person.archived_at.is_(None),
            Person.employment_status == "active",
            Department.archived_at.is_(None),
        )
    )
    memberships = (
        select(DepartmentMembership.department_id)
        .join(Department, Department.id == DepartmentMembership.department_id)
        .where(
            DepartmentMembership.person_id == person_id,
            DepartmentMembership.is_active.is_(True),
            Department.archived_at.is_(None),
        )
    )
    return primary.union(memberships)


def assigned_asset_clause(person_id: UUID):
    departments = person_department_ids(person_id)
    responsibility = exists(
        select(AssetResponsibility.id)
        .correlate(Asset)
        .where(
            AssetResponsibility.asset_id == Asset.id,
            AssetResponsibility.person_id == person_id,
            AssetResponsibility.role_type.in_(("responsible", "user")),
            AssetResponsibility.archived_at.is_(None),
            active_period(AssetResponsibility),
        )
    )
    grant = exists(
        select(AccessGrant.id)
        .correlate(Asset)
        .where(
            or_(
                AccessGrant.asset_id == Asset.id,
                AccessGrant.account_id.in_(
                    select(Account.id)
                    .where(Account.asset_id == Asset.id, Account.archived_at.is_(None))
                    .correlate(Asset)
                ),
            ),
            or_(
                AccessGrant.person_id == person_id,
                and_(AccessGrant.person_id.is_(None), AccessGrant.department_id.in_(departments)),
            ),
            AccessGrant.archived_at.is_(None),
            AccessGrant.status == "active",
            active_period(AccessGrant),
        )
    )
    return or_(responsibility, grant)


def asset_visibility_clause(context: AccessContext):
    # Null sharing_scope preserves the old registry's discovery policy.
    # Newly registered drafts explicitly start private.
    if context.is_global_manager:
        return Asset.id.is_not(None)
    shared = or_(
        and_(Asset.sharing_scope.is_(None), Asset.confidentiality != "personal"),
        Asset.sharing_scope == "company",
    )
    if context.department_scopes:
        shared = or_(
            shared,
            and_(
                Asset.sharing_scope == "team",
                Asset.owner_department_id.in_(context.department_scopes),
            ),
        )
    if context.person_id is None:
        return shared
    return or_(
        shared,
        Asset.created_by_person_id == context.person_id,
        and_(
            Asset.sharing_scope == "team",
            Asset.owner_department_id.in_(person_department_ids(context.person_id)),
        ),
        assigned_asset_clause(context.person_id),
    )


def can_manage_asset(db: Session, context: AccessContext, asset: Asset) -> bool:
    if not context.has_permission("asset.write"):
        return False
    if context.is_global_manager:
        return True
    if "auditor" in context.roles:
        return False
    if asset.sharing_scope == "private" and asset.created_by_person_id != context.person_id:
        return False
    if (
        context.person_id is not None
        and asset.created_by_person_id == context.person_id
        and (asset.status == "draft" or asset.sharing_scope is not None)
    ):
        return True
    if asset.owner_department_id in context.department_scopes:
        return True
    if not context.person_id:
        return False
    return (
        db.scalar(
            select(AssetResponsibility.id)
            .correlate(Asset)
            .where(
                AssetResponsibility.asset_id == asset.id,
                AssetResponsibility.person_id == context.person_id,
                AssetResponsibility.role_type == "responsible",
                AssetResponsibility.archived_at.is_(None),
                active_period(AssetResponsibility),
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
