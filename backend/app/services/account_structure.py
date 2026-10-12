"""Read policies over the existing account ledger; no duplicate account store."""

from datetime import date

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.orm import Session

from app.models import (
    Account,
    Asset,
    AssetCategory,
    AssetResponsibility,
    AssetType,
    Person,
    PlatformTenant,
    RegistrationIdentityProfile,
    ResourceProfile,
)


def child_account_clause():
    # Use the canonical account association, never a client-provided source label.
    return exists(select(Account.id).where(Account.asset_id == Asset.id))


def account_parent(db: Session, asset_id):
    tenant = db.scalar(
        select(PlatformTenant)
        .join(Account, Account.platform_tenant_id == PlatformTenant.id)
        .where(Account.asset_id == asset_id, PlatformTenant.archived_at.is_(None))
    )
    parent = db.get(Asset, tenant.asset_id) if tenant else None
    if parent and not parent.archived_at and parent.status != "deleted":
        return parent, tenant
    return None, None


def account_asset_clause():
    classified = Asset.asset_type_id.in_(
        select(AssetType.id)
        .join(AssetCategory)
        .where(
            or_(
                and_(
                    AssetCategory.code == "platform_account",
                    AssetType.code != "registration_identity",
                ),
                AssetType.code.in_(["platform_tenant", "platform_account"]),
            )
        )
    )
    return or_(
        classified,
        *[
            exists(select(model.id).where(model.asset_id == Asset.id))
            for model in (Account, PlatformTenant)
        ],
    )


def communication_resource_clause():
    # Contact management has its own entry; category changes must not leak it back.
    return or_(
        Asset.asset_type_id.in_(select(AssetType.id).where(AssetType.code == "registration_identity")),
        exists(select(RegistrationIdentityProfile.id).where(
            RegistrationIdentityProfile.asset_id == Asset.id,
        )),
    )


def asset_library_exclusion_clause():
    personal_subscription = and_(
        Asset.source_system.is_not(None),
        Asset.source_system == "membership-registration",
        Asset.asset_type_id.in_(select(AssetType.id).where(AssetType.code == "saas_subscription")),
    )
    platform_reference = exists(
        select(ResourceProfile.id).where(
            ResourceProfile.asset_id == Asset.id,
            ResourceProfile.resource_family == "platform_catalog",
            ResourceProfile.archived_at.is_(None),
        )
    )
    return or_(
        account_asset_clause(), communication_resource_clause(), personal_subscription,
        platform_reference,
    )


def responsibility_map(db: Session):
    """Only an effective, confirmed, active person counts as a responsible owner."""
    today = date.today()
    result = {}
    rows = db.execute(
        select(AssetResponsibility, Person)
        .outerjoin(Person)
        .where(
            AssetResponsibility.archived_at.is_(None),
            AssetResponsibility.role_type == "responsible",
        )
    )
    for row, person in rows:
        effective = (row.starts_at is None or row.starts_at <= today) and (
            row.ends_at is None or row.ends_at >= today
        )
        active = bool(person and not person.archived_at and person.employment_status == "active")
        result[row.asset_id] = {
            "has_owner": effective and active,
            "responsible_person_id": str(person.id) if person else None,
            "responsible_person_name": person.display_name if person else None,
            "responsibility_issue": None
            if effective and active
            else (
                "负责人已离职"
                if person and person.employment_status == "departed"
                else "负责人非在职或资料不可用"
                if not active
                else "责任配置未生效或已到期"
            ),
        }
    return result


def owner_facts(owners, asset_id):
    return owners.get(
        asset_id,
        {
            "has_owner": False,
            "responsible_person_id": None,
            "responsible_person_name": None,
            "responsibility_issue": "尚未配置负责人",
        },
    )


def child_employee_issue(account, people):
    if account.account_kind == "service" and account.primary_person_id is None:
        return False
    person = people.get(account.primary_person_id)
    return not person or person.employment_status != "active"
