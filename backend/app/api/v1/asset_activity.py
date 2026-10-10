"""Personal bookmarks, subscription evidence and explicit draft confirmation."""

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.access import (
    AccessContext,
    asset_visibility_clause,
    get_access_context,
    require_asset_visible,
    require_asset_write,
)
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import (
    Asset,
    AssetBookmark,
    AssetConfirmation,
    AssetEvidence,
    AuditLog,
    Person,
    ServiceInstance,
)
from app.schemas.assets import AssetRead
from app.schemas.common import ListResponse, Pagination
from app.services.asset_confirmation import (
    confirmation_preview,
    draft_digest,
    draft_snapshot,
    lock_asset,
    snapshot_digest,
)

router = APIRouter(tags=["asset-activity"])


def employee(db: Session, access: AccessContext) -> Person:
    person = db.get(Person, access.person_id) if access.person_id else None
    if person is None or person.archived_at is not None or person.employment_status != "active":
        raise HTTPException(422, "请先关联有效的在职员工身份")
    return person


def visible(db: Session, access: AccessContext, asset_id: UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.archived_at is not None:
        raise HTTPException(404, "资产不存在或无权查看")
    require_asset_visible(db, access, asset)
    return asset


def audit(db: Session, access: AccessContext, action: str, asset_id: UUID, facts: dict) -> None:
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action=action,
            object_type="asset",
            object_id=asset_id,
            after_data=facts,
            request_id=action,
        )
    )


@router.get("/space/bookmarks", response_model=list[UUID])
def bookmarks(db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)):
    person = employee(db, access)
    return list(
        db.scalars(
            select(AssetBookmark.asset_id)
            .join(Asset, Asset.id == AssetBookmark.asset_id)
            .where(
                AssetBookmark.person_id == person.id,
                Asset.archived_at.is_(None),
                asset_visibility_clause(access),
            )
        )
    )


@router.put("/assets/{asset_id}/bookmark", status_code=204, dependencies=[Depends(require_csrf)])
def add_bookmark(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    person = employee(db, access)
    visible(db, access, asset_id)
    # One asset row lock serializes concurrent PUTs; the unique key is the second guard.
    lock_asset(db, asset_id)
    if not db.scalar(
        select(AssetBookmark.id).where(
            AssetBookmark.asset_id == asset_id, AssetBookmark.person_id == person.id
        )
    ):
        db.add(AssetBookmark(asset_id=asset_id, person_id=person.id))
        audit(db, access, "asset.bookmark.add", asset_id, {})
        db.commit()
    return Response(status_code=204)


@router.delete("/assets/{asset_id}/bookmark", status_code=204, dependencies=[Depends(require_csrf)])
def remove_bookmark(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    person = employee(db, access)
    # A revoked user may remove their own stale bookmark without reading the asset.
    db.execute(
        delete(AssetBookmark).where(
            AssetBookmark.person_id == person.id, AssetBookmark.asset_id == asset_id
        )
    )
    db.commit()
    return Response(status_code=204)


class EvidenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    kind: Literal["exploration", "case", "method_share", "usage"]
    title: str = Field(min_length=1, max_length=200)
    problem: str = Field(min_length=1, max_length=2000)
    method: str = Field(min_length=1, max_length=2000)
    output: str = Field(min_length=1, max_length=2000)
    observed_effect: str | None = Field(default=None, max_length=2000)
    asset_id: UUID | None = None
    subscription_id: UUID | None = None


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    asset_id: UUID | None
    subscription_id: UUID | None
    kind: str
    title: str
    problem: str
    method: str
    output: str
    observed_effect: str | None
    review_status: str
    created_at: datetime


@router.get("/space/evidence", response_model=ListResponse[EvidenceRead])
def evidence_list(
    subscription_id: UUID | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=24, ge=1, le=100),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    person = employee(db, access)
    conditions = [AssetEvidence.person_id == person.id, AssetEvidence.archived_at.is_(None)]
    if subscription_id:
        conditions.append(AssetEvidence.subscription_id == subscription_id)
    total = db.scalar(select(func.count()).select_from(AssetEvidence).where(*conditions)) or 0
    rows = db.scalars(
        select(AssetEvidence)
        .where(*conditions)
        .order_by(AssetEvidence.created_at.desc(), AssetEvidence.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return ListResponse[EvidenceRead](
        data=[EvidenceRead.model_validate(row) for row in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.post("/space/evidence", response_model=EvidenceRead, dependencies=[Depends(require_csrf)])
def create_evidence(
    payload: EvidenceInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
):
    person = employee(db, access)
    linked_asset = payload.asset_id
    if payload.subscription_id:
        instance = db.get(ServiceInstance, payload.subscription_id)
        if instance is None or instance.archived_at is not None:
            raise HTTPException(404, "订阅不存在")
        visible(db, access, instance.asset_id)
        if linked_asset and linked_asset != instance.asset_id:
            raise HTTPException(422, "订阅与关联资产不一致")
        if payload.kind == "exploration" and (
            instance.funding_source != "personal" or instance.payer_person_id != person.id
        ):
            raise HTTPException(422, "AI 探索须关联本人自费订阅；其他应用请登记为案例")
        linked_asset = instance.asset_id
    elif payload.kind == "exploration":
        raise HTTPException(422, "AI 探索须选择已登记的本人自费订阅")
    if linked_asset:
        visible(db, access, linked_asset)
    body = payload.model_dump(mode="json", exclude={"request_id"})
    digest = hashlib.sha256(
        json.dumps(body, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    identity = uuid5(NAMESPACE_URL, f"asset-evidence:{access.user.id}:{payload.request_id}")
    existing = db.get(AssetEvidence, identity)
    if existing:
        if existing.archived_at is not None or existing.request_digest != digest:
            raise HTTPException(409, "请求编号已用于不同的证据内容")
        return existing
    item = AssetEvidence(
        id=identity,
        person_id=person.id,
        asset_id=linked_asset,
        request_digest=digest,
        **payload.model_dump(exclude={"request_id", "asset_id"}),
    )
    db.add(item)
    audit(
        db,
        access,
        "asset.evidence.create",
        linked_asset or identity,
        {"evidence_id": str(identity), "kind": payload.kind, "review_status": "pending_review"},
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "保存冲突，请重试同一请求") from exc
    db.refresh(item)
    return item


class ConfirmationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: UUID
    version: int = Field(ge=1)
    sharing_scope: Literal["private", "team", "company"] = "private"
    publish_new_version: bool = False


class ConfirmationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    asset_version: int
    outcome_version: int
    content_digest: str
    sharing_scope: str
    expires_at: datetime
    preview: dict


class ConfirmInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirmation_id: UUID
    version: int = Field(ge=1)
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    confirmed: Literal[True]


def owned_draft(db: Session, access: AccessContext, asset_id: UUID) -> Asset:
    employee(db, access)
    asset = lock_asset(db, asset_id)
    if asset is None or asset.archived_at is not None:
        raise HTTPException(404, "草稿不存在")
    require_asset_visible(db, access, asset)
    if asset.created_by_person_id != access.person_id:
        raise HTTPException(403, "只有创建人可以确认这份草稿")
    return asset


@router.post(
    "/assets/{asset_id}/confirmation",
    response_model=ConfirmationRead,
    dependencies=[Depends(require_csrf)],
)
def prepare_confirmation(
    asset_id: UUID,
    payload: ConfirmationInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
):
    asset = owned_draft(db, access, asset_id)
    if payload.sharing_scope == "team" and asset.owner_department_id is None:
        raise HTTPException(422, "未关联部门，暂不能选择团队共享")
    # A self-funded subscription is a personal fact, not a company license.
    subscription = db.scalar(
        select(ServiceInstance).where(
            ServiceInstance.asset_id == asset_id, ServiceInstance.archived_at.is_(None)
        )
    )
    if (
        subscription
        and subscription.funding_source == "personal"
        and payload.sharing_scope != "private"
    ):
        raise HTTPException(422, "个人自费订阅请保留私有；分享探索证据不转移使用许可")
    if asset.status != "draft" or asset.version != payload.version:
        raise HTTPException(409, "草稿已改变，请重新读取")
    snapshot = draft_snapshot(db, asset, payload.sharing_scope)
    digest = snapshot_digest(snapshot)
    outcome_version = max(1, asset.outcome_version + int(payload.publish_new_version))

    def response(item):
        return {
            "id": item.id,
            "asset_version": item.asset_version,
            "outcome_version": item.outcome_version,
            "content_digest": item.content_digest,
            "sharing_scope": item.sharing_scope,
            "expires_at": item.expires_at,
            "preview": confirmation_preview(snapshot),
        }

    identity = uuid5(NAMESPACE_URL, f"asset-confirm:{access.user.id}:{payload.request_id}")
    row = db.get(AssetConfirmation, identity)
    now = datetime.now(UTC)
    if row:
        if (
            row.asset_id != asset_id
            or row.content_digest != digest
            or row.asset_version != payload.version
            or row.outcome_version != outcome_version
            or row.cancelled_at
            or row.consumed_at
        ):
            raise HTTPException(409, "确认请求已经失效，请重新预览")
        if row.expires_at <= now:
            raise HTTPException(409, "确认已过期，请重新预览")
        return response(row)
    row = AssetConfirmation(
        id=identity,
        asset_id=asset_id,
        user_id=access.user.id,
        asset_version=payload.version,
        outcome_version=outcome_version,
        content_digest=digest,
        sharing_scope=payload.sharing_scope,
        expires_at=now + timedelta(minutes=30),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return response(row)


@router.post(
    "/assets/{asset_id}/confirm", response_model=AssetRead, dependencies=[Depends(require_csrf)]
)
def confirm_draft(
    asset_id: UUID,
    payload: ConfirmInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
):
    asset = owned_draft(db, access, asset_id)
    row = db.get(AssetConfirmation, payload.confirmation_id)
    if row is None or row.asset_id != asset_id or row.user_id != access.user.id:
        raise HTTPException(404, "确认记录不存在")
    if row.asset_version != payload.version or row.content_digest != payload.content_digest:
        raise HTTPException(409, "确认内容不匹配，请重新预览")
    now = datetime.now(UTC)
    if row.cancelled_at:
        raise HTTPException(409, "已取消确认")
    if row.consumed_at:
        # Only the exact, unchanged result is a safe retry.
        if (
            asset.version != row.asset_version + 1
            or asset.status != "active"
            or draft_digest(db, asset, row.sharing_scope) != row.result_digest
        ):
            raise HTTPException(409, "登记后资料已变化，请重新读取")
        return asset
    if (
        row.expires_at <= now
        or row.outcome_version not in {max(1, asset.outcome_version), asset.outcome_version + 1}
        or asset.status != "draft"
        or asset.version != row.asset_version
        or draft_digest(db, asset, row.sharing_scope) != row.content_digest
    ):
        raise HTTPException(409, "草稿或附件已改变，请重新预览后确认")
    asset.sharing_scope = row.sharing_scope
    asset.confidentiality = "personal" if row.sharing_scope == "private" else "internal"
    asset.status = "active"
    # Confirmation records the employee's deposit, not management approval or value.
    asset.review_status = "not_required" if asset.is_personal_subscription else "pending_review"
    asset.confirmed_by_person_id = access.person_id
    asset.confirmed_at = now
    asset.outcome_version = row.outcome_version
    asset.version += 1
    row.consumed_at = now
    row.result_digest = draft_digest(db, asset, row.sharing_scope)
    audit(
        db,
        access,
        "asset.registration.confirm",
        asset_id,
        {
            "confirmed_version": row.asset_version,
            "outcome_version": asset.outcome_version,
            "content_digest": row.content_digest,
            "sharing_scope": row.sharing_scope,
            "review_status": asset.review_status,
        },
    )
    db.commit()
    db.refresh(asset)
    return asset


@router.delete(
    "/assets/{asset_id}/confirmation/{confirmation_id}",
    status_code=204,
    dependencies=[Depends(require_csrf)],
)
def cancel_confirmation(
    asset_id: UUID,
    confirmation_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
):
    # Prepare, confirm and cancel use the same asset lock order.
    owned_draft(db, access, asset_id)
    row = db.scalar(
        select(AssetConfirmation)
        .where(
            AssetConfirmation.id == confirmation_id,
            AssetConfirmation.asset_id == asset_id,
            AssetConfirmation.user_id == access.user.id,
        )
        .with_for_update()
    )
    if row is None:
        raise HTTPException(404, "确认记录不存在")
    if row.consumed_at:
        raise HTTPException(409, "登记已完成，无法取消此前确认")
    row.cancelled_at = datetime.now(UTC)
    db.commit()
    return Response(status_code=204)
