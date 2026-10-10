"""Task-oriented projections over the canonical Asset registry."""

from datetime import date
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.access import (
    AccessContext,
    asset_visibility_clause,
    get_access_context,
    person_department_ids,
    require_asset_write,
)
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import (
    AccessGrant,
    Account,
    Asset,
    AssetBookmark,
    AssetCategory,
    AssetEvidence,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Person,
    ServiceInstance,
    ServiceProduct,
)
from app.schemas.assets import AssetRead
from app.schemas.catalog import AssetTypeRead
from app.schemas.common import ListResponse, Pagination
from app.services.assets import allocate_asset_code, ensure_internal_identifier

router = APIRouter(tags=["asset-space"])
AI_ASSISTED_CODES = ("internal_system", "automation_script")
AI_DEVELOPMENT_METHODS = ("vibe_coding", "mixed")


def ai_registration_type_clause():
    return or_(
        AssetType.code.startswith("ai_", autoescape=True), AssetType.code.in_(AI_ASSISTED_CODES)
    )


def ai_outcome_clause():
    return or_(
        Asset.asset_type_id.in_(
            select(AssetType.id).where(AssetType.code.startswith("ai_", autoescape=True))
        ),
        and_(
            Asset.asset_type_id.in_(
                select(AssetType.id).where(AssetType.code.in_(AI_ASSISTED_CODES))
            ),
            Asset.development_method.in_(AI_DEVELOPMENT_METHODS),
        ),
    )


class AIRegistrationTypeRead(AssetTypeRead):
    registration_name: str
    requires_ai_development: bool


@router.get("/space/registration-types", response_model=list[AIRegistrationTypeRead])
def ai_registration_types(
    db: Session = Depends(get_db),
    _: AccessContext = Depends(get_access_context),
):
    types = db.scalars(
        select(AssetType)
        .where(AssetType.archived_at.is_(None), ai_registration_type_clause())
        .order_by(AssetType.name)
    )
    names = {"internal_system": "AI 辅助开发系统", "automation_script": "AI 辅助自动化脚本"}
    return [
        AIRegistrationTypeRead(
            **AssetTypeRead.model_validate(item).model_dump(),
            registration_name=names.get(item.code, item.name),
            requires_ai_development=item.code in AI_ASSISTED_CODES,
        )
        for item in types
    ]


def active_period(model):
    today = date.today()
    return and_(
        or_(model.starts_at.is_(None), model.starts_at <= today),
        or_(model.ends_at.is_(None), model.ends_at >= today),
    )


def personal_scope(person_id, department_id, category):
    def responsibility(role):
        return exists(
            select(AssetResponsibility.id)
            .correlate(Asset)
            .where(
                AssetResponsibility.asset_id == Asset.id,
                AssetResponsibility.person_id == person_id,
                AssetResponsibility.role_type == role,
                AssetResponsibility.archived_at.is_(None),
                active_period(AssetResponsibility),
            )
        )

    responsible = responsibility("responsible")
    using = responsibility("user")
    granted = exists(
        select(AccessGrant.id)
        .correlate(Asset)
        .where(
            or_(
                AccessGrant.asset_id == Asset.id,
                AccessGrant.account_id.in_(
                    select(Account.id)
                    .where(Account.asset_id == Asset.id, Account.archived_at.is_(None))
                    .correlate(Asset)
                ),
            ),
            or_(
                AccessGrant.person_id == person_id,
                and_(
                    AccessGrant.department_id.in_(person_department_ids(person_id)),
                    AccessGrant.person_id.is_(None),
                ),
            ),
            AccessGrant.archived_at.is_(None),
            AccessGrant.status == "active",
            active_period(AccessGrant),
        )
    )
    created = Asset.created_by_person_id == person_id
    mine = or_(created, responsible, using, granted)
    if category == "bookmarks":
        return exists(
            select(AssetBookmark.id)
            .correlate(Asset)
            .where(AssetBookmark.asset_id == Asset.id, AssetBookmark.person_id == person_id)
        )
    if category == "created":
        return created
    if category == "responsible":
        return responsible
    if category == "using":
        return or_(responsible, using, granted)
    if category == "drafts":
        return and_(created, Asset.status == "draft")
    if category == "subscriptions":
        return and_(
            mine,
            exists(
                select(ServiceInstance.id)
                .correlate(Asset)
                .where(ServiceInstance.asset_id == Asset.id, ServiceInstance.archived_at.is_(None))
            ),
        )
    if category == "ai":
        return and_(mine, ai_outcome_clause())
    return mine


@router.get("/space/assets", response_model=ListResponse[AssetRead])
def space_assets(
    scope: Literal["discover", "mine", "team"] = "mine",
    category: Literal[
        "all",
        "created",
        "responsible",
        "using",
        "subscriptions",
        "ai",
        "drafts",
        "workflows",
        "bookmarks",
    ] = "all",
    workflow_view: Literal["all", "created", "bookmarks"] = "all",
    department_id: UUID | None = None,
    asset_type_id: UUID | None = None,
    asset_category_id: UUID | None = None,
    keyword: str = Query(default="", max_length=200),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    conditions = [Asset.archived_at.is_(None), asset_visibility_clause(access)]
    person = db.get(Person, access.person_id) if access.person_id else None
    if scope == "mine":
        conditions.append(
            personal_scope(access.person_id, person.department_id if person else None, category)
            if access.person_id
            else False
        )
    if scope == "team":
        selected = department_id or (person.department_id if person else None)
        conditions.append(Asset.owner_department_id == selected if selected else False)
    if category == "workflows":
        conditions.append(
            Asset.asset_type_id.in_(select(AssetType.id).where(AssetType.code == "ai_workflow"))
        )
        if workflow_view != "all":
            conditions.append(
                personal_scope(access.person_id, None, workflow_view) if access.person_id else False
            )
    elif workflow_view != "all":
        raise HTTPException(422, "工作流视图仅用于工作流列表")
    if asset_type_id:
        conditions.append(Asset.asset_type_id == asset_type_id)
    if asset_category_id:
        conditions.append(
            Asset.asset_type_id.in_(
                select(AssetType.id).where(AssetType.category_id == asset_category_id)
            )
        )
    if keyword.strip():
        conditions.append(
            or_(
                Asset.name.contains(keyword.strip(), autoescape=True),
                Asset.description.contains(keyword.strip(), autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(Asset).where(*conditions)) or 0
    statement = select(Asset).where(*conditions)
    if scope != "mine" and category != "workflows":
        statement = (
            statement.join(AssetType, Asset.asset_type_id == AssetType.id)
            .join(AssetCategory, AssetType.category_id == AssetCategory.id)
            .order_by(AssetCategory.sort_order, AssetCategory.id)
        )
    rows = db.scalars(
        statement.order_by(Asset.updated_at.desc(), Asset.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ListResponse[AssetRead](
        data=[AssetRead.model_validate(a) for a in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/space/groups")
def space_groups(
    scope: Literal["discover", "team"] = "discover",
    department_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    conditions = [Asset.archived_at.is_(None), asset_visibility_clause(access)]
    if scope == "team":
        person = db.get(Person, access.person_id) if access.person_id else None
        selected = department_id or (person.department_id if person else None)
        conditions.append(Asset.owner_department_id == selected if selected else False)
    counts = dict(
        db.execute(
            select(AssetType.category_id, func.count(Asset.id))
            .join(Asset, Asset.asset_type_id == AssetType.id)
            .where(*conditions)
            .group_by(AssetType.category_id)
        ).all()
    )
    # Keep historical categories with visible records discoverable.
    categories = db.scalars(
        select(AssetCategory)
        .where(or_(AssetCategory.archived_at.is_(None), AssetCategory.id.in_(counts)))
        .order_by(AssetCategory.sort_order, AssetCategory.id)
    )
    return {
        "total": sum(counts.values()),
        "categories": [
            {
                "id": row.id,
                "parent_id": row.parent_id,
                "code": row.code,
                "name": row.name,
                "sort_order": row.sort_order,
                "count": counts.get(row.id, 0),
            }
            for row in categories
        ],
    }


class DraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=2000)
    asset_type_id: UUID
    source_type: Literal["manual", "agent", "connector"] = "manual"
    source_system: str | None = Field(default=None, max_length=120)
    source_agent: str | None = Field(default=None, max_length=120)
    source_reference: str | None = Field(default=None, max_length=500)
    development_method: Literal["traditional", "low_code", "vibe_coding", "mixed"] | None = None


def draft_id(user_id: UUID, request_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"asset-draft:{user_id}:{request_id}")


@router.post("/assets/draft", response_model=AssetRead, dependencies=[Depends(require_csrf)])
def create_draft(
    payload: DraftInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
):
    return persist_draft(payload, db, access)


def persist_draft(payload: DraftInput, db: Session, access: AccessContext, *, commit=True):
    if not access.person_id:
        raise HTTPException(422, "请先关联员工身份")
    asset_type = db.get(AssetType, payload.asset_type_id)
    if asset_type is None or asset_type.archived_at is not None:
        raise HTTPException(422, "资产类型不可用")
    identity = draft_id(access.user.id, payload.request_id)
    fields = payload.model_dump(exclude={"request_id"})
    existing = db.get(Asset, identity)
    if existing:
        if existing.archived_at is not None or any(
            getattr(existing, k) != v for k, v in fields.items()
        ):
            raise HTTPException(409, "该请求编号已经用于其他草稿内容")
        return existing
    if asset_type.code in AI_ASSISTED_CODES:
        if payload.development_method not in AI_DEVELOPMENT_METHODS:
            raise HTTPException(
                422, "AI 成果需注明 AI 辅助编程或混合开发；其他系统和脚本请由管理后台登记"
            )
    elif not asset_type.code.startswith("ai_"):
        raise HTTPException(
            403, "成果登记仅支持 AI 相关类型；订阅请在我的订阅登记，其他资产请由管理后台登记"
        )
    elif payload.development_method:
        raise HTTPException(422, "开发方式仅适用于 AI 辅助系统或脚本")
    person = db.get(Person, access.person_id)
    if (
        person is None or person.archived_at is not None
        or person.employment_status != "active"
    ):
        raise HTTPException(422, "员工身份不可用")
    item = Asset(
        id=identity,
        **fields,
        asset_code=allocate_asset_code(db, person.legal_entity_id, payload.asset_type_id),
        legal_entity_id=person.legal_entity_id,
        owner_department_id=person.department_id,
        ownership_scope="pending",
        created_by_person_id=person.id,
        status="draft",
        review_status="pending_review",
        confidentiality="personal",
        sharing_scope="private",
    )
    db.add(item)
    try:
        db.flush()
        ensure_internal_identifier(db, item)
        # Registration identity is server verified; AI proposals never replace this default.
        db.add(AssetResponsibility(
            asset_id=item.id, person_id=person.id, role_type="responsible", is_primary=True,
        ))
        db.add(
            AuditLog(
                actor_user_id=access.user.id,
                action="asset.draft.create",
                object_type="asset",
                object_id=item.id,
                request_id=str(payload.request_id),
                after_data={
                    "source_type": item.source_type,
                    "source_system": item.source_system,
                    "source_agent": item.source_agent,
                    "status": "draft",
                    "created_by_person_id": str(person.id),
                    "responsible_person_id": str(person.id),
                },
            )
        )
        if commit:
            db.commit()
        else:
            db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "请求冲突，请使用同一请求编号重试") from exc
    db.refresh(item)
    return item


class MembershipInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    service_product_id: UUID
    plan: str = Field(min_length=1, max_length=200)
    catalog_plan: str | None = Field(default=None, min_length=1, max_length=200)
    funding_source: Literal["company", "department", "personal", "free", "trial"]
    starts_at: date
    usage_frequency: Literal["daily", "weekly", "monthly", "rarely"]
    primary_purpose: str = Field(min_length=1, max_length=500)


@router.post("/space/memberships", response_model=AssetRead, dependencies=[Depends(require_csrf)])
def create_membership(
    payload: MembershipInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
):
    person = db.get(Person, access.person_id) if access.person_id else None
    if person is None or person.archived_at is not None:
        raise HTTPException(422, "请先关联有效员工身份")
    product = db.get(ServiceProduct, payload.service_product_id)
    if product is None or product.archived_at is not None:
        raise HTTPException(422, "服务不可用，请联系管理员补充服务目录")
    identity = uuid5(NAMESPACE_URL, f"membership:{access.user.id}:{payload.request_id}")
    existing = db.get(Asset, identity)
    if existing:
        instance = db.scalar(select(ServiceInstance).where(ServiceInstance.asset_id == identity))
        expected = dict(
            service_product_id=payload.service_product_id,
            subscription_name=payload.plan,
            funding_source=payload.funding_source,
            starts_at=payload.starts_at,
            usage_frequency=payload.usage_frequency,
            primary_purpose=payload.primary_purpose,
        )
        if (
            existing.archived_at is not None
            or instance is None
            or instance.archived_at is not None
            or any(getattr(instance, k) != v for k, v in expected.items())
        ):
            raise HTTPException(409, "请求编号对应的登记内容已改变")
        return existing
    from app.services.service_catalog import validate_subscription

    validate_subscription(db, product, payload.plan, payload.catalog_plan)
    asset_type = db.scalar(
        select(AssetType).where(
            AssetType.code == "saas_subscription", AssetType.archived_at.is_(None)
        )
    )
    if asset_type is None:
        raise HTTPException(422, "服务订阅类型尚未配置")
    item = Asset(
        id=identity,
        name=f"{product.name} · {payload.plan}"[:200],
        asset_type_id=asset_type.id,
        asset_code=allocate_asset_code(db, person.legal_entity_id, asset_type.id),
        legal_entity_id=person.legal_entity_id,
        owner_department_id=person.department_id,
        created_by_person_id=person.id,
        ownership_scope="pending",
        confidentiality="personal",
        sharing_scope="private",
        source_type="manual",
        source_system="membership-registration",
        status="draft",
        review_status="pending_review",
        description=payload.primary_purpose,
    )
    db.add(item)
    try:
        db.flush()
        ensure_internal_identifier(db, item)
        db.add(
            ServiceInstance(
                asset_id=item.id,
                service_product_id=product.id,
                subscription_name=payload.plan,
                funding_source=payload.funding_source,
                payer_person_id=person.id if payload.funding_source == "personal" else None,
                starts_at=payload.starts_at,
                usage_frequency=payload.usage_frequency,
                primary_purpose=payload.primary_purpose,
            )
        )
        db.add(
            AuditLog(
                actor_user_id=access.user.id,
                action="membership.register",
                object_type="asset",
                object_id=item.id,
                request_id=str(payload.request_id),
                after_data={"status": "draft"},
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "登记冲突，请使用同一请求编号重试") from exc
    db.refresh(item)
    return item


@router.get("/space/summary")
def space_summary(
    db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)
):
    categories = ("created", "responsible", "using", "subscriptions", "ai", "drafts", "bookmarks")
    counts = {category: 0 for category in categories}
    if not access.person_id:
        return {**counts, "evidence": 0}
    for category in categories:
        counts[category] = (
            db.scalar(
                select(func.count())
                .select_from(Asset)
                .where(
                    Asset.archived_at.is_(None),
                    asset_visibility_clause(access),
                    personal_scope(access.person_id, None, category),
                )
            )
            or 0
        )
    counts["evidence"] = (
        db.scalar(
            select(func.count())
            .select_from(AssetEvidence)
            .where(AssetEvidence.person_id == access.person_id, AssetEvidence.archived_at.is_(None))
        )
        or 0
    )
    return counts


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    asset_id: UUID
    service_product_id: UUID
    subscription_name: str | None
    funding_source: str | None
    payer_person_id: UUID | None
    starts_at: date | None
    expires_at: date | None
    usage_frequency: str | None
    primary_purpose: str | None


@router.get("/space/memberships", response_model=list[MembershipRead])
def memberships(db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)):
    if not access.person_id:
        return []
    return list(
        db.scalars(
            select(ServiceInstance)
            .join(Asset, Asset.id == ServiceInstance.asset_id)
            .where(
                ServiceInstance.archived_at.is_(None),
                Asset.archived_at.is_(None),
                asset_visibility_clause(access),
                personal_scope(access.person_id, None, "subscriptions"),
            )
            .order_by(ServiceInstance.created_at.desc())
        )
    )
