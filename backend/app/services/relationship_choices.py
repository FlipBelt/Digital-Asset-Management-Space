"""Typed relationship choices over the existing resource and organization ledgers."""

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.core.access import (
    asset_visibility_clause,
    can_govern_asset,
    can_manage_asset,
    require_asset_visible,
)
from app.models import (
    Asset,
    AssetPlatformLink,
    AssetRelation,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Department,
    LegalEntity,
    Platform,
    PlatformTenant,
    ResourceProfile,
    ServiceInstance,
)
from app.schemas.assets import RelationshipChoiceRead, RelationshipTargetRead
from app.services.account_structure import child_account_clause, communication_resource_clause
from app.services.asset_confirmation import lock_asset
from app.services.audited_requests import audited_retry


def relationship_choices(db, access, current):
    if not can_manage_asset(db, access, current) or current.is_child_account:
        return []
    if db.scalar(select(Asset.id).where(Asset.id == current.id, communication_resource_clause())):
        return []
    types = {row.id: row for row in db.scalars(select(AssetType))}
    entities = {row.id: row for row in db.scalars(select(LegalEntity).where(
        LegalEntity.archived_at.is_(None), LegalEntity.status == "active",
    ))}
    platforms = list(db.scalars(select(Platform).where(Platform.archived_at.is_(None))))
    departments = list(db.scalars(select(Department).where(
        Department.archived_at.is_(None), Department.status == "active",
    )))
    rows = list(db.scalars(select(Asset).where(
        Asset.archived_at.is_(None), Asset.status.not_in(["deleted", "retired"]),
        Asset.id != current.id, asset_visibility_clause(access),
        ~child_account_clause(), ~communication_resource_clause(),
    ).order_by(Asset.name, Asset.id)))
    catalog_ids = set(db.scalars(select(ResourceProfile.asset_id).where(
        ResourceProfile.resource_family == "platform_catalog",
        ResourceProfile.archived_at.is_(None),
    )))
    # Private personal subscriptions and catalog placeholders are not shared dependencies.
    rows = [row for row in rows if row.id not in catalog_ids and not row.is_personal_subscription]
    personal_ids = set(db.scalars(select(ServiceInstance.asset_id).where(
        ServiceInstance.funding_source == "personal", ServiceInstance.archived_at.is_(None),
    )))
    rows = [row for row in rows if row.id not in personal_ids]
    tenants = {row.asset_id: row for row in db.scalars(select(PlatformTenant).where(
        PlatformTenant.archived_at.is_(None),
    ))}

    def code(row):
        return types[row.asset_type_id].code if row.asset_type_id in types else ""

    def runtime(row):
        kind = types.get(row.asset_type_id)
        return bool(kind and (kind.profile_kind == "internal_system" or kind.code in {
            "ai_workflow", "automation_script", "ai_application", "ai_agent",
        }))

    def host(row):
        return code(row) in {"platform_tenant", "cloud_server", "cloud_resource", "cloud_service"}

    def target(row, kind):
        if kind == "asset":
            object_type = types[row.asset_type_id].name if row.asset_type_id in types else "资产"
            return RelationshipTargetRead(id=row.id, label=row.name, object_type=object_type,
                                          detail=row.asset_code)
        return RelationshipTargetRead(id=row.id, label=row.name, object_type={
            "platform": "平台", "legal_entity": "公司", "department": "部门",
        }[kind], detail=entities[row.legal_entity_id].name
            if kind == "department" and row.legal_entity_id in entities else "")

    choices = []

    def add(group, relation, label, direction, kind, targets, description):
        if kind == "asset" and (direction == "downstream" or relation == "MANAGES"):
            targets = [row for row in targets if can_manage_asset(db, access, row)]
        choices.append(RelationshipChoiceRead(
            key=f"{relation}:{kind}:{direction}", group=group, relation_type=relation,
            label=label, direction=direction, target_kind=kind,
            targets=sorted([target(row, kind) for row in targets], key=lambda row: (row.label, row.id)),
            description=description,
        ))

    if can_govern_asset(access, current):
        add("ownership", "OWNED_BY", "归属公司", "upstream", "legal_entity",
            [row for row in entities.values() if access.is_global_manager
             or row.id == current.legal_entity_id],
            "更新公司归属；不改变负责人，也不授予访问权限。")
        add("ownership", "OWNED_BY", "归属部门", "upstream", "department",
            [row for row in departments if (current.legal_entity_id is None
             or row.legal_entity_id == current.legal_entity_id)
             and (access.is_global_manager or row.id in access.department_scopes)],
            "从当前公司已有部门选择，归属范围同步到责任与使用。")
    if current.id in tenants and can_govern_asset(access, current):
        add("ownership", "ON_PLATFORM", "所属平台", "upstream", "platform", platforms,
            "维护企业账号的所属平台；手机号与邮箱在平台与账号中引用。")
    if runtime(current):
        add("deployment", "DEPLOYED_ON", "部署在平台", "upstream", "platform", platforms,
            "选择已登记的平台；具体公司账号或服务器可以在下方关系中选择。")
        add("deployment", "DEPLOYED_ON", "部署在账号或资源", "upstream", "asset",
            [row for row in rows if host(row)], "选择承载当前系统的企业账号或云资源。")
        add("deployment", "MOUNTED_ON", "挂载到资源", "upstream", "asset",
            [row for row in rows if host(row)], "记录当前应用或工作流挂载在哪个资源中。")
    if host(current):
        add("deployment", "DEPLOYED_ON", "承载系统（被部署）", "downstream", "asset",
            [row for row in rows if runtime(row)], "所选系统 → 部署在 → 当前账号或资源。")
        add("deployment", "MOUNTED_ON", "被系统挂载", "downstream", "asset",
            [row for row in rows if runtime(row)], "所选系统 → 挂载到 → 当前资源。")
    add("usage", "CALLS", "调用接口", "upstream", "asset",
        [row for row in rows if code(row) == "api_service"], "当前对象 → 调用 → 已登记的接口实例。")
    if code(current) == "api_service":
        add("usage", "CALLS", "被调用", "downstream", "asset", rows,
            "所选对象 → 调用 → 当前接口；同一关系会在两端显示。")
    add("usage", "USES", "使用资产或账号", "upstream", "asset", rows,
        "记录实际使用的资产或企业账号，与人员授权分别维护。")
    add("usage", "USES", "使用平台服务", "upstream", "platform", platforms,
        "选择已登记的平台；这里记录使用关系，不代替账号开通或审批。")
    add("usage", "USES", "被其他对象使用", "downstream", "asset", rows,
        "所选对象 → 使用 → 当前对象；不以购买或开通代替实际使用。")
    if current.id in tenants:
        add("ownership", "MANAGES", "管理资源", "upstream", "asset",
            [row for row in rows if row.id not in tenants], "当前企业账号管理的系统、接口或云资源。")
    else:
        add("ownership", "MANAGES", "由企业账号管理", "downstream", "asset",
            [row for row in rows if row.id in tenants], "选择已有企业账号作为管理账号。")
    add("other", "DEPENDS_ON", "依赖资产", "upstream", "asset", rows,
        "无法用部署、调用或使用准确表达时，记录必要依赖并补充说明。")
    add("other", "RELATED_TO", "关联协作", "peer", "asset", rows,
        "两个对象相互关联，不表示归属、部署或使用。")
    return choices


def create_connection(db, access, asset_id, payload):
    current = lock_asset(db, asset_id)
    require_asset_visible(db, access, current)
    if not can_manage_asset(db, access, current):
        raise HTTPException(403, "无权维护该对象的关系")
    if current.archived_at or current.status == "deleted" or current.is_child_account:
        raise HTTPException(409, "请在有效父账号或资产中维护关系")
    prior, fingerprint = audited_retry(db, access, "asset.relationship.connect", payload, asset_id)
    if prior:
        return
    if current.version != payload.version:
        raise HTTPException(409, "资料已更新，请刷新后建立关系")
    choice = next((row for row in relationship_choices(db, access, current)
                   if row.key == payload.choice_key), None)
    if choice is None or payload.target_id not in {row.id for row in choice.targets}:
        raise HTTPException(422, "所选关系或对象当前不可用，请重新选择")
    before = None
    if choice.target_kind == "legal_entity":
        before = {"legal_entity_id": str(current.legal_entity_id)}
        if current.legal_entity_id != payload.target_id:
            responsibilities = list(db.scalars(select(AssetResponsibility).where(
                AssetResponsibility.asset_id == current.id,
                AssetResponsibility.role_type.in_(["responsible", "user"]),
                AssetResponsibility.archived_at.is_(None),
            )))
            if responsibilities:
                raise HTTPException(422, "已有生效责任配置，请先在责任与使用中完成公司交接")
            current.owner_department_id = None
            current.ownership_scope = "company"
        current.legal_entity_id = payload.target_id
        tenant = db.scalar(select(PlatformTenant).where(PlatformTenant.asset_id == current.id))
        if tenant:
            tenant.legal_entity_id = payload.target_id
    elif choice.target_kind == "department":
        department = db.get(Department, payload.target_id)
        before = {"owner_department_id": str(current.owner_department_id),
                  "ownership_scope": current.ownership_scope}
        current.owner_department_id = department.id
        current.legal_entity_id = department.legal_entity_id
        current.ownership_scope = "department"
    elif choice.relation_type == "ON_PLATFORM":
        tenant = db.scalar(select(PlatformTenant).where(PlatformTenant.asset_id == current.id))
        before = {"platform_id": str(tenant.platform_id)}
        tenant.platform_id = payload.target_id
        tenant.verification_status = "pending"
    elif choice.target_kind == "platform":
        relation = choice.relation_type.lower()
        link = db.scalar(select(AssetPlatformLink).where(
            AssetPlatformLink.asset_id == current.id, AssetPlatformLink.platform_id == payload.target_id,
            AssetPlatformLink.relation_type == relation, AssetPlatformLink.archived_at.is_(None),
        ))
        if link is None:
            db.add(AssetPlatformLink(asset_id=current.id, platform_id=payload.target_id,
                                    relation_type=relation, note=payload.note))
        elif payload.note:
            link.note = payload.note
    else:
        related = db.get(Asset, payload.target_id)
        require_asset_visible(db, access, related)
        # Inverse writes still require authority over the object that makes the claim.
        if choice.direction == "downstream" and not can_manage_asset(db, access, related):
            raise HTTPException(403, "无权代表所选对象建立使用或部署关系")
        source, target = (related, current) if choice.direction == "downstream" else (current, related)
        if choice.direction == "peer" and str(source.id) > str(target.id):
            source, target = target, source
        profile = db.scalar(select(ResourceProfile).where(
            ResourceProfile.asset_id == target.id, ResourceProfile.archived_at.is_(None),
        )) if choice.relation_type == "MANAGES" else None
        manager = db.scalar(select(PlatformTenant).where(
            PlatformTenant.asset_id == source.id, PlatformTenant.archived_at.is_(None),
        )) if profile else None
        if profile and manager:
            if not can_manage_asset(db, access, target):
                raise HTTPException(403, "无权修改所选资源的管理账号")
            before = {"managed_under_account_id": str(profile.managed_under_account_id)}
            profile.managed_under_account_id = manager.id
            if target.id != current.id:
                target.version += 1
        else:
            relation = db.scalar(select(AssetRelation).where(
                AssetRelation.source_asset_id == source.id, AssetRelation.target_asset_id == target.id,
                func.lower(AssetRelation.relation_type) == choice.relation_type.lower(),
            ))
            if relation is None:
                db.add(AssetRelation(source_asset_id=source.id, target_asset_id=target.id,
                                     relation_type=choice.relation_type, note=payload.note))
            else:
                relation.archived_at = None
                if payload.note:
                    relation.note = payload.note
    current.version += 1
    db.add(AuditLog(actor_user_id=access.user.id, action="asset.relationship.connect",
                    object_type="asset", object_id=current.id, request_id=str(payload.request_id),
                    before_data=before, after_data={"request_digest": fingerprint,
                        "choice_key": payload.choice_key, "target_id": str(payload.target_id),
                        "version": current.version, "note": payload.note}))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "关联已存在或对象资料有冲突，请刷新后查看") from exc


def save_platform_identifier(db, access, asset_id, payload):
    asset = lock_asset(db, asset_id)
    require_asset_visible(db, access, asset)
    if not can_govern_asset(access, asset):
        raise HTTPException(403, "只有资产管理员或所属部门负责人可以维护账号 ID")
    tenant = db.scalar(select(PlatformTenant).where(
        PlatformTenant.asset_id == asset_id, PlatformTenant.archived_at.is_(None),
    ))
    if tenant is None or asset.archived_at:
        raise HTTPException(422, "请在有效企业账号中维护平台原生 ID")
    prior, fingerprint = audited_retry(db, access, "platform.identifier.update", payload, asset_id)
    if prior:
        return
    if asset.version != payload.version:
        raise HTTPException(409, "账号资料已更新，请刷新后填写 ID")
    value = (payload.identifier or "").strip() or None
    duplicate = db.scalar(select(PlatformTenant.id).where(
        PlatformTenant.id != tenant.id, PlatformTenant.platform_id == tenant.platform_id,
        PlatformTenant.tenant_identifier == value, PlatformTenant.archived_at.is_(None),
    )) if value else None
    if duplicate:
        raise HTTPException(409, "这个平台 ID 已登记，请使用已有账号")
    before = {"identifier": tenant.tenant_identifier, "identifier_type": tenant.external_identifier_type}
    changed = value != tenant.tenant_identifier or payload.identifier_type != tenant.external_identifier_type
    tenant.tenant_identifier = value
    tenant.external_identifier_type = payload.identifier_type
    if changed:
        tenant.verification_status = "pending"
    asset.version += 1
    db.add(AuditLog(actor_user_id=access.user.id, action="platform.identifier.update",
                    object_type="asset", object_id=asset_id, request_id=str(payload.request_id),
                    before_data=before, after_data={"request_digest": fingerprint,
                        "identifier": value, "identifier_type": payload.identifier_type,
                        "version": asset.version}))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "平台 ID 已存在，请使用已有账号") from exc
