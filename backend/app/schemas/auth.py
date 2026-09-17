from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionCreate(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=12, max_length=256)


class CurrentUserRead(BaseModel):
    id: UUID
    username: str
    person_id: UUID | None
    display_name: str | None = None
    department_id: UUID | None = None
    job_title: str | None = None
    roles: list[str]
    permissions: list[str] = []
    csrf_token: str


class SessionRead(BaseModel):
    user: CurrentUserRead
    expires_at: datetime
    session_token: str | None = None
