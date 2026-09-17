from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import (
    create_session,
    get_current_session,
    get_permission_codes,
    get_role_codes,
    require_csrf,
    session_token_from_request,
    token_hash,
    verify_password,
)
from app.core.config import get_settings
from app.db.session import get_db
from app.models import AuditLog, DingTalkPersonProfile, Person, User, UserSession
from app.schemas.auth import CurrentUserRead, SessionCreate, SessionRead

router = APIRouter(prefix="/sessions", tags=["sessions"])


def serialize_current_user(db: Session, user: User, session: UserSession) -> CurrentUserRead:
    person = db.get(Person, user.person_id) if user.person_id else None
    profile = (
        db.scalar(
            select(DingTalkPersonProfile).where(DingTalkPersonProfile.person_id == user.person_id)
        )
        if user.person_id
        else None
    )
    return CurrentUserRead(
        id=user.id,
        username=user.username,
        person_id=user.person_id,
        display_name=person.display_name if person else None,
        department_id=person.department_id if person else None,
        job_title=profile.job_title if profile else None,
        roles=get_role_codes(db, user.id),
        permissions=get_permission_codes(db, user.id),
        csrf_token=session.csrf_token,
    )


def set_session_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.session_cookie_name,
        value=token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.session_secure_cookie,
        samesite="lax",
        path="/",
    )


@router.post("", response_model=SessionRead)
def login(
    payload: SessionCreate, request: Request, response: Response, db: Session = Depends(get_db)
) -> SessionRead:
    user = db.scalar(select(User).where(User.username == payload.username.strip().lower()))
    if user is None or not user.is_active or user.archived_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password"
        )
    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid username or password"
        )
    token, session = create_session(db, user, request.headers.get("user-agent", "")[:300] or None)
    set_session_cookie(response, token)
    db.add(
        AuditLog(
            actor_user_id=user.id, action="session.login", object_type="user", object_id=user.id
        )
    )
    db.commit()
    return SessionRead(
        user=serialize_current_user(db, user, session),
        expires_at=session.expires_at,
        session_token=token,
    )


@router.get("/current", response_model=CurrentUserRead)
def current_session(
    current: tuple[User, UserSession] = Depends(get_current_session), db: Session = Depends(get_db)
) -> CurrentUserRead:
    return serialize_current_user(db, *current)


@router.delete("/current", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request, _: User = Depends(require_csrf), db: Session = Depends(get_db)
) -> Response:
    token, _source = session_token_from_request(request)
    session = db.scalar(
        select(UserSession).where(UserSession.token_hash == token_hash(token or ""))
    )
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.add(
            AuditLog(
                actor_user_id=session.user_id,
                action="session.logout",
                object_type="user",
                object_id=session.user_id,
            )
        )
        db.commit()
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return response
