"""Explicit human review, separate from registration and responsibility assignment."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.asset_space import ai_outcome_clause
from app.core.access import AccessContext, can_govern_asset, get_access_context
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import Asset, AuditLog
from app.schemas.assets import AssetRead
from app.services.asset_confirmation import lock_asset

router = APIRouter(prefix="/asset-reviews", tags=["asset-reviews"])


def reviewer(access):
    if not access.has_permission("asset.write") or not (
        access.is_global_manager or access.department_scopes
    ):
        raise HTTPException(403, "需要部门负责人或资产管理员审核权限")


@router.get("")
def queue(
    status: Literal["pending_review", "approved", "rejected"] = "pending_review",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    asset_id: UUID | None = None,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    reviewer(access)
    query = select(Asset).where(
        Asset.archived_at.is_(None),
        Asset.status == "active",
        Asset.review_status == status,
        ai_outcome_clause(),
    )
    if asset_id is not None:
        query = query.where(Asset.id == asset_id)
    if not access.is_global_manager:
        query = query.where(Asset.owner_department_id.in_(access.department_scopes))
    from sqlalchemy import func

    total = db.scalar(select(func.count()).select_from(query.subquery()))
    items = db.scalars(
        query.order_by(Asset.updated_at.desc(), Asset.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return {
        "data": [AssetRead.model_validate(a) for a in items],
        "pagination": {"page": page, "page_size": page_size, "total": total},
    }


class ReviewInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=2000)


@router.post("/{asset_id}", response_model=AssetRead, dependencies=[Depends(require_csrf)])
def review(
    asset_id: UUID,
    payload: ReviewInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    reviewer(access)
    item = lock_asset(db, asset_id)
    if item is None or item.archived_at is not None or not can_govern_asset(access, item):
        raise HTTPException(404, "待审成果不存在或超出审核范围")
    if not db.scalar(select(Asset.id).where(Asset.id == asset_id, ai_outcome_clause())):
        raise HTTPException(404, "该资产不属于AI成果审核范围")
    if (
        item.version != payload.version
        or item.status != "active"
        or item.review_status != "pending_review"
    ):
        raise HTTPException(409, "成果版本或审核状态已变化，请刷新后核对")
    if payload.decision == "rejected" and not payload.reason:
        raise HTTPException(422, "退回时请填写原因")
    before = item.review_status
    item.review_status = payload.decision
    item.version += 1
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="asset.review",
            object_type="asset",
            object_id=item.id,
            before_data={"review_status": before, "version": payload.version},
            after_data={
                "review_status": item.review_status,
                "reason": payload.reason,
                "version": item.version,
                "reviewed_at": datetime.now(UTC).isoformat(),
            },
            request_id=f"asset-review:{item.id}:{payload.version}",
        )
    )
    db.commit()
    db.refresh(item)
    return item
