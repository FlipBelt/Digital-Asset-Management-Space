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


class ProfileInput(StrictInput):
    repository_url: str | None = Field(default=None, max_length=1000)
    production_url: str | None = Field(default=None, max_length=1000)
    tech_stack: str | None = Field(default=None, max_length=1000)
    deployment_guide_url: str | None = Field(default=None, max_length=1000)
    recovery_guide_url: str | None = Field(default=None, max_length=1000)
    backup_description: str | None = Field(default=None, max_length=4000)


class FieldInput(StrictInput):
    field_definition_id: UUID
    value: str | int | float | bool | None


class IdentifierInput(StrictInput):
    namespace: str = Field(min_length=1, max_length=80)
    identifier_type: str = Field(min_length=1, max_length=80)
    identifier_value: str = Field(min_length=1, max_length=500)


class DetailsInput(StrictInput):
    request_id: UUID
    version: int = Field(ge=1)
    profile: ProfileInput | None = None
    fields: list[FieldInput] = Field(default_factory=list, max_length=100)
    identifiers: list[IdentifierInput] = Field(default_factory=list, max_length=30)
    proposed_responsible_person_id: UUID | None = None
    proposed_user_person_ids: list[UUID] = Field(default_factory=list, max_length=50)


class AttachmentInput(StrictInput):
    request_id: UUID
    version: int = Field(ge=1)
    file_name: str = Field(min_length=1, max_length=290)
    content_base64: str = Field(min_length=1, max_length=28_000_000)
