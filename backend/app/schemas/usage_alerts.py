from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class UsageAlertRuleWrite(BaseModel):
    provider_connection_id: UUID
    name: str = Field(min_length=1, max_length=200)
    metric_key: str = Field(default="balance", min_length=1, max_length=100)
    threshold: Decimal
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    recipient_person_ids: list[UUID] = Field(min_length=1, max_length=50)
    enabled: bool = True


class UsageAlertRuleRead(UsageAlertRuleWrite):
    id: UUID
    last_state: str | None
    last_notified_at: datetime | None


class UsageNotificationScheduleWrite(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    connection_ids: list[UUID] = Field(min_length=1, max_length=100)
    recipient_person_ids: list[UUID] = Field(min_length=1, max_length=50)
    time_of_day: str = Field(pattern=r"^([01]\\d|2[0-3]):[0-5]\\d$")
    timezone: str = Field(default="Asia/Shanghai", max_length=50)
    enabled: bool = True


class UsageNotificationScheduleRead(UsageNotificationScheduleWrite):
    id: UUID
    last_sent_on: str | None


class UsageNotificationLogRead(BaseModel):
    id: UUID
    event_type: Literal["threshold_breach", "daily_digest", "delivery_failed"]
    status: str
    recipient_count: int
    message_summary: str
    detail: dict
    created_at: datetime
