"""Only bounded structured summaries; actor, roles and confirmation are never input."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class DeviceStart(StrictInput):
    client_name: Literal["Codex", "Qoder-CN"] = "Codex"


class DevicePoll(StrictInput):
    device_code: str = Field(min_length=32, max_length=128)


class DeviceCode(StrictInput):
    user_code: str = Field(pattern=r"^[A-Z2-9]{8}$")


class DeviceApprove(DeviceCode):
    approved: bool


class DraftUpdate(StrictInput):
    request_id: UUID
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)


class IncubationInput(StrictInput):
    request_id: UUID
    id: UUID | None = None
    version: int = Field(default=0, ge=0)
    title: str = Field(min_length=1, max_length=200)
    stage: Literal["discovering", "opportunity", "blueprint", "testing", "paused", "ready"]
    workflow_summary: str = Field(default="", max_length=4000)
    opportunity_summary: str = Field(default="", max_length=4000)
    blueprint_summary: str = Field(default="", max_length=6000)
    next_step: str = Field(default="", max_length=1000)
    asset_id: UUID | None = None
