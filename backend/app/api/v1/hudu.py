"""Hudu-inspired read models for the first local product slice.

The endpoint is deliberately a projection over the existing asset ledger.  It
does not introduce a second source of truth: edits continue to use the
canonical ``/assets`` APIs while this router joins the pieces needed by the
simpler asset-library experience.
"""

from __future__ import annotations

from datetime import date, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, asset_visibility_clause, get_access_context
from app.db.session import get_db
from app.models import (
    Account,
    Asset,
    AssetCategory,
    AssetIdentifier,
    AssetRelation,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Department,
    InfrastructureProfile,
    InternalSystemProfile,
    LegalEntity,
    Person,
    Platform,
    PlatformTenant,
    ResourceProfile,
)

router = APIRouter(prefix="/hudu", tags=["hudu-workspace"])


def _iso(value):
    return value.isoformat() if value is not None else None


def _maps(db: Session):
    categories = {
        item.id: item
        for item in db.scalars(select(AssetCategory).where(AssetCategory.archived_at.is_(None)))
    }
    types = {
        item.id: item
        for item in db.scalars(select(AssetType).where(AssetType.archived_at.is_(None)))
    }
    departments = {
        item.id: item
        for item in db.scalars(select(Department).where(Department.archived_at.is_(None)))
    }
    entities = {
        item.id: item
        for item in db.scalars(select(LegalEntity).where(LegalEntity.archived_at.is_(None)))
    }
    people = {
        item.id: item
        for item in db.scalars(select(Person).where(Person.archived_at.is_(None)))
    }
    return categories, types, departments, entities, people


def _asset_item(asset: Asset, categories, types, departments, entities, people):
    asset_type = types.get(asset.asset_type_id)
    category = categories.get(asset_type.category_id) if asset_type else None
    department = departments.get(asset.owner_department_id) if asset.owner_department_id else None
    entity = entities.get(asset.legal_entity_id) if asset.legal_entity_id else None
    return {
        "id": str(asset.id),
        "asset_code": asset.asset_code,
        "name": asset.name,
        "status": asset.status,
        "review_status": asset.review_status,
        "criticality": asset.criticality,
        "confidentiality": asset.confidentiality,
        "ownership_scope": asset.ownership_scope,
        "asset_type_id": str(asset.asset_type_id),
        "asset_type_code": asset_type.code if asset_type else None,
        "asset_type_name": asset_type.name if asset_type else "未分类类型",
        "profile_kind": asset_type.profile_kind if asset_type else "generic",
        "category_id": str(category.id) if category else None,
        "category_code": category.code if category else None,
        "category_name": category.name if category else "其他资产",
        "legal_entity_id": str(asset.legal_entity_id) if asset.legal_entity_id else None,
        "legal_entity_name": entity.name if entity else None,
        "owner_department_id": str(asset.owner_department_id) if asset.owner_department_id else None,
        "owner_department_name": department.name if department else None,
        "expires_at": _iso(asset.expires_at),
        "started_at": _iso(asset.started_at),
        "last_verified_at": _iso(asset.last_verified_at),
        "description": asset.description,
        "version": asset.version,
        "updated_at": _iso(asset.updated_at),
        "created_at": _iso(asset.created_at),
        "archived_at": _iso(asset.archived_at),
        "has_owner": bool(asset.owner_department_id),
    }


def _active_assets(db: Session, access: AccessContext, *, include_archived: bool = False, keyword: str | None = None):
    filters = [] if include_archived else [Asset.archived_at.is_(None)]
    filters.append(asset_visibility_clause(access))
    if keyword and keyword.strip():
        term = f"%{keyword.strip()}%"
        identifier_match = exists(
            select(AssetIdentifier.id).where(
                AssetIdentifier.asset_id == Asset.id,
                AssetIdentifier.archived_at.is_(None),
                AssetIdentifier.identifier_value.ilike(term),
            )
        )
        filters.append(or_(Asset.name.ilike(term), Asset.asset_code.ilike(term), identifier_match))
    return list(db.scalars(select(Asset).where(*filters).order_by(Asset.updated_at.desc(), Asset.id)))


@router.get("/overview")
def overview(db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)):
    categories, types, departments, entities, people = _maps(db)
    assets = _active_assets(db, access)
    today = date.today()
    soon = today + timedelta(days=30)
    items = [_asset_item(item, categories, types, departments, entities, people) for item in assets]
    due = [item for item in items if item["expires_at"] and item["expires_at"][:10] <= soon.isoformat()]
    missing_owner = [item for item in items if not item["has_owner"]]
    category_counts: dict[str, int] = {}
    for item in items:
        key = item["category_name"]
        category_counts[key] = category_counts.get(key, 0) + 1
    return {
        "total_assets": len(items),
        "active_assets": sum(1 for item in items if item["status"] == "active"),
        "draft_assets": sum(1 for item in items if item["status"] in {"draft", "pending_review"}),
        "expiring_soon": len(due),
        "missing_owner": len(missing_owner),
        "category_counts": [{"label": key, "value": value} for key, value in sorted(category_counts.items(), key=lambda row: -row[1])],
        "recent_assets": items[:8],
        "due_items": due[:8],
        "generated_at": __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat(),
    }


@router.get("/assets")
def list_hudu_assets(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    keyword: str | None = None,
    category_id: UUID | None = None,
    asset_type_id: UUID | None = None,
    status: str | None = None,
    only_due: bool = False,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    categories, types, departments, entities, people = _maps(db)
    items = [_asset_item(item, categories, types, departments, entities, people) for item in _active_assets(db, access, include_archived=include_archived, keyword=keyword)]
    today = date.today()
    soon = today + timedelta(days=30)
    if category_id:
        items = [item for item in items if item["category_id"] == str(category_id)]
    if asset_type_id:
        items = [item for item in items if item["asset_type_id"] == str(asset_type_id)]
    if status:
        items = [item for item in items if item["status"] == status]
    if only_due:
        items = [item for item in items if item["expires_at"] and item["expires_at"][:10] <= soon.isoformat()]
    total = len(items)
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "categories": [
            {"id": str(item.id), "code": item.code, "name": item.name, "count": sum(1 for asset in items if asset["category_id"] == str(item.id))}
            for item in sorted(categories.values(), key=lambda row: (row.sort_order, row.name))
            if any(asset["category_id"] == str(item.id) for asset in items)
        ],
        "types": [
            {"id": str(item.id), "code": item.code, "name": item.name, "category_id": str(item.category_id), "count": sum(1 for asset in items if asset["asset_type_id"] == str(item.id))}
            for item in sorted(types.values(), key=lambda row: row.name)
            if any(asset["asset_type_id"] == str(item.id) for asset in items)
        ],
    }


@router.get("/expirations")
def expirations(db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)):
    categories, types, departments, entities, people = _maps(db)
    assets = [_asset_item(item, categories, types, departments, entities, people) for item in _active_assets(db, access)]
    today = date.today()
    soon = today + timedelta(days=90)
    due = [item for item in assets if (item["expires_at"] and item["expires_at"][:10] <= soon.isoformat()) or not item["has_owner"]]
    due.sort(key=lambda item: (item["expires_at"] is None, item["expires_at"] or "9999-12-31", item["name"]))
    return {"items": due, "total": len(due), "window_days": 90}


@router.get("/assets/{asset_id}")
def get_hudu_asset(asset_id: UUID, db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)):
    categories, types, departments, entities, people = _maps(db)
    asset = db.scalar(select(Asset).where(Asset.id == asset_id, Asset.archived_at.is_(None), asset_visibility_clause(access)))
    if asset is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="资产不存在")
    base = _asset_item(asset, categories, types, departments, entities, people)
    responsibilities = []
    for row in db.scalars(select(AssetResponsibility).where(AssetResponsibility.asset_id == asset_id, AssetResponsibility.archived_at.is_(None)).order_by(AssetResponsibility.is_primary.desc(), AssetResponsibility.created_at)):
        person = people.get(row.person_id) if row.person_id else None
        department = departments.get(row.department_id) if row.department_id else None
        responsibilities.append({"id": str(row.id), "role_type": row.role_type, "is_primary": row.is_primary, "person_id": str(row.person_id) if row.person_id else None, "person_name": person.display_name if person else None, "department_id": str(row.department_id) if row.department_id else None, "department_name": department.name if department else None, "starts_at": _iso(row.starts_at), "ends_at": _iso(row.ends_at)})
    relations = []
    relation_rows = db.scalars(select(AssetRelation).where(AssetRelation.archived_at.is_(None), or_(AssetRelation.source_asset_id == asset_id, AssetRelation.target_asset_id == asset_id))).all()
    related_ids = {row.target_asset_id if row.source_asset_id == asset_id else row.source_asset_id for row in relation_rows}
    related_assets = {row.id: row for row in db.scalars(select(Asset).where(Asset.id.in_(related_ids), Asset.archived_at.is_(None)))} if related_ids else {}
    for row in relation_rows:
        related_id = row.target_asset_id if row.source_asset_id == asset_id else row.source_asset_id
        related = related_assets.get(related_id)
        if not related:
            continue
        related_item = _asset_item(related, categories, types, departments, entities, people)
        relations.append({"id": str(row.id), "relation_type": row.relation_type, "note": row.note, "direction": "outbound" if row.source_asset_id == asset_id else "inbound", "related_asset_id": str(related.id), "related_name": related.name, "related_asset_code": related.asset_code, "related_type_name": related_item["asset_type_name"], "related_category_name": related_item["category_name"]})
    identifiers = [{"id": str(row.id), "namespace": row.namespace, "identifier_type": row.identifier_type, "identifier_value": row.identifier_value, "is_primary": row.is_primary, "verification_status": row.verification_status} for row in db.scalars(select(AssetIdentifier).where(AssetIdentifier.asset_id == asset_id, AssetIdentifier.archived_at.is_(None)).order_by(AssetIdentifier.is_primary.desc(), AssetIdentifier.created_at))]
    profile = None
    if types.get(asset.asset_type_id) and types[asset.asset_type_id].profile_kind == "internal_system":
        row = db.scalar(select(InternalSystemProfile).where(InternalSystemProfile.asset_id == asset_id))
        if row:
            profile = {"kind": "internal_system", "data": {"repository_url": row.repository_url, "production_url": row.production_url, "tech_stack": row.tech_stack, "deployment_guide_url": row.deployment_guide_url, "recovery_guide_url": row.recovery_guide_url, "backup_description": row.backup_description}}
    if profile is None:
        row = db.scalar(select(ResourceProfile).where(ResourceProfile.asset_id == asset_id))
        if row:
            profile = {"kind": "resource", "data": {"resource_family": row.resource_family, "external_identifier_type": row.external_identifier_type, "external_identifier_value": row.external_identifier_value, "management_url": row.management_url, "verification_status": row.verification_status}}
    if profile is None:
        row = db.scalar(select(InfrastructureProfile).where(InfrastructureProfile.asset_id == asset_id))
        if row:
            profile = {"kind": "infrastructure", "data": {"external_resource_id": row.external_resource_id, "region": row.region, "environment": row.environment, "specification": row.specification, "public_address": row.public_address}}
    account_context = None
    account = db.scalar(select(Account).where(Account.asset_id == asset_id, Account.archived_at.is_(None)))
    if account:
        tenant = db.get(PlatformTenant, account.platform_tenant_id)
        platform = db.get(Platform, tenant.platform_id) if tenant else None
        account_context = {"login_identifier": account.login_identifier, "account_type": account.account_type, "mfa_status": account.mfa_status, "privilege_level": account.privilege_level, "platform_name": platform.name if platform else None, "tenant_identifier": tenant.tenant_identifier if tenant else None}
    history = [{"id": str(row.id), "action": row.action, "created_at": _iso(row.created_at), "after_data": row.after_data} for row in db.scalars(select(AuditLog).where(AuditLog.object_type == "asset", AuditLog.object_id == asset_id).order_by(AuditLog.created_at.desc()).limit(12))]
    return {"asset": base, "responsibilities": responsibilities, "relations": relations, "identifiers": identifiers, "profile": profile, "account_context": account_context, "history": history}
