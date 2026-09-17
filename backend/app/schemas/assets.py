from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class AssetCreate(BaseModel):
    asset_code: str | None = Field(default=None, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    asset_type_id: UUID
    legal_entity_id: UUID | None = None
    owner_department_id: UUID | None = None
    ownership_scope: str = "pending"
    status: str = "draft"
    criticality: str = "normal"
    confidentiality: str = "internal"
    started_at: date | None = None
    expires_at: date | None = None
    description: str | None = None


class AssetPatch(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    owner_department_id: UUID | None = None
    ownership_scope: str | None = None
    status: str | None = None
    criticality: str | None = None
    confidentiality: str | None = None
    started_at: date | None = None
    expires_at: date | None = None
    last_verified_at: datetime | None = None
    description: str | None = None


class AssetRead(ORMModel):
    id: UUID
    asset_code: str
    name: str
    asset_type_id: UUID
    legal_entity_id: UUID | None
    owner_department_id: UUID | None
    ownership_scope: str
    created_by_person_id: UUID | None
    confirmed_by_person_id: UUID | None
    confirmed_at: datetime | None
    review_status: str
    status: str
    criticality: str
    confidentiality: str
    source_type: str
    started_at: date | None
    expires_at: date | None
    last_verified_at: datetime | None
    description: str | None
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None


class AssetResponsibilityCreate(BaseModel):
    person_id: UUID | None = None
    department_id: UUID | None = None
    role_type: str = Field(min_length=1, max_length=50)
    is_primary: bool = False
    starts_at: date | None = None
    ends_at: date | None = None

    @model_validator(mode="after")
    def validate_subject(self) -> "AssetResponsibilityCreate":
        if (self.person_id is None) == (self.department_id is None):
            raise ValueError("person_id和department_id必须且只能填写一个")
        return self


class AssetResponsibilityRead(ORMModel):
    id: UUID
    asset_id: UUID
    person_id: UUID | None
    department_id: UUID | None
    role_type: str
    is_primary: bool
    starts_at: date | None
    ends_at: date | None
    archived_at: datetime | None


class AssetAssignmentWrite(BaseModel):
    version: int = Field(ge=1)
    owner_department_id: UUID | None = None
    # Older clients omit this field. The endpoint then derives the compatible
    # scope from the selected department instead of resetting it to pending.
    ownership_scope: str | None = None
    responsible_person_id: UUID
    user_person_ids: list[UUID] = Field(default_factory=list)


class AssetAssignmentRead(BaseModel):
    owner_department_id: UUID | None
    ownership_scope: str
    responsible_person_id: UUID | None
    user_person_ids: list[UUID]


class AssetRelationCreate(BaseModel):
    target_asset_id: UUID
    relation_type: str = Field(min_length=1, max_length=50)
    note: str | None = None


class AssetRelationRead(ORMModel):
    id: UUID
    source_asset_id: UUID
    target_asset_id: UUID
    relation_type: str
    source_type: str
    note: str | None
    archived_at: datetime | None


class RelationshipNodeRead(BaseModel):
    id: str
    layer: int
    label: str
    object_type: str
    kind: str
    asset_id: UUID | None = None
    status: str | None = None
    href: str | None = None


class RelationshipEdgeRead(BaseModel):
    id: str
    source: str
    target: str
    label: str
    section: Literal["structure", "business", "responsibility"]
    direction: Literal["upstream", "downstream", "peer", "responsibility"]
    source_model: str
    editable: bool = False
    relation_id: UUID | None = None
    note: str | None = None
    edit_kind: str | None = None
    edit_target_id: UUID | None = None


class AssetRelationshipViewRead(BaseModel):
    current_node: RelationshipNodeRead
    nodes: list[RelationshipNodeRead]
    edges: list[RelationshipEdgeRead]


class RelationshipLinkUpdate(BaseModel):
    target_id: UUID


class AssetPlatformLinkCreate(BaseModel):
    platform_id: UUID
    relation_type: str = Field(default="uses", min_length=1, max_length=50)
    review_status: str = "pending_review"
    source_import_record_id: UUID | None = None
    note: str | None = None


class AssetPlatformLinkRead(ORMModel):
    id: UUID
    asset_id: UUID
    platform_id: UUID
    relation_type: str
    source_type: str
    source_import_record_id: UUID | None
    review_status: str
    confirmed_by_person_id: UUID | None
    confirmed_at: datetime | None
    note: str | None
    archived_at: datetime | None


class IntelligentRelationCreate(BaseModel):
    related_asset_id: UUID
    direction: str = Field(pattern=r"^(upstream|downstream|peer)$")
    relation_type: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z_]+$")
    note: str | None = None


class RelationOptionRead(BaseModel):
    relation_type: str
    label: str
    target_type_codes: list[str]
    direction: str


class AssetIdentifierCreate(BaseModel):
    namespace: str = Field(min_length=1, max_length=80)
    identifier_type: str = Field(min_length=1, max_length=80)
    identifier_value: str = Field(min_length=1, max_length=500)
    is_primary: bool = False
    verification_status: str = "pending"
    confidentiality: str = "internal"


class AssetIdentifierRead(ORMModel):
    id: UUID
    asset_id: UUID
    namespace: str
    identifier_type: str
    identifier_value: str
    is_primary: bool
    verification_status: str
    confidentiality: str
    source_import_record_id: UUID | None
    archived_at: datetime | None


class AssetFieldValueInput(BaseModel):
    field_definition_id: UUID
    value: str | int | float | bool | list | None


class AssetFieldValueRead(ORMModel):
    id: UUID
    asset_id: UUID
    field_definition_id: UUID
    value: dict
