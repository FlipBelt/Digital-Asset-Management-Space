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
    AssetEvidence,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Person,
    ServiceInstance,
    ServiceProduct,
)
from app.schemas.assets import AssetRead
from app.schemas.common import ListResponse, Pagination
from app.services.assets import allocate_asset_code, ensure_internal_identifier

router = APIRouter(tags=["asset-space"])
AI_CODES = ("ai_skill", "ai_plugin", "ai_agent", "ai_workflow", "automation_script")


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
        return and_(
            mine, Asset.asset_type_id.in_(select(AssetType.id).where(AssetType.code.in_(AI_CODES)))
        )
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
    department_id: UUID | None = None,
    asset_type_id: UUID | None = None,
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
    if asset_type_id:
        conditions.append(Asset.asset_type_id == asset_type_id)
    if keyword.strip():
        conditions.append(
            or_(
                Asset.name.contains(keyword.strip(), autoescape=True),
                Asset.description.contains(keyword.strip(), autoescape=True),
            )
        )
    total = db.scalar(select(func.count()).select_from(Asset).where(*conditions)) or 0
    rows = db.scalars(
        select(Asset)
        .where(*conditions)
        .order_by(Asset.updated_at.desc(), Asset.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ListResponse[AssetRead](
        data=[AssetRead.model_validate(a) for a in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


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
    if not access.person_id:
        raise HTTPException(422, "请先关联员工身份")
    asset_type = db.get(AssetType, payload.asset_type_id)
    if asset_type is None or asset_type.archived_at is not None:
        raise HTTPException(422, "资产类型不可用")
    if payload.development_method and asset_type.code != "internal_system":
        raise HTTPException(422, "开发方式仅适用于系统资产")
    identity = draft_id(access.user.id, payload.request_id)
    fields = payload.model_dump(exclude={"request_id"})
    existing = db.get(Asset, identity)
    if existing:
        if existing.archived_at is not None or any(
            getattr(existing, k) != v for k, v in fields.items()
        ):
            raise HTTPException(409, "该请求编号已经用于其他草稿内容")
        return existing
    person = db.get(Person, access.person_id)
    if person is None or person.archived_at is not None:
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
                },
            )
        )
        db.commit()
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
