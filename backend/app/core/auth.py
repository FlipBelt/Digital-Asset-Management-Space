from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models import Permission, Role, RolePermission, User, UserRoleScope, UserSession

_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (InvalidHashError, VerifyMismatchError):
        return False


def token_hash(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User, device_summary: str | None) -> tuple[str, UserSession]:
    settings = get_settings()
    token = token_urlsafe(48)
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash(token),
        csrf_token=token_urlsafe(32),
        expires_at=datetime.now(UTC) + timedelta(hours=settings.session_ttl_hours),
        device_summary=device_summary,
    )
    db.add(session)
    user.last_login_at = datetime.now(UTC)
    db.commit()
    db.refresh(session)
    return token, session


def get_role_codes(db: Session, user_id: UUID) -> list[str]:
    return list(
        db.scalars(
            select(Role.code)
            .join(UserRoleScope, UserRoleScope.role_id == Role.id)
            .where(UserRoleScope.user_id == user_id)
            .distinct()
        )
    )


def get_permission_codes(db: Session, user_id: UUID) -> list[str]:
    """Resolve permissions from the current database state on every request."""
    roles = set(get_role_codes(db, user_id))
    # Test operators keep their normal identity record but receive the full
    # permission catalog in the isolated service.  This keeps the session
    # payload consistent with the server-side AccessContext test override.
    if get_settings().app_env.lower() == "test" or "system_admin" in roles:
        return list(db.scalars(select(Permission.code).order_by(Permission.code)))
    return list(
        db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(Role, Role.id == RolePermission.role_id)
            .join(UserRoleScope, UserRoleScope.role_id == Role.id)
            .where(UserRoleScope.user_id == user_id)
            .distinct()
            .order_by(Permission.code)
        )
    )


def session_token_from_request(request: Request) -> tuple[str | None, str | None]:
    """Prefer the explicit PM session header and preserve the legacy cookie path."""
    header_token = request.headers.get("x-pm-session", "").strip()
    if header_token:
        return header_token[:512], "header"
    cookie_token = request.cookies.get(get_settings().session_cookie_name)
    return cookie_token, "cookie" if cookie_token else None


def get_current_session(
    request: Request, db: Session = Depends(get_db)
) -> tuple[User, UserSession]:
    token, source = session_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="authentication required"
        )
    session = db.scalar(
        select(UserSession).where(
            UserSession.token_hash == token_hash(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="session expired")
    user = db.get(User, session.user_id)
    if user is None or not user.is_active or user.archived_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user is inactive")
    # The explicit session header is not automatically attached by a browser to
    # cross-site form submissions.  Cookie compatibility remains protected by
    # CSRF validation for every state-changing API request.
    if request.method.upper() not in {"GET", "HEAD", "OPTIONS"} and source != "header":
        supplied = request.headers.get("x-csrf-token")
        if not supplied or supplied != session.csrf_token:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid CSRF token")
    return user, session


def require_authenticated(current: tuple[User, UserSession] = Depends(get_current_session)) -> User:
    return current[0]


def operator_from_request(
    current: tuple[User, UserSession] = Depends(get_current_session),
) -> User:
    """Trusted operator identity for API handlers; never derived from client claims."""
    return current[0]


def require_csrf(
    request: Request, current: tuple[User, UserSession] = Depends(get_current_session)
) -> User:
    _, source = session_token_from_request(request)
    if source == "header":
        return current[0]
    supplied = request.headers.get("x-csrf-token")
    if not supplied or supplied != current[1].csrf_token:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid CSRF token")
    return current[0]


def require_system_admin(
    current: User = Depends(require_authenticated), db: Session = Depends(get_db)
) -> User:
    # The isolated test service is deliberately open to authenticated
    # operators so testers can exercise admin/configuration APIs without
    # changing production role assignments.  The environment is server-side
    # configuration and cannot be enabled by request headers.
    if (
        get_settings().app_env.lower() != "test"
        and "system_admin" not in get_role_codes(db, current.id)
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="system administrator required"
        )
    return current


def require_developer_supervisor(
    current: User = Depends(require_authenticated), db: Session = Depends(get_db)
) -> User:
    """Gate the out-of-band developer control plane.

    A system administrator alone is deliberately insufficient: the operator
    must also hold the dedicated role and match the server-side allowlist.
    """
    configured_username = (get_settings().developer_supervisor_username or "").strip()
    roles = set(get_role_codes(db, current.id))
    if get_settings().app_env.lower() == "test":
        return current
    if (
        not configured_username
        or current.username != configured_username
        or "developer_supervisor" not in roles
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="developer control plane access required",
        )
    return current
