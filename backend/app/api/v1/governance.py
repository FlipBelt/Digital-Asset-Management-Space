from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, require_permission
from app.db.session import get_db
from app.models import Asset, AssetResponsibility, RiskFinding, WorkflowRequest
from app.schemas.inventory import (
    RiskFindingRead,
    WorkflowRequestCreate,
    WorkflowRequestRead,
)

router = APIRouter(tags=["governance"])
require_governance_write = Depends(require_permission("governance.write"))


@router.get("/requests", response_model=list[WorkflowRequestRead])
def list_requests(db: Session = Depends(get_db)) -> list[WorkflowRequest]:
    return list(
        db.scalars(
            select(WorkflowRequest)
            .where(WorkflowRequest.archived_at.is_(None))
            .order_by(WorkflowRequest.created_at.desc())
        )
    )


@router.post("/requests", response_model=WorkflowRequestRead, status_code=status.HTTP_201_CREATED)
def create_request(
    payload: WorkflowRequestCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_governance_write,
) -> WorkflowRequest:
    item = WorkflowRequest(**payload.model_dump(), request_no=f"REQ-{uuid4().hex[:10].upper()}")
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/requests/{request_id}/transition", response_model=WorkflowRequestRead)
def transition_request(
    request_id: UUID,
    target_status: str,
    version: int,
    db: Session = Depends(get_db),
    _: AccessContext = require_governance_write,
) -> WorkflowRequest:
    item = db.get(WorkflowRequest, request_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(status_code=404, detail="申请不存在")
    if item.version != version:
        raise HTTPException(status_code=409, detail="申请已被其他用户修改")
    allowed = {
        "draft": {"pending", "cancelled"},
        "pending": {"approved", "rejected", "cancelled"},
        "approved": {"executing"},
        "executing": {"completed", "failed"},
    }
    if target_status not in allowed.get(item.status, set()):
        raise HTTPException(status_code=409, detail="当前状态不能执行此操作")
    item.status = target_status
    item.version += 1
    db.commit()
    db.refresh(item)
    return item


@router.get("/risk-findings", response_model=list[RiskFindingRead])
def list_risks(db: Session = Depends(get_db)) -> list[RiskFinding]:
    return list(
        db.scalars(
            select(RiskFinding)
            .where(RiskFinding.archived_at.is_(None))
            .order_by(RiskFinding.detected_at.desc())
        )
    )


@router.post("/risk-findings/scan", response_model=list[RiskFindingRead])
def scan_risks(
    db: Session = Depends(get_db),
    _: AccessContext = require_governance_write,
) -> list[RiskFinding]:
    existing = {
        (item.rule_key, item.asset_id)
        for item in db.scalars(
            select(RiskFinding).where(
                RiskFinding.archived_at.is_(None), RiskFinding.status == "open"
            )
        )
    }
    created: list[RiskFinding] = []
    assets = list(db.scalars(select(Asset).where(Asset.archived_at.is_(None))))
    for asset in assets:
        has_primary = db.scalar(
            select(AssetResponsibility.id).where(
                AssetResponsibility.asset_id == asset.id,
                AssetResponsibility.archived_at.is_(None),
                AssetResponsibility.is_primary.is_(True),
            )
        )
        rules: list[tuple[str, str, str]] = []
        if has_primary is None:
            rules.append(("NO_PRIMARY_OWNER", "medium", "资产缺少主要负责人"))
        if asset.criticality == "critical":
            backup = db.scalar(
                select(AssetResponsibility.id).where(
                    AssetResponsibility.asset_id == asset.id,
                    AssetResponsibility.archived_at.is_(None),
                    AssetResponsibility.role_type == "backup_maintainer",
                )
            )
            if backup is None:
                rules.append(("CRITICAL_NO_BACKUP_OWNER", "high", "关键资产缺少备用负责人"))
        if asset.expires_at and asset.expires_at <= (datetime.now(UTC).date() + timedelta(days=30)):
            rules.append(("SUBSCRIPTION_EXPIRING", "medium", "资产将在30天内到期"))
        for key, severity, title in rules:
            if (key, asset.id) not in existing:
                finding = RiskFinding(
                    rule_key=key,
                    asset_id=asset.id,
                    severity=severity,
                    title=f"{asset.name}：{title}",
                    detail={"asset_code": asset.asset_code},
                )
                db.add(finding)
                created.append(finding)
    db.commit()
    for item in created:
        db.refresh(item)
    return created


@router.post("/risk-findings/{finding_id}/resolve", response_model=RiskFindingRead)
def resolve_risk(
    finding_id: UUID,
    version: int,
    db: Session = Depends(get_db),
    _: AccessContext = require_governance_write,
) -> RiskFinding:
    item = db.get(RiskFinding, finding_id)
    if item is None:
        raise HTTPException(status_code=404, detail="风险项不存在")
    if item.version != version:
        raise HTTPException(status_code=409, detail="风险项已被其他用户修改")
    item.status = "resolved"
    item.resolved_at = datetime.now(UTC)
    item.version += 1
    db.commit()
    db.refresh(item)
    return item
