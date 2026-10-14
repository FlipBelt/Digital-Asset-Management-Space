from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PermissionMutation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    expected_revision: str = Field(pattern=r"^[0-9a-f]{64}$")
    reason: str = Field(min_length=1, max_length=1000)


class PermissionRoleWrite(PermissionMutation):
    role_code: Literal[
        "system_admin",
        "asset_manager",
        "employee",
        "executive",
        "auditor",
        "department_manager",
        "group_leader",
    ]
    department_id: UUID | None = None

    @model_validator(mode="after")
    def validate_scope(self):
        scoped = self.role_code in {"department_manager", "group_leader"}
        if scoped != (self.department_id is not None):
            raise ValueError("部门负责人和组长必须选择部门；其他角色不设置部门范围")
        return self


class PermissionAccessWrite(PermissionMutation):
    enabled: bool


class PermissionResourceWrite(PermissionMutation):
    asset_id: UUID
    starts_at: date | None = None
    ends_at: date | None = None

    @model_validator(mode="after")
    def validate_period(self):
        if self.starts_at and self.ends_at and self.starts_at > self.ends_at:
            raise ValueError("结束日期不能早于开始日期")
        if self.ends_at and self.ends_at < date.today():
            raise ValueError("授权结束日期不能早于今天")
        return self
