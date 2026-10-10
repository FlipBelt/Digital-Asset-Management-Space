"""Evidence-based verification of instantiated company accounts, separate from catalog review."""

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.access import AccessContext, require_global_manager
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import Asset, AuditLog, LegalEntity, Platform, PlatformTenant
from app.schemas.inventory import PlatformTenantRead
from app.services.asset_confirmation import lock_asset
from app.services.service_catalog import digest

router = APIRouter(tags=["account-verification"])


class AccountVerificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    version: int = Field(ge=1)
    decision: Literal["verified", "pending"]
    tenant_identifier: str | None = Field(default=None, min_length=1, max_length=200)
    identifier_unavailable: bool = False
    ownership_nature: Literal["company_owned", "company_managed", "personal_owned", "pending"]
    platform_confirmed: bool = False
    company_confirmed: bool = False
    identifier_confirmed: bool = False
    evidence_note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_verified_facts(self):
        if self.decision == "verified":
            if not (
                self.platform_confirmed and self.company_confirmed and self.identifier_confirmed
            ):
                raise ValueError("请逐项核对实际平台、公司归属和账号标识")
            if not self.tenant_identifier and not self.identifier_unavailable:
                raise ValueError("请填写平台账号编号；平台确实不提供时请注明原因")
            if self.identifier_unavailable and self.tenant_identifier:
                raise ValueError("已填写账号编号，不能同时选择平台不提供编号")
            if self.ownership_nature == "pending":
                raise ValueError("请确认账号归属性质")
        return self


def snapshot(tenant: PlatformTenant, asset: Asset):
    return {
        "tenant_identifier": tenant.tenant_identifier,
        "ownership_nature": tenant.ownership_nature,
        "verification_status": tenant.verification_status,
        "asset_status": asset.status,
        "evidence_note": tenant.evidence_note,
        "asset_version": asset.version,
        "last_verified_at": (
            asset.last_verified_at.astimezone(UTC).isoformat() if asset.last_verified_at else None
        ),
    }


@router.post(
    "/platform-tenants/{tenant_id}/verification",
    response_model=PlatformTenantRead,
    dependencies=[Depends(require_csrf)],
)
def verify_account(
    tenant_id: UUID,
    payload: AccountVerificationInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_global_manager),
):
    action = "platform_tenant.verify"
    fingerprint = digest({**payload.model_dump(mode="json"), "target": str(tenant_id)})
    # Serialize retries from this actor before locking the underlying asset.
    if db.bind.dialect.name == "postgresql":
        key = int(
            digest({"actor": str(access.user.id), "request": str(payload.request_id)})[:15], 16
        )
        db.execute(select(func.pg_advisory_xact_lock(key)))
    previous = db.scalar(
        select(AuditLog).where(
            AuditLog.actor_user_id == access.user.id,
            AuditLog.action == action,
            AuditLog.request_id == str(payload.request_id),
        )
    )
    if previous and (previous.after_data or {}).get("request_digest") != fingerprint:
        raise HTTPException(409, "请求编号对应的核验内容已改变")
    tenant = db.scalar(
        select(PlatformTenant).where(
            PlatformTenant.id == tenant_id, PlatformTenant.archived_at.is_(None)
        )
    )
    if tenant is None:
        raise HTTPException(404, "公司平台账号不存在")
    asset = lock_asset(db, tenant.asset_id)
    if asset is None or asset.archived_at is not None:
        raise HTTPException(404, "公司平台账号不存在")
    db.refresh(tenant, with_for_update=True)
    if tenant.archived_at is not None:
        raise HTTPException(404, "公司平台账号不存在")
    if previous:
        if snapshot(tenant, asset) != (previous.after_data or {}).get("snapshot"):
            raise HTTPException(409, "核验后账号资料已改变，请重新读取")
        return tenant
    if asset.version != payload.version:
        raise HTTPException(409, "账号资料已改变，请重新读取后核验")
    entity = db.get(LegalEntity, tenant.legal_entity_id)
    platform = db.get(Platform, tenant.platform_id)
    if not entity or entity.archived_at or asset.legal_entity_id != tenant.legal_entity_id:
        raise HTTPException(422, "账号的公司主体无效或与资产归属不一致，请先维护资产资料")
    if not platform or platform.archived_at:
        raise HTTPException(422, "所属平台不可用，请先维护平台目录")
    before = snapshot(tenant, asset)
    tenant.tenant_identifier = payload.tenant_identifier
    if payload.tenant_identifier and not tenant.external_identifier_type:
        tenant.external_identifier_type = "platform_uid"
    tenant.ownership_nature = payload.ownership_nature
    tenant.verification_status = payload.decision
    tenant.evidence_note = payload.evidence_note
    asset.last_verified_at = datetime.now(UTC) if payload.decision == "verified" else None
    if payload.decision == "verified" and asset.status == "draft":
        asset.status = "active"
    asset.version += 1
    try:
        db.flush()
        db.add(
            AuditLog(
                actor_user_id=access.user.id,
                action=action,
                object_type="platform_tenant",
                object_id=tenant.id,
                request_id=str(payload.request_id),
                before_data=before,
                after_data={
                    "request_digest": fingerprint,
                    "snapshot": snapshot(tenant, asset),
                    "checks": {
                        "platform": payload.platform_confirmed,
                        "company": payload.company_confirmed,
                        "identifier": payload.identifier_confirmed,
                        "identifier_unavailable": payload.identifier_unavailable,
                    },
                },
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "平台账号编号已被同一公司的其他账号使用") from exc
    db.refresh(tenant)
    return tenant
