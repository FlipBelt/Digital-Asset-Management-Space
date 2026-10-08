"""No browser session fallback: delegated tokens only work on /agent routes."""

import hashlib
import secrets
import threading
import time
from collections import defaultdict, deque
from dataclasses import replace
from datetime import UTC, datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, get_access_context
from app.core.config import get_settings
from app.db.session import get_db
from app.models import AgentGrant, Person, User

SCOPES = ("asset:read", "asset:draft", "incubation:read", "incubation:write")
_rate_lock = threading.Lock()
_buckets: dict[str, deque] = defaultdict(deque)


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def now() -> datetime:
    return datetime.now(UTC)


def enabled():
    if not get_settings().agent_connector_enabled:
        raise HTTPException(404, "连接器尚未启用")


def frontend_url(path: str) -> str:
    # A validated administrator setting, never request Host or client input.
    return get_settings().agent_frontend_url.rstrip("/") + "/" + path.lstrip("/")


def throttle(key: str, limit: int, window: int = 600):
    clock = time.monotonic()
    with _rate_lock:
        if len(_buckets) >= 2048:
            for old_key in list(_buckets):
                if not _buckets[old_key] or _buckets[old_key][-1] < clock - 600:
                    del _buckets[old_key]
        if len(_buckets) >= 2048 and key not in _buckets:
            raise HTTPException(429, "请求过多，请稍后重试")
        bucket = _buckets[key]
        while bucket and bucket[0] < clock - window:
            bucket.popleft()
        if len(bucket) >= limit:
            raise HTTPException(429, "请求过多，请稍后重试", headers={"Retry-After": str(window)})
        bucket.append(clock)


def random_code() -> str:
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))


def employee_access(db: Session, user: User) -> AccessContext:
    person = db.get(Person, user.person_id) if user.person_id else None
    if (
        not user.is_active
        or user.archived_at is not None
        or person is None
        or person.archived_at is not None
        or person.employment_status != "active"
    ):
        raise HTTPException(403, "当前身份不能使用连接器")
    original = get_access_context(user, db)
    if not original.has_permission("asset.read") or not original.has_permission("asset.write"):
        raise HTTPException(403, "当前身份没有成果登记权限")
    # The connector has ordinary employee visibility even for administrator accounts.
    return replace(original, roles=frozenset({"employee"}), department_scopes=frozenset())


def agent_access(request: Request, db: Session = Depends(get_db)) -> AccessContext:
    enabled()
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer agt_") or len(header) > 200:
        raise HTTPException(401, "请重新授权连接器", headers={"WWW-Authenticate": "Bearer"})
    token = header.removeprefix("Bearer ")
    grant = db.scalar(
        select(AgentGrant).where(AgentGrant.token_hash == digest(token)).with_for_update()
    )
    if (
        grant is None
        or grant.revoked_at is not None
        or grant.token_expires_at is None
        or grant.token_expires_at <= now()
    ):
        raise HTTPException(401, "请重新授权连接器", headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, grant.user_id)
    if user is None:
        raise HTTPException(401, "请重新授权连接器")
    request.state.agent_grant_id = grant.id
    throttle(f"agent:{grant.id}", 120, 60)
    return employee_access(db, user)
