"""Serialize auditable mutations by actor/request and reject changed retries."""

from fastapi import HTTPException
from sqlalchemy import func, select

from app.models import AuditLog
from app.services.service_catalog import digest


def audited_retry(db, access, action, payload, target):
    fingerprint = digest({**payload.model_dump(mode="json"), "target": str(target)})
    if db.bind.dialect.name == "postgresql":
        key = int(
            digest({"actor": str(access.user.id), "request": str(payload.request_id)})[:15], 16
        )
        db.execute(select(func.pg_advisory_xact_lock(key)))
    previous = db.scalar(
        select(AuditLog).where(
            AuditLog.actor_user_id == access.user.id,
            AuditLog.action == action,
            AuditLog.request_id == str(payload.request_id),
        )
    )
    if previous and (previous.after_data or {}).get("request_digest") != fingerprint:
        raise HTTPException(409, "同一请求编号的内容已改变，请重新提交")
    return previous, fingerprint
