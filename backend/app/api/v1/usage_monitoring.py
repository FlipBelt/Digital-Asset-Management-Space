from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, get_access_context, require_asset_write
from app.db.session import get_db
from app.models import (
    ConnectorDefinition,
    DingTalkPersonProfile,
    ProviderConnection,
    UsageAlertRule,
    UsageNotificationLog,
    UsageNotificationSchedule,
)
from app.schemas.usage_alerts import (
    UsageAlertRuleRead,
    UsageAlertRuleWrite,
    UsageNotificationLogRead,
    UsageNotificationScheduleRead,
    UsageNotificationScheduleWrite,
)
from app.services.personal_subscription_policy import personal_subscription_connection_clause
from app.services.usage_connectors import PLATFORM_CATALOG, platform_code_for
from app.services.usage_notifications import run_monitoring_cycle

router = APIRouter(prefix="/usage-monitoring", tags=["usage-monitoring"])


def _hidden_connection_ids(db: Session, access: AccessContext) -> set[UUID]:
    if access.is_global_manager:
        return set()
    return set(
        db.scalars(
            select(ProviderConnection.id).where(
                ~personal_subscription_connection_clause(access.person_id)
            )
        )
    )


def _require_connection_privacy(db: Session, connection_id: UUID, access: AccessContext) -> None:
    if not access.is_global_manager and db.scalar(
        select(ProviderConnection.id).where(
            ProviderConnection.id == connection_id,
            ~personal_subscription_connection_clause(access.person_id),
        )
    ):
        raise HTTPException(status_code=404, detail="平台连接不存在")


def _connection(db: Session, connection_id: UUID, access: AccessContext) -> ProviderConnection:
    _require_connection_privacy(db, connection_id, access)
    item = db.get(ProviderConnection, connection_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(status_code=422, detail="平台连接不存在")
    if platform_code_for(item, db) not in PLATFORM_CATALOG:
        raise HTTPException(status_code=422, detail="该连接不支持用量监控")
    return item


def _validate_recipients(db: Session, person_ids: list[UUID]) -> None:
    found = set(
        db.scalars(
            select(DingTalkPersonProfile.person_id).where(
                DingTalkPersonProfile.person_id.in_(person_ids)
            )
        )
    )
    if set(person_ids) - found:
        raise HTTPException(status_code=422, detail="收件人必须已绑定钉钉身份")


def _rule_read(item: UsageAlertRule) -> dict:
    return {
        "id": item.id,
        "provider_connection_id": item.provider_connection_id,
        "name": item.name,
        "metric_key": item.metric_key,
        "threshold": item.threshold,
        "currency": item.currency,
        "recipient_person_ids": item.recipient_person_ids,
        "enabled": item.enabled,
        "last_state": item.last_state,
        "last_notified_at": item.last_notified_at,
    }


def _schedule_read(item: UsageNotificationSchedule) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "connection_ids": item.connection_ids,
        "recipient_person_ids": item.recipient_person_ids,
        "time_of_day": item.time_of_day,
        "timezone": item.timezone,
        "enabled": item.enabled,
        "last_sent_on": item.last_sent_on.isoformat() if item.last_sent_on else None,
    }


@router.get("/overview")
def overview(
    db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)
) -> dict:
    connections = [
        item
        for item in db.scalars(
            select(ProviderConnection)
            .join(ConnectorDefinition)
            .where(
                ProviderConnection.archived_at.is_(None),
                ConnectorDefinition.code.in_(PLATFORM_CATALOG),
                True
                if access.is_global_manager
                else personal_subscription_connection_clause(access.person_id),
            )
            .order_by(ProviderConnection.name)
        )
    ]
    people = list(
        db.execute(
            select(DingTalkPersonProfile.person_id, DingTalkPersonProfile.dingtalk_user_id)
        ).mappings()
    )
    return {
        "connections": [
            {
                "id": item.id,
                "name": item.name,
                "platform_code": platform_code_for(item, db),
                "status": item.status,
                "latest_snapshot_at": (item.configuration or {}).get("latest_snapshot_at"),
            }
            for item in connections
        ],
        "dingtalk_recipient_person_ids": [row["person_id"] for row in people],
    }


@router.get("/rules", response_model=list[UsageAlertRuleRead])
def list_rules(
    db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)
) -> list[dict]:
    return [
        _rule_read(item)
        for item in db.scalars(
            select(UsageAlertRule)
            .where(
                UsageAlertRule.archived_at.is_(None),
                UsageAlertRule.provider_connection_id.not_in(_hidden_connection_ids(db, access)),
            )
            .order_by(UsageAlertRule.created_at.desc())
        )
    ]


@router.post("/rules", response_model=UsageAlertRuleRead, status_code=status.HTTP_201_CREATED)
def create_rule(
    payload: UsageAlertRuleWrite,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> dict:
    _connection(db, payload.provider_connection_id, access)
    _validate_recipients(db, payload.recipient_person_ids)
    data = payload.model_dump()
    data["recipient_person_ids"] = [str(item) for item in payload.recipient_person_ids]
    item = UsageAlertRule(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _rule_read(item)


@router.put("/rules/{rule_id}", response_model=UsageAlertRuleRead)
def update_rule(
    rule_id: UUID,
    payload: UsageAlertRuleWrite,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> dict:
    item = db.get(UsageAlertRule, rule_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    _require_connection_privacy(db, item.provider_connection_id, access)
    _connection(db, payload.provider_connection_id, access)
    _validate_recipients(db, payload.recipient_person_ids)
    data = payload.model_dump()
    data["recipient_person_ids"] = [str(item) for item in payload.recipient_person_ids]
    for key, value in data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _rule_read(item)


@router.get("/schedules", response_model=list[UsageNotificationScheduleRead])
def list_schedules(
    db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)
) -> list[dict]:
    hidden = {str(item) for item in _hidden_connection_ids(db, access)}
    return [
        _schedule_read(item)
        for item in db.scalars(
            select(UsageNotificationSchedule)
            .where(UsageNotificationSchedule.archived_at.is_(None))
            .order_by(UsageNotificationSchedule.created_at.desc())
        )
        if not hidden.intersection(item.connection_ids)
    ]


@router.post(
    "/schedules", response_model=UsageNotificationScheduleRead, status_code=status.HTTP_201_CREATED
)
def create_schedule(
    payload: UsageNotificationScheduleWrite,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> dict:
    for connection_id in payload.connection_ids:
        _connection(db, connection_id, access)
    _validate_recipients(db, payload.recipient_person_ids)
    data = payload.model_dump()
    data["connection_ids"] = [str(item) for item in payload.connection_ids]
    data["recipient_person_ids"] = [str(item) for item in payload.recipient_person_ids]
    item = UsageNotificationSchedule(**data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return _schedule_read(item)


@router.put("/schedules/{schedule_id}", response_model=UsageNotificationScheduleRead)
def update_schedule(
    schedule_id: UUID,
    payload: UsageNotificationScheduleWrite,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> dict:
    item = db.get(UsageNotificationSchedule, schedule_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(status_code=404, detail="定时发送规则不存在")
    hidden = {str(identity) for identity in _hidden_connection_ids(db, access)}
    if hidden.intersection(item.connection_ids):
        raise HTTPException(status_code=404, detail="定时发送规则不存在")
    for connection_id in payload.connection_ids:
        _connection(db, connection_id, access)
    _validate_recipients(db, payload.recipient_person_ids)
    data = payload.model_dump()
    data["connection_ids"] = [str(item) for item in payload.connection_ids]
    data["recipient_person_ids"] = [str(item) for item in payload.recipient_person_ids]
    for key, value in data.items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return _schedule_read(item)


@router.get("/logs", response_model=list[UsageNotificationLogRead])
def list_logs(
    db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)
) -> list[UsageNotificationLog]:
    hidden = _hidden_connection_ids(db, access)
    hidden_strings = {str(identity) for identity in hidden}
    hidden_rules = select(UsageAlertRule.id).where(
        UsageAlertRule.provider_connection_id.in_(hidden)
    )
    hidden_schedules = {
        identity
        for identity, connection_ids in db.execute(
            select(UsageNotificationSchedule.id, UsageNotificationSchedule.connection_ids)
        )
        if hidden_strings.intersection(connection_ids)
    }
    return list(
        db.scalars(
            select(UsageNotificationLog)
            .where(
                or_(
                    UsageNotificationLog.provider_connection_id.is_(None),
                    UsageNotificationLog.provider_connection_id.not_in(hidden),
                ),
                or_(
                    UsageNotificationLog.usage_alert_rule_id.is_(None),
                    UsageNotificationLog.usage_alert_rule_id.not_in(hidden_rules),
                ),
                or_(
                    UsageNotificationLog.usage_notification_schedule_id.is_(None),
                    UsageNotificationLog.usage_notification_schedule_id.not_in(hidden_schedules),
                ),
            )
            .order_by(UsageNotificationLog.created_at.desc())
            .limit(100)
        )
    )


@router.post("/run")
def run_now(
    db: Session = Depends(get_db), access: AccessContext = Depends(require_asset_write)
) -> dict[str, int]:
    # The existing monitoring cycle is global and cannot safely run on a filtered subset.
    if _hidden_connection_ids(db, access):
        raise HTTPException(status_code=403, detail="包含无权查看的个人订阅，请由管理员执行监控")
    return run_monitoring_cycle(db)
