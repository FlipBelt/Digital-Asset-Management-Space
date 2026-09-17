import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.sessions import serialize_current_user, set_session_cookie
from app.core.access import AccessContext, require_global_manager
from app.core.auth import create_session, get_permission_codes, get_role_codes
from app.core.config import get_settings
from app.db.session import get_db
from app.models import (
    AppSetting,
    AuditLog,
    Department,
    DepartmentMembership,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    Person,
    Role,
    User,
    UserRoleScope,
)
from app.schemas.dingtalk import (
    DingTalkAuthCode,
    DingTalkClientDiagnostic,
    DingTalkIdentityRead,
    DingTalkLoginRequest,
    DingTalkLoginUser,
    DingTalkPersonProfileRead,
    DingTalkPublicConfig,
    DingTalkSessionRead,
    DingTalkSyncRequest,
)
from app.services.dingtalk import DingTalkClient, DingTalkDirectorySync

router = APIRouter(prefix="/dingtalk", tags=["dingtalk"])
# Exact public aliases requested by the web client.  The existing /api/v1
# endpoints remain available so current deployments keep working unchanged.
public_router = APIRouter(prefix="/api/dingtalk", tags=["dingtalk"])
logger = logging.getLogger("account_center.dingtalk")


@router.get("/status")
def connector_status() -> dict:
    settings = get_settings()
    return {
        "enabled": settings.dingtalk_enabled,
        "configured": settings.dingtalk_enabled and not settings.dingtalk_missing_settings(),
        "corp_id": settings.dingtalk_corp_id,
    }


@router.get("/config", response_model=DingTalkPublicConfig)
@public_router.get("/config", response_model=DingTalkPublicConfig)
def public_config() -> DingTalkPublicConfig:
    settings = get_settings()
    return DingTalkPublicConfig(
        corp_id=settings.dingtalk_corp_id,
        agent_id=settings.dingtalk_agent_id,
        configured=settings.dingtalk_enabled and not settings.dingtalk_missing_settings(),
    )


@router.post("/client-diagnostic", status_code=204)
def record_client_diagnostic(payload: DingTalkClientDiagnostic, request: Request) -> Response:
    logger.warning(
        "DingTalk client diagnostic phase=%s bridge=%s message=%s ua=%s ip=%s",
        payload.phase,
        payload.bridge or "none",
        payload.message.replace("\n", " ")[:1000],
        payload.user_agent[:500],
        request.client.host if request.client else "unknown",
    )
    return Response(status_code=204)


def _ensure_role_scope(db: Session, user: User, role_code: str, scope_type: str, scope_id) -> None:
    role = db.scalar(select(Role).where(Role.code == role_code))
    if role is None:
        return
    exists = db.scalar(
        select(UserRoleScope.id).where(
            UserRoleScope.user_id == user.id,
            UserRoleScope.role_id == role.id,
            UserRoleScope.scope_type == scope_type,
            UserRoleScope.scope_id == scope_id,
        )
    )
    if exists is None:
        db.add(
            UserRoleScope(
                user_id=user.id, role_id=role.id, scope_type=scope_type, scope_id=scope_id
            )
        )


def _department_from_dingtalk_detail(db: Session, profile_data: dict) -> Department | None:
    raw_department_ids = profile_data.get("dept_id_list", [])
    if not isinstance(raw_department_ids, list):
        return None
    for department_id in raw_department_ids:
        link = db.scalar(
            select(DingTalkDepartmentLink).where(
                DingTalkDepartmentLink.dingtalk_department_id == str(department_id)
            )
        )
        if link is not None:
            department = db.get(Department, link.department_id)
            if department is not None and department.archived_at is None:
                return department
    return None


def _provision_dingtalk_user(
    db: Session, profile_data: dict
) -> tuple[User, Person, DingTalkPersonProfile, str]:
    """Resolve the server-verified DingTalk user into the local identity model."""
    dingtalk_user_id = str(profile_data.get("userid") or profile_data.get("user_id") or "")
    if not dingtalk_user_id:
        raise HTTPException(status_code=401, detail="DingTalk identity was not returned")

    profile = db.scalar(
        select(DingTalkPersonProfile).where(
            DingTalkPersonProfile.dingtalk_user_id == dingtalk_user_id
        )
    )
    person = db.get(Person, profile.person_id) if profile is not None else None
    department = _department_from_dingtalk_detail(db, profile_data)
    if person is None:
        # Controlled first-login provisioning: only create a person when the
        # verified DingTalk department is already linked to this company.
        if department is None:
            raise HTTPException(
                status_code=403,
                detail="DingTalk organization has not been synchronized for this user",
            )
        employee_no = str(profile_data.get("job_number") or f"DT-{dingtalk_user_id}")[:50]
        person = db.scalar(
            select(Person).where(
                Person.legal_entity_id == department.legal_entity_id,
                Person.employee_no == employee_no,
            )
        )
        if person is None:
            person = Person(
                legal_entity_id=department.legal_entity_id,
                department_id=department.id,
                employee_no=employee_no,
                display_name=str(profile_data.get("name") or dingtalk_user_id)[:100],
                email=profile_data.get("email"),
                employment_status="active",
            )
            db.add(person)
            db.flush()
        if profile is None:
            profile = DingTalkPersonProfile(person_id=person.id, dingtalk_user_id=dingtalk_user_id)
            db.add(profile)
    assert profile is not None

    person.display_name = str(profile_data.get("name") or person.display_name)[:100]
    person.email = profile_data.get("email") or person.email
    if department is not None:
        person.department_id = department.id
    profile.union_id = (
        profile_data.get("unionid") or profile_data.get("union_id") or profile.union_id
    )
    profile.job_title = (
        profile_data.get("title") or profile_data.get("position") or profile.job_title
    )
    profile.profile_data = {
        **(profile.profile_data or {}),
        "avatar": profile_data.get("avatar") or profile_data.get("avatar_url"),
        "department_ids": profile_data.get("dept_id_list", []),
    }

    user = db.scalar(select(User).where(User.person_id == person.id))
    if user is None:
        user = User(
            person_id=person.id,
            username=f"dingtalk:{dingtalk_user_id}".lower(),
            password_hash="!dingtalk-sso-only!",
            is_active=True,
        )
        db.add(user)
        db.flush()
    _ensure_role_scope(db, user, "employee", "company", person.legal_entity_id)
    # Compatibility for the pre-SSO bootstrap setting: this value lives in
    # server-side configuration and is only evaluated after DingTalk has
    # verified the identity and stored its stable userid mapping.  It is not
    # driven by a request header, browser storage, or client supplied name.
    bootstrap = db.scalar(select(AppSetting).where(AppSetting.key == "organization_bootstrap"))
    configured_candidate = (
        (bootstrap.value or {}).get("initial_administrator_candidate") if bootstrap else None
    )
    if configured_candidate and person.display_name == configured_candidate:
        _ensure_role_scope(db, user, "system_admin", "company", person.legal_entity_id)
        _ensure_role_scope(db, user, "asset_manager", "company", person.legal_entity_id)
    return user, person, profile, dingtalk_user_id


def _identity_read(
    person: Person, profile: DingTalkPersonProfile, db: Session
) -> DingTalkIdentityRead:
    is_department_manager = db.scalar(
        select(DepartmentMembership.id).where(
            DepartmentMembership.person_id == person.id,
            DepartmentMembership.is_active.is_(True),
            DepartmentMembership.is_manager.is_(True),
        )
    )
    return DingTalkIdentityRead(
        person_id=person.id,
        display_name=person.display_name,
        department_id=person.department_id,
        job_title=profile.job_title,
        is_department_manager=is_department_manager is not None,
    )


def _create_dingtalk_session(
    auth_code: str, request: Request, response: Response, db: Session
) -> tuple[User, Person, DingTalkPersonProfile, str, object]:
    profile_data = DingTalkClient().user_from_auth_code(auth_code)
    user, person, profile, _ = _provision_dingtalk_user(db, profile_data)
    if not user.is_active or user.archived_at is not None or person.archived_at is not None:
        raise HTTPException(status_code=403, detail="DingTalk user is not active in this system")
    manager_departments = list(
        db.scalars(
            select(DepartmentMembership.department_id).where(
                DepartmentMembership.person_id == person.id,
                DepartmentMembership.is_active.is_(True),
                DepartmentMembership.is_manager.is_(True),
            )
        )
    )
    for department_id in manager_departments:
        _ensure_role_scope(db, user, "department_manager", "department", department_id)
    db.flush()
    token, session = create_session(db, user, request.headers.get("user-agent", "")[:300] or None)
    set_session_cookie(response, token)
    db.add(
        AuditLog(
            actor_user_id=user.id,
            action="session.dingtalk_login",
            object_type="user",
            object_id=user.id,
        )
    )
    db.commit()
    return user, person, profile, token, session


def _primary_role(roles: list[str]) -> str:
    for role in (
        "system_admin",
        "asset_manager",
        "department_manager",
        "auditor",
        "executive",
        "employee",
    ):
        if role in roles:
            return role
    return "employee"


@router.post("/login", response_model=dict[str, DingTalkLoginUser])
@public_router.post("/login", response_model=dict[str, DingTalkLoginUser])
def login_with_dingtalk(
    payload: DingTalkLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict[str, DingTalkLoginUser]:
    """Exchange a one-time authCode and return the application's own session token."""
    user, person, profile, token, _ = _create_dingtalk_session(
        payload.auth_code, request, response, db
    )
    roles = get_role_codes(db, user.id)
    department = db.get(Department, person.department_id) if person.department_id else None
    return {
        "user": DingTalkLoginUser(
            ding_user_id=profile.dingtalk_user_id,
            name=person.display_name,
            avatar=(profile.profile_data or {}).get("avatar"),
            department=department.name if department else None,
            role=_primary_role(roles),
            roles=roles,
            permissions=get_permission_codes(db, user.id),
            session_token=token,
        )
    }


@router.post("/identity", response_model=DingTalkSessionRead)
def identify_dingtalk_user(
    payload: DingTalkAuthCode,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> DingTalkSessionRead:
    """Exchange a DingTalk auth code, provision roles, and issue the server session cookie."""
    user, person, profile, _, session = _create_dingtalk_session(
        payload.auth_code, request, response, db
    )
    return DingTalkSessionRead(
        user=serialize_current_user(db, user, session),
        identity=_identity_read(person, profile, db),
        expires_at=session.expires_at,
    )


@router.post("/sync")
def sync_directory(
    payload: DingTalkSyncRequest,
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_global_manager),
) -> dict:
    result = DingTalkDirectorySync(db, DingTalkClient()).run(payload.legal_entity_id)
    return {"status": "success", **result.as_dict()}


@router.get(
    "/profiles",
    response_model=list[DingTalkPersonProfileRead],
)
def list_profiles(
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_global_manager),
) -> list[DingTalkPersonProfile]:
    return list(
        db.scalars(select(DingTalkPersonProfile).order_by(DingTalkPersonProfile.updated_at.desc()))
    )
