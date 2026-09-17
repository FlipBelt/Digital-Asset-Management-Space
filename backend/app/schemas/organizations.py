from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

from app.schemas.common import ORMModel


class LegalEntityCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)


class LegalEntityRead(ORMModel):
    id: UUID
    code: str
    name: str
    status: str
    created_at: datetime


class LegalEntityPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None


class LegalEntityProfileWrite(BaseModel):
    entity_type: str | None = Field(default=None, max_length=50)
    jurisdiction: str | None = Field(default=None, max_length=120)
    registration_status: str | None = Field(default=None, max_length=32)
    legal_representative: str | None = Field(default=None, max_length=120)
    established_on: date | None = None
    registered_address: str | None = None
    registered_capital: str | None = Field(default=None, max_length=120)
    business_scope: str | None = None
    source_note: str | None = None
    verification_status: str = "pending"


class LegalEntityProfileRead(LegalEntityProfileWrite, ORMModel):
    id: UUID
    legal_entity_id: UUID


class LegalEntityIdentifierCreate(BaseModel):
    namespace: str = Field(default="cn", min_length=1, max_length=80)
    identifier_type: str = Field(min_length=1, max_length=80)
    identifier_value: str = Field(min_length=1, max_length=200)
    is_primary: bool = False
    verification_status: str = "pending"
    source_note: str | None = None


class LegalEntityIdentifierRead(LegalEntityIdentifierCreate, ORMModel):
    id: UUID
    legal_entity_id: UUID
    archived_at: datetime | None


class DepartmentCreate(BaseModel):
    legal_entity_id: UUID
    parent_id: UUID | None = None
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)


class DepartmentRead(ORMModel):
    id: UUID
    legal_entity_id: UUID
    parent_id: UUID | None
    code: str
    name: str
    status: str


class DepartmentPatch(BaseModel):
    parent_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=200)
    status: str | None = None


class PersonCreate(BaseModel):
    legal_entity_id: UUID
    department_id: UUID | None = None
    employee_no: str = Field(min_length=1, max_length=50)
    display_name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    person_type: str = "employee"


class PersonRead(ORMModel):
    id: UUID
    legal_entity_id: UUID
    department_id: UUID | None
    employee_no: str
    display_name: str
    email: str | None
    employment_status: str
    person_type: str


class PersonPatch(BaseModel):
    department_id: UUID | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    employment_status: str | None = None
    person_type: str | None = None


class DepartmentMembershipRead(ORMModel):
    id: UUID
    person_id: UUID
    department_id: UUID
    is_manager: bool
    is_primary: bool
    is_active: bool
