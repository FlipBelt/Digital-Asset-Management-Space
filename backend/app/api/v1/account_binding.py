from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import (
    AccessContext,
    can_manage_asset,
    require_asset_visible,
    require_asset_write,
)
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import Account, AuditLog, PlatformTenant
from app.schemas.inventory import AccountRead
from app.services.account_binding import require_active_employee
from app.services.asset_confirmation import lock_asset
from app.services.audited_requests import audited_retry

router = APIRouter(tags=["account-binding"])


class AccountEmployeeBindingInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    version: int = Field(ge=1)
    primary_person_id: UUID | None


def binding_snapshot(account, asset):
    return {
        "primary_person_id": str(account.primary_person_id) if account.primary_person_id else None,
        "asset_version": asset.version,
    }


@router.patch(
    "/workspace/platform-accounts/{asset_id}/child-accounts/{account_id}/employee",
    response_model=AccountRead,
    dependencies=[Depends(require_csrf)],
)
def bind_account_employee(
    asset_id: UUID,
    account_id: UUID,
    payload: AccountEmployeeBindingInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
):
    previous, fingerprint = audited_retry(db, access, "account.employee.bind", payload, account_id)
    parent = lock_asset(db, asset_id)
    if parent is None or parent.archived_at:
        raise HTTPException(404, "公司平台账号不存在")
    require_asset_visible(db, access, parent)
    if not can_manage_asset(db, access, parent):
        raise HTTPException(403, "无权维护该公司平台账号")
    tenant = db.scalar(
        select(PlatformTenant).where(
            PlatformTenant.asset_id == parent.id,
            PlatformTenant.archived_at.is_(None),
        )
    )
    account = db.scalar(
        select(Account)
        .where(
            Account.id == account_id,
            Account.archived_at.is_(None),
        )
        .with_for_update()
    )
    if not tenant or not account or account.platform_tenant_id != tenant.id:
        raise HTTPException(404, "账号明细不属于当前公司平台账号")
    asset = lock_asset(db, account.asset_id)
    if asset is None or asset.archived_at:
        raise HTTPException(404, "账号明细不存在")
    require_asset_visible(db, access, asset)
    if previous:
        if binding_snapshot(account, asset) != previous.after_data.get("snapshot"):
            raise HTTPException(409, "绑定后账号资料已改变，请重新读取")
        return account
    if asset.version != payload.version:
        raise HTTPException(409, "账号资料已改变，请重新读取")
    require_active_employee(db, payload.primary_person_id, tenant.legal_entity_id)
    before = binding_snapshot(account, asset)
    account.primary_person_id = payload.primary_person_id
    asset.version += 1
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="account.employee.bind",
            object_type="account",
            object_id=account.id,
            before_data=before,
            after_data={
                "snapshot": binding_snapshot(account, asset),
                "request_digest": fingerprint,
                "platform_tenant_id": str(tenant.id),
            },
            request_id=str(payload.request_id),
        )
    )
    db.commit()
    db.refresh(account)
    return account
