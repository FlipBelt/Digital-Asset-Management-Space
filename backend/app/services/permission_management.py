"""Explicit local roles and resource access, separate from directory leadership."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.core.auth import get_role_codes
from app.models import (
    AccessGrant,
    Account,
    AppSetting,
    Asset,
    AssetType,
    AuditLog,
    Department,
    DepartmentMembership,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    Person,
    RegistrationIdentityProfile,
    ResourceProfile,
    Role,
    ServiceInstance,
    User,
    UserRoleScope,
    UserSession,
)
from app.services.audited_requests import audited_retry
from app.services.organization_leadership import (
    MANUAL_PERMISSION_POLICY_KEY,
    department_leadership_role,
    leadership_policy,
    resolved_role_scopes,
)
from app.services.service_catalog import digest

ROLE_CODES = {
    "system_admin",
    "asset_manager",
    "employee",
    "executive",
    "auditor",
    "department_manager",
    "group_leader",
}
GLOBAL_ROLES = {"system_admin", "asset_manager", "executive", "auditor"}


def lock_permission_changes(db):
    # Every role change and local account disable uses the same transaction lock.
    if db.bind.dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(640133711221)))


def permission_policy(db):
    setting = db.scalar(select(AppSetting).where(AppSetting.key == MANUAL_PERMISSION_POLICY_KEY))
    return dict(setting.value or {}) if setting else {}


def _save_policy(db, values):
    setting = db.scalar(select(AppSetting).where(AppSetting.key == MANUAL_PERMISSION_POLICY_KEY))
    if setting is None:
        setting = AppSetting(key=MANUAL_PERMISSION_POLICY_KEY, value=values)
        db.add(setting)
    else:
        setting.value = values


def _effective_user(db, user):
    if user is None or not user.is_active or user.archived_at is not None:
        return False
    person = db.get(Person, user.person_id) if user.person_id else None
    return (
        person is None
        if not user.person_id
        else bool(person and person.archived_at is None and person.employment_status == "active")
    )


def ensure_system_admin_survives(db, user_id, *, remove_system_role=False, disable_user=False):
    """Caller holds lock_permission_changes; count usable admins, not stored roles alone."""
    user = db.get(User, user_id)
    if user is None or "system_admin" not in get_role_codes(db, user.id):
        return
    if not (remove_system_role or disable_user):
        return
    remaining = [
        candidate.id
        for candidate in db.scalars(select(User))
        if candidate.id != user.id
        and _effective_user(db, candidate)
        and "system_admin" in get_role_codes(db, candidate.id)
    ]
    if not remaining:
        raise HTTPException(409, "必须保留至少一位可登录的系统管理员，请先完成管理员交接")


def _require_admin(db, actor):
    db.refresh(actor)
    if not _effective_user(db, actor) or "system_admin" not in get_role_codes(db, actor.id):
        raise HTTPException(403, "只有当前有效系统管理员可以管理权限")


def _require_user(db, user_id, *, effective=False):
    user = db.scalar(select(User).where(User.id == user_id, User.archived_at.is_(None)))
    if user is None:
        raise HTTPException(404, "本系统登录账号不存在；员工需先完成本人登录")
    if effective and not _effective_user(db, user):
        raise HTTPException(422, "只能向当前在职且访问已启用的员工授予权限")
    return user


def _roles(db):
    return {
        role.code: role
        for role in db.scalars(
            select(Role).where(
                Role.archived_at.is_(None),
                Role.code.in_(ROLE_CODES),
            )
        )
    }


def _scope_label(db, scope_type, scope_id):
    if scope_type == "department":
        department = db.get(Department, scope_id)
        return department.name if department else "部门资料待核对"
    return "全集团" if scope_type == "company" else "本人"


def _directory_scopes(db, user):
    person = db.get(Person, user.person_id) if user.person_id else None
    policy = leadership_policy(db)
    profile = (
        db.scalar(
            select(DingTalkPersonProfile).where(
                DingTalkPersonProfile.person_id == user.person_id,
            )
        )
        if user.person_id
        else None
    )
    if (
        not person
        or not profile
        or not policy
        or str(person.legal_entity_id) != policy.get("legal_entity_id")
        or (profile.profile_data or {}).get("directory_status") == "not_in_current_directory"
    ):
        return set()
    scopes = set()
    for department in db.scalars(
        select(Department)
        .join(DingTalkDepartmentLink, DingTalkDepartmentLink.department_id == Department.id)
        .join(DepartmentMembership, DepartmentMembership.department_id == Department.id)
        .where(
            DepartmentMembership.person_id == person.id,
            DepartmentMembership.is_active.is_(True),
            DepartmentMembership.is_manager.is_(True),
            Department.archived_at.is_(None),
            Department.status == "active",
        )
    ):
        code = department_leadership_role(department, policy)
        if code:
            scopes.add((code, "department", department.id))
    return scopes


def _user_details(db, user):
    roles = _roles(db)
    person = db.get(Person, user.person_id) if user.person_id else None
    policy = permission_policy(db)
    manual_ids = set(policy.get("manual_role_scope_ids", []))
    effective = set(resolved_role_scopes(db, user.id))
    directory = _directory_scopes(db, user)
    assignments = []
    for stored in db.scalars(
        select(UserRoleScope).where(UserRoleScope.user_id == user.id).order_by(UserRoleScope.id)
    ):
        role = db.get(Role, stored.role_id)
        key = (role.code, stored.scope_type, stored.scope_id) if role else None
        if not role or role.code not in roles or key not in effective:
            continue
        is_manual = str(stored.id) in manual_ids
        if key in directory and not is_manual:
            continue
        assignments.append(
            {
                "id": str(stored.id),
                "role_code": role.code,
                "role_name": role.name,
                "scope_type": stored.scope_type,
                "scope_id": str(stored.scope_id) if stored.scope_id else None,
                "scope_label": _scope_label(db, stored.scope_type, stored.scope_id),
                "source": "manual" if is_manual else "stored",
                "revocable": True,
            }
        )
    for code, scope_type, scope_id in sorted(directory, key=lambda row: (row[0], str(row[2]))):
        role = roles.get(code)
        if role:
            assignments.append(
                {
                    "id": None,
                    "role_code": code,
                    "role_name": role.name,
                    "scope_type": scope_type,
                    "scope_id": str(scope_id),
                    "scope_label": _scope_label(db, scope_type, scope_id),
                    "source": "directory",
                    "revocable": False,
                }
            )
    department_ids = (
        set(
            db.scalars(
                select(DepartmentMembership.department_id).where(
                    DepartmentMembership.person_id == user.person_id,
                    DepartmentMembership.is_active.is_(True),
                )
            )
        )
        if user.person_id
        else set()
    )
    if person and person.department_id:
        department_ids.add(person.department_id)
    grants = []
    if user.person_id:
        for grant in db.scalars(
            select(AccessGrant)
            .where(
                or_(
                    AccessGrant.person_id == user.person_id,
                    AccessGrant.department_id.in_(department_ids) if department_ids else False,
                ),
                AccessGrant.archived_at.is_(None),
                AccessGrant.status == "active",
            )
            .order_by(AccessGrant.id)
        ):
            account = db.get(Account, grant.account_id) if grant.account_id else None
            asset = db.get(Asset, grant.asset_id or (account.asset_id if account else None))
            grants.append(
                {
                    "id": str(grant.id),
                    "asset_id": str(asset.id) if asset else None,
                    "asset_name": asset.name if asset else "历史资源待核对",
                    "scope_label": "本人"
                    if grant.person_id == user.person_id
                    else _scope_label(db, "department", grant.department_id),
                    "source": "direct" if grant.person_id == user.person_id else "department",
                    "grant_role": grant.grant_role,
                    "starts_at": grant.starts_at.isoformat() if grant.starts_at else None,
                    "ends_at": grant.ends_at.isoformat() if grant.ends_at else None,
                    "revocable": grant.person_id == user.person_id,
                }
            )
    core = {
        "id": str(user.id),
        "person_id": str(user.person_id) if user.person_id else None,
        "display_name": person.display_name if person else user.username,
        "employee_no": person.employee_no if person else None,
        "department": _scope_label(db, "department", person.department_id)
        if person and person.department_id
        else "未登记部门",
        "is_active": user.is_active,
        "employment_status": person.employment_status if person else None,
        "assignments": assignments,
        "resource_grants": grants,
        "roles": sorted({row[0] for row in effective}),
        "is_effective": _effective_user(db, user),
    }
    core["revision"] = digest(
        {
            **core,
            "updated_at": user.updated_at.isoformat(),
            "bootstrap_revoked": str(user.id) in policy.get("bootstrap_revoked_user_ids", []),
        }
    )
    return core


def user_details(db, user_id):
    return _user_details(db, _require_user(db, user_id))


def list_users(db, keyword=""):
    users = list(db.scalars(select(User).where(User.archived_at.is_(None)).order_by(User.id)))
    needle = keyword.strip().casefold()
    items = []
    for user in users:
        details = _user_details(db, user)
        if (
            needle
            and needle
            not in " ".join(
                str(details.get(key) or "")
                for key in (
                    "display_name",
                    "employee_no",
                    "department",
                )
            ).casefold()
        ):
            continue
        items.append(
            {
                key: value
                for key, value in details.items()
                if key not in {"assignments", "resource_grants"}
            }
        )
    return {"items": items[:100], "total": len(items)}


def _eligible_resource(db, asset):
    if asset is None:
        return False
    kind = db.get(AssetType, asset.asset_type_id)
    if (
        (kind and kind.code == "registration_identity")
        or db.scalar(
            select(RegistrationIdentityProfile.id).where(
                RegistrationIdentityProfile.asset_id == asset.id,
                RegistrationIdentityProfile.archived_at.is_(None),
            )
        )
        or db.scalar(
            select(ResourceProfile.id).where(
                ResourceProfile.asset_id == asset.id,
                ResourceProfile.resource_family == "platform_catalog",
                ResourceProfile.archived_at.is_(None),
            )
        )
    ):
        return False
    return bool(
        asset.archived_at is None
        and asset.status not in {"deleted", "retired", "draft"}
        and not asset.is_personal_subscription
        and not asset.is_child_account
        and not db.scalar(
            select(ServiceInstance.id).where(
                ServiceInstance.asset_id == asset.id,
                ServiceInstance.funding_source == "personal",
                ServiceInstance.archived_at.is_(None),
            )
        )
    )


def catalog(db, actor):
    policy = leadership_policy(db)
    linked = set(db.scalars(select(DingTalkDepartmentLink.department_id)))
    departments = []
    for department in db.scalars(
        select(Department)
        .where(
            Department.archived_at.is_(None),
            Department.status == "active",
        )
        .order_by(Department.name, Department.id)
    ):
        if department.id in linked:
            code = department_leadership_role(department, policy)
            if not code or department.name.endswith(("公司", "合伙企业", "个体工商户")):
                continue
            choices = [code]
        else:
            choices = ["department_manager", "group_leader"]
        departments.append(
            {"id": str(department.id), "name": department.name, "role_codes": choices}
        )
    return {
        "current_user_id": str(actor.id),
        "roles": [
            {
                "code": role.code,
                "name": role.name,
                "scope_type": "department"
                if role.code in {"department_manager", "group_leader"}
                else "company"
                if role.code in GLOBAL_ROLES
                else "self",
                "scope_label": "指定部门"
                if role.code in {"department_manager", "group_leader"}
                else "全集团"
                if role.code in GLOBAL_ROLES
                else "本人",
            }
            for role in _roles(db).values()
        ],
        "departments": departments,
        "resources": [
            {"id": str(asset.id), "name": asset.name, "asset_code": asset.asset_code}
            for asset in db.scalars(select(Asset).order_by(Asset.name, Asset.id))
            if _eligible_resource(db, asset)
        ],
    }


def _start(db, access, user_id, action, payload, *, effective=False):
    lock_permission_changes(db)
    _require_admin(db, access.user)
    prior, fingerprint = audited_retry(db, access, action, payload, user_id)
    user = _require_user(db, user_id, effective=effective and prior is None)
    details = _user_details(db, user)
    if prior is None and details["revision"] != payload.expected_revision:
        raise HTTPException(409, "员工权限已改变，请刷新后重新操作")
    return user, details, prior, fingerprint


def _finish(db, access, user, action, payload, fingerprint, before, after):
    user.updated_at = datetime.now(UTC)
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action=action,
            object_type="user",
            object_id=user.id,
            request_id=str(payload.request_id),
            before_data=before,
            after_data={**after, "request_digest": fingerprint, "reason": payload.reason},
        )
    )
    db.commit()
    db.refresh(user)
    return _user_details(db, user)


def grant_role(db, access, user_id, payload):
    action = "permission.role.grant"
    user, _, prior, fingerprint = _start(db, access, user_id, action, payload, effective=True)
    if prior:
        return _user_details(db, user)
    role = _roles(db).get(payload.role_code)
    if role is None:
        raise HTTPException(422, "这个预置角色当前不可用")
    scope_type = (
        "department"
        if payload.department_id
        else "company"
        if role.code in GLOBAL_ROLES
        else "self"
    )
    if payload.department_id:
        option = next(
            (
                row
                for row in catalog(db, access.user)["departments"]
                if row["id"] == str(payload.department_id)
            ),
            None,
        )
        if option is None or role.code not in option["role_codes"]:
            raise HTTPException(422, "部门范围或主管/组长类型当前不可用")
    policy = permission_policy(db)
    manual_ids = set(policy.get("manual_role_scope_ids", []))
    query = select(UserRoleScope).where(
        UserRoleScope.user_id == user.id,
        UserRoleScope.role_id == role.id,
        UserRoleScope.scope_type == scope_type,
    )
    if payload.department_id:
        query = query.where(UserRoleScope.scope_id == payload.department_id)
    stored = db.scalar(query.order_by(UserRoleScope.id))
    if stored is None:
        stored = UserRoleScope(
            user_id=user.id, role_id=role.id, scope_type=scope_type, scope_id=payload.department_id
        )
        db.add(stored)
        db.flush()
    manual_ids.add(str(stored.id))
    policy["manual_role_scope_ids"] = sorted(manual_ids)
    _save_policy(db, policy)
    return _finish(
        db,
        access,
        user,
        action,
        payload,
        fingerprint,
        None,
        {
            "role_scope_id": str(stored.id),
            "role_code": role.code,
            "scope_type": scope_type,
            "scope_id": str(payload.department_id) if payload.department_id else None,
        },
    )


def revoke_role(db, access, user_id, assignment_id, payload):
    action = "permission.role.revoke"
    # Binding the target to the fingerprint prevents reusing a revoke request for another role.
    target = f"{user_id}:{assignment_id}"
    lock_permission_changes(db)
    _require_admin(db, access.user)
    prior, fingerprint = audited_retry(db, access, action, payload, target)
    user = _require_user(db, user_id)
    details = _user_details(db, user)
    if prior:
        return details
    if details["revision"] != payload.expected_revision:
        raise HTTPException(409, "员工权限已改变，请刷新后重新操作")
    assignment = next(
        (row for row in details["assignments"] if row["id"] == str(assignment_id)), None
    )
    if assignment is None or not assignment["revocable"]:
        raise HTTPException(422, "该权限来自通讯录或已失效，请在来源中管理")
    stored = db.get(UserRoleScope, assignment_id)
    policy = permission_policy(db)
    if assignment["role_code"] == "system_admin":
        # Removing one duplicate global grant does not remove the effective role.
        siblings = [
            row
            for row in details["assignments"]
            if row["id"] != str(assignment_id) and row["role_code"] == "system_admin"
        ]
        if not siblings:
            ensure_system_admin_survives(db, user.id, remove_system_role=True)
    if assignment["role_code"] in {"system_admin", "asset_manager"}:
        revoked = set(policy.get("bootstrap_revoked_user_ids", []))
        revoked.add(str(user.id))
        policy["bootstrap_revoked_user_ids"] = sorted(revoked)
    manual_ids = set(policy.get("manual_role_scope_ids", []))
    manual_ids.discard(str(stored.id))
    policy["manual_role_scope_ids"] = sorted(manual_ids)
    _save_policy(db, policy)
    db.delete(stored)
    return _finish(
        db,
        access,
        user,
        action,
        payload,
        fingerprint,
        assignment,
        {
            "role_scope_id": str(assignment_id),
            "role_code": assignment["role_code"],
            "directory_permissions_preserved": True,
        },
    )


def set_user_access(db, access, user_id, payload):
    action = "permission.user.access"
    user, details, prior, fingerprint = _start(db, access, user_id, action, payload)
    if prior:
        return _user_details(db, user)
    if payload.enabled:
        person = db.get(Person, user.person_id) if user.person_id else None
        if user.person_id and (
            not person or person.archived_at or person.employment_status != "active"
        ):
            raise HTTPException(422, "离职或无效员工须先在人员管理中完成在职状态核对")
    else:
        ensure_system_admin_survives(db, user.id, disable_user=True)
        if user.id == access.user.id:
            raise HTTPException(409, "不能暂停本人访问，请由另一位系统管理员操作")
        for session in db.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
            )
        ):
            session.revoked_at = datetime.now(UTC)
    user.is_active = payload.enabled
    return _finish(
        db,
        access,
        user,
        action,
        payload,
        fingerprint,
        {"is_active": details["is_active"]},
        {"is_active": user.is_active},
    )


def grant_resource(db, access, user_id, payload):
    action = "permission.resource.grant"
    user, _, prior, fingerprint = _start(db, access, user_id, action, payload, effective=True)
    if prior:
        return _user_details(db, user)
    if not user.person_id:
        raise HTTPException(422, "资源访问必须关联在职员工档案")
    asset = db.get(Asset, payload.asset_id)
    if not _eligible_resource(db, asset):
        raise HTTPException(422, "只能选择有效公司资源，个人订阅和子账号不单独授权")
    existing = db.scalar(
        select(AccessGrant).where(
            AccessGrant.person_id == user.person_id,
            AccessGrant.asset_id == asset.id,
            AccessGrant.account_id.is_(None),
            AccessGrant.grant_type == "resource_access",
            AccessGrant.grant_role == "viewer",
            AccessGrant.archived_at.is_(None),
            AccessGrant.status == "active",
            AccessGrant.starts_at == payload.starts_at,
            AccessGrant.ends_at == payload.ends_at,
        )
    )
    if existing is None:
        existing = AccessGrant(
            asset_id=asset.id,
            person_id=user.person_id,
            grant_type="resource_access",
            grant_role="viewer",
            status="active",
            starts_at=payload.starts_at,
            ends_at=payload.ends_at,
            note=payload.reason,
        )
        db.add(existing)
        db.flush()
    return _finish(
        db,
        access,
        user,
        action,
        payload,
        fingerprint,
        None,
        {"grant_id": str(existing.id), "asset_id": str(asset.id), "grant_role": "viewer"},
    )


def revoke_resource(db, access, user_id, grant_id, payload):
    action = "permission.resource.revoke"
    lock_permission_changes(db)
    _require_admin(db, access.user)
    prior, fingerprint = audited_retry(db, access, action, payload, f"{user_id}:{grant_id}")
    user = _require_user(db, user_id)
    details = _user_details(db, user)
    if prior:
        return details
    if details["revision"] != payload.expected_revision:
        raise HTTPException(409, "员工权限已改变，请刷新后重新操作")
    grant = db.get(AccessGrant, grant_id)
    if not grant or not user.person_id or grant.person_id != user.person_id or grant.archived_at:
        raise HTTPException(422, "不能在员工页面撤销部门共享授权或其他员工的授权")
    before = {"grant_id": str(grant.id), "status": grant.status}
    grant.status = "revoked"
    grant.archived_at = datetime.now(UTC)
    return _finish(
        db,
        access,
        user,
        action,
        payload,
        fingerprint,
        before,
        {"grant_id": str(grant.id), "status": "revoked", "other_access_paths_preserved": True},
    )
