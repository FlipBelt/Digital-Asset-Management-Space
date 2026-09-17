from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AssetCategoryCreate(BaseModel):
    parent_id: UUID | None = None
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    sort_order: int = 0


class AssetCategoryRead(ORMModel):
    id: UUID
    parent_id: UUID | None
    code: str
    name: str
    sort_order: int


class AssetTypeCreate(BaseModel):
    category_id: UUID
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    profile_kind: str = "generic"
    code_prefix: str = Field(
        default="AST", min_length=2, max_length=20, pattern=r"^[A-Z][A-Z0-9_]*$"
    )
    ownership_default: str = "manual"
    completeness_rules: dict = Field(default_factory=dict)


class AssetTypeRead(ORMModel):
    id: UUID
    category_id: UUID
    code: str
    name: str
    profile_kind: str
    code_prefix: str
    ownership_default: str
    is_system: bool
    completeness_rules: dict


class AssetFieldDefinitionCreate(BaseModel):
    field_key: str = Field(min_length=1, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=1, max_length=120)
    data_type: str = "text"
    is_required: bool = False
    options: list | None = None
    group_name: str = Field(default="基础信息", min_length=1, max_length=120)
    help_text: str | None = None
    unit: str | None = Field(default=None, max_length=40)
    validation: dict = Field(default_factory=dict)
    confidentiality: str = "internal"
    is_searchable: bool = False
    completeness_weight: int = Field(default=0, ge=0, le=100)
    sort_order: int = 0
    entry_visibility: str = "optional"
    requirement_stage: str = "optional"
    applies_to_existing: bool = False
    condition_rules: dict = Field(default_factory=dict)


class AssetFieldDefinitionRead(ORMModel):
    id: UUID
    asset_type_id: UUID
    field_key: str
    label: str
    data_type: str
    is_required: bool
    options: list | None
    group_name: str
    help_text: str | None
    unit: str | None
    validation: dict
    confidentiality: str
    is_searchable: bool
    completeness_weight: int
    sort_order: int
    entry_visibility: str
    requirement_stage: str
    applies_to_existing: bool
    condition_rules: dict


class RelationDefinitionRead(ORMModel):
    id: UUID
    relation_type: str
    source_type_code: str
    target_type_code: str
    forward_label: str
    inverse_label: str
    category: str
    source_max_count: int | None
    target_max_count: int | None
    is_system: bool


class RelationDefinitionCreate(BaseModel):
    relation_type: str = Field(min_length=1, max_length=50, pattern=r"^[A-Z_]+$")
    source_type_code: str = Field(min_length=1, max_length=80)
    target_type_code: str = Field(min_length=1, max_length=80)
    forward_label: str = Field(min_length=1, max_length=100)
    inverse_label: str = Field(min_length=1, max_length=100)
    category: str = "upstream"
    source_max_count: int | None = Field(default=None, ge=1)
    target_max_count: int | None = Field(default=None, ge=1)
