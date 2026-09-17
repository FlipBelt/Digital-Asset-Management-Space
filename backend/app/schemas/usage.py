from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

UsagePlatformCode = Literal["deepseek", "minimax", "aliyun"]
MiniMaxKeyType = Literal["token_plan"]


class UsageConnectionCreate(BaseModel):
    platform_code: UsagePlatformCode
    legal_entity_id: UUID
    service_instance_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=1000)
    access_key_id: str | None = Field(default=None, min_length=1, max_length=200)
    access_key_secret: str | None = Field(default=None, min_length=1, max_length=1000)
    key_type: MiniMaxKeyType | None = None
    group_id: str | None = Field(default=None, max_length=200)
    low_balance_threshold: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    sync_interval_minutes: int = Field(default=60, ge=5, le=1440)
    status: Literal["enabled", "disabled"] = "enabled"


class UsageConnectionUpdate(BaseModel):
    service_instance_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    api_key: str | None = Field(default=None, min_length=1, max_length=1000)
    access_key_id: str | None = Field(default=None, min_length=1, max_length=200)
    access_key_secret: str | None = Field(default=None, min_length=1, max_length=1000)
    key_type: MiniMaxKeyType | None = None
    group_id: str | None = Field(default=None, max_length=200)
    low_balance_threshold: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    sync_interval_minutes: int | None = Field(default=None, ge=5, le=1440)
    status: Literal["enabled", "disabled"] | None = None


class UsageConnectionRead(BaseModel):
    id: UUID
    platform_code: UsagePlatformCode
    platform_name: str
    legal_entity_id: UUID
    service_instance_id: UUID | None
    name: str
    status: str
    configuration: dict
    last_synced_at: datetime | None
    last_error: str | None


class UsageConnectionActionResult(BaseModel):
    status: str
    message: str
    metrics_written: int = 0
    observed_at: datetime | None = None
    snapshot: dict | None = None


class UsageEventCreate(BaseModel):
    input_tokens: Decimal | None = Field(default=None, ge=0)
    output_tokens: Decimal | None = Field(default=None, ge=0)
    total_tokens: Decimal | None = Field(default=None, ge=0)
    cost: Decimal | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    collected_at: datetime | None = None
