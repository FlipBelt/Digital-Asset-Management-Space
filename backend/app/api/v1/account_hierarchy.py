"""Platform-first account navigation, projected from visible canonical records."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, asset_visibility_clause, get_access_context
from app.db.session import get_db
from app.models import (
    Account,
    Asset,
    AssetPlatformLink,
    LegalEntity,
    Person,
    Platform,
    PlatformAccountRegistrationIdentity,
    PlatformTenant,
    RegistrationIdentityProfile,
    ServiceInstance,
    ServiceProduct,
)
from app.schemas.inventory import AccountRead, PlatformTenantRead
from app.services.account_structure import owner_facts, responsibility_map

router = APIRouter(tags=["account-hierarchy"])


@router.get("/account-hierarchy")
def account_hierarchy(
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    visible = {
        row.id: row
        for row in db.scalars(
            select(Asset).where(
                Asset.archived_at.is_(None),
                Asset.status != "deleted",
                asset_visibility_clause(access),
            )
        )
    }
    people = {row.id: row for row in db.scalars(select(Person).where(Person.archived_at.is_(None)))}
    companies = {row.id: row.name for row in db.scalars(select(LegalEntity))}
    owners = responsibility_map(db)
    platforms = {
        row.id: {
            "id": str(row.id),
            "name": row.name,
            "category": row.category,
            "website": row.website,
            "review_status": row.review_status,
            "company_accounts": [],
            "personal_accounts": [],
            "pending_identities": [],
            "registration_identities": [],
        }
        for row in db.scalars(
            select(Platform).where(Platform.archived_at.is_(None)).order_by(Platform.name)
        )
    }
    tenant_platforms = {}
    tenant_rows = list(
        db.scalars(select(PlatformTenant).where(PlatformTenant.archived_at.is_(None)))
    )
    child_rows = list(db.scalars(select(Account).where(Account.archived_at.is_(None))))
    for tenant in tenant_rows:
        asset = visible.get(tenant.asset_id)
        if not asset or tenant.platform_id not in platforms:
            continue
        children = []
        for child in child_rows:
            if child.platform_tenant_id != tenant.id or child.asset_id not in visible:
                continue
            person = people.get(child.primary_person_id)
            children.append(
                {
                    **AccountRead.model_validate(child).model_dump(mode="json"),
                    "version": visible[child.asset_id].version,
                    "person_name": person.display_name if person else None,
                    "employment_status": person.employment_status if person else None,
                }
            )
        row = {
            **PlatformTenantRead.model_validate(tenant).model_dump(mode="json"),
            "name": asset.name,
            "asset_code": asset.asset_code,
            "version": asset.version,
            "company_name": companies.get(tenant.legal_entity_id),
            "children": children,
            **owner_facts(owners, asset.id),
        }
        key = (
            "personal_accounts"
            if tenant.ownership_nature in {"personal_owned", "personal_for_company"}
            else "company_accounts"
        )
        platforms[tenant.platform_id][key].append(row)
        tenant_platforms[tenant.id] = tenant.platform_id
    for instance, product in db.execute(
        select(ServiceInstance, ServiceProduct)
        .join(ServiceProduct, ServiceProduct.id == ServiceInstance.service_product_id)
        .where(ServiceInstance.archived_at.is_(None), ServiceProduct.archived_at.is_(None))
    ):
        asset = visible.get(instance.asset_id)
        if asset and asset.is_personal_subscription and product.platform_id in platforms:
            creator = people.get(asset.created_by_person_id)
            platforms[product.platform_id]["personal_accounts"].append(
                {
                    "asset_id": str(asset.id),
                    "name": asset.name,
                    "asset_code": asset.asset_code,
                    "is_subscription": True,
                    "plan_name": instance.subscription_name,
                    "person_name": creator.display_name if creator else None,
                    "verification_status": "not_required",
                    "children": [],
                }
            )
    identity_platforms = {}
    for link in db.scalars(
        select(AssetPlatformLink).where(AssetPlatformLink.archived_at.is_(None))
    ):
        identity_platforms.setdefault(link.asset_id, set()).add(link.platform_id)
    for link in db.scalars(
        select(PlatformAccountRegistrationIdentity).where(
            PlatformAccountRegistrationIdentity.status == "active"
        )
    ):
        platform_id = tenant_platforms.get(link.platform_tenant_id)
        if platform_id:
            identity_platforms.setdefault(link.registration_identity_asset_id, set()).add(
                platform_id
            )
    unlinked = []
    for profile in db.scalars(
        select(RegistrationIdentityProfile).where(
            RegistrationIdentityProfile.archived_at.is_(None),
        )
    ):
        asset = visible.get(profile.asset_id)
        if not asset:
            continue
        row = {
            "asset_id": str(asset.id),
            "name": profile.identifier_masked or "注册身份",
            "asset_code": asset.asset_code,
            "verification_status": profile.verification_status,
        }
        matched = [key for key in identity_platforms.get(asset.id, set()) if key in platforms]
        if not matched:
            unlinked.append(row)
        for key in matched:
            platforms[key]["registration_identities"].append(row)
            if profile.verification_status != "verified":
                platforms[key]["pending_identities"].append(row)
    return {"platforms": list(platforms.values()), "unlinked_identities": unlinked}
