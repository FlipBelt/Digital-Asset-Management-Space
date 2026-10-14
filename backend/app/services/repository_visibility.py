"""Repository disclosure is an explicit, versioned owner decision."""

import re

from sqlalchemy import select

from app.models import AssetIdentifier

GITHUB_URL = re.compile(r"https?://(?:www\.)?github\.com(?:/[^\s<>\[\]\"'`，。；！？、]*)?", re.I)


def visibility_map(db, asset_ids):
    result = dict.fromkeys(asset_ids, "unknown")
    if result:
        for row in db.scalars(
            select(AssetIdentifier).where(
                AssetIdentifier.asset_id.in_(result),
                AssetIdentifier.identifier_type == "repository_visibility",
                AssetIdentifier.archived_at.is_(None),
            )
        ):
            if row.identifier_value in {"public", "private"}:
                result[row.asset_id] = row.identifier_value
    return result


def repository_visibility(db, asset_id):
    return visibility_map(db, [asset_id])[asset_id]


def hide_repository_urls(value):
    if isinstance(value, str):
        return GITHUB_URL.sub("[仓库地址未公开]", value)
    if isinstance(value, list):
        return [hide_repository_urls(item) for item in value]
    if isinstance(value, dict):
        return {key: hide_repository_urls(item) for key, item in value.items()}
    return value


def project_profile(db, profile):
    if profile is None:
        return None
    from app.schemas.inventory import InternalSystemProfileRead

    state = repository_visibility(db, profile.asset_id)
    data = InternalSystemProfileRead.model_validate(profile).model_dump()
    data["repository_visibility"] = state
    if state != "public":
        data["repository_url"] = None
        for key in ("deployment_guide_url", "recovery_guide_url", "production_url"):
            if data[key] and GITHUB_URL.search(data[key]):
                data[key] = None
        data = hide_repository_urls(data)
    return data


def set_visibility(db, asset_id, value):
    row = db.scalar(
        select(AssetIdentifier).where(
            AssetIdentifier.asset_id == asset_id,
            AssetIdentifier.identifier_type == "repository_visibility",
            AssetIdentifier.archived_at.is_(None),
        )
    )
    if row is None:
        row = AssetIdentifier(
            asset_id=asset_id,
            namespace=str(asset_id),
            identifier_type="repository_visibility",
            identifier_value=value,
        )
        db.add(row)
    else:
        row.identifier_value = value
