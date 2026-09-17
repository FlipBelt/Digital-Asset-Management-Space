from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field


class ScenarioSummaryRead(BaseModel):
    code: str
    name: str
    description: str
    asset_count: int = 0
    platform_count: int = 0
    account_count: int = 0
    resource_count: int = 0
    responsible_count: int = 0


class ScenarioNodeRead(BaseModel):
    id: str
    parent_id: str | None = None
    kind: str
    label: str
    subtitle: str | None = None
    asset_id: UUID | None = None
    status: str = "active"
    responsible_name: str | None = None
    department_name: str | None = None
    href: str | None = None
    metadata: dict[str, str | int | bool | None] = Field(default_factory=dict)


class ScenarioOverviewRead(BaseModel):
    scenario: ScenarioSummaryRead
    nodes: list[ScenarioNodeRead] = Field(default_factory=list)
    unclassified_count: int = 0


class RegistrationIdentityCreate(BaseModel):
    identifier: str = Field(min_length=1, max_length=500)
    identity_type: str | None = None
    legal_entity_id: UUID | None = None
    platform_id: UUID | None = None
    source_nature: str = "company_owned"
    custodian_person_id: UUID | None = None
    verification_status: str = "pending"
    note: str | None = None


class RegistrationIdentityRead(BaseModel):
    id: UUID
    asset_id: UUID
    asset_code: str
    legal_entity_id: UUID | None
    name: str
    identity_type: str
    identifier: str
    source_nature: str
    custodian_person_id: UUID | None
    verification_status: str


class CompanyPlatformAccountCreate(BaseModel):
    platform_id: UUID
    legal_entity_id: UUID
    internal_name: str = Field(min_length=1, max_length=200)
    registration_identity_asset_id: UUID | None = None
    external_identifier_type: str | None = None
    external_identifier_value: str | None = None
    evidence_note: str | None = None
    ownership_nature: str = "company_owned"
    account_scope: str = "primary_account"
    status: str = "active"
    description: str | None = None
    ownership_scope: str = "company"
    owner_department_id: UUID | None = None
    responsible_person_id: UUID | None = None
    user_person_ids: list[UUID] = Field(default_factory=list)


class IntakeLinkRead(BaseModel):
    kind: str
    label: str
    relation: str
    asset_id: UUID | None = None


class IntakeNextActionRead(BaseModel):
    key: str
    label: str
    description: str
    target: str
    required: bool = False


class IntakeResultRead(BaseModel):
    id: UUID
    asset_id: UUID
    asset_code: str
    name: str
    object_type: str
    completion_percent: int
    links: list[IntakeLinkRead] = Field(default_factory=list)
    next_actions: list[IntakeNextActionRead] = Field(default_factory=list)


class PlatformAccountContextRead(BaseModel):
    asset_id: UUID
    platform_id: UUID
    platform_name: str
    platform_category: str
    platform_website: str | None = None
    tenant_identifier: str | None = None
    external_identifier_type: str | None = None
    ownership_nature: str
    account_scope: str
    verification_status: str
    evidence_note: str | None = None
    registration_identities: list[RegistrationIdentityRead] = Field(default_factory=list)


class PlatformAccountChildCreate(BaseModel):
    """A login or seat kept as a detail of an L4 company platform account."""

    display_name: str = Field(min_length=1, max_length=200)
    login_identifier: str = Field(min_length=1, max_length=320)
    account_kind: str = "member_login"
    account_role: str = "member"
    account_type: str = "shared_business"
    login_method: str = "password_vault"
    mfa_status: str = "unknown"
    privilege_level: str = "normal"
    parent_account_id: UUID | None = None
    note: str | None = Field(default=None, max_length=2000)


class ResourceCreate(BaseModel):
    legal_entity_id: UUID | None = None
    asset_type_id: UUID
    resource_family: str
    name: str = Field(min_length=1, max_length=200)
    business_purpose: str | None = Field(default=None, max_length=2000)
    managed_under_account_id: UUID | None = None
    platform_id: UUID | None = None
    platform_relation_type: str = "uses"
    parent_resource_asset_id: UUID | None = None
    owner_department_id: UUID | None = None
    external_identifier_type: str | None = None
    external_identifier_value: str | None = None
    management_url: str | None = None
    status: str = "active"
    criticality: str = "normal"
    responsible_person_id: UUID | None = None
    user_person_ids: list[UUID] = Field(default_factory=list)


class AccessGrantCreate(BaseModel):
    account_id: UUID | None = None
    asset_id: UUID | None = None
    person_id: UUID | None = None
    department_id: UUID | None = None
    grant_type: str
    grant_role: str = "member"
    monthly_budget: Decimal | None = None
    currency: str | None = None
    renewal_day: int | None = Field(default=None, ge=1, le=31)
    note: str | None = None


class MapNode(BaseModel):
    id: str
    label: str
    kind: str
    status: str = "active"
    asset_id: UUID | None = None
    subtitle: str | None = None


class MapEdge(BaseModel):
    id: str
    source: str
    target: str
    relation: str


class AssetMapRead(BaseModel):
    nodes: list[MapNode]
    edges: list[MapEdge]


class ImportCandidate(BaseModel):
    row_number: int
    source_category: str | None = None
    source_identifier: str | None = None
    suggested_object_type: str
    suggested_name: str
    confidence: float = Field(ge=0, le=1)
    raw: dict
    warnings: list[str] = Field(default_factory=list)


class FlexibleImportPreview(BaseModel):
    source_name: str
    source_kind: str
    source_sha256: str | None = None
    recognized_counts: dict[str, int] = Field(default_factory=dict)
    candidates: list[ImportCandidate]


class FlexibleImportStage(BaseModel):
    source_name: str
    source_kind: str
    source_sha256: str | None = None
    recognized_counts: dict[str, int] = Field(default_factory=dict)
    candidates: list[ImportCandidate]


class FlexibleImportStageResult(BaseModel):
    batch_id: UUID
    staged_count: int
    status: str
    proposed_object_count: int = 0
    proposed_relation_count: int = 0


class ImportBatchRead(BaseModel):
    id: UUID
    file_name: str
    status: str
    total_count: int
    proposed_object_count: int
    proposed_relation_count: int
    analysis_mode: str | None = None
    created_at: datetime


class ImportProposalObjectRead(BaseModel):
    id: UUID
    proposal_key: str
    source_record_id: UUID | None = None
    source_file: str | None = None
    source_reference: str | None = None
    layer_code: str
    object_type: str
    suggested_name: str
    normalized_payload: dict
    evidence: list[dict] = Field(default_factory=list)
    extraction_confidence: float
    match_confidence: float
    match_status: str
    review_status: str
    matched_asset_id: UUID | None = None
    matched_platform_id: UUID | None = None
    matched_person_id: UUID | None = None
    matched_department_id: UUID | None = None
    review_note: str | None = None


class ImportProposalRelationRead(BaseModel):
    id: UUID
    source_proposal_id: UUID
    target_proposal_id: UUID
    relation_type: str
    evidence: list[dict] = Field(default_factory=list)
    confidence: float
    validation_status: str
    review_status: str
    review_note: str | None = None


class ImportProposalRelationPatch(BaseModel):
    review_status: str | None = None
    review_note: str | None = Field(default=None, max_length=2000)


class ImportPlanRead(BaseModel):
    batch_id: UUID
    analysis_mode: str
    catalog_fingerprint: str
    summary: dict
    objects: list[ImportProposalObjectRead]
    relations: list[ImportProposalRelationRead]


class ImportProposalObjectPatch(BaseModel):
    review_status: str | None = None
    matched_asset_id: UUID | None = None
    matched_platform_id: UUID | None = None
    matched_person_id: UUID | None = None
    matched_department_id: UUID | None = None
    review_note: str | None = Field(default=None, max_length=2000)


class ImportDryRunResult(BaseModel):
    batch_id: UUID
    can_commit: bool
    create_count: int
    reuse_count: int
    pending_review_count: int
    invalid_relation_count: int
    messages: list[str] = Field(default_factory=list)


class ImportCommitRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


class ImportCommitResult(BaseModel):
    batch_id: UUID
    status: str
    created: int
    reused: int
    skipped: int


class BossPilotImportRequest(BaseModel):
    legal_entity_id: UUID | None = None
    boss_person_id: UUID | None = None
    include_internal_apps: bool = False


class BossPilotImportResult(BaseModel):
    batch_id: UUID
    created_service_assets: int
    created_internal_system_assets: int
    pending_access_grants: int
    unresolved_access_grants: int
    staged_finance_records: int
    status: str


class BossPilotRollbackResult(BaseModel):
    batch_id: UUID
    archived_assets: int
    archived_access_grants: int
    archived_relations: int
    status: str


class LayerRecordRead(BaseModel):
    id: str
    layer: int
    name: str
    object_type: str
    legal_entity_name: str | None = None
    platform_name: str | None = None
    category: str | None = None
    ownership_nature: str | None = None
    account_count: int = 0
    status: str
    asset_id: UUID | None = None
    updated_at: datetime


class ImportAccountCandidateRead(BaseModel):
    """A redacted login fact awaiting an evidenced L4 company account."""

    source_record_id: UUID
    platform_name: str
    login_identifier: str
    source_file: str
    evidence: list[str] = Field(default_factory=list)
    confidence: float
    status: str
    pending_reason: str
    assigned_l4_asset_id: UUID | None = None
    assigned_l4_name: str | None = None


class LegacyHierarchyNormalizeResult(BaseModel):
    batch_id: UUID
    linked_service_instances: int
    platform_count: int
