from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import (
    ArchiveMixin,
    Base,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    VersionMixin,
)


class LegalEntity(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "legal_entities"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class LegalEntityProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Optional statutory profile.  Kept separate so existing legal entities stay valid."""

    __tablename__ = "legal_entity_profiles"

    legal_entity_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_entities.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    jurisdiction: Mapped[str | None] = mapped_column(String(120), nullable=True)
    registration_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    legal_representative: Mapped[str | None] = mapped_column(String(120), nullable=True)
    established_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    registered_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    registered_capital: Mapped[str | None] = mapped_column(String(120), nullable=True)
    business_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)


class LegalEntityIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "legal_entity_identifiers"
    __table_args__ = (
        UniqueConstraint("namespace", "identifier_type", "identifier_value"),
        Index("ix_legal_entity_identifiers_entity", "legal_entity_id", "identifier_type"),
    )

    legal_entity_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_entities.id", ondelete="CASCADE"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(80), default="cn", nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(80), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(200), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class Department(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("legal_entity_id", "code"),)

    legal_entity_id: Mapped[UUID] = mapped_column(ForeignKey("legal_entities.id"), nullable=False)
    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)


class Person(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "people"
    __table_args__ = (UniqueConstraint("legal_entity_id", "employee_no"),)

    legal_entity_id: Mapped[UUID] = mapped_column(ForeignKey("legal_entities.id"), nullable=False)
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    employee_no: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    employment_status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    person_type: Mapped[str] = mapped_column(String(32), default="employee", nullable=False)


class User(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "users"

    person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("people.id"), unique=True, nullable=True
    )
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(500), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserSession(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_sessions"
    __table_args__ = (Index("ix_user_sessions_lookup", "token_hash", "expires_at"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    csrf_token: Mapped[str] = mapped_column(String(96), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    device_summary: Mapped[str | None] = mapped_column(String(300), nullable=True)


class Role(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "roles"

    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class Permission(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "permissions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)


class RolePermission(Base):
    __tablename__ = "role_permissions"

    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), primary_key=True)
    permission_id: Mapped[UUID] = mapped_column(ForeignKey("permissions.id"), primary_key=True)


class UserRoleScope(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_role_scopes"
    __table_args__ = (UniqueConstraint("user_id", "role_id", "scope_type", "scope_id"),)

    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_id: Mapped[UUID | None] = mapped_column(nullable=True)


class DingTalkDepartmentLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dingtalk_department_links"

    department_id: Mapped[UUID] = mapped_column(
        ForeignKey("departments.id"), unique=True, nullable=False
    )
    dingtalk_department_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class DingTalkPersonProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "dingtalk_person_profiles"

    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), unique=True, nullable=False)
    dingtalk_user_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    union_id: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    profile_data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class DepartmentMembership(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A person's DingTalk organization placement, including department leadership."""

    __tablename__ = "department_memberships"
    __table_args__ = (UniqueConstraint("person_id", "department_id"),)

    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), nullable=False)
    department_id: Mapped[UUID] = mapped_column(ForeignKey("departments.id"), nullable=False)
    is_manager: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class Provider(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "providers"

    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Platform(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "platforms"
    __table_args__ = (UniqueConstraint("provider_id", "code"),)

    provider_id: Mapped[UUID | None] = mapped_column(ForeignKey("providers.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="other", nullable=False)
    website: Mapped[str | None] = mapped_column(String(500), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_by_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("people.id"), nullable=True
    )


class AssetCategory(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "asset_categories"

    parent_id: Mapped[UUID | None] = mapped_column(ForeignKey("asset_categories.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)


class BusinessScenario(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    """A user-facing business context used to navigate existing assets."""

    __tablename__ = "business_scenarios"
    __table_args__ = (UniqueConstraint("code"),)

    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AssetType(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "asset_types"
    __table_args__ = (UniqueConstraint("category_id", "code"),)

    category_id: Mapped[UUID] = mapped_column(ForeignKey("asset_categories.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    profile_kind: Mapped[str] = mapped_column(String(80), default="generic", nullable=False)
    code_prefix: Mapped[str] = mapped_column(String(20), default="AST", nullable=False)
    ownership_default: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completeness_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AssetFieldDefinition(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "asset_field_definitions"
    __table_args__ = (UniqueConstraint("asset_type_id", "field_key"),)

    asset_type_id: Mapped[UUID] = mapped_column(ForeignKey("asset_types.id"), nullable=False)
    field_key: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    data_type: Mapped[str] = mapped_column(String(32), nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    options: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    group_name: Mapped[str] = mapped_column(String(120), default="基础信息", nullable=False)
    help_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(40), nullable=True)
    validation: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    confidentiality: Mapped[str] = mapped_column(String(32), default="internal", nullable=False)
    is_searchable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completeness_weight: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(default=0, nullable=False)
    entry_visibility: Mapped[str] = mapped_column(
        String(32), default="optional", server_default="optional", nullable=False
    )
    requirement_stage: Mapped[str] = mapped_column(
        String(32), default="optional", server_default="optional", nullable=False
    )
    applies_to_existing: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    condition_rules: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Asset(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, VersionMixin, Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("legal_entity_id", "asset_code"),
        Index("ix_assets_scope", "legal_entity_id", "owner_department_id", "asset_type_id"),
        Index("ix_assets_status", "status", "criticality"),
    )

    asset_code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    asset_type_id: Mapped[UUID] = mapped_column(ForeignKey("asset_types.id"), nullable=False)
    # An L2 identity or L6 service can be real even where its owning legal
    # entity is still unknown.  L4 keeps its own non-null legal-entity rule.
    legal_entity_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("legal_entities.id"), nullable=True
    )
    owner_department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )
    ownership_scope: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    created_by_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("people.id"), nullable=True
    )
    confirmed_by_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("people.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    criticality: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    confidentiality: Mapped[str] = mapped_column(String(32), default="internal", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    started_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssetScenarioLink(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Evidence-aware many-to-many link from a canonical asset to a scenario."""

    __tablename__ = "asset_scenario_links"
    __table_args__ = (
        UniqueConstraint("asset_id", "scenario_id"),
        Index("ix_asset_scenario_links_scenario", "scenario_id", "asset_id"),
    )

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    scenario_id: Mapped[UUID] = mapped_column(
        ForeignKey("business_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    confidence: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), default=Decimal("0.5"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssetCodeSequence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_code_sequences"
    __table_args__ = (UniqueConstraint("legal_entity_id", "asset_type_id"),)

    legal_entity_id: Mapped[UUID] = mapped_column(
        ForeignKey("legal_entities.id", ondelete="CASCADE"), nullable=False
    )
    asset_type_id: Mapped[UUID] = mapped_column(
        ForeignKey("asset_types.id", ondelete="CASCADE"), nullable=False
    )
    last_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class AssetIdentifier(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "asset_identifiers"
    __table_args__ = (
        Index(
            "uq_asset_identifiers_active_value",
            "namespace",
            "identifier_type",
            "identifier_value",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
        Index("ix_asset_identifiers_lookup", "namespace", "identifier_type", "identifier_value"),
    )

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    namespace: Mapped[str] = mapped_column(String(80), nullable=False)
    identifier_type: Mapped[str] = mapped_column(String(80), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(500), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    source_import_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_import_records.id", ondelete="SET NULL"), nullable=True
    )
    confidentiality: Mapped[str] = mapped_column(String(32), default="internal", nullable=False)
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AssetFieldValue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "asset_field_values"
    __table_args__ = (UniqueConstraint("asset_id", "field_definition_id"),)

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    field_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("asset_field_definitions.id"), nullable=False
    )
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)


class AssetResponsibility(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "asset_responsibilities"
    __table_args__ = (
        CheckConstraint(
            "(person_id IS NOT NULL AND department_id IS NULL) OR "
            "(person_id IS NULL AND department_id IS NOT NULL)",
            name="exactly_one_subject",
        ),
        Index("ix_asset_responsibilities_subject", "person_id", "department_id", "role_type"),
        Index(
            "uq_asset_one_responsible",
            "asset_id",
            unique=True,
            postgresql_where=text("role_type = 'responsible' AND archived_at IS NULL"),
        ),
    )

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    role_type: Mapped[str] = mapped_column(String(50), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class AssetRelation(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "asset_relations"
    __table_args__ = (
        CheckConstraint("source_asset_id <> target_asset_id", name="different_assets"),
        UniqueConstraint("source_asset_id", "target_asset_id", "relation_type"),
    )

    source_asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    target_asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class RelationDefinition(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "relation_definitions"
    __table_args__ = (UniqueConstraint("relation_type", "source_type_code", "target_type_code"),)

    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type_code: Mapped[str] = mapped_column(String(80), nullable=False)
    target_type_code: Mapped[str] = mapped_column(String(80), nullable=False)
    forward_label: Mapped[str] = mapped_column(String(100), nullable=False)
    inverse_label: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(32), default="upstream", nullable=False)
    source_max_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_max_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class PlatformTenant(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "platform_tenants"
    __table_args__ = (UniqueConstraint("platform_id", "legal_entity_id", "tenant_identifier"),)

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    platform_id: Mapped[UUID] = mapped_column(ForeignKey("platforms.id"), nullable=False)
    legal_entity_id: Mapped[UUID] = mapped_column(ForeignKey("legal_entities.id"), nullable=False)
    tenant_identifier: Mapped[str | None] = mapped_column(String(200), nullable=True)
    external_identifier_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    ownership_nature: Mapped[str] = mapped_column(
        String(32), default="company_owned", nullable=False
    )
    account_scope: Mapped[str] = mapped_column(
        String(32), default="primary_account", nullable=False
    )
    verification_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    evidence_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssetPlatformLink(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    """Optional link from any instantiated asset to the platform directory.

    Platforms are catalog objects rather than assets, so ``AssetRelation`` cannot
    represent a direct L2/L3 or L6/L3 link.  This table keeps that association
    explicit without forcing an L4 tenant to exist first.
    """

    __tablename__ = "asset_platform_links"
    __table_args__ = (
        Index(
            "uq_asset_platform_links_active",
            "asset_id",
            "platform_id",
            "relation_type",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
        ),
    )

    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="CASCADE"), nullable=False
    )
    platform_id: Mapped[UUID] = mapped_column(
        ForeignKey("platforms.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(50), default="uses", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    source_import_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_import_records.id", ondelete="SET NULL"), nullable=True
    )
    review_status: Mapped[str] = mapped_column(
        String(32), default="pending_review", nullable=False
    )
    confirmed_by_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("people.id"), nullable=True
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class RegistrationIdentityProfile(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "registration_identity_profiles"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    identity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(500), nullable=False)
    identifier_masked: Mapped[str] = mapped_column(String(500), nullable=False)
    identifier_fingerprint: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_nature: Mapped[str] = mapped_column(String(32), default="company_owned", nullable=False)
    custodian_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class PlatformAccountRegistrationIdentity(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "platform_account_registration_identities"
    __table_args__ = (
        UniqueConstraint(
            "platform_tenant_id",
            "registration_identity_asset_id",
            "role",
            name="uq_tenant_identity_role",
        ),
    )

    platform_tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_tenants.id"), nullable=False
    )
    registration_identity_asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(32), default="primary", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class Account(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("platform_tenant_id", "normalized_login_identifier"),)

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    platform_tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("platform_tenants.id"), nullable=False
    )
    login_identifier: Mapped[str] = mapped_column(String(320), nullable=False)
    normalized_login_identifier: Mapped[str] = mapped_column(String(320), nullable=False)
    account_type: Mapped[str] = mapped_column(String(50), nullable=False)
    registration_identity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    registration_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("people.id"), nullable=True
    )
    mfa_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False)
    privilege_level: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    parent_account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    account_kind: Mapped[str] = mapped_column(String(32), default="member_login", nullable=False)
    login_method: Mapped[str] = mapped_column(
        String(32), default="registration_identity", nullable=False
    )
    account_role: Mapped[str] = mapped_column(String(32), default="member", nullable=False)
    primary_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    legacy_source_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    legacy_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class AccessGrant(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "access_grants"

    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    department_id: Mapped[UUID | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    grant_type: Mapped[str] = mapped_column(String(50), nullable=False)
    grant_role: Mapped[str] = mapped_column(String(50), default="member", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    monthly_budget: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    renewal_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(300), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy_source_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    legacy_metadata: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class CredentialReference(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "credential_references"

    account_id: Mapped[UUID | None] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    item_id: Mapped[str] = mapped_column(String(500), nullable=False)
    secure_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AccountGrant(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "account_grants"
    __table_args__ = (UniqueConstraint("account_id", "person_id", "privilege_level", "starts_at"),)

    account_id: Mapped[UUID] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), nullable=False)
    privilege_level: Mapped[str] = mapped_column(String(32), default="normal", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    ends_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class InternalSystemProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "internal_system_profiles"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    repository_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    production_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    tech_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    deployment_guide_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    recovery_guide_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    backup_description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ResourceProfile(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "resource_profiles"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    resource_family: Mapped[str] = mapped_column(String(50), nullable=False)
    managed_under_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platform_tenants.id"), nullable=True
    )
    parent_resource_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id"), nullable=True
    )
    external_identifier_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    external_identifier_value: Mapped[str | None] = mapped_column(String(500), nullable=True)
    management_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CredentialRecord(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "credential_records"

    subject_type: Mapped[str] = mapped_column(String(50), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(nullable=False)
    credential_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    masked_hint: Mapped[str | None] = mapped_column(String(300), nullable=True)
    storage_mode: Mapped[str] = mapped_column(String(32), default="external_vault", nullable=False)
    content_reference: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    custodian_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_rotated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ServiceProduct(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "service_products"
    __table_args__ = (UniqueConstraint("provider_id", "code"),)

    provider_id: Mapped[UUID] = mapped_column(ForeignKey("providers.id"), nullable=False)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    service_category: Mapped[str] = mapped_column(String(80), nullable=False)
    billing_mode: Mapped[str] = mapped_column(String(50), nullable=False)


class ServiceInstance(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "service_instances"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    service_product_id: Mapped[UUID] = mapped_column(
        ForeignKey("service_products.id"), nullable=False
    )
    purchase_platform_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platforms.id"), nullable=True
    )
    purchase_tenant_asset_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("assets.id"), nullable=True
    )
    subscription_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="CNY", nullable=False)
    starts_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class MetricDefinition(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "metric_definitions"

    metric_key: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    aggregation: Mapped[str] = mapped_column(String(32), default="latest", nullable=False)


class MetricSample(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "metric_samples"
    __table_args__ = (
        Index(
            "ix_metric_samples_lookup",
            "service_instance_id",
            "metric_definition_id",
            "collected_at",
        ),
    )

    service_instance_id: Mapped[UUID] = mapped_column(
        ForeignKey("service_instances.id"), nullable=False
    )
    metric_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("metric_definitions.id"), nullable=False
    )
    value: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)


class AuditLog(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_object", "object_type", "object_id", "created_at"),)

    actor_user_id: Mapped[UUID | None] = mapped_column(nullable=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_id: Mapped[UUID | None] = mapped_column(nullable=True)
    before_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    after_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class InfrastructureProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "infrastructure_profiles"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    external_resource_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    region: Mapped[str | None] = mapped_column(String(120), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    specification: Mapped[str | None] = mapped_column(Text, nullable=True)
    public_address: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DeviceProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "device_profiles"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    manufacturer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(200), nullable=True)
    location: Mapped[str | None] = mapped_column(String(300), nullable=True)
    assignee_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    warranty_expires_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class DomainProfile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "domain_profiles"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), unique=True, nullable=False)
    domain_name: Mapped[str] = mapped_column(String(253), unique=True, nullable=False)
    registrar: Mapped[str | None] = mapped_column(String(200), nullable=True)
    dns_provider: Mapped[str | None] = mapped_column(String(200), nullable=True)
    certificate_provider: Mapped[str | None] = mapped_column(String(200), nullable=True)
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class AssetAttachment(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "asset_attachments"

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(120), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class AssetEvent(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "asset_events"
    __table_args__ = (Index("ix_asset_events_asset", "asset_id", "occurred_at"),)

    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    summary: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AppSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class ConnectorDefinition(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "connector_definitions"

    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(32), default="1.0", nullable=False)
    capabilities: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ProviderConnection(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "provider_connections"

    connector_definition_id: Mapped[UUID] = mapped_column(
        ForeignKey("connector_definitions.id"), nullable=False
    )
    legal_entity_id: Mapped[UUID] = mapped_column(ForeignKey("legal_entities.id"), nullable=False)
    platform_tenant_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platform_tenants.id"), nullable=True
    )
    credential_reference_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("credential_references.id"), nullable=True
    )
    service_instance_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("service_instances.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="disabled", nullable=False)
    configuration: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExternalMapping(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "external_mappings"
    __table_args__ = (UniqueConstraint("provider_connection_id", "external_type", "external_id"),)

    provider_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("provider_connections.id"), nullable=False
    )
    asset_id: Mapped[UUID] = mapped_column(ForeignKey("assets.id"), nullable=False)
    external_type: Mapped[str] = mapped_column(String(80), nullable=False)
    external_id: Mapped[str] = mapped_column(String(500), nullable=False)
    external_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class SyncJob(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "sync_jobs"

    provider_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("provider_connections.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    schedule: Mapped[str | None] = mapped_column(String(120), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class SyncJobRun(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "sync_job_runs"

    sync_job_id: Mapped[UUID] = mapped_column(ForeignKey("sync_jobs.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class UsageAlertRule(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    """A platform-neutral threshold evaluated against a connector snapshot."""

    __tablename__ = "usage_alert_rules"

    provider_connection_id: Mapped[UUID] = mapped_column(
        ForeignKey("provider_connections.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    metric_key: Mapped[str] = mapped_column(String(100), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    recipient_person_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class UsageNotificationSchedule(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    """A daily DingTalk digest schedule for selected platform connections."""

    __tablename__ = "usage_notification_schedules"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    connection_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    recipient_person_ids: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(5), nullable=False)
    timezone: Mapped[str] = mapped_column(String(50), default="Asia/Shanghai", nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sent_on: Mapped[date | None] = mapped_column(Date, nullable=True)


class UsageNotificationLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "usage_notification_logs"

    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    usage_alert_rule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("usage_alert_rules.id"), nullable=True
    )
    usage_notification_schedule_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("usage_notification_schedules.id"), nullable=True
    )
    provider_connection_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("provider_connections.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    message_summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class WorkflowRequest(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, VersionMixin, Base):
    __tablename__ = "workflow_requests"

    request_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    request_type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    requester_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class Handover(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, VersionMixin, Base):
    __tablename__ = "handovers"

    handover_no: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    person_id: Mapped[UUID] = mapped_column(ForeignKey("people.id"), nullable=False)
    receiver_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    reviewer_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    reason: Mapped[str] = mapped_column(String(80), default="departure", nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class RiskFinding(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, VersionMixin, Base):
    __tablename__ = "risk_findings"

    rule_key: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="open", nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ImportBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "import_batches"

    file_name: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="preview", nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)


class SourceImportRecord(UUIDPrimaryKeyMixin, TimestampMixin, ArchiveMixin, Base):
    __tablename__ = "source_import_records"

    import_batch_id: Mapped[UUID] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(50), nullable=False)
    source_identifier: Mapped[str | None] = mapped_column(String(500), nullable=True)
    raw_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    suggested_object_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    suggested_name: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4), nullable=True)
    mapping_status: Mapped[str] = mapped_column(
        String(32), default="pending_review", nullable=False
    )
    canonical_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    canonical_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("accounts.id"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportAnalysis(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One reproducible interpretation of an import batch."""

    __tablename__ = "import_analyses"
    __table_args__ = (Index("ix_import_analyses_batch_created", "import_batch_id", "created_at"),)

    import_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    analysis_mode: Mapped[str] = mapped_column(String(32), default="rules", nullable=False)
    analyzer_version: Mapped[str] = mapped_column(String(50), nullable=False)
    catalog_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="completed", nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    failure_detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportProposedObject(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A reviewed, non-canonical object proposed from one source record."""

    __tablename__ = "import_proposed_objects"
    __table_args__ = (
        UniqueConstraint("import_batch_id", "proposal_key"),
        Index("ix_import_proposed_objects_batch_status", "import_batch_id", "review_status"),
        Index("ix_import_proposed_objects_match", "matched_asset_id", "matched_person_id"),
    )

    import_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    source_import_record_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("source_import_records.id", ondelete="SET NULL"), nullable=True
    )
    proposal_key: Mapped[str] = mapped_column(String(200), nullable=False)
    layer_code: Mapped[str] = mapped_column(String(32), nullable=False)
    object_type: Mapped[str] = mapped_column(String(80), nullable=False)
    suggested_name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_payload: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    extraction_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    match_confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0, nullable=False)
    match_status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
    matched_asset_id: Mapped[UUID | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    matched_platform_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("platforms.id"), nullable=True
    )
    matched_person_id: Mapped[UUID | None] = mapped_column(ForeignKey("people.id"), nullable=True)
    matched_department_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class ImportProposedRelation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A relationship inferred between proposed or already matched objects."""

    __tablename__ = "import_proposed_relations"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id",
            "source_proposal_id",
            "target_proposal_id",
            "relation_type",
            name="uq_import_proposed_relation",
        ),
        Index("ix_import_proposed_relations_batch_status", "import_batch_id", "review_status"),
    )

    import_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    source_proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_proposed_objects.id", ondelete="CASCADE"), nullable=False
    )
    target_proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("import_proposed_objects.id", ondelete="CASCADE"), nullable=False
    )
    relation_type: Mapped[str] = mapped_column(String(50), nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeveloperIntakeBatch(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A developer-only, sanitized review area outside the asset ledger.

    It intentionally has no raw file or credential column. A record may carry
    account identifiers when needed for review, but passwords, keys, cookies
    and other secrets must never be copied into this model.
    """

    __tablename__ = "developer_intake_batches"

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    source_location: Mapped[str] = mapped_column(String(1000), nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="staged", nullable=False)
    confidentiality: Mapped[str] = mapped_column(
        String(32), default="developer_only", nullable=False
    )
    responsible_person_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("people.id"), nullable=True
    )
    created_by_user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    summary: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class DeveloperIntakeRecord(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One sanitized classification record visible only in the control plane."""

    __tablename__ = "developer_intake_records"
    __table_args__ = (
        UniqueConstraint("developer_intake_batch_id", "record_key"),
        Index(
            "ix_developer_intake_records_batch_status",
            "developer_intake_batch_id",
            "review_status",
        ),
    )

    developer_intake_batch_id: Mapped[UUID] = mapped_column(
        ForeignKey("developer_intake_batches.id", ondelete="CASCADE"), nullable=False
    )
    record_key: Mapped[str] = mapped_column(String(200), nullable=False)
    source_file: Mapped[str] = mapped_column(String(300), nullable=False)
    suggested_name: Mapped[str] = mapped_column(String(300), nullable=False)
    suggested_layers: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    disposition: Mapped[str] = mapped_column(String(32), default="hold", nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    masked_identifiers: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
    review_note: Mapped[str | None] = mapped_column(Text, nullable=True)
