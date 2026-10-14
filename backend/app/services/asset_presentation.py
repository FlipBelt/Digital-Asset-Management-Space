"""Safe read projections over existing asset and account records."""

from sqlalchemy import select

from app.core.access import require_asset_visible
from app.models import (
    AssetFieldDefinition,
    AssetFieldValue,
    InternalSystemProfile,
    RegistrationIdentityProfile,
    ResourceProfile,
)
from app.schemas.assets import AssetCardLink, AssetRead
from app.services.account_structure import account_parent
from app.services.repository_visibility import GITHUB_URL, hide_repository_urls, visibility_map

PROFILE_LINKS = {
    "repository_url": "代码仓库",
    "production_url": "打开应用",
    "deployment_guide_url": "部署说明",
    "recovery_guide_url": "恢复说明",
}
INHERITED_FIELDS = (
    "legal_entity_id",
    "owner_department_id",
    "ownership_scope",
    "status",
    "criticality",
    "confidentiality",
    "sharing_scope",
    "started_at",
    "expires_at",
    "last_verified_at",
    "description",
    "source_type",
    "source_system",
    "source_agent",
    "source_reference",
    "development_method",
    "created_by_person_id",
    "confirmed_by_person_id",
    "confirmed_at",
)


def card_link_map(db, asset_ids):
    result = {identity: [] for identity in asset_ids}
    visibility = visibility_map(db, asset_ids)
    if not result:
        return result
    for profile in db.scalars(
        select(InternalSystemProfile).where(InternalSystemProfile.asset_id.in_(result))
    ):
        for key, label in PROFILE_LINKS.items():
            value = getattr(profile, key)
            if value:
                result[profile.asset_id].append(AssetCardLink(label=label, url=value))
    for profile in db.scalars(
        select(ResourceProfile).where(
            ResourceProfile.asset_id.in_(result), ResourceProfile.archived_at.is_(None)
        )
    ):
        if profile.management_url:
            result[profile.asset_id].append(
                AssetCardLink(label="管理入口", url=profile.management_url)
            )
    fields = db.execute(
        select(AssetFieldValue, AssetFieldDefinition)
        .join(AssetFieldDefinition)
        .where(
            AssetFieldValue.asset_id.in_(result),
            AssetFieldDefinition.archived_at.is_(None),
            AssetFieldDefinition.confidentiality.in_(("public", "internal")),
            AssetFieldDefinition.data_type == "url",
        )
        .order_by(AssetFieldDefinition.sort_order, AssetFieldDefinition.id)
    )
    for field, definition in fields:
        value = (field.value or {}).get("value")
        if isinstance(value, str) and value:
            result[field.asset_id].append(AssetCardLink(label=definition.label, url=value))
    for identity, links in result.items():
        if visibility[identity] != "public":
            result[identity] = [
                link
                for link in links
                if link.label != "代码仓库" and not GITHUB_URL.search(link.url)
            ]
    return result


def registration_name_map(db, asset_ids):
    if not asset_ids:
        return {}
    return dict(db.execute(select(
        RegistrationIdentityProfile.asset_id, RegistrationIdentityProfile.identifier_value,
    ).where(RegistrationIdentityProfile.asset_id.in_(asset_ids))).all())


def asset_list_reads(db, assets):
    rows = list(assets)
    names = registration_name_map(db, [asset.id for asset in rows])
    links = card_link_map(db, [asset.id for asset in rows])
    visibility = visibility_map(db, [asset.id for asset in rows])
    return [
        AssetRead.model_validate(asset).model_copy(
            update={
                "name": names.get(asset.id, asset.name),
                "card_links": links[asset.id],
                "repository_visibility": visibility[asset.id],
                "description": asset.description
                if visibility[asset.id] == "public"
                else hide_repository_urls(asset.description),
                "source_reference": asset.source_reference
                if visibility[asset.id] == "public"
                else hide_repository_urls(asset.source_reference),
            }
        )
        for asset in rows
    ]


def asset_detail_read(db, asset, access):
    item = AssetRead.model_validate(asset)
    item.name = registration_name_map(db, [asset.id]).get(asset.id, item.name)
    origin = asset
    if item.is_child_account:
        parent, tenant = account_parent(db, asset.id)
        if parent is None:
            from fastapi import HTTPException

            raise HTTPException(409, "所属公司账号不可用，请在平台与账号中维护关联")
        require_asset_visible(db, access, parent)
        origin = parent
        for key in INHERITED_FIELDS:
            setattr(item, key, getattr(parent, key))
        item.parent_asset_id = parent.id
        item.management_href = f"/accounts?platform={tenant.platform_id}&tenant={parent.id}"
        item.verification_status = tenant.verification_status
    item.card_links = card_link_map(db, [origin.id])[origin.id]
    item.repository_visibility = visibility_map(db, [origin.id])[origin.id]
    if item.repository_visibility != "public":
        item.description = hide_repository_urls(item.description)
        item.source_reference = hide_repository_urls(item.source_reference)
    return item


def governance_origin(db, asset, access):
    if not asset.is_child_account:
        return asset
    parent, _ = account_parent(db, asset.id)
    if parent is None:
        from fastapi import HTTPException

        raise HTTPException(409, "所属公司账号不可用，请在平台与账号中维护关联")
    require_asset_visible(db, access, parent)
    return parent
