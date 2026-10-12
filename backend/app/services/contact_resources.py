"""Communication resources belong to holders; platform accounts only reference them."""

import hashlib
import re
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.access import can_manage_asset, require_asset_visible
from app.models import (
    Asset,
    AssetCategory,
    AssetIdentifier,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Department,
    LegalEntity,
    Person,
    RegistrationIdentityProfile,
)
from app.schemas.workspace import RegistrationIdentityRead
from app.services.assets import allocate_asset_code, ensure_internal_identifier


def normalize_identifier(value):
    value = value.strip()
    compact = re.sub(r"[\s-]", "", value)
    if compact.startswith("+86"):
        compact = compact[3:]
    if re.fullmatch(r"1\d{10}", compact):
        return compact, "phone"
    if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        return value.casefold(), "email"
    raise HTTPException(422, "请填写有效的手机号或邮箱")


def registration_blocked(db, asset_id):
    return bool(
        db.scalar(
            select(AssetIdentifier.id).where(
                AssetIdentifier.asset_id == asset_id,
                AssetIdentifier.identifier_type == "registration_restriction",
                AssetIdentifier.identifier_value == "do_not_use",
                AssetIdentifier.archived_at.is_(None),
            )
        )
    )


def contact_read(db, profile, asset):
    return RegistrationIdentityRead(
        id=profile.id,
        asset_id=asset.id,
        asset_code=asset.asset_code,
        legal_entity_id=asset.legal_entity_id,
        name=asset.name,
        identity_type=profile.identity_type,
        identifier=profile.identifier_value,
        source_nature=profile.source_nature,
        custodian_person_id=profile.custodian_person_id,
        verification_status=profile.verification_status,
        version=asset.version,
        owner_department_id=asset.owner_department_id,
        note=asset.description,
        registration_blocked=registration_blocked(db, asset.id),
    )


def normalize_contact_catalog(db):
    # An explicit administrator reconciliation also moves the existing type, preserving UUIDs.
    category = db.scalar(
        select(AssetCategory).where(AssetCategory.code == "communication_resources")
    )
    if category is None:
        category = AssetCategory(code="communication_resources", name="手机号与邮箱", sort_order=15)
        db.add(category)
        db.flush()
    asset_type = db.scalar(select(AssetType).where(AssetType.code == "registration_identity"))
    if asset_type is None:
        raise HTTPException(422, "缺少手机号与邮箱类型")
    asset_type.category_id = category.id
    asset_type.name = "手机号 / 邮箱"
    return asset_type


def require_identity_reference(db, access, identity, company_id):
    if identity is None or identity.archived_at is not None or identity.status == "deleted":
        raise HTTPException(422, "所选手机号或邮箱不存在")
    require_asset_visible(db, access, identity)
    profile = db.scalar(
        select(RegistrationIdentityProfile).where(
            RegistrationIdentityProfile.asset_id == identity.id,
            RegistrationIdentityProfile.archived_at.is_(None),
        )
    )
    if profile is None:
        raise HTTPException(422, "所选对象不是有效的手机号或邮箱资源")
    if registration_blocked(db, identity.id):
        raise HTTPException(422, "此号码或邮箱已注明禁止用于平台注册，请选择其他资源")
    if identity.legal_entity_id != company_id and not access.is_global_manager:
        raise HTTPException(422, "跨公司引用需由资产管理员登记；通讯资源的归属不会改写")
    return profile


def save_contact(db, access, row, asset_type, source_note):
    value, kind = normalize_identifier(row.identifier)
    fingerprint = hashlib.sha256(value.encode()).hexdigest()
    if db.bind.dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(int(fingerprint[:15], 16))))
    profile = db.scalar(
        select(RegistrationIdentityProfile)
        .where(
            RegistrationIdentityProfile.identifier_fingerprint == fingerprint,
        )
        .with_for_update()
    )
    entity = db.get(LegalEntity, row.legal_entity_id) if row.legal_entity_id else None
    if row.legal_entity_id and (entity is None or entity.archived_at):
        raise HTTPException(422, "所选公司不存在")
    custodian = db.get(Person, row.custodian_person_id) if row.custodian_person_id else None
    if row.custodian_person_id and (
        custodian is None
        or custodian.archived_at
        or custodian.employment_status != "active"
        or custodian.legal_entity_id != row.legal_entity_id
    ):
        raise HTTPException(422, "请绑定通讯资源所属公司的实际在职同事")
    department = db.get(Department, row.owner_department_id) if row.owner_department_id else None
    if row.owner_department_id and (
        department is None
        or department.archived_at
        or department.legal_entity_id != row.legal_entity_id
    ):
        raise HTTPException(422, "通讯资源的使用部门不属于所选公司")
    if not custodian and not department:
        raise HTTPException(422, "请选择保管同事，或为共用号码选择使用部门")
    before = None
    if profile:
        asset = db.scalar(select(Asset).where(Asset.id == profile.asset_id).with_for_update())
        if profile.archived_at or asset is None or asset.archived_at or asset.status == "deleted":
            raise HTTPException(409, "已有通讯资源已归档，请先在回收站核对")
        if not can_manage_asset(db, access, asset):
            raise HTTPException(403, "无权更新已有通讯资源")
        if row.expected_version != asset.version:
            raise HTTPException(409, "通讯资源已有更新，请刷新预览后再保存")
        before = {
            "version": asset.version,
            "custodian": str(profile.custodian_person_id),
            "company": str(asset.legal_entity_id),
            "department": str(asset.owner_department_id),
            "verification_status": profile.verification_status,
        }
        asset.version += 1
    else:
        if row.expected_version is not None:
            raise HTTPException(409, "通讯资源已改变，请刷新预览")
        asset = Asset(
            name=f"{'手机号' if kind == 'phone' else '邮箱'} · {value}",
            asset_type_id=asset_type.id,
            asset_code=allocate_asset_code(db, row.legal_entity_id, asset_type.id),
            source_type="manual",
            created_by_person_id=access.person_id,
        )
        db.add(asset)
        db.flush()
        ensure_internal_identifier(db, asset)
        profile = RegistrationIdentityProfile(
            asset_id=asset.id,
            identity_type=kind,
            identifier_value=value,
            identifier_masked=value,
            identifier_fingerprint=fingerprint,
        )
        db.add(profile)
    asset.legal_entity_id = row.legal_entity_id
    asset.owner_department_id = row.owner_department_id
    asset.ownership_scope = "department" if department else "company"
    asset.description = "\n".join(value for value in (row.note, source_note) if value)
    asset.status = "active"
    asset.review_status = "not_required"
    profile.source_nature = row.source_nature
    profile.custodian_person_id = row.custodian_person_id
    profile.verification_status = row.verification_status
    profile.last_verified_at = (
        datetime.now(UTC) if row.verification_status == "documented" else None
    )
    responsibility = db.scalar(
        select(AssetResponsibility).where(
            AssetResponsibility.asset_id == asset.id,
            AssetResponsibility.role_type == "responsible",
            AssetResponsibility.archived_at.is_(None),
        )
    )
    # Use the explicit source holder; a shared resource is a department responsibility.
    if responsibility:
        responsibility.person_id = row.custodian_person_id
        responsibility.department_id = None if custodian else row.owner_department_id
        responsibility.starts_at = None
        responsibility.ends_at = None
    else:
        db.add(
            AssetResponsibility(
                asset_id=asset.id,
                person_id=row.custodian_person_id,
                department_id=None if custodian else row.owner_department_id,
                role_type="responsible",
                is_primary=True,
            )
        )
    restriction = db.scalar(
        select(AssetIdentifier).where(
            AssetIdentifier.asset_id == asset.id,
            AssetIdentifier.identifier_type == "registration_restriction",
            AssetIdentifier.archived_at.is_(None),
        )
    )
    if row.registration_blocked and restriction is None:
        db.add(
            AssetIdentifier(
                asset_id=asset.id,
                namespace=str(asset.id),
                identifier_type="registration_restriction",
                identifier_value="do_not_use",
                verification_status="documented",
            )
        )
    elif not row.registration_blocked and restriction:
        restriction.archived_at = datetime.now(UTC)
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="contact.reconcile.row",
            object_type="asset",
            object_id=asset.id,
            before_data=before,
            after_data={
                "custodian": str(row.custodian_person_id),
                "company": str(row.legal_entity_id),
                "department": str(row.owner_department_id),
                "source_note": source_note,
                "verification_status": row.verification_status,
                "registration_blocked": row.registration_blocked,
            },
        )
    )
    db.flush()
    return contact_read(db, profile, asset)
