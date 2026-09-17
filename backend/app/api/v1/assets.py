from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.access import (
    AccessContext,
    asset_visibility_clause,
    can_govern_asset,
    can_manage_asset,
    get_access_context,
    require_asset_visible,
    require_asset_write,
)
from app.db.session import get_db
from app.models import (
    AccessGrant,
    Account,
    AccountGrant,
    Asset,
    AssetFieldDefinition,
    AssetFieldValue,
    AssetIdentifier,
    AssetPlatformLink,
    AssetRelation,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Department,
    LegalEntity,
    Person,
    Platform,
    PlatformAccountRegistrationIdentity,
    PlatformTenant,
    RelationDefinition,
    ResourceProfile,
    ServiceInstance,
    SourceImportRecord,
)
from app.repositories.assets import asset_repository
from app.schemas.assets import (
    AssetAssignmentRead,
    AssetAssignmentWrite,
    AssetCreate,
    AssetFieldValueInput,
    AssetFieldValueRead,
    AssetIdentifierCreate,
    AssetIdentifierRead,
    AssetPatch,
    AssetPlatformLinkCreate,
    AssetPlatformLinkRead,
    AssetRead,
    AssetRelationCreate,
    AssetRelationRead,
    AssetRelationshipViewRead,
    AssetResponsibilityCreate,
    AssetResponsibilityRead,
    IntelligentRelationCreate,
    RelationOptionRead,
    RelationshipLinkUpdate,
)
from app.schemas.common import ListResponse, Pagination
from app.services.assets import asset_service

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("", response_model=ListResponse[AssetRead])
def list_assets(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    legal_entity_id: UUID | None = None,
    department_id: UUID | None = None,
    asset_type_id: UUID | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    criticality: str | None = None,
    include_archived: bool = False,
    keyword: str | None = None,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> ListResponse[AssetRead]:
    items, total = asset_repository.list(
        db,
        page=page,
        page_size=page_size,
        legal_entity_id=legal_entity_id,
        department_id=department_id,
        asset_type_id=asset_type_id,
        status=status_filter,
        criticality=criticality,
        include_archived=include_archived,
        keyword=keyword,
        visibility_filter=asset_visibility_clause(access),
    )
    return ListResponse[AssetRead](
        data=[AssetRead.model_validate(item) for item in items],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> Asset:
    return asset_service.create(db, payload, created_by_person_id=access.person_id)


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> Asset:
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    return asset


@router.get("/{asset_id}/identifiers", response_model=list[AssetIdentifierRead])
def list_identifiers(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[AssetIdentifier]:
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    return list(
        db.scalars(
            select(AssetIdentifier)
            .where(AssetIdentifier.asset_id == asset_id, AssetIdentifier.archived_at.is_(None))
            .order_by(
                AssetIdentifier.is_primary.desc(),
                AssetIdentifier.namespace,
                AssetIdentifier.identifier_type,
            )
        )
    )


@router.get("/{asset_id}/platform-links", response_model=list[AssetPlatformLinkRead])
def list_platform_links(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[AssetPlatformLink]:
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    return list(
        db.scalars(
            select(AssetPlatformLink)
            .where(
                AssetPlatformLink.asset_id == asset_id,
                AssetPlatformLink.archived_at.is_(None),
            )
            .order_by(AssetPlatformLink.created_at)
        )
    )


@router.post(
    "/{asset_id}/platform-links",
    response_model=AssetPlatformLinkRead,
    status_code=status.HTTP_201_CREATED,
)
def create_platform_link(
    asset_id: UUID,
    payload: AssetPlatformLinkCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> AssetPlatformLink:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权维护平台关联")
    platform = db.get(Platform, payload.platform_id)
    if platform is None or platform.archived_at is not None:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="所选平台不存在")
    if payload.source_import_record_id:
        source = db.get(SourceImportRecord, payload.source_import_record_id)
        if source is None or source.archived_at is not None:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="来源资料记录不存在")
    if payload.review_status not in {"pending_review", "approved", "rejected"}:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="关联审核状态无效")
    item = AssetPlatformLink(
        asset_id=asset.id,
        source_type="manual",
        **payload.model_dump(),
    )
    if item.review_status == "approved":
        item.confirmed_by_person_id = access.person_id
        item.confirmed_at = datetime.now(UTC)
    db.add(item)
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="asset.platform_link.create",
            object_type="asset",
            object_id=asset.id,
            after_data={
                "platform_id": str(platform.id),
                "relation_type": item.relation_type,
                "review_status": item.review_status,
            },
            request_id="asset-platform-link",
        )
    )
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="该平台关联已经存在") from exc
    db.refresh(item)
    return item


@router.post("/{asset_id}/platform-links/{link_id}/archive", response_model=AssetPlatformLinkRead)
def archive_platform_link(
    asset_id: UUID,
    link_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> AssetPlatformLink:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权维护平台关联")
    item = db.get(AssetPlatformLink, link_id)
    if item is None or item.asset_id != asset_id or item.archived_at is not None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="平台关联不存在")
    item.archived_at = datetime.now(UTC)
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="asset.platform_link.archive",
            object_type="asset",
            object_id=asset.id,
            after_data={"platform_link_id": str(item.id)},
            request_id="asset-platform-link",
        )
    )
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/{asset_id}/identifiers",
    response_model=AssetIdentifierRead,
    status_code=status.HTTP_201_CREATED,
)
def create_identifier(
    asset_id: UUID,
    payload: AssetIdentifierCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> AssetIdentifier:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权维护该资产标识")
    if payload.is_primary:
        for item in db.scalars(
            select(AssetIdentifier).where(
                AssetIdentifier.asset_id == asset_id,
                AssetIdentifier.namespace == payload.namespace,
                AssetIdentifier.archived_at.is_(None),
            )
        ):
            item.is_primary = False
    item = AssetIdentifier(asset_id=asset_id, **payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="该平台标识已经绑定其他有效资产") from exc
    db.refresh(item)
    return item


@router.patch("/{asset_id}", response_model=AssetRead)
def patch_asset(
    asset_id: UUID,
    payload: AssetPatch,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> Asset:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权修改该资产")
    changes = payload.model_dump(exclude_unset=True)
    if ("owner_department_id" in changes or "status" in changes) and not can_govern_asset(
        access, asset
    ):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="归属与状态只能由部门负责人或资产管理员修改")
    return asset_service.update(db, asset_id, payload)


@router.post("/{asset_id}/archive", response_model=AssetRead)
def archive_asset(
    asset_id: UUID,
    version: int,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> Asset:
    asset = asset_service.require(db, asset_id)
    if not can_govern_asset(access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权归档该资产")
    return asset_service.archive(db, asset_id, version)


@router.post("/{asset_id}/restore", response_model=AssetRead)
def restore_asset(
    asset_id: UUID,
    version: int,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> Asset:
    asset = asset_repository.get(db, asset_id, include_archived=True)
    if asset is None or not can_govern_asset(access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权恢复该资产")
    return asset_service.restore(db, asset_id, version)


@router.get("/{asset_id}/responsibilities", response_model=list[AssetResponsibilityRead])
def list_responsibilities(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[AssetResponsibilityRead]:
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    return [
        AssetResponsibilityRead.model_validate(item)
        for item in asset_repository.list_responsibilities(db, asset_id)
    ]


@router.post(
    "/{asset_id}/responsibilities",
    response_model=AssetResponsibilityRead,
    status_code=status.HTTP_201_CREATED,
)
def create_responsibility(
    asset_id: UUID,
    payload: AssetResponsibilityCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> AssetResponsibilityRead:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权维护该资产责任关系")
    if payload.role_type in {"responsible", "user"}:
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="负责人和使用人员请通过责任配置接口维护")
    return AssetResponsibilityRead.model_validate(
        asset_service.add_responsibility(db, asset_id, payload)
    )


@router.get("/{asset_id}/relations", response_model=list[AssetRelationRead])
def list_relations(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[AssetRelationRead]:
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    return [
        AssetRelationRead.model_validate(item)
        for item in asset_repository.list_relations(db, asset_id)
    ]


def _relationship_layer(type_code: str | None) -> int:
    if type_code == "registration_identity":
        return 2
    if type_code in {"platform_tenant", "platform_account"}:
        return 4
    return 6


def _relationship_relation_label(relation_type: str) -> str:
    return {
        "registered_by": "注册身份",
        "purchased_via": "购买 / 开通",
        "deployed_on": "部署于",
        "calls": "调用",
        "uses": "使用",
        "depends_on": "依赖",
        "manages": "管理资源",
        "contains": "包含",
        "stored_in": "存储于",
        "replaces": "替代",
    }.get(relation_type.lower(), relation_type)


def _relationship_direction(
    relation_type: str, *, current_is_source: bool
) -> str:
    """Normalize direction from the relation's business meaning.

    Most governed relations point from a consumer to its upstream provider,
    while manages/contains point from a parent to its downstream object.
    Keeping this rule server-side prevents each page from guessing direction
    from source_asset_id alone.
    """
    if relation_type.lower() == "replaces":
        return "peer"
    downstream_source_relations = {"manages", "contains"}
    source_is_downstream = relation_type.lower() in downstream_source_relations
    if current_is_source:
        return "downstream" if source_is_downstream else "upstream"
    return "upstream" if source_is_downstream else "downstream"


@router.get("/{asset_id}/relationship-view", response_model=AssetRelationshipViewRead)
def get_relationship_view(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> AssetRelationshipViewRead:
    """Return one canonical relationship read model for an asset detail page.

    The domain stores different facts in specialized tables: platform and
    tenant structure, registration identities, service purchases, resource
    management, responsibilities, grants, and explicit asset relations.  This
    endpoint joins those facts for display without copying them into a second
    source of truth.
    """
    current = asset_service.require(db, asset_id)
    require_asset_visible(db, access, current)

    assets = list(
        db.scalars(
            select(Asset).where(
                Asset.archived_at.is_(None), asset_visibility_clause(access)
            )
        )
    )
    assets_by_id = {item.id: item for item in assets}
    if current.id not in assets_by_id:
        assets_by_id[current.id] = current
    asset_types = {
        item.id: item
        for item in db.scalars(select(AssetType).where(AssetType.archived_at.is_(None)))
    }
    entities = {
        item.id: item
        for item in db.scalars(select(LegalEntity).where(LegalEntity.archived_at.is_(None)))
    }
    platforms = {
        item.id: item
        for item in db.scalars(select(Platform).where(Platform.archived_at.is_(None)))
    }
    tenants = list(
        db.scalars(
            select(PlatformTenant).where(PlatformTenant.archived_at.is_(None))
        )
    )
    tenant_by_id = {item.id: item for item in tenants}
    tenant_by_asset_id = {item.asset_id: item for item in tenants}
    identity_links = list(
        db.scalars(
            select(PlatformAccountRegistrationIdentity).where(
                PlatformAccountRegistrationIdentity.status == "active",
                PlatformAccountRegistrationIdentity.platform_tenant_id.in_(
                    tenant_by_id.keys()
                )
                if tenant_by_id
                else False,
            )
        )
    )
    platform_links = list(
        db.scalars(
            select(AssetPlatformLink).where(
                AssetPlatformLink.archived_at.is_(None),
                AssetPlatformLink.asset_id.in_(assets_by_id.keys()),
            )
        )
    ) if assets_by_id else []
    service_instances = list(
        db.scalars(
            select(ServiceInstance).where(ServiceInstance.archived_at.is_(None))
        )
    )
    resource_profiles = list(
        db.scalars(
            select(ResourceProfile).where(ResourceProfile.archived_at.is_(None))
        )
    )
    asset_relations = list(
        db.scalars(
            select(AssetRelation).where(
                AssetRelation.archived_at.is_(None),
                (AssetRelation.source_asset_id == asset_id)
                | (AssetRelation.target_asset_id == asset_id),
            )
        )
    )
    responsibilities = list(
        db.scalars(
            select(AssetResponsibility).where(
                AssetResponsibility.asset_id == asset_id,
                AssetResponsibility.archived_at.is_(None),
            )
        )
    )
    account_ids = list(
        db.scalars(
            select(Account.id).where(
                Account.archived_at.is_(None),
                Account.platform_tenant_id == tenant_by_asset_id[asset_id].id,
            )
        )
    ) if asset_id in tenant_by_asset_id else []
    access_grants = list(
        db.scalars(
            select(AccessGrant).where(
                AccessGrant.archived_at.is_(None),
                (AccessGrant.asset_id == asset_id)
                | (AccessGrant.account_id.in_(account_ids) if account_ids else False),
            )
        )
    )
    account_grants = list(
        db.scalars(
            select(AccountGrant).where(
                AccountGrant.archived_at.is_(None),
                AccountGrant.account_id.in_(account_ids),
            )
        )
    ) if account_ids else []
    people = {
        item.id: item
        for item in db.scalars(select(Person).where(Person.archived_at.is_(None)))
    }
    departments = {
        item.id: item
        for item in db.scalars(select(Department).where(Department.archived_at.is_(None)))
    }

    nodes: dict[str, object] = {}
    edges: list[dict[str, object]] = []
    edge_keys: set[tuple[object, ...]] = set()

    def add_asset_node(item: Asset) -> str:
        key = f"asset:{item.id}"
        if key not in nodes:
            asset_type = asset_types.get(item.asset_type_id)
            nodes[key] = {
                "id": key,
                "layer": _relationship_layer(asset_type.code if asset_type else None),
                "label": item.name,
                "object_type": asset_type.name if asset_type else "资产",
                "kind": asset_type.code if asset_type else "asset",
                "asset_id": item.id,
                "status": item.status,
                "href": f"/assets/{item.id}",
            }
        return key

    def add_entity_node(entity_id: UUID) -> str | None:
        item = entities.get(entity_id)
        if item is None:
            return None
        key = f"entity:{item.id}"
        nodes.setdefault(
            key,
            {
                "id": key,
                "layer": 1,
                "label": item.name,
                "object_type": "公司主体",
                "kind": "entity",
                "asset_id": None,
                "status": item.status,
                "href": f"/directory/entity/{item.id}",
            },
        )
        return key

    def add_platform_node(platform_id: UUID) -> str | None:
        item = platforms.get(platform_id)
        if item is None:
            return None
        key = f"platform:{item.id}"
        nodes.setdefault(
            key,
            {
                "id": key,
                "layer": 3,
                "label": item.name,
                "object_type": "平台",
                "kind": "platform",
                "asset_id": None,
                "status": item.review_status,
                "href": f"/directory/platform/{item.id}",
            },
        )
        return key

    def add_subject_node(person_id: UUID | None, department_id: UUID | None) -> str | None:
        if person_id is not None and person_id in people:
            item = people[person_id]
            key = f"person:{item.id}"
            nodes.setdefault(
                key,
                {
                    "id": key,
                    "layer": 5,
                    "label": item.display_name,
                    "object_type": "人员",
                    "kind": "person",
                    "asset_id": None,
                    "status": item.employment_status,
                    "href": "/organization",
                },
            )
            return key
        if department_id is not None and department_id in departments:
            item = departments[department_id]
            key = f"department:{item.id}"
            nodes.setdefault(
                key,
                {
                    "id": key,
                    "layer": 5,
                    "label": item.name,
                    "object_type": "部门",
                    "kind": "department",
                    "asset_id": None,
                    "status": item.status,
                    "href": "/organization",
                },
            )
            return key
        return None

    def add_edge(
        *,
        edge_id: str,
        source: str,
        target: str,
        label: str,
        section: str,
        direction: str,
        source_model: str,
        editable: bool = False,
        relation_id: UUID | None = None,
        note: str | None = None,
        edit_kind: str | None = None,
        edit_target_id: UUID | None = None,
        dedupe_key: tuple[object, ...] | None = None,
    ) -> None:
        key = dedupe_key or (source, target, label, section)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "label": label,
                "section": section,
                "direction": direction,
                "source_model": source_model,
                "editable": editable,
                "relation_id": relation_id,
                "note": note,
                "edit_kind": edit_kind,
                "edit_target_id": edit_target_id,
            }
        )

    current_key = add_asset_node(current)

    # Structural ownership and platform facts are canonical fields, not manual edges.
    if current.legal_entity_id:
        entity_key = add_entity_node(current.legal_entity_id)
        if entity_key:
            add_edge(
                edge_id=f"asset-entity:{current.id}",
                source=entity_key,
                target=current_key,
                label="所属主体",
                section="structure",
                direction="upstream",
                source_model="Asset.legal_entity_id",
                editable=True,
                edit_kind="legal_entity",
                edit_target_id=current.legal_entity_id,
                dedupe_key=("legal_entity", current.id),
            )

    tenant = tenant_by_asset_id.get(current.id)
    if tenant:
        platform_key = add_platform_node(tenant.platform_id)
        if platform_key:
            add_edge(
                edge_id=f"tenant-platform:{tenant.id}",
                source=platform_key,
                target=current_key,
                label="所属平台",
                section="structure",
                direction="upstream",
                source_model="PlatformTenant.platform_id",
                editable=True,
                edit_kind="platform",
                edit_target_id=tenant.platform_id,
                dedupe_key=("platform", current.id, tenant.platform_id),
            )
        for link in identity_links:
            if link.platform_tenant_id != tenant.id:
                continue
            identity = assets_by_id.get(link.registration_identity_asset_id)
            if identity is None:
                continue
            identity_key = add_asset_node(identity)
            add_edge(
                edge_id=f"tenant-identity:{link.id}",
                source=identity_key,
                target=current_key,
                label="注册身份",
                section="structure",
                direction="upstream",
                source_model="PlatformAccountRegistrationIdentity",
                editable=True,
                edit_kind="registration_identity",
                edit_target_id=identity.id,
                dedupe_key=("registration_identity", frozenset((identity.id, current.id))),
            )

    for link in platform_links:
        if link.asset_id != current.id:
            continue
        platform_key = add_platform_node(link.platform_id)
        if platform_key:
            add_edge(
                edge_id=f"asset-platform:{link.id}",
                source=platform_key,
                target=current_key,
                label={
                    "registered_on": "登记于平台",
                    "uses": "关联平台",
                    "provided_by": "由平台提供",
                }.get(link.relation_type.lower(), link.relation_type),
                section="structure",
                direction="upstream",
                source_model="AssetPlatformLink",
                dedupe_key=("platform", current.id, link.platform_id, link.relation_type.lower()),
            )

    # Canonical purchase/management records create business edges in the view.
    for instance in service_instances:
        service_asset = assets_by_id.get(instance.asset_id)
        if service_asset is None:
            continue
        if instance.purchase_tenant_asset_id:
            tenant_asset = assets_by_id.get(instance.purchase_tenant_asset_id)
            if tenant_asset is None:
                continue
            source_key = add_asset_node(tenant_asset)
            target_key = add_asset_node(service_asset)
            if current.id in {tenant_asset.id, service_asset.id}:
                add_edge(
                    edge_id=f"service-purchase:{instance.id}",
                    source=source_key,
                    target=target_key,
                    label="购买 / 开通",
                    section="business",
                    direction="downstream" if current.id == tenant_asset.id else "upstream",
                    source_model="ServiceInstance.purchase_tenant_asset_id",
                    dedupe_key=(
                        "canonical_business",
                        "purchased_via",
                        frozenset((tenant_asset.id, service_asset.id)),
                    ),
                )
        elif instance.purchase_platform_id:
            platform_key = add_platform_node(instance.purchase_platform_id)
            target_key = add_asset_node(service_asset)
            if platform_key and current.id == service_asset.id:
                add_edge(
                    edge_id=f"service-platform:{instance.id}",
                    source=platform_key,
                    target=target_key,
                    label="购买 / 开通",
                    section="business",
                    direction="upstream",
                    source_model="ServiceInstance.purchase_platform_id",
                    dedupe_key=(
                        "purchase_platform",
                        instance.purchase_platform_id,
                        service_asset.id,
                    ),
                )

    for profile in resource_profiles:
        resource_asset = assets_by_id.get(profile.asset_id)
        tenant_row = tenant_by_id.get(profile.managed_under_account_id)
        if resource_asset is not None and tenant_row is not None:
            tenant_asset = assets_by_id.get(tenant_row.asset_id)
            if tenant_asset is not None and current.id in {tenant_asset.id, resource_asset.id}:
                add_edge(
                    edge_id=f"resource-manager:{profile.id}",
                    source=add_asset_node(tenant_asset),
                    target=add_asset_node(resource_asset),
                    label="管理资源",
                    section="business",
                    direction="downstream" if current.id == tenant_asset.id else "upstream",
                    source_model="ResourceProfile.managed_under_account_id",
                    dedupe_key=(
                        "canonical_business",
                        "manages",
                        frozenset((tenant_asset.id, resource_asset.id)),
                    ),
                )
        parent = assets_by_id.get(profile.parent_resource_asset_id)
        if (
            parent is not None
            and resource_asset is not None
            and current.id in {parent.id, resource_asset.id}
        ):
            add_edge(
                edge_id=f"resource-parent:{profile.id}",
                source=add_asset_node(parent),
                target=add_asset_node(resource_asset),
                label="包含",
                section="business",
                direction="downstream" if current.id == parent.id else "upstream",
                source_model="ResourceProfile.parent_resource_asset_id",
                dedupe_key=(
                    "canonical_business",
                    "contains",
                    frozenset((parent.id, resource_asset.id)),
                ),
            )

    for relation in asset_relations:
        source_asset = assets_by_id.get(relation.source_asset_id)
        target_asset = assets_by_id.get(relation.target_asset_id)
        if source_asset is None or target_asset is None:
            continue
        relation_type = relation.relation_type.lower()
        label = _relationship_relation_label(relation_type)
        if relation_type == "registered_by":
            dedupe_key = ("registration_identity", frozenset((source_asset.id, target_asset.id)))
            section = "structure"
        elif relation_type in {"purchased_via", "manages", "contains"}:
            dedupe_key = (
                "canonical_business",
                relation_type,
                frozenset((source_asset.id, target_asset.id)),
            )
            section = "business"
        else:
            dedupe_key = ("asset_relation", relation.id)
            section = "business"
        add_edge(
            edge_id=f"asset-relation:{relation.id}",
            source=add_asset_node(source_asset),
            target=add_asset_node(target_asset),
            label=label,
            section=section,
            direction=_relationship_direction(
                relation_type, current_is_source=relation.source_asset_id == current.id
            ),
            source_model="AssetRelation",
            editable=True,
            relation_id=relation.id,
            note=relation.note,
            dedupe_key=dedupe_key,
        )

    for item in responsibilities:
        subject_key = add_subject_node(item.person_id, item.department_id)
        if subject_key:
            add_edge(
                edge_id=f"responsibility:{item.id}",
                source=subject_key,
                target=current_key,
                label={"responsible": "负责人", "user": "使用人员"}.get(
                    item.role_type, item.role_type
                ),
                section="responsibility",
                direction="responsibility",
                source_model="AssetResponsibility",
                dedupe_key=("responsibility", item.id),
            )
    for item in access_grants:
        subject_key = add_subject_node(item.person_id, item.department_id)
        if subject_key:
            add_edge(
                edge_id=f"access-grant:{item.id}",
                source=subject_key,
                target=current_key,
                label="账号 / 资产授权",
                section="responsibility",
                direction="responsibility",
                source_model="AccessGrant",
                dedupe_key=("access_grant", item.id),
                note=item.note,
            )
    for item in account_grants:
        subject_key = add_subject_node(item.person_id, None)
        if subject_key:
            add_edge(
                edge_id=f"account-grant:{item.id}",
                source=subject_key,
                target=current_key,
                label="账号权限",
                section="responsibility",
                direction="responsibility",
                source_model="AccountGrant",
                dedupe_key=("account_grant", item.id),
            )

    return AssetRelationshipViewRead(
        current_node=nodes[current_key],
        nodes=list(nodes.values()),
        edges=edges,
    )


@router.put(
    "/{asset_id}/relationship-links/{link_kind}",
    response_model=AssetRelationshipViewRead,
)
def update_relationship_link(
    asset_id: UUID,
    link_kind: str,
    payload: RelationshipLinkUpdate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> AssetRelationshipViewRead:
    """Update a canonical relationship through its owning domain model."""
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        raise HTTPException(status_code=403, detail="无权维护该资产关联")

    if link_kind == "legal_entity":
        entity = db.get(LegalEntity, payload.target_id)
        if entity is None or entity.archived_at is not None:
            raise HTTPException(status_code=422, detail="所选公司主体不存在")
        asset.legal_entity_id = entity.id
        tenant = db.scalar(
            select(PlatformTenant).where(
                PlatformTenant.asset_id == asset.id,
                PlatformTenant.archived_at.is_(None),
            )
        )
        if tenant is not None:
            tenant.legal_entity_id = entity.id
    elif link_kind == "platform":
        tenant = db.scalar(
            select(PlatformTenant).where(
                PlatformTenant.asset_id == asset.id,
                PlatformTenant.archived_at.is_(None),
            )
        )
        if tenant is None:
            raise HTTPException(status_code=422, detail="当前资产不是公司平台账号")
        platform = db.get(Platform, payload.target_id)
        if platform is None or platform.archived_at is not None:
            raise HTTPException(status_code=422, detail="所选平台不存在")
        tenant.platform_id = platform.id
    elif link_kind == "registration_identity":
        tenant = db.scalar(
            select(PlatformTenant).where(
                PlatformTenant.asset_id == asset.id,
                PlatformTenant.archived_at.is_(None),
            )
        )
        identity = db.get(Asset, payload.target_id)
        identity_type = db.scalar(
            select(AssetType).where(AssetType.code == "registration_identity")
        )
        if tenant is None:
            raise HTTPException(status_code=422, detail="当前资产不是公司平台账号")
        if (
            identity is None
            or identity.archived_at is not None
            or identity_type is None
            or identity.asset_type_id != identity_type.id
        ):
            raise HTTPException(status_code=422, detail="所选对象不是有效的注册身份")
        require_asset_visible(db, access, identity)
        if identity.legal_entity_id != asset.legal_entity_id:
            raise HTTPException(status_code=422, detail="注册身份与平台账号必须属于同一公司")
        active_link = db.scalar(
            select(PlatformAccountRegistrationIdentity).where(
                PlatformAccountRegistrationIdentity.platform_tenant_id == tenant.id,
                PlatformAccountRegistrationIdentity.status == "active",
            )
        )
        if active_link is None or active_link.registration_identity_asset_id != identity.id:
            if active_link is not None:
                active_link.status = "inactive"
            db.add(
                PlatformAccountRegistrationIdentity(
                    platform_tenant_id=tenant.id,
                    registration_identity_asset_id=identity.id,
                    role="primary",
                    status="active",
                )
            )
            old_relations = db.scalars(
                select(AssetRelation).where(
                    AssetRelation.archived_at.is_(None),
                    AssetRelation.relation_type.in_(["registered_by", "REGISTERED_BY"]),
                    (
                        (AssetRelation.source_asset_id == asset.id)
                        | (AssetRelation.target_asset_id == asset.id)
                    ),
                )
            )
            for relation in old_relations:
                relation.archived_at = datetime.now(UTC)
            db.add(
                AssetRelation(
                    source_asset_id=asset.id,
                    target_asset_id=identity.id,
                    relation_type="registered_by",
                    source_type="relationship_view",
                )
            )
    else:
        raise HTTPException(status_code=422, detail="不支持修改该类关联")

    db.commit()
    return get_relationship_view(asset_id, db, access)


@router.get("/{asset_id}/relation-neighborhood", response_model=list[AssetRelationRead])
def list_relation_neighborhood(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[AssetRelationRead]:
    """List both upstream and downstream assets for the relationship view."""
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    visible: list[AssetRelationRead] = []
    for item in asset_repository.list_relation_neighborhood(db, asset_id):
        other_id = (
            item.target_asset_id if item.source_asset_id == asset_id else item.source_asset_id
        )
        other = asset_service.require(db, other_id)
        if db.scalar(select(Asset.id).where(Asset.id == other.id, asset_visibility_clause(access))):
            visible.append(AssetRelationRead.model_validate(item))
    return visible


@router.get("/{asset_id}/relation-options", response_model=list[RelationOptionRead])
def list_relation_options(
    asset_id: UUID,
    direction: str = Query(pattern="^(upstream|downstream|peer)$"),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[RelationOptionRead]:
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    current_type = db.get(AssetType, asset.asset_type_id)
    if current_type is None:
        return []
    definitions = list(
        db.scalars(
            select(RelationDefinition).where(
                RelationDefinition.archived_at.is_(None),
                RelationDefinition.category == ("peer" if direction == "peer" else "upstream"),
                (
                    RelationDefinition.source_type_code.in_([current_type.code, "*"])
                    if direction in {"upstream", "peer"}
                    else RelationDefinition.target_type_code.in_([current_type.code, "*"])
                ),
            )
        )
    )
    grouped: dict[tuple[str, str], set[str]] = {}
    for definition in definitions:
        label = (
            definition.forward_label
            if direction in {"upstream", "peer"}
            else definition.inverse_label
        )
        target_code = (
            definition.target_type_code
            if direction in {"upstream", "peer"}
            else definition.source_type_code
        )
        grouped.setdefault((definition.relation_type, label), set()).add(target_code)
    return [
        RelationOptionRead(
            relation_type=relation_type,
            label=label,
            target_type_codes=sorted(target_codes),
            direction=direction,
        )
        for (relation_type, label), target_codes in grouped.items()
    ]


@router.post(
    "/{asset_id}/relations",
    response_model=AssetRelationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_relation(
    asset_id: UUID,
    payload: AssetRelationCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> AssetRelationRead:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权维护该资产关系")
    return AssetRelationRead.model_validate(asset_service.add_relation(db, asset_id, payload))


@router.post(
    "/{asset_id}/relations/intelligent",
    response_model=AssetRelationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_intelligent_relation(
    asset_id: UUID,
    payload: IntelligentRelationCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> AssetRelationRead:
    current = asset_service.require(db, asset_id)
    related = asset_service.require(db, payload.related_asset_id)
    require_asset_visible(db, access, current)
    require_asset_visible(db, access, related)
    if not can_manage_asset(db, access, current) or not can_manage_asset(db, access, related):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="需要同时拥有两端资产的维护权限")
    source, target = (
        (current, related)
        if payload.direction in {"upstream", "peer"}
        else (related, current)
    )
    source_type = db.get(AssetType, source.asset_type_id)
    target_type = db.get(AssetType, target.asset_type_id)
    definition = db.scalar(
        select(RelationDefinition)
        .where(
            RelationDefinition.relation_type == payload.relation_type.upper(),
            RelationDefinition.source_type_code.in_([source_type.code, "*"]),
            RelationDefinition.target_type_code.in_([target_type.code, "*"]),
            RelationDefinition.archived_at.is_(None),
        )
        .order_by(
            (RelationDefinition.source_type_code != "*").desc(),
            (RelationDefinition.target_type_code != "*").desc(),
        )
    )
    if definition is None or (
        payload.direction == "peer" and definition.category != "peer"
    ) or (payload.direction != "peer" and definition.category != "upstream"):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="当前资产类型不支持该关系")
    if definition.source_max_count is not None:
        existing_count = db.scalar(
            select(func.count()).where(
                AssetRelation.source_asset_id == source.id,
                AssetRelation.relation_type == definition.relation_type,
                AssetRelation.archived_at.is_(None),
            )
        )
        if existing_count >= definition.source_max_count:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail="该资产已达到此类上游关系数量上限")
    item = AssetRelation(
        source_asset_id=source.id,
        target_asset_id=target.id,
        relation_type=definition.relation_type,
        source_type="manual",
        note=payload.note,
    )
    db.add(item)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="该关系已存在") from exc
    db.refresh(item)
    return AssetRelationRead.model_validate(item)


@router.post("/{asset_id}/responsibilities/{responsibility_id}/archive")
def archive_responsibility(
    asset_id: UUID,
    responsibility_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> dict[str, str]:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权维护该资产责任关系")
    asset_service.archive_responsibility(db, asset_id, responsibility_id)
    return {"status": "archived"}


@router.post("/{asset_id}/relations/{relation_id}/archive")
def archive_relation(
    asset_id: UUID,
    relation_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> dict[str, str]:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权维护该资产关系")
    asset_service.archive_relation(db, asset_id, relation_id)
    return {"status": "archived"}


@router.get("/{asset_id}/field-values", response_model=list[AssetFieldValueRead])
def list_field_values(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[AssetFieldValue]:
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    return list(db.scalars(select(AssetFieldValue).where(AssetFieldValue.asset_id == asset_id)))


@router.put("/{asset_id}/field-values", response_model=list[AssetFieldValueRead])
def save_field_values(
    asset_id: UUID,
    payload: list[AssetFieldValueInput],
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[AssetFieldValue]:
    asset = asset_service.require(db, asset_id)
    if not can_manage_asset(db, access, asset):
        from fastapi import HTTPException

        raise HTTPException(status_code=403, detail="无权维护该资产扩展字段")
    allowed = {
        item.id
        for item in db.scalars(
            select(AssetFieldDefinition).where(
                AssetFieldDefinition.asset_type_id == asset.asset_type_id
            )
        )
    }
    if any(row.field_definition_id not in allowed for row in payload):
        from fastapi import HTTPException

        raise HTTPException(status_code=422, detail="包含未定义的扩展字段")
    saved: list[AssetFieldValue] = []
    for row in payload:
        item = db.scalar(
            select(AssetFieldValue).where(
                AssetFieldValue.asset_id == asset_id,
                AssetFieldValue.field_definition_id == row.field_definition_id,
            )
        )
        if item is None:
            item = AssetFieldValue(
                asset_id=asset_id,
                field_definition_id=row.field_definition_id,
                value={"value": row.value},
            )
            db.add(item)
        else:
            item.value = {"value": row.value}
        saved.append(item)
    db.commit()
    for item in saved:
        db.refresh(item)
    return saved


@router.get("/{asset_id}/assignment", response_model=AssetAssignmentRead)
def get_assignment(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> AssetAssignmentRead:
    asset = asset_service.require(db, asset_id)
    require_asset_visible(db, access, asset)
    rows = asset_repository.list_responsibilities(db, asset_id)
    responsible_person_id = next(
        (row.person_id for row in rows if row.role_type == "responsible"), None
    ) or next(
        (row.person_id for row in rows if row.role_type == "proposed_responsible"), None
    )
    user_role = "user" if any(row.role_type == "user" for row in rows) else "proposed_user"
    return AssetAssignmentRead(
        owner_department_id=asset.owner_department_id,
        ownership_scope=asset.ownership_scope,
        responsible_person_id=responsible_person_id,
        user_person_ids=[
            row.person_id for row in rows if row.role_type == user_role and row.person_id
        ],
    )


@router.put("/{asset_id}/assignment", response_model=AssetAssignmentRead)
def save_assignment(
    asset_id: UUID,
    payload: AssetAssignmentWrite,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> AssetAssignmentRead:
    from fastapi import HTTPException

    asset = asset_service.require(db, asset_id)
    if asset.version != payload.version:
        raise HTTPException(status_code=409, detail="记录已被其他用户修改")
    existing = asset_repository.list_responsibilities(db, asset_id)
    old_responsible = next(
        (row.person_id for row in existing if row.role_type == "responsible"), None
    )
    governance_change = (
        payload.owner_department_id != asset.owner_department_id
        or payload.ownership_scope != asset.ownership_scope
        or payload.responsible_person_id != old_responsible
    )
    if governance_change:
        if not can_govern_asset(access, asset):
            raise HTTPException(
                status_code=403, detail="归属和负责人只能由部门负责人或资产管理员调整"
            )
    elif not can_manage_asset(db, access, asset):
        raise HTTPException(status_code=403, detail="无权调整使用人员")

    people_ids = {payload.responsible_person_id, *payload.user_person_ids}
    people = list(
        db.scalars(select(Person).where(Person.id.in_(people_ids), Person.archived_at.is_(None)))
    )
    if len({person.id for person in people}) != len(people_ids) or (
        asset.legal_entity_id is not None
        and any(person.legal_entity_id != asset.legal_entity_id for person in people)
    ):
        raise HTTPException(status_code=422, detail="负责人和使用人员必须是当前公司在职成员")
    ownership_scope = payload.ownership_scope or (
        "department" if payload.owner_department_id else "company"
    )
    if ownership_scope not in {"pending", "company", "department"}:
        raise HTTPException(status_code=422, detail="归属范围无效")
    if ownership_scope == "department" and not payload.owner_department_id:
        raise HTTPException(status_code=422, detail="部门级资产必须选择归属部门")
    if ownership_scope != "department" and payload.owner_department_id:
        raise HTTPException(status_code=422, detail="只有部门级资产可以设置归属部门")
    if payload.owner_department_id:
        department = db.get(Department, payload.owner_department_id)
        if (
            asset.legal_entity_id is None
            or
            department is None
            or department.legal_entity_id != asset.legal_entity_id
            or department.archived_at is not None
        ):
            raise HTTPException(status_code=422, detail="归属部门不属于当前公司")

    now = datetime.now(UTC)
    for row in existing:
        if row.role_type in {"responsible", "user", "proposed_responsible", "proposed_user"}:
            row.archived_at = now
    db.flush()
    db.add(
        AssetResponsibility(
            asset_id=asset.id,
            person_id=payload.responsible_person_id,
            role_type="responsible",
            is_primary=True,
        )
    )
    for person_id in dict.fromkeys(payload.user_person_ids):
        if person_id != payload.responsible_person_id:
            db.add(
                AssetResponsibility(
                    asset_id=asset.id, person_id=person_id, role_type="user", is_primary=False
                )
            )
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="asset.assignment.confirm",
            object_type="asset",
            object_id=asset.id,
            before_data={
                "owner_department_id": (
                    str(asset.owner_department_id) if asset.owner_department_id else None
                ),
                "ownership_scope": asset.ownership_scope,
                "responsible_person_id": str(old_responsible) if old_responsible else None,
            },
            after_data={
                "owner_department_id": (
                    str(payload.owner_department_id) if payload.owner_department_id else None
                ),
                "ownership_scope": ownership_scope,
                "responsible_person_id": str(payload.responsible_person_id),
                "user_person_ids": [str(person_id) for person_id in payload.user_person_ids],
                "review_status": "approved",
            },
            request_id="asset-assignment",
        )
    )
    asset.owner_department_id = payload.owner_department_id
    asset.ownership_scope = ownership_scope
    asset.status = "active"
    asset.review_status = "approved"
    asset.confirmed_by_person_id = access.person_id
    asset.confirmed_at = now
    asset.version += 1
    db.commit()
    return AssetAssignmentRead(
        owner_department_id=asset.owner_department_id,
        ownership_scope=asset.ownership_scope,
        responsible_person_id=payload.responsible_person_id,
        user_person_ids=[
            person_id
            for person_id in dict.fromkeys(payload.user_person_ids)
            if person_id != payload.responsible_person_id
        ],
    )
