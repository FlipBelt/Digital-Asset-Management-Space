from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.access import (
    AccessContext,
    asset_visibility_clause,
    can_manage_asset,
    get_access_context,
    require_asset_visible,
    require_global_manager,
)
from app.db.session import get_db
from app.models import (
    Account,
    Asset,
    AssetPlatformLink,
    AuditLog,
    CredentialReference,
    InternalSystemProfile,
    MetricDefinition,
    MetricSample,
    Platform,
    PlatformTenant,
    Provider,
    ServiceInstance,
    ServiceProduct,
)
from app.schemas.assets import AssetRelationshipViewRead
from app.schemas.inventory import (
    AccountCreate,
    AccountRead,
    CredentialReferenceCreate,
    CredentialReferenceRead,
    InternalSystemProfileRead,
    InternalSystemProfileUpsert,
    MetricDefinitionRead,
    MetricSampleCreate,
    MetricSampleRead,
    PlatformCreate,
    PlatformPatch,
    PlatformRead,
    PlatformTenantCreate,
    PlatformTenantRead,
    ProviderCreate,
    ProviderRead,
    ServiceInstanceCreate,
    ServiceInstanceRead,
    ServiceProductCreate,
    ServiceProductRead,
)

router = APIRouter(tags=["inventory"])


def visible_asset_ids(access: AccessContext):
    return select(Asset.id).where(Asset.archived_at.is_(None), asset_visibility_clause(access))


def require_visible_asset(db: Session, access: AccessContext, asset_id: UUID) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None or asset.archived_at is not None:
        raise HTTPException(status_code=404, detail="资产不存在")
    require_asset_visible(db, access, asset)
    return asset


def require_manageable_asset(db: Session, access: AccessContext, asset_id: UUID) -> Asset:
    asset = require_visible_asset(db, access, asset_id)
    if not can_manage_asset(db, access, asset):
        raise HTTPException(status_code=403, detail="无权维护该资产")
    return asset


def commit(db: Session, item, action: str, object_type: str):
    try:
        db.flush()
        object_id = item.id
        db.add(
            AuditLog(
                action=action,
                object_type=object_type,
                object_id=object_id,
                after_data={"id": str(object_id)},
                request_id="local-development",
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="记录重复或关联数据无效") from exc
    db.refresh(item)
    return item


@router.get("/providers", response_model=list[ProviderRead])
def list_providers(db: Session = Depends(get_db)) -> list[Provider]:
    return list(
        db.scalars(select(Provider).where(Provider.archived_at.is_(None)).order_by(Provider.name))
    )


@router.post("/providers", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
def create_provider(
    payload: ProviderCreate,
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_global_manager),
) -> Provider:
    item = Provider(**payload.model_dump())
    db.add(item)
    return commit(db, item, "provider.create", "provider")


@router.get("/platforms", response_model=list[PlatformRead])
def list_platforms(db: Session = Depends(get_db)) -> list[Platform]:
    return list(
        db.scalars(select(Platform).where(Platform.archived_at.is_(None)).order_by(Platform.name))
    )


@router.post("/platforms", response_model=PlatformRead, status_code=status.HTTP_201_CREATED)
def create_platform(
    payload: PlatformCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> Platform:
    data = payload.model_dump(exclude={"review_status", "submitted_by_person_id"})
    item = Platform(
        **data,
        review_status="pending_review",
        submitted_by_person_id=access.person_id,
    )
    db.add(item)
    return commit(db, item, "platform.create", "platform")


@router.patch("/platforms/{platform_id}", response_model=PlatformRead)
def update_platform(
    platform_id: UUID,
    payload: PlatformPatch,
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_global_manager),
) -> Platform:
    item = db.get(Platform, platform_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(status_code=404, detail="平台目录对象不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    return commit(db, item, "platform.update", "platform")


@router.get("/platforms/{platform_id}/relationship-view", response_model=AssetRelationshipViewRead)
def get_platform_relationship_view(
    platform_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> AssetRelationshipViewRead:
    """Build the L3 directory relationship view from canonical model facts."""
    platform = db.get(Platform, platform_id)
    if platform is None or platform.archived_at is not None:
        raise HTTPException(status_code=404, detail="平台目录对象不存在")

    visible_assets = list(
        db.scalars(
            select(Asset).where(
                Asset.archived_at.is_(None), asset_visibility_clause(access)
            )
        )
    )
    assets_by_id = {item.id: item for item in visible_assets}
    nodes: dict[str, dict] = {
        f"platform:{platform.id}": {
            "id": f"platform:{platform.id}",
            "layer": 3,
            "label": platform.name,
            "object_type": "平台",
            "kind": "platform",
            "asset_id": None,
            "status": platform.review_status,
            "href": f"/directory/platform/{platform.id}",
        }
    }
    edges: list[dict] = []
    seen: set[tuple[object, ...]] = set()
    current_key = f"platform:{platform.id}"

    def add_asset_node(item: Asset) -> str:
        key = f"asset:{item.id}"
        if key not in nodes:
            nodes[key] = {
                "id": key,
                "layer": 6,
                "label": item.name,
                "object_type": "资产",
                "kind": "asset",
                "asset_id": item.id,
                "status": item.status,
                "href": f"/assets/{item.id}",
            }
        return key

    def add_edge(
        *, edge_id: str, source: str, target: str, label: str, section: str,
        direction: str, source_model: str, note: str | None = None,
    ) -> None:
        key = (source, target, label, section)
        if key in seen:
            return
        seen.add(key)
        edges.append(
            {
                "id": edge_id,
                "source": source,
                "target": target,
                "label": label,
                "section": section,
                "direction": direction,
                "source_model": source_model,
                "editable": False,
                "relation_id": None,
                "note": note,
                "edit_kind": None,
                "edit_target_id": None,
            }
        )

    tenants = list(
        db.scalars(
            select(PlatformTenant).where(
                PlatformTenant.platform_id == platform.id,
                PlatformTenant.archived_at.is_(None),
                PlatformTenant.asset_id.in_(assets_by_id),
            )
        )
    ) if assets_by_id else []
    for tenant in tenants:
        tenant_asset = assets_by_id.get(tenant.asset_id)
        if tenant_asset is not None:
            add_edge(
                edge_id=f"platform-tenant:{tenant.id}",
                source=current_key,
                target=add_asset_node(tenant_asset),
                label="企业平台账号",
                section="structure",
                direction="downstream",
                source_model="PlatformTenant.platform_id",
            )

    links = list(
        db.scalars(
            select(AssetPlatformLink).where(
                AssetPlatformLink.platform_id == platform.id,
                AssetPlatformLink.archived_at.is_(None),
                AssetPlatformLink.asset_id.in_(assets_by_id),
            )
        )
    ) if assets_by_id else []
    link_labels = {
        "registered_on": "登记于平台",
        "uses": "关联平台",
        "provided_by": "由平台提供",
    }
    for link in links:
        linked_asset = assets_by_id.get(link.asset_id)
        if linked_asset is not None:
            add_edge(
                edge_id=f"platform-asset:{link.id}",
                source=add_asset_node(linked_asset),
                target=current_key,
                label=link_labels.get(link.relation_type.lower(), link.relation_type),
                section="structure",
                direction="downstream",
                source_model="AssetPlatformLink",
                note=link.note,
            )

    instances = list(
        db.scalars(
            select(ServiceInstance).where(
                ServiceInstance.purchase_platform_id == platform.id,
                ServiceInstance.archived_at.is_(None),
                ServiceInstance.asset_id.in_(assets_by_id),
            )
        )
    ) if assets_by_id else []
    for instance in instances:
        service_asset = assets_by_id.get(instance.asset_id)
        if service_asset is not None:
            add_edge(
                edge_id=f"platform-service:{instance.id}",
                source=current_key,
                target=add_asset_node(service_asset),
                label="购买 / 开通",
                section="business",
                direction="downstream",
                source_model="ServiceInstance.purchase_platform_id",
            )

    return AssetRelationshipViewRead(
        current_node=nodes[current_key],
        nodes=list(nodes.values()),
        edges=edges,
    )


@router.get("/platform-tenants", response_model=list[PlatformTenantRead])
def list_platform_tenants(
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[PlatformTenant]:
    return list(
        db.scalars(
            select(PlatformTenant)
            .where(
                PlatformTenant.archived_at.is_(None),
                PlatformTenant.asset_id.in_(visible_asset_ids(access)),
            )
            .order_by(PlatformTenant.created_at.desc())
        )
    )


@router.post(
    "/platform-tenants", response_model=PlatformTenantRead, status_code=status.HTTP_201_CREATED
)
def create_platform_tenant(
    payload: PlatformTenantCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> PlatformTenant:
    require_manageable_asset(db, access, payload.asset_id)
    item = PlatformTenant(**payload.model_dump())
    db.add(item)
    return commit(db, item, "platform_tenant.create", "platform_tenant")


@router.get("/accounts", response_model=list[AccountRead])
def list_accounts(
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[Account]:
    return list(
        db.scalars(
            select(Account)
            .where(
                Account.archived_at.is_(None),
                Account.asset_id.in_(visible_asset_ids(access)),
            )
            .order_by(Account.created_at.desc())
        )
    )


@router.post("/accounts", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    payload: AccountCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> Account:
    require_manageable_asset(db, access, payload.asset_id)
    data = payload.model_dump()
    item = Account(**data, normalized_login_identifier=payload.login_identifier.strip().lower())
    db.add(item)
    return commit(db, item, "account.create", "account")


@router.get("/credential-references", response_model=list[CredentialReferenceRead])
def list_credential_references(
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[CredentialReference]:
    visible_accounts = select(Account.id).where(Account.asset_id.in_(visible_asset_ids(access)))
    return list(
        db.scalars(
            select(CredentialReference)
            .where(
                CredentialReference.archived_at.is_(None),
                or_(
                    CredentialReference.asset_id.in_(visible_asset_ids(access)),
                    CredentialReference.account_id.in_(visible_accounts),
                ),
            )
            .order_by(CredentialReference.created_at.desc())
        )
    )


@router.post(
    "/credential-references",
    response_model=CredentialReferenceRead,
    status_code=status.HTTP_201_CREATED,
)
def create_credential_reference(
    payload: CredentialReferenceCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> CredentialReference:
    asset_id = payload.asset_id
    if not asset_id and payload.account_id:
        account = db.get(Account, payload.account_id)
        asset_id = account.asset_id if account else None
    if not asset_id:
        raise HTTPException(status_code=422, detail="凭据引用必须关联可管理的账号或资产")
    require_manageable_asset(db, access, asset_id)
    item = CredentialReference(**payload.model_dump())
    db.add(item)
    return commit(db, item, "credential_reference.create", "credential_reference")


@router.get("/service-products", response_model=list[ServiceProductRead])
def list_service_products(db: Session = Depends(get_db)) -> list[ServiceProduct]:
    return list(
        db.scalars(
            select(ServiceProduct)
            .where(ServiceProduct.archived_at.is_(None))
            .order_by(ServiceProduct.name)
        )
    )


@router.post(
    "/service-products", response_model=ServiceProductRead, status_code=status.HTTP_201_CREATED
)
def create_service_product(
    payload: ServiceProductCreate,
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_global_manager),
) -> ServiceProduct:
    item = ServiceProduct(**payload.model_dump())
    db.add(item)
    return commit(db, item, "service_product.create", "service_product")


@router.get("/service-instances", response_model=list[ServiceInstanceRead])
def list_service_instances(
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[ServiceInstance]:
    return list(
        db.scalars(
            select(ServiceInstance)
            .where(
                ServiceInstance.archived_at.is_(None),
                ServiceInstance.asset_id.in_(visible_asset_ids(access)),
            )
            .order_by(ServiceInstance.created_at.desc())
        )
    )


@router.post(
    "/service-instances", response_model=ServiceInstanceRead, status_code=status.HTTP_201_CREATED
)
def create_service_instance(
    payload: ServiceInstanceCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> ServiceInstance:
    require_manageable_asset(db, access, payload.asset_id)
    item = ServiceInstance(**payload.model_dump())
    db.add(item)
    return commit(db, item, "service_instance.create", "service_instance")


@router.get("/metric-definitions", response_model=list[MetricDefinitionRead])
def list_metric_definitions(db: Session = Depends(get_db)) -> list[MetricDefinition]:
    return list(
        db.scalars(
            select(MetricDefinition)
            .where(MetricDefinition.archived_at.is_(None))
            .order_by(MetricDefinition.display_name)
        )
    )


@router.get(
    "/service-instances/{service_instance_id}/metrics", response_model=list[MetricSampleRead]
)
def list_metrics(
    service_instance_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> list[MetricSample]:
    instance = db.get(ServiceInstance, service_instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="服务实例不存在")
    require_visible_asset(db, access, instance.asset_id)
    return list(
        db.scalars(
            select(MetricSample)
            .where(MetricSample.service_instance_id == service_instance_id)
            .order_by(MetricSample.collected_at.desc())
        )
    )


@router.post(
    "/service-instances/{service_instance_id}/metrics",
    response_model=MetricSampleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_metric(
    service_instance_id: UUID,
    payload: MetricSampleCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> MetricSample:
    instance = db.get(ServiceInstance, service_instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="服务实例不存在")
    require_manageable_asset(db, access, instance.asset_id)
    item = MetricSample(
        service_instance_id=service_instance_id,
        **payload.model_dump(exclude={"collected_at"}),
        collected_at=payload.collected_at or datetime.now(UTC),
    )
    db.add(item)
    return commit(db, item, "metric_sample.create", "metric_sample")


@router.get(
    "/assets/{asset_id}/internal-system-profile",
    response_model=InternalSystemProfileRead | None,
)
def get_internal_profile(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> InternalSystemProfile | None:
    require_visible_asset(db, access, asset_id)
    return db.scalar(
        select(InternalSystemProfile).where(InternalSystemProfile.asset_id == asset_id)
    )


@router.put("/assets/{asset_id}/internal-system-profile", response_model=InternalSystemProfileRead)
def upsert_internal_profile(
    asset_id: UUID,
    payload: InternalSystemProfileUpsert,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> InternalSystemProfile:
    require_manageable_asset(db, access, asset_id)
    item = db.scalar(
        select(InternalSystemProfile).where(InternalSystemProfile.asset_id == asset_id)
    )
    if item is None:
        item = InternalSystemProfile(asset_id=asset_id, **payload.model_dump())
        db.add(item)
        action = "internal_system_profile.create"
    else:
        for key, value in payload.model_dump().items():
            setattr(item, key, value)
        action = "internal_system_profile.update"
    return commit(db, item, action, "internal_system_profile")
