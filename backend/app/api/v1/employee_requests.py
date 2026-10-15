"""Employee applications are separate from registration and access grants."""

from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.access import AccessContext, get_access_context, require_asset_visible
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import Asset, AuditLog, Person, Platform, WorkflowRequest
from app.schemas.inventory import WorkflowRequestRead

router = APIRouter(tags=["employee-requests"])


class EmployeeRequestInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    request_type: Literal["seat", "platform", "account"]
    resource_name: str = Field(min_length=1, max_length=160)
    purpose: str = Field(min_length=1, max_length=2000)
    asset_id: UUID | None = None
    platform_id: UUID | None = None


class CancelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)


def employee(db: Session, access: AccessContext) -> Person:
    person = db.get(Person, access.person_id) if access.person_id else None
    if person is None or person.archived_at is not None or person.employment_status != "active":
        raise HTTPException(422, "请先关联有效员工身份")
    return person


def audit(db: Session, access: AccessContext, item: WorkflowRequest, action: str, before=None):
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action=action,
            object_type="workflow_request",
            object_id=item.id,
            before_data=before,
            after_data={
                "status": item.status,
                "version": item.version,
                "request_type": item.request_type,
            },
        )
    )


@router.get("/space/requests", response_model=list[WorkflowRequestRead])
def my_requests(db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)):
    person = employee(db, access)
    return list(
        db.scalars(
            select(WorkflowRequest)
            .where(
                WorkflowRequest.requester_person_id == person.id,
                WorkflowRequest.archived_at.is_(None),
            )
            .order_by(WorkflowRequest.created_at.desc(), WorkflowRequest.id)
        )
    )


@router.post(
    "/space/requests",
    response_model=WorkflowRequestRead,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
def create_my_request(
    payload: EmployeeRequestInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    person = employee(db, access)
    identity = uuid5(NAMESPACE_URL, f"employee-request:{access.user.id}:{payload.request_id}")
    detail = {
        "resource_name": payload.resource_name,
        "purpose": payload.purpose,
        "platform_id": str(payload.platform_id) if payload.platform_id else None,
    }
    existing = db.get(WorkflowRequest, identity)
    if existing:
        if (
            existing.archived_at is not None
            or existing.request_type != payload.request_type
            or existing.asset_id != payload.asset_id
            or existing.detail != detail
        ):
            raise HTTPException(409, "该请求编号已用于其他申请内容")
        return existing
    if payload.asset_id:
        asset = db.get(Asset, payload.asset_id)
        if asset is None or asset.archived_at is not None:
            raise HTTPException(404, "资产不存在或无权查看")
        require_asset_visible(db, access, asset)
    if payload.platform_id:
        platform = db.get(Platform, payload.platform_id)
        if platform is None or platform.archived_at is not None:
            raise HTTPException(422, "平台不可用，请重新选择")
    labels = {"seat": "席位申请", "platform": "平台申请", "account": "账号申请"}
    item = WorkflowRequest(
        id=identity,
        request_no=f"REQ-{identity.hex[:16].upper()}",
        request_type=payload.request_type,
        title=f"{labels[payload.request_type]} · {payload.resource_name}",
        requester_person_id=person.id,
        asset_id=payload.asset_id,
        status="pending",
        version=1,
        detail=detail,
    )
    db.add(item)
    audit(db, access, item, "request.submit")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.get(WorkflowRequest, identity)
        if (
            existing
            and existing.request_type == payload.request_type
            and existing.asset_id == payload.asset_id
            and existing.detail == detail
        ):
            return existing
        raise HTTPException(409, "申请内容发生冲突，请重新提交") from None
    db.refresh(item)
    return item


@router.post(
    "/space/requests/{request_id}/cancel",
    response_model=WorkflowRequestRead,
    dependencies=[Depends(require_csrf)],
)
def cancel_my_request(
    request_id: UUID,
    payload: CancelInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    person = employee(db, access)
    item = db.scalar(
        select(WorkflowRequest)
        .where(
            WorkflowRequest.id == request_id,
            WorkflowRequest.requester_person_id == person.id,
            WorkflowRequest.archived_at.is_(None),
        )
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "申请不存在或无权操作")
    if item.version != payload.version:
        raise HTTPException(409, "申请状态已更新，请刷新后重试")
    if item.status not in {"draft", "pending"}:
        raise HTTPException(409, "当前申请已经处理，不能撤回")
    before = {"status": item.status, "version": item.version}
    item.status = "cancelled"
    item.version += 1
    audit(db, access, item, "request.cancel", before)
    db.commit()
    db.refresh(item)
    return item
