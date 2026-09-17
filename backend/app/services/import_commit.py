"""Audited promotion of reviewed import proposals into instantiated assets."""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AssetPlatformLink,
    AuditLog,
    ImportBatch,
    ImportProposedObject,
    ImportProposedRelation,
    InternalSystemProfile,
    Platform,
    RegistrationIdentityProfile,
    ResourceProfile,
    SourceImportRecord,
)
from app.services.assets import allocate_asset_code, ensure_internal_identifier
from app.services.import_planning import classify_l6_asset_type


def _identity_type(value: str) -> str:
    if re.fullmatch(r"1\d{10}", value.strip()):
        return "phone"
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value.strip()):
        return "email"
    if value.strip().lower().startswith(("wx:", "wechat:")):
        return "wechat"
    return "other"


def _asset(db: Session, *, name: str, type_code: str, source_record_id: UUID | None, actor: UUID) -> Asset:
    from app.models import AssetType

    asset_type = db.scalar(select(AssetType).where(AssetType.code == type_code))
    if asset_type is None:
        raise ValueError(f"缺少资产类型：{type_code}")
    item = Asset(
        asset_code=allocate_asset_code(db, None, asset_type.id),
        name=name[:200],
        asset_type_id=asset_type.id,
        legal_entity_id=None,
        ownership_scope="pending",
        status="active",
        review_status="approved",
        source_type="import",
        created_by_person_id=None,
        confirmed_at=datetime.now(UTC),
        description="按实例化原则由已审核资料候选升级；公司主体、L4/L5关系待后续人工连接。",
    )
    db.add(item)
    db.flush()
    ensure_internal_identifier(db, item)
    db.add(AuditLog(
        actor_user_id=actor,
        action="import.instance.promote",
        object_type="asset",
        object_id=item.id,
        before_data=None,
        after_data={"source_import_record_id": str(source_record_id) if source_record_id else None,
                    "name": item.name, "asset_type": type_code, "confirmed_at": item.confirmed_at.isoformat()},
        request_id="import-instance-commit",
    ))
    return item


def commit_reviewed_import_batch(db: Session, *, batch_id: UUID, actor_user_id: UUID, reason: str) -> dict[str, Any]:
    batch = db.get(ImportBatch, batch_id)
    if batch is None:
        raise ValueError("导入批次不存在")
    if batch.status == "committed":
        return {"batch_id": str(batch.id), "status": batch.status, "created": 0, "reused": 0, "skipped": 0}
    proposals = list(db.scalars(select(ImportProposedObject).where(
        ImportProposedObject.import_batch_id == batch.id,
        ImportProposedObject.review_status == "approved",
    )))
    if not proposals:
        raise ValueError("没有已批准的候选对象")
    records = {r.id: r for r in db.scalars(select(SourceImportRecord).where(SourceImportRecord.import_batch_id == batch.id))}
    created = reused = skipped = 0
    proposal_assets: dict[UUID, Asset] = {}
    identity_assets: dict[str, Asset] = {}
    platforms: dict[str, Platform] = {}
    record_priority: dict[UUID, int] = {}
    for proposal in proposals:
        record = records.get(proposal.source_import_record_id)
        payload = proposal.normalized_payload or {}
        # The curated Aliyun directory contains source evidence and broad
        # service summaries, not confirmed L6 instances. Keep those records in
        # the review/source pool so a future import cannot silently promote
        # them into the asset ledger.
        if (
            record
            and record.source_kind == "aliyun_directory_curated"
            and proposal.object_type in {"service_instance", "resource", "internal_system"}
        ):
            proposal.review_status = "pending_review"
            record.mapping_status = "pending_review"
            record.canonical_asset_id = None
            record.review_note = "阿里云目录仅保留来源证据；没有明确实例事实，不自动建立 L6。"
            skipped += 1
            continue
        if proposal.object_type == "platform":
            name = proposal.suggested_name.strip()
            platform = db.scalar(select(Platform).where(Platform.name == name, Platform.archived_at.is_(None)))
            if platform is None:
                code = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:70] or hashlib.sha1(name.encode()).hexdigest()[:12]
                platform = db.scalar(select(Platform).where(Platform.code == code, Platform.archived_at.is_(None)))
                if platform is None:
                    platform = Platform(code=code, name=name, category="other", review_status="approved", description="由已审核资料候选建立的平台目录项")
                    db.add(platform)
                    db.flush()
                    created += 1
                else:
                    reused += 1
            else:
                reused += 1
            proposal.matched_platform_id = platform.id
            platforms[name.casefold()] = platform
            if record:
                record.mapping_status = "committed_catalog"
                record.review_note = reason
            continue
        if proposal.object_type in {"platform_account", "access_grant", "department_reference"}:
            skipped += 1
            continue
        type_code = {
            "registration_identity": "registration_identity",
            "service_instance": "saas_subscription",
            "resource": "cloud_server",
            "internal_system": "internal_system",
        }.get(proposal.object_type)
        if proposal.object_type in {"service_instance", "resource"}:
            type_code = classify_l6_asset_type(
                object_type=proposal.object_type,
                name=proposal.suggested_name,
                payload=payload,
            )
        if type_code is None:
            skipped += 1
            continue
        existing: Asset | None = None
        identity_value = str(payload.get("identifier") or proposal.suggested_name).strip()
        identity_fp = hashlib.sha256(identity_value.lower().encode()).hexdigest()
        if proposal.object_type == "registration_identity":
            existing = identity_assets.get(identity_fp)
            if existing is None:
                prior = db.scalar(select(RegistrationIdentityProfile).where(RegistrationIdentityProfile.identifier_fingerprint == identity_fp))
                if prior is not None:
                    existing = db.get(Asset, prior.asset_id)
                    if existing is not None and existing.archived_at is not None and existing.source_type == "import":
                        existing.archived_at = None
                        existing.status = "active"
                        existing.review_status = "approved"
                        prior.archived_at = None
        if proposal.matched_asset_id:
            existing = db.get(Asset, proposal.matched_asset_id)
        if existing is not None:
            asset = existing
            reused += 1
        else:
            asset = _asset(db, name=proposal.suggested_name, type_code=type_code,
                           source_record_id=proposal.source_import_record_id, actor=actor_user_id)
            created += 1
        proposal_assets[proposal.id] = asset
        proposal.matched_asset_id = asset.id
        if proposal.object_type == "registration_identity":
            identity_assets[identity_fp] = asset
        if record:
            record.mapping_status = "committed"
            record.review_note = reason
            priority = 3 if proposal.object_type in {"service_instance", "resource", "internal_system"} else 1
            if record_priority.get(record.id, 0) <= priority:
                record.canonical_asset_id = asset.id
                record_priority[record.id] = priority
        if proposal.object_type == "registration_identity":
            value = identity_value
            profile = db.scalar(select(RegistrationIdentityProfile).where(RegistrationIdentityProfile.identifier_fingerprint == identity_fp))
            if profile is None:
                db.add(RegistrationIdentityProfile(asset_id=asset.id, identity_type=_identity_type(value), identifier_value=value,
                    identifier_masked=value, identifier_fingerprint=identity_fp, source_nature="company_owned", verification_status="verified"))
            else:
                profile.identifier_value = value
                profile.identifier_masked = value
                profile.archived_at = None
        elif type_code == "internal_system":
            if db.scalar(select(InternalSystemProfile).where(InternalSystemProfile.asset_id == asset.id)) is None:
                db.add(InternalSystemProfile(asset_id=asset.id, production_url=payload.get("production_url"), repository_url=payload.get("repository_url")))
        else:
            if db.scalar(select(ResourceProfile).where(ResourceProfile.asset_id == asset.id)) is None:
                db.add(ResourceProfile(asset_id=asset.id, resource_family=str(payload.get("resource_family") or proposal.object_type),
                    external_identifier_value=payload.get("external_identifier"), management_url=payload.get("management_url"), verification_status="verified"))
        platform_name = str(payload.get("platform_name") or "").strip()
        platform = platforms.get(platform_name.casefold()) if platform_name else None
        if platform is None and proposal.matched_platform_id:
            platform = db.get(Platform, proposal.matched_platform_id)
        link_relation_type = "registered_on" if proposal.object_type == "registration_identity" else "uses"
        if platform is not None and db.scalar(select(AssetPlatformLink).where(
            AssetPlatformLink.asset_id == asset.id,
            AssetPlatformLink.platform_id == platform.id,
            AssetPlatformLink.relation_type == link_relation_type,
            AssetPlatformLink.archived_at.is_(None),
        )) is None:
            db.add(AssetPlatformLink(asset_id=asset.id, platform_id=platform.id, relation_type=link_relation_type, source_type="import", source_import_record_id=proposal.source_import_record_id, review_status="approved", confirmed_by_person_id=None, confirmed_at=datetime.now(UTC), note=reason))
    for relation in db.scalars(select(ImportProposedRelation).where(ImportProposedRelation.import_batch_id == batch.id, ImportProposedRelation.review_status == "approved")):
        source = proposal_assets.get(relation.source_proposal_id)
        target = proposal_assets.get(relation.target_proposal_id)
        source_proposal = db.get(ImportProposedObject, relation.source_proposal_id)
        target_proposal = db.get(ImportProposedObject, relation.target_proposal_id)
        if relation.relation_type == "REGISTERED_ON":
            platform_id = target_proposal.matched_platform_id if target_proposal else None
            if source is None or platform_id is None:
                continue
            if db.scalar(select(AssetPlatformLink).where(
                AssetPlatformLink.asset_id == source.id,
                AssetPlatformLink.platform_id == platform_id,
                AssetPlatformLink.relation_type == "registered_on",
                AssetPlatformLink.archived_at.is_(None),
            )) is None:
                db.add(AssetPlatformLink(
                    asset_id=source.id,
                    platform_id=platform_id,
                    relation_type="registered_on",
                    source_type="import",
                    source_import_record_id=(source_proposal.source_import_record_id if source_proposal else None),
                    review_status="approved",
                    confirmed_by_person_id=None,
                    confirmed_at=datetime.now(UTC),
                    note=reason,
                ))
            continue
        if source is None or target is None:
            continue
        from app.models import AssetRelation
        if source.id != target.id and db.scalar(select(AssetRelation).where(AssetRelation.source_asset_id == source.id, AssetRelation.target_asset_id == target.id, AssetRelation.relation_type == relation.relation_type, AssetRelation.archived_at.is_(None))) is None:
            db.add(AssetRelation(source_asset_id=source.id, target_asset_id=target.id, relation_type=relation.relation_type, source_type="import", note=reason))
    batch.status = "committed"
    batch.success_count = created
    batch.error_count = skipped
    batch.errors = [{"kind": "commit_summary", "created": created, "reused": reused, "skipped": skipped, "reason": reason}]
    db.add(AuditLog(actor_user_id=actor_user_id, action="import.batch.commit", object_type="import_batch", object_id=batch.id, before_data=None, after_data=batch.errors[0], request_id="import-instance-commit"))
    db.commit()
    return {"batch_id": str(batch.id), "status": batch.status, "created": created, "reused": reused, "skipped": skipped}
