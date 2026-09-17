from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.auth import CurrentUserRead
from app.schemas.common import ORMModel


class DingTalkAuthCode(BaseModel):
    auth_code: str = Field(min_length=1, max_length=2000)


class DingTalkLoginRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    auth_code: str = Field(alias="authCode", min_length=1, max_length=2000)


class DingTalkPublicConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    corp_id: str | None = Field(alias="corpId")
    agent_id: str | None = Field(alias="agentId")
    configured: bool


class DingTalkLoginUser(BaseModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    ding_user_id: str = Field(alias="dingUserId")
    name: str
    avatar: str | None = None
    department: str | None = None
    role: str
    roles: list[str]
    permissions: list[str]
    session_token: str = Field(alias="sessionToken")


class DingTalkClientDiagnostic(BaseModel):
    phase: str = Field(min_length=1, max_length=80)
    bridge: str | None = Field(default=None, max_length=80)
    message: str = Field(default="", max_length=1000)
    user_agent: str = Field(default="", max_length=500)


class DingTalkSyncRequest(BaseModel):
    legal_entity_id: str


class DingTalkPersonProfileRead(ORMModel):
    person_id: UUID
    dingtalk_user_id: str
    job_title: str | None


class DingTalkIdentityRead(BaseModel):
    person_id: UUID
    display_name: str
    department_id: UUID | None
    job_title: str | None
    is_department_manager: bool


class DingTalkSessionRead(BaseModel):
    user: CurrentUserRead
    identity: DingTalkIdentityRead
    expires_at: datetime
