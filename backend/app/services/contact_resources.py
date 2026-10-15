"""Communication resources belong to holders; platform accounts only reference them."""

import hashlib
import re
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.access import active_period, can_manage_asset, require_asset_visible
from app.models import (
    Asset,
    AssetCategory,
    AssetIdentifier,
    AssetRelation,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Department,
    LegalEntity,
    Person,
    PlatformAccountRegistrationIdentity,
    PlatformTenant,
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
        name=profile.identifier_value,
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


def require_contact_custodian(db, access, person_id, company_id):
    if person_id is None:
        return None
    person = db.get(Person, person_id)
    if person is None or person.archived_at or person.employment_status != "active":
        raise HTTPException(422, "保管同事必须为在职且未归档的人员")
    # A business company and its shared directory need not use the same entity UUID.
    if (
        company_id is not None
        and person.legal_entity_id != company_id
        and not access.is_global_manager
    ):
        raise HTTPException(422, "跨公司保管同事需由资产管理员登记")
    return person


def normalize_contact_catalog(db):
    # An explicit administrator reconciliation also moves the existing type, preserving UUIDs.
    category = db.scalar(
        select(AssetCategory).where(AssetCategory.code == "communication_resources")
    )
    if category is None:
        category = AssetCategory(code="communication_resources", name="注册与登录标识", sort_order=15)
        db.add(category)
        db.flush()
    asset_type = db.scalar(select(AssetType).where(AssetType.code == "registration_identity"))
    if asset_type is None:
        raise HTTPException(422, "缺少手机号与邮箱类型")
    asset_type.category_id = category.id
    category.name = "注册与登录标识"
    asset_type.name = "注册与登录标识"
    return asset_type


def require_identity_reference(db, access, identity, company_id):
    if identity is not None:
        identity = db.scalar(select(Asset).where(Asset.id == identity.id).with_for_update()
                             .execution_options(populate_existing=True))
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


def release_archived_identity_claim(db, access, profile, target_asset_id, request_id, fingerprint):
    if profile.archived_at is None:
        return False
    asset = db.scalar(select(Asset).where(Asset.id == profile.asset_id).with_for_update())
    if asset is None or asset.archived_at is None or asset.status != "archived":
        return False
    account_reference = db.scalar(select(PlatformAccountRegistrationIdentity.id)
        .join(PlatformTenant, PlatformTenant.id == PlatformAccountRegistrationIdentity.platform_tenant_id)
        .join(Asset, Asset.id == PlatformTenant.asset_id)
        .where(PlatformAccountRegistrationIdentity.registration_identity_asset_id == asset.id,
               PlatformAccountRegistrationIdentity.status == "active",
               active_period(PlatformAccountRegistrationIdentity),
               PlatformTenant.archived_at.is_(None), Asset.archived_at.is_(None)))
    relation_reference = db.scalar(select(AssetRelation.id).join(Asset,
        (Asset.id == AssetRelation.source_asset_id) | (Asset.id == AssetRelation.target_asset_id))
        .where((AssetRelation.source_asset_id == asset.id) | (AssetRelation.target_asset_id == asset.id),
               AssetRelation.archived_at.is_(None), Asset.id != asset.id, Asset.archived_at.is_(None)))
    if account_reference or relation_reference:
        return False
    # Only release the unique lookup claim. The archived identifier, object and history stay intact.
    if profile.identifier_fingerprint == fingerprint:
        historical_fingerprint = hashlib.sha256(f"archived-registry:{profile.id}:{fingerprint}".encode()).hexdigest()
        profile.identifier_fingerprint = historical_fingerprint
        db.add(AuditLog(actor_user_id=access.user.id, action="registration_identity.release_archived_claim",
            object_type="asset", object_id=asset.id, request_id=str(request_id),
            before_data={"identifier_fingerprint": fingerprint},
            after_data={"identifier_fingerprint": historical_fingerprint, "reused_by": str(target_asset_id)}))
        db.flush()
    return True


def save_contact(db, access, row, asset_type, source_note, *, asset_id=None):
    if asset_id is not None and row.identity_type not in ("phone", "email"):
        value, kind = row.identifier.strip(), row.identity_type
        if not value or any(ord(char) < 32 for char in value):
            raise HTTPException(422, "请填写有效的用户名或账号标识")
    else:
        value, kind = normalize_identifier(row.identifier)
        if asset_id is not None and kind != row.identity_type:
            raise HTTPException(422, "标识内容与所选类型不一致，请核对手机号或邮箱格式")
    fingerprint = hashlib.sha256(value.lower().encode()).hexdigest()
    if db.bind.dialect.name == "postgresql":
        db.execute(select(func.pg_advisory_xact_lock(int(fingerprint[:15], 16))))
    asset = None
    if asset_id is not None:
        asset = db.scalar(select(Asset).where(Asset.id == asset_id).with_for_update()
                          .execution_options(populate_existing=True))
    profile = db.scalar(
        select(RegistrationIdentityProfile)
        .where(
            RegistrationIdentityProfile.asset_id == asset_id if asset_id is not None
            else RegistrationIdentityProfile.identifier_fingerprint == fingerprint,
        )
        .with_for_update()
    )
    if asset_id is not None:
        if profile is None or asset is None or profile.archived_at or asset.archived_at or asset.status == "deleted":
            raise HTTPException(404, "注册与登录标识不存在或已删除")
        # Historical imports may store formatted numbers with a different fingerprint.
        for candidate in db.scalars(select(RegistrationIdentityProfile).where(
            RegistrationIdentityProfile.asset_id != asset_id,
        )):
            try:
                candidate_value = normalize_identifier(candidate.identifier_value)[0]
            except HTTPException:
                candidate_value = candidate.identifier_value.strip()
            if candidate.identifier_fingerprint == fingerprint or candidate_value.lower() == value.lower():
                if release_archived_identity_claim(db, access, candidate, asset_id, row.request_id, fingerprint):
                    continue
                other = db.get(Asset, candidate.asset_id)
                state = "回收站" if other.status == "deleted" else "历史归档" if other.archived_at else "当前登记"
                raise HTTPException(409, {"code": "registration_identifier_conflict",
                    "message": f"该标识已由 {other.asset_code} 占用（{state}），请核对已有记录。",
                    "conflict": {"asset_id": str(other.id), "asset_code": other.asset_code,
                        "name": candidate.identifier_value, "deleted": other.status == "deleted",
                        "historical": candidate.archived_at is not None}})
    entity = db.get(LegalEntity, row.legal_entity_id) if row.legal_entity_id else None
    if row.legal_entity_id and (entity is None or entity.archived_at):
        raise HTTPException(422, "所选公司不存在")
    custodian = require_contact_custodian(db, access, row.custodian_person_id, row.legal_entity_id)
    department = db.get(Department, row.owner_department_id) if row.owner_department_id else None
    if row.owner_department_id and (
        department is None
        or department.archived_at
        or (department.legal_entity_id != row.legal_entity_id and not access.is_global_manager)
    ):
        raise HTTPException(422, "通讯资源的使用部门不属于所选公司")
    if not custodian and not department and (
        asset_id is None or profile.custodian_person_id or asset.owner_department_id
    ):
        raise HTTPException(422, "请选择保管同事，或为共用号码选择使用部门")
    before = None
    if profile:
        if asset is None:
            asset = db.scalar(select(Asset).where(Asset.id == profile.asset_id).with_for_update())
        if profile.archived_at or asset is None or asset.archived_at or asset.status == "deleted":
            raise HTTPException(409, "已有通讯资源已归档，请先在回收站核对")
        if not can_manage_asset(db, access, asset):
            raise HTTPException(403, "无权更新已有通讯资源")
        if row.expected_version != asset.version:
            raise HTTPException(409, "通讯资源已有更新，请刷新预览后再保存")
        before = {
            "version": asset.version,
            "identifier": profile.identifier_value,
            "identity_type": profile.identity_type,
            "custodian": str(profile.custodian_person_id),
            "company": str(asset.legal_entity_id),
            "department": str(asset.owner_department_id),
            "verification_status": profile.verification_status,
        }
        if asset_id is not None:
            profile.identifier_value = profile.identifier_masked = value
            profile.identifier_fingerprint = fingerprint
            profile.identity_type = kind
        asset.version += 1
    else:
        if row.expected_version is not None:
            raise HTTPException(409, "通讯资源已改变，请刷新预览")
        asset = Asset(
            name=value[:200],
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
    # Asset.name is a bounded cache; registry reads use the full identifier value.
    asset.name = profile.identifier_value[:200]
    asset.legal_entity_id = row.legal_entity_id
    asset.owner_department_id = row.owner_department_id
    asset.ownership_scope = "department" if department else "company"
    asset.description = "\n".join(value for value in (row.note, source_note) if value)
    if asset_id is None:
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
    if responsibility and (custodian or department):
        responsibility.person_id = row.custodian_person_id
        responsibility.department_id = None if custodian else row.owner_department_id
        responsibility.starts_at = None
        responsibility.ends_at = None
    elif responsibility is None and (custodian or department):
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
            action="registration_identity.update.row" if asset_id is not None else "contact.reconcile.row",
            object_type="asset",
            object_id=asset.id,
            before_data=before,
            after_data={
                "version": asset.version,
                "identifier": profile.identifier_value,
                "identity_type": profile.identity_type,
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
