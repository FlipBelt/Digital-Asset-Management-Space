"""Group actionable records using canonical account and service associations."""

from sqlalchemy import select

from app.models import (
    AssetPlatformLink,
    AssetResponsibility,
    Platform,
    PlatformTenant,
    ResourceProfile,
    ServiceInstance,
    ServiceProduct,
)


def followup_contexts(db, assets, types, people):
    visible = {row.id: row for row in assets}
    platforms = {row.id: row for row in db.scalars(select(Platform).where(
        Platform.archived_at.is_(None),
    ))}
    tenants = {row.asset_id: row for row in db.scalars(select(PlatformTenant).where(
        PlatformTenant.archived_at.is_(None), PlatformTenant.asset_id.in_(visible),
    ))}
    tenants_by_id = {row.id: row for row in tenants.values()}
    profiles = {row.asset_id: row for row in db.scalars(select(ResourceProfile).where(
        ResourceProfile.archived_at.is_(None), ResourceProfile.asset_id.in_(visible),
    ))}
    instances = {row.asset_id: row for row in db.scalars(select(ServiceInstance).where(
        ServiceInstance.archived_at.is_(None), ServiceInstance.asset_id.in_(visible),
    ))}
    products = {row.id: row for row in db.scalars(select(ServiceProduct))}
    links = {}
    for row in db.scalars(select(AssetPlatformLink).where(
        AssetPlatformLink.archived_at.is_(None), AssetPlatformLink.asset_id.in_(visible),
    ).order_by(AssetPlatformLink.created_at, AssetPlatformLink.id)):
        if row.relation_type in {"provided_by", "uses", "registered_on"}:
            links.setdefault(row.asset_id, row.platform_id)
    proposals = {}
    for row in db.scalars(select(AssetResponsibility).where(
        AssetResponsibility.archived_at.is_(None),
        AssetResponsibility.asset_id.in_(visible),
        AssetResponsibility.role_type == "proposed_responsible",
    ).order_by(AssetResponsibility.created_at.desc())):
        person = people.get(row.person_id)
        if person and person.employment_status == "active":
            proposals.setdefault(row.asset_id, person.display_name)

    result = {}
    excluded = set()
    for asset_id, asset in visible.items():
        profile = profiles.get(asset_id)
        instance = instances.get(asset_id)
        if (profile and profile.resource_family == "platform_catalog") or (
            instance and instance.funding_source == "personal"
        ):
            excluded.add(asset_id)
            continue
        tenant = tenants.get(asset_id)
        product = products.get(instance.service_product_id) if instance else None
        parent = tenants.get(instance.purchase_tenant_asset_id) if instance else None
        if parent is None and profile:
            parent = tenants_by_id.get(profile.managed_under_account_id)
        platform_id = (tenant or parent).platform_id if tenant or parent else (
            product.platform_id if product and product.platform_id else
            instance.purchase_platform_id if instance and instance.purchase_platform_id else
            links.get(asset_id)
        )
        platform = platforms.get(platform_id)
        asset_type = types.get(asset.asset_type_id)
        subscription = bool((asset_type and asset_type.code == "saas_subscription")
                            or (instance and product and product.billing_mode == "subscription"))
        kind = "account" if tenant else "subscription" if subscription else "asset"
        account = visible.get((tenant or parent).asset_id) if tenant or parent else None
        account_group = bool(tenant or subscription)
        group_key = f"account:{account.id}" if account_group and account else (
            f"platform:{platform.id}" if account_group and platform else
            "subscription:unlinked" if account_group else "business-assets"
        )
        title = account.name if account_group and account else (
            platform.name if account_group and platform else
            "尚未关联平台或公司账号的订阅" if account_group else "业务资产"
        )
        result[asset_id] = {
            "followup_kind": kind,
            "group_key": group_key,
            "group_label": title,
            "group_section": "accounts" if account_group else "assets",
            "platform_name": platform.name if platform else None,
            "parent_account_name": account.name if account else None,
            "group_href": f"/accounts?platform={platform.id}&tenant={account.id}"
            if account_group and account and platform else
            f"/accounts?platform={platform.id}" if account_group and platform else None,
            "plan_name": instance.subscription_name if instance else None,
            "service_expires_at": instance.expires_at.isoformat()
            if instance and instance.expires_at else None,
            "proposed_responsible_name": proposals.get(asset_id),
        }
    return result, excluded
