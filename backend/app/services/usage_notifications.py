"""Threshold monitoring and scheduled DingTalk summaries for platform connections."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ConnectorDefinition,
    DingTalkPersonProfile,
    ProviderConnection,
    UsageAlertRule,
    UsageNotificationLog,
    UsageNotificationSchedule,
)
from app.services.dingtalk import DingTalkClient
from app.services.usage_connectors import PLATFORM_CATALOG, platform_code_for, sync_connection


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _current_metric(
    connection: ProviderConnection, metric_key: str
) -> tuple[Decimal | None, str | None]:
    snapshot = (connection.configuration or {}).get("latest_snapshot")
    if not isinstance(snapshot, dict):
        return None, None
    if metric_key == "balance":
        values = snapshot.get("balances", [])
        if not isinstance(values, list):
            return None, None
        for item in values:
            if not isinstance(item, dict):
                continue
            raw = (
                item.get("value")
                if item.get("key") == "AvailableAmount"
                else item.get("total_balance")
            )
            value = _decimal(raw)
            if value is not None:
                return value, str(item.get("currency") or snapshot.get("currency") or "") or None
    if metric_key == "quota_remaining":
        values = snapshot.get("items", [])
        remaining = [_decimal(item.get("remaining")) for item in values if isinstance(item, dict)]
        parsed = [value for value in remaining if value is not None]
        return (min(parsed), None) if parsed else (None, None)
    return None, None


def _recipient_dingtalk_ids(db: Session, person_ids: list[UUID | str]) -> list[str]:
    normalized = [UUID(str(item)) for item in person_ids]
    if not normalized:
        return []
    return list(
        db.scalars(
            select(DingTalkPersonProfile.dingtalk_user_id).where(
                DingTalkPersonProfile.person_id.in_(normalized)
            )
        )
    )


def _log(
    db: Session,
    *,
    event_type: str,
    status: str,
    summary: str,
    recipients: int,
    detail: dict[str, Any],
    rule: UsageAlertRule | None = None,
    schedule: UsageNotificationSchedule | None = None,
    connection: ProviderConnection | None = None,
) -> None:
    db.add(
        UsageNotificationLog(
            event_type=event_type,
            status=status,
            message_summary=summary,
            recipient_count=recipients,
            detail=detail,
            usage_alert_rule_id=rule.id if rule else None,
            usage_notification_schedule_id=schedule.id if schedule else None,
            provider_connection_id=connection.id if connection else None,
        )
    )


def _send(db: Session, recipients: list[UUID | str], content: str) -> int:
    dingtalk_ids = _recipient_dingtalk_ids(db, recipients)
    DingTalkClient().send_work_notification(dingtalk_ids, content)
    return len(dingtalk_ids)


def evaluate_alerts(db: Session) -> dict[str, int]:
    result = {"evaluated": 0, "sent": 0, "failed": 0}
    rules = db.scalars(
        select(UsageAlertRule).where(
            UsageAlertRule.archived_at.is_(None), UsageAlertRule.enabled.is_(True)
        )
    )
    for rule in rules:
        connection = db.get(ProviderConnection, rule.provider_connection_id)
        if (
            connection is None
            or connection.archived_at is not None
            or connection.status != "enabled"
        ):
            continue
        value, currency = _current_metric(connection, rule.metric_key)
        if value is None:
            continue
        result["evaluated"] += 1
        state = "breached" if value < rule.threshold else "normal"
        is_new_breach = state == "breached" and rule.last_state != "breached"
        rule.last_state = state
        if not is_new_breach:
            continue
        display_currency = currency or rule.currency
        unit = f" {display_currency}" if display_currency else ""
        content = (
            f"【集团数字资产中心】额度告警\n{connection.name}\n"
            f"当前{rule.metric_key}：{value}{unit}\n"
            f"告警阈值：{rule.threshold}{unit}\n"
            "请登录服务与用量查看详情。"
        )
        try:
            count = _send(db, list(rule.recipient_person_ids or []), content)
        except Exception as exc:  # Preserve the monitoring result even if DingTalk is unavailable.
            result["failed"] += 1
            _log(
                db,
                event_type="delivery_failed",
                status="failed",
                summary=f"{connection.name} 阈值告警发送失败",
                recipients=0,
                detail={"error": str(exc), "metric_key": rule.metric_key, "value": str(value)},
                rule=rule,
                connection=connection,
            )
        else:
            result["sent"] += 1
            rule.last_notified_at = datetime.now(UTC)
            _log(
                db,
                event_type="threshold_breach",
                status="sent",
                summary=f"{connection.name} 低于 {rule.threshold} 的阈值告警",
                recipients=count,
                detail={
                    "metric_key": rule.metric_key,
                    "value": str(value),
                    "threshold": str(rule.threshold),
                },
                rule=rule,
                connection=connection,
            )
    db.commit()
    return result


def _summary_line(connection: ProviderConnection, code: str) -> str:
    snapshot = (connection.configuration or {}).get("latest_snapshot")
    observed_at = (connection.configuration or {}).get("latest_snapshot_at") or "未同步"
    if not isinstance(snapshot, dict):
        return f"- {connection.name}（{code}）：尚无可发送的同步数据"
    if code == "minimax":
        values = snapshot.get("items", [])
        detail = "；".join(
            f"{item.get('label')}={item.get('remaining')}"
            for item in values[:6]
            if isinstance(item, dict)
        )
    else:
        values = snapshot.get("balances", [])
        detail = "；".join(
            f"{item.get('label') or item.get('currency')}="
            f"{item.get('value') or item.get('total_balance')}"
            for item in values[:6]
            if isinstance(item, dict)
        )
    return f"- {connection.name}（{code}）：{detail or '未返回可展示数值'}；同步 {observed_at}"


def run_due_schedules(db: Session, now: datetime | None = None) -> dict[str, int]:
    result = {"due": 0, "sent": 0, "failed": 0}
    for schedule in db.scalars(
        select(UsageNotificationSchedule).where(
            UsageNotificationSchedule.archived_at.is_(None),
            UsageNotificationSchedule.enabled.is_(True),
        )
    ):
        try:
            local_now = (now or datetime.now(UTC)).astimezone(ZoneInfo(schedule.timezone))
        except Exception:
            local_now = (now or datetime.now(UTC)).astimezone(ZoneInfo("Asia/Shanghai"))
        if (
            schedule.last_sent_on == local_now.date()
            or local_now.strftime("%H:%M") != schedule.time_of_day
        ):
            continue
        result["due"] += 1
        connection_ids = [UUID(str(item)) for item in schedule.connection_ids or []]
        rows = [db.get(ProviderConnection, item) for item in connection_ids]
        lines = ["【集团数字资产中心】平台余额与额度定时汇总"]
        for connection in rows:
            if connection is None or connection.archived_at is not None:
                continue
            lines.append(_summary_line(connection, platform_code_for(connection, db)))
        content = "\n".join(lines)
        try:
            count = _send(db, list(schedule.recipient_person_ids or []), content)
        except Exception as exc:
            result["failed"] += 1
            _log(
                db,
                event_type="delivery_failed",
                status="failed",
                summary=f"{schedule.name} 定时汇总发送失败",
                recipients=0,
                detail={"error": str(exc)},
                schedule=schedule,
            )
        else:
            result["sent"] += 1
            schedule.last_sent_on = local_now.date()
            _log(
                db,
                event_type="daily_digest",
                status="sent",
                summary=schedule.name,
                recipients=count,
                detail={"connection_count": len(lines) - 1},
                schedule=schedule,
            )
    db.commit()
    return result


def sync_due_connections(db: Session, now: datetime | None = None) -> int:
    current = now or datetime.now(UTC)
    synced = 0
    rows = list(db.scalars(
        select(ProviderConnection)
        .join(ConnectorDefinition)
        .where(
            ProviderConnection.archived_at.is_(None),
            ProviderConnection.status == "enabled",
            ConnectorDefinition.code.in_(PLATFORM_CATALOG),
        )
    ))
    # Materialize the query and release its connection before provider I/O.
    # sync_connection also commits before each external request.
    db.commit()
    for connection in rows:
        interval = int((connection.configuration or {}).get("sync_interval_minutes", 60) or 60)
        last = connection.last_synced_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last is not None and (current - last).total_seconds() < interval * 60:
            continue
        sync_connection(db, connection, platform_code_for(connection, db))
        synced += 1
    return synced


def run_monitoring_cycle(db: Session) -> dict[str, int]:
    synced = sync_due_connections(db)
    alerts = evaluate_alerts(db)
    schedules = run_due_schedules(db)
    return {
        "synced": synced,
        **{f"alerts_{key}": value for key, value in alerts.items()},
        **{f"schedules_{key}": value for key, value in schedules.items()},
    }
