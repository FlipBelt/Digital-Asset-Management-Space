"""Explicit, evidence-based departures and preserved handover records."""

from datetime import UTC, date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, active_period, require_global_manager
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import (
    AccessGrant,
    Account,
    Asset,
    AssetResponsibility,
    AuditLog,
    Person,
    PlatformTenant,
    RegistrationIdentityProfile,
    User,
    UserSession,
)
from app.schemas.organizations import PersonRead
from app.services.audited_requests import audited_retry

router = APIRouter(tags=["employee-lifecycle"])


class EmployeeLifecycleInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_id: UUID
    expected_updated_at: datetime
    employment_status: Literal["departed", "active"]
    departed_on: date | None = None
    evidence_note: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def validate_date(self):
        if self.expected_updated_at.tzinfo is None:
            raise ValueError("员工版本时间必须带时区")
        if self.employment_status == "departed" and (
            self.departed_on is None or self.departed_on > date.today()
        ):
            raise ValueError("请填写已发生的实际离职日期")
        if self.employment_status == "active" and self.departed_on is not None:
            raise ValueError("纠正为在职时不填写离职日期")
        return self


def lifecycle_snapshot(person):
    return {
        "employment_status": person.employment_status,
        "updated_at": person.updated_at.astimezone(UTC).isoformat(),
    }


def handover_rows(db: Session, person_ids):
    result = {
        key: {"accounts": [], "responsibilities": [], "grants": [], "local_login_enabled": False}
        for key in person_ids
    }
    tenants = {
        row.id: row
        for row in db.scalars(select(PlatformTenant).where(PlatformTenant.archived_at.is_(None)))
    }
    assets = {
        row.id: row
        for row in db.scalars(
            select(Asset).where(
                Asset.archived_at.is_(None),
                Asset.status != "deleted",
            )
        )
    }

    def reference(asset, tenant=None):
        return {
            "asset_id": str(asset.id),
            "name": asset.name,
            "href": f"/accounts?platform={tenant.platform_id}&tenant={tenant.asset_id}"
            if tenant
            else f"/assets/{asset.id}",
        }

    tenant_by_asset = {row.asset_id: row for row in tenants.values()}
    for identity in db.scalars(
        select(RegistrationIdentityProfile).where(
            RegistrationIdentityProfile.archived_at.is_(None),
            RegistrationIdentityProfile.custodian_person_id.in_(person_ids),
        )
    ):
        asset = assets.get(identity.asset_id)
        if asset:
            result[identity.custodian_person_id]["accounts"].append(reference(asset))
    accounts = {
        row.id: row for row in db.scalars(select(Account).where(Account.archived_at.is_(None)))
    }
    for account in accounts.values():
        tenant = tenants.get(account.platform_tenant_id)
        child = assets.get(account.asset_id)
        parent = assets.get(tenant.asset_id) if tenant else None
        if not child or not parent:
            continue
        for key in {account.primary_person_id, account.registration_person_id} & person_ids:
            result[key]["accounts"].append(
                {
                    **reference(parent, tenant),
                    "account_id": str(account.id),
                    "login_identifier": account.login_identifier,
                }
            )
    for row in db.scalars(
        select(AssetResponsibility).where(
            AssetResponsibility.person_id.in_(person_ids),
            AssetResponsibility.archived_at.is_(None),
            AssetResponsibility.role_type == "responsible",
            active_period(AssetResponsibility),
        )
    ):
        asset = assets.get(row.asset_id)
        if asset:
            result[row.person_id]["responsibilities"].append(
                reference(asset, tenant_by_asset.get(asset.id))
            )
    for grant in db.scalars(
        select(AccessGrant).where(
            AccessGrant.person_id.in_(person_ids),
            AccessGrant.archived_at.is_(None),
            AccessGrant.status == "active",
            active_period(AccessGrant),
        )
    ):
        account = accounts.get(grant.account_id)
        tenant = tenants.get(account.platform_tenant_id) if account else None
        asset = assets.get(tenant.asset_id if tenant else grant.asset_id)
        if asset:
            result[grant.person_id]["grants"].append(
                {
                    **reference(asset, tenant),
                    "grant_id": str(grant.id),
                    "grant_role": grant.grant_role,
                }
            )
    for user in db.scalars(
        select(User).where(User.person_id.in_(person_ids), User.archived_at.is_(None))
    ):
        result[user.person_id]["local_login_enabled"] = user.is_active
    return result


@router.get("/employee-lifecycle")
def list_employee_lifecycle(
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_global_manager),
):
    people = list(
        db.scalars(
            select(Person)
            .where(
                Person.archived_at.is_(None),
                Person.person_type == "employee",
            )
            .order_by(Person.display_name)
        )
    )
    ids = {row.id for row in people}
    impacts = handover_rows(db, ids)
    events = {}
    for log in db.scalars(
        select(AuditLog)
        .where(
            AuditLog.action == "employee.lifecycle",
            AuditLog.object_id.in_(ids),
        )
        .order_by(AuditLog.created_at.desc())
    ):
        events.setdefault(
            log.object_id,
            {
                "evidence_note": log.after_data.get("evidence_note"),
                "departed_on": log.after_data.get("departed_on"),
                "recorded_at": log.created_at.isoformat(),
            },
        )
    return {
        "items": [
            {
                **PersonRead.model_validate(row).model_dump(mode="json"),
                "last_event": events.get(row.id),
                "handover": impacts[row.id],
            }
            for row in people
        ]
    }


@router.post("/people/{person_id}/lifecycle", dependencies=[Depends(require_csrf)])
def change_employee_lifecycle(
    person_id: UUID,
    payload: EmployeeLifecycleInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_global_manager),
):
    previous, fingerprint = audited_retry(db, access, "employee.lifecycle", payload, person_id)
    person = db.scalar(
        select(Person)
        .where(
            Person.id == person_id,
            Person.archived_at.is_(None),
            Person.person_type == "employee",
        )
        .with_for_update()
    )
    if not person:
        raise HTTPException(404, "员工不存在")
    if previous:
        if lifecycle_snapshot(person) != previous.after_data.get("snapshot"):
            raise HTTPException(409, "员工资料已再次改变，请重新读取")
        return PersonRead.model_validate(person)
    if person.updated_at != payload.expected_updated_at:
        raise HTTPException(409, "员工资料已改变，请重新读取后操作")
    if payload.employment_status == "departed" and person.id == access.person_id:
        raise HTTPException(409, "不能登记本人离职，请由另一位管理员操作")
    before = lifecycle_snapshot(person)
    now = datetime.now(UTC)
    person.employment_status = payload.employment_status
    person.updated_at = now
    disabled = 0
    if payload.employment_status == "departed":
        for user in db.scalars(
            select(User)
            .where(
                User.person_id == person.id,
                User.archived_at.is_(None),
            )
            .with_for_update()
        ):
            disabled += int(user.is_active)
            user.is_active = False
            for session in db.scalars(
                select(UserSession).where(
                    UserSession.user_id == user.id,
                    UserSession.revoked_at.is_(None),
                )
            ):
                session.revoked_at = now
    # External accounts, grants and responsibilities remain recorded until explicitly handed over.
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="employee.lifecycle",
            object_type="person",
            object_id=person.id,
            before_data=before,
            after_data={
                "snapshot": lifecycle_snapshot(person),
                "request_digest": fingerprint,
                "evidence_note": payload.evidence_note,
                "departed_on": payload.departed_on.isoformat() if payload.departed_on else None,
                "disabled_local_logins": disabled,
            },
            request_id=str(payload.request_id),
        )
    )
    db.commit()
    db.refresh(person)
    return PersonRead.model_validate(person)
