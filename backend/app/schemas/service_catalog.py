from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from app.schemas.inventory import ServiceProductRead
from app.services.catalog_reference import known_plan_name

Name = Annotated[str, Field(min_length=1, max_length=200)]


class DirectoryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    provider_id: UUID | None = None
    name: Name
    category: str = Field(default="other", min_length=1, max_length=80)
    website: HttpUrl | None = None
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("name")
    @classmethod
    def platform_not_plan(cls, value):
        if known_plan_name(value):
            raise ValueError("这是套餐名称，请在平台/供应商的服务下维护套餐")
        return value


class DirectoryUpdate(DirectoryCreate):
    expected_revision: str = Field(min_length=64, max_length=64)


class DirectoryReview(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    expected_revision: str = Field(min_length=64, max_length=64)
    decision: Literal["approved", "rejected"]
    note: str = Field(min_length=1, max_length=2000)
    source_url: HttpUrl | None = None


class DirectoryService(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    product_id: UUID | None = None
    expected_revision: str = Field(min_length=64, max_length=64)
    name: Name
    billing_mode: Literal["subscription", "usage", "free", "one_time", "other"] = "subscription"
    plan_options: list[Name] = Field(default_factory=list, max_length=50)

    @field_validator("name")
    @classmethod
    def service_not_plan(cls, value):
        if known_plan_name(value):
            raise ValueError("请填写服务名称，并将套餐放入可选套餐列表")
        return value

    @field_validator("plan_options")
    @classmethod
    def unique_plans(cls, values):
        values = [value.strip() for value in values]
        if any(not value for value in values) or len({value.casefold() for value in values}) != len(
            values
        ):
            raise ValueError("套餐名称不能为空或重复")
        return values


class DirectoryRead(BaseModel):
    id: UUID
    kind: Literal["platform", "provider"]
    provider_id: UUID | None
    provider_name: str | None
    name: str
    category: str
    website: str | None
    description: str | None
    review_status: str
    revision: str
    review_note: str | None = None
    source_url: str | None = None
    services: list[ServiceProductRead]


class SubscriptionOption(ServiceProductRead):
    platform_name: str
