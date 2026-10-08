"""Bind confirmation to the exact draft and its related facts."""

import hashlib
import json
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AssetAttachment,
    AssetFieldDefinition,
    AssetFieldValue,
    AssetIdentifier,
    AssetRelation,
    AssetResponsibility,
    InternalSystemProfile,
    Person,
    ServiceInstance,
)


def draft_snapshot(db: Session, asset: Asset, sharing_scope: str) -> dict:
    facts = {
        "asset": {
            name: getattr(asset, name)
            for name in (
                "id",
                "name",
                "description",
                "asset_type_id",
                "legal_entity_id",
                "owner_department_id",
                "ownership_scope",
                "criticality",
                "confidentiality",
                "created_by_person_id",
                "source_type",
                "source_system",
                "source_agent",
                "source_reference",
                "development_method",
                "started_at",
                "expires_at",
                "version",
            )
        },
        "sharing_scope": sharing_scope,
        "attachments": [
            {
                "id": str(row.id),
                "file_name": row.file_name,
                "file_path": row.file_path,
                "size_bytes": row.size_bytes,
            }
            for row in db.scalars(
                select(AssetAttachment)
                .where(AssetAttachment.asset_id == asset.id, AssetAttachment.archived_at.is_(None))
                .order_by(AssetAttachment.id)
            )
        ],
        "relations": [
            (str(row.id), str(row.source_asset_id), str(row.target_asset_id), row.relation_type)
            for row in db.scalars(
                select(AssetRelation)
                .where(
                    or_(
                        AssetRelation.source_asset_id == asset.id,
                        AssetRelation.target_asset_id == asset.id,
                    ),
                    AssetRelation.archived_at.is_(None),
                )
                .order_by(AssetRelation.id)
            )
        ],
        "responsibilities": [
            (
                str(row.id),
                str(row.person_id),
                str(row.department_id),
                row.role_type,
                str(row.starts_at),
                str(row.ends_at),
                db.get(Person, row.person_id).display_name if row.person_id else "",
            )
            for row in db.scalars(
                select(AssetResponsibility)
                .where(
                    AssetResponsibility.asset_id == asset.id,
                    AssetResponsibility.archived_at.is_(None),
                )
                .order_by(AssetResponsibility.id)
            )
        ],
        "subscriptions": [
            {
                name: getattr(row, name)
                for name in (
                    "id",
                    "service_product_id",
                    "subscription_name",
                    "funding_source",
                    "payer_person_id",
                    "usage_frequency",
                    "primary_purpose",
                    "starts_at",
                    "expires_at",
                    "currency",
                )
            }
            for row in db.scalars(
                select(ServiceInstance)
                .where(ServiceInstance.asset_id == asset.id, ServiceInstance.archived_at.is_(None))
                .order_by(ServiceInstance.id)
            )
        ],
        "profile": next(
            (
                {
                    key: getattr(row, key)
                    for key in (
                        "repository_url",
                        "production_url",
                        "tech_stack",
                        "deployment_guide_url",
                        "recovery_guide_url",
                        "backup_description",
                    )
                }
                for row in db.scalars(
                    select(InternalSystemProfile).where(InternalSystemProfile.asset_id == asset.id)
                )
            ),
            None,
        ),
        "identifiers": [
            {
                "namespace": row.namespace,
                "identifier_type": row.identifier_type,
                "identifier_value": row.identifier_value,
            }
            for row in db.scalars(
                select(AssetIdentifier)
                .where(AssetIdentifier.asset_id == asset.id, AssetIdentifier.archived_at.is_(None))
                .order_by(AssetIdentifier.id)
            )
        ],
        "fields": [
            (
                str(row.field_definition_id),
                row.value,
                db.get(AssetFieldDefinition, row.field_definition_id).label,
            )
            for row in db.scalars(
                select(AssetFieldValue)
                .where(AssetFieldValue.asset_id == asset.id)
                .order_by(AssetFieldValue.id)
            )
        ],
    }
    return json.loads(json.dumps(facts, default=str, ensure_ascii=False))


def snapshot_digest(snapshot: dict) -> str:
    encoded = json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def draft_digest(db: Session, asset: Asset, sharing_scope: str) -> str:
    return snapshot_digest(draft_snapshot(db, asset, sharing_scope))


def confirmation_preview(snapshot: dict) -> dict:
    # Storage paths stay on the server; the immutable attachment ID binds content.
    return {
        **snapshot,
        "attachments": [
            {key: value for key, value in item.items() if key != "file_path"}
            for item in snapshot["attachments"]
        ],
    }


def lock_asset(db: Session, asset_id: UUID) -> Asset | None:
    return db.scalar(
        select(Asset)
        .where(Asset.id == asset_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
