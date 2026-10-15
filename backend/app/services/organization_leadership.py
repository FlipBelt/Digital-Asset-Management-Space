from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    Department,
    DepartmentMembership,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    Person,
    Role,
    User,
    UserRoleScope,
)

POLICY_KEY = "dingtalk_leadership_policy"
LEADERSHIP_ROLES = {"department_manager", "group_leader"}


def leadership_policy(db: Session) -> dict:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == POLICY_KEY))
    value = setting.value if setting and isinstance(setting.value, dict) else {}
    if not isinstance(value.get("department_kinds"), dict) or not value.get("legal_entity_id"):
        return {}
    return value


def department_leadership_role(department: Department, policy: dict) -> str | None:
    if not policy:
        return "department_manager"
    if str(department.legal_entity_id) != policy.get("legal_entity_id"):
        return "department_manager"
    kind = policy["department_kinds"].get(department.code)
    # Unclassified source units never acquire supervisor privileges automatically.
    return {"department": "department_manager", "group": "group_leader"}.get(kind)


def resolved_role_scopes(db: Session, user_id: UUID) -> list[tuple[str, str, UUID | None]]:
    rows = list(
        db.execute(
            select(Role.code, UserRoleScope.scope_type, UserRoleScope.scope_id)
            .join(UserRoleScope, UserRoleScope.role_id == Role.id)
            .where(UserRoleScope.user_id == user_id)
        ).all()
    )
    policy = leadership_policy(db)
    user = db.get(User, user_id)
    person = db.get(Person, user.person_id) if user and user.person_id else None
    profile = (
        db.scalar(select(DingTalkPersonProfile).where(DingTalkPersonProfile.person_id == person.id))
        if person
        else None
    )
    if (
        not policy
        or not person
        or not profile
        or str(person.legal_entity_id) != policy["legal_entity_id"]
    ):
        return [tuple(row) for row in rows]
    source_departments = {
        d.id: d
        for d in db.scalars(
            select(Department)
            .join(DingTalkDepartmentLink, DingTalkDepartmentLink.department_id == Department.id)
            .where(Department.legal_entity_id == person.legal_entity_id)
        )
    }
    # Preserve stored grants for rollback. For linked DingTalk units the current
    # membership and confirmed unit kind determine their effective leadership.
    effective = {
        tuple(row)
        for row in rows
        if not (
            row[0] in LEADERSHIP_ROLES and row[1] == "department" and row[2] in source_departments
        )
    }
    if (profile.profile_data or {}).get("directory_status") == "not_in_current_directory":
        return [tuple(row) for row in rows]
    for membership in db.scalars(
        select(DepartmentMembership).where(
            DepartmentMembership.person_id == person.id,
            DepartmentMembership.is_active.is_(True),
            DepartmentMembership.is_manager.is_(True),
        )
    ):
        department = source_departments.get(membership.department_id)
        if not department or department.archived_at is not None or department.status != "active":
            continue
        role = department_leadership_role(department, policy)
        if role:
            effective.add((role, "department", department.id))
    return list(effective)
