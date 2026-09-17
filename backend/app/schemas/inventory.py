from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import ORMModel


class ProviderCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    website: str | None = None


class ProviderRead(ORMModel):
    id: UUID
    code: str
    name: str
    website: str | None


class PlatformCreate(BaseModel):
    provider_id: UUID | None = None
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    category: str = "other"
    website: str | None = None
    review_status: str = "pending_review"
    description: str | None = None
    submitted_by_person_id: UUID | None = None


class PlatformPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    code: str | None = Field(default=None, min_length=1, max_length=80)
    category: str | None = None
    website: str | None = None
    description: str | None = None


class PlatformRead(ORMModel):
    id: UUID
    provider_id: UUID | None
    code: str
    name: str
    category: str
    website: str | None
    review_status: str
    description: str | None
    submitted_by_person_id: UUID | None


class PlatformTenantCreate(BaseModel):
    asset_id: UUID
    platform_id: UUID
    legal_entity_id: UUID
    tenant_identifier: str | None = Field(default=None, max_length=200)
    external_identifier_type: str | None = None
    ownership_nature: str = "company_owned"
    account_scope: str = "primary_account"
    verification_status: str = "pending"
    evidence_note: str | None = None


class PlatformTenantRead(ORMModel):
    id: UUID
    asset_id: UUID
    platform_id: UUID
    legal_entity_id: UUID
    tenant_identifier: str | None
    external_identifier_type: str | None
    ownership_nature: str
    account_scope: str
    verification_status: str
    evidence_note: str | None


class AccountCreate(BaseModel):
    asset_id: UUID
    platform_tenant_id: UUID
    login_identifier: str = Field(min_length=1, max_length=320)
    account_type: str = "company_primary"
    registration_identity_type: str = "company"
    registration_person_id: UUID | None = None
    mfa_status: str = "unknown"
    privilege_level: str = "normal"
    parent_account_id: UUID | None = None
    account_kind: str = "member_login"
    login_method: str = "registration_identity"
    account_role: str = "member"
    primary_person_id: UUID | None = None
    legacy_source_id: str | None = None
    legacy_metadata: dict = Field(default_factory=dict)


class AccountRead(ORMModel):
    id: UUID
    asset_id: UUID
    platform_tenant_id: UUID
    login_identifier: str
    account_type: str
    registration_identity_type: str
    registration_person_id: UUID | None
    mfa_status: str
    privilege_level: str
    parent_account_id: UUID | None
    account_kind: str
    login_method: str
    account_role: str
    primary_person_id: UUID | None
    legacy_source_id: str | None
    legacy_metadata: dict


class CredentialReferenceCreate(BaseModel):
    account_id: UUID | None = None
    asset_id: UUID | None = None
    provider: str = Field(min_length=1, max_length=80)
    item_id: str = Field(min_length=1, max_length=500)
    secure_url: str | None = None

    @model_validator(mode="after")
    def validate_subject(self) -> "CredentialReferenceCreate":
        if self.account_id is None and self.asset_id is None:
            raise ValueError("必须关联账号或资产")
        return self


class CredentialReferenceRead(ORMModel):
    id: UUID
    account_id: UUID | None
    asset_id: UUID | None
    provider: str
    item_id: str
    secure_url: str | None
    last_rotated_at: datetime | None
    last_verified_at: datetime | None


class ServiceProductCreate(BaseModel):
    provider_id: UUID
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    service_category: str = "other"
    billing_mode: str = "subscription"


class ServiceProductRead(ORMModel):
    id: UUID
    provider_id: UUID
    code: str
    name: str
    service_category: str
    billing_mode: str


class ServiceInstanceCreate(BaseModel):
    asset_id: UUID
    service_product_id: UUID
    purchase_platform_id: UUID | None = None
    purchase_tenant_asset_id: UUID | None = None
    subscription_name: str | None = None
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    starts_at: date | None = None
    expires_at: date | None = None


class ServiceInstanceRead(ORMModel):
    id: UUID
    asset_id: UUID
    service_product_id: UUID
    purchase_platform_id: UUID | None
    purchase_tenant_asset_id: UUID | None
    subscription_name: str | None
    currency: str
    starts_at: date | None
    expires_at: date | None


class MetricDefinitionRead(ORMModel):
    id: UUID
    metric_key: str
    display_name: str
    unit: str
    aggregation: str


class MetricSampleCreate(BaseModel):
    metric_definition_id: UUID
    value: Decimal
    currency: str | None = None
    period_start: datetime | None = None
    period_end: datetime | None = None
    collected_at: datetime | None = None
    source_type: str = "manual"


class MetricSampleRead(ORMModel):
    id: UUID
    service_instance_id: UUID
    metric_definition_id: UUID
    value: Decimal
    currency: str | None
    period_start: datetime | None
    period_end: datetime | None
    collected_at: datetime
    source_type: str


class InternalSystemProfileUpsert(BaseModel):
    repository_url: str | None = None
    production_url: str | None = None
    tech_stack: str | None = None
    deployment_guide_url: str | None = None
    recovery_guide_url: str | None = None
    backup_description: str | None = None


class InternalSystemProfileRead(ORMModel):
    id: UUID
    asset_id: UUID
    repository_url: str | None
    production_url: str | None
    tech_stack: str | None
    deployment_guide_url: str | None
    recovery_guide_url: str | None
    backup_description: str | None


class ConnectorDefinitionRead(ORMModel):
    id: UUID
    code: str
    name: str
    version: str
    capabilities: list
    enabled: bool


class ProviderConnectionCreate(BaseModel):
    connector_definition_id: UUID
    legal_entity_id: UUID
    platform_tenant_id: UUID | None = None
    credential_reference_id: UUID | None = None
    name: str = Field(min_length=1, max_length=200)
    status: str = "disabled"
    configuration: dict = Field(default_factory=dict)


class ProviderConnectionRead(ORMModel):
    id: UUID
    connector_definition_id: UUID
    legal_entity_id: UUID
    platform_tenant_id: UUID | None
    credential_reference_id: UUID | None
    name: str
    status: str
    configuration: dict
    last_synced_at: datetime | None
    last_error: str | None


class WorkflowRequestCreate(BaseModel):
    request_type: str
    title: str = Field(min_length=1, max_length=200)
    requester_person_id: UUID | None = None
    asset_id: UUID | None = None
    detail: dict = Field(default_factory=dict)


class WorkflowRequestRead(ORMModel):
    id: UUID
    request_no: str
    request_type: str
    title: str
    requester_person_id: UUID | None
    asset_id: UUID | None
    status: str
    detail: dict
    version: int
    created_at: datetime


class RiskFindingRead(ORMModel):
    id: UUID
    rule_key: str
    asset_id: UUID | None
    person_id: UUID | None
    severity: str
    status: str
    title: str
    detail: dict
    version: int
    detected_at: datetime


class AuditLogRead(ORMModel):
    id: UUID
    action: str
    object_type: str
    object_id: UUID | None
    before_data: dict | None
    after_data: dict | None
    created_at: datetime
