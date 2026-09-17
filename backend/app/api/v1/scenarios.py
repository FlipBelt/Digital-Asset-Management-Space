from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, asset_visibility_clause, get_access_context
from app.db.session import get_db
from app.models import (
    Account,
    Asset,
    AssetPlatformLink,
    AssetResponsibility,
    AssetScenarioLink,
    AssetType,
    BusinessScenario,
    Department,
    Person,
    Platform,
    PlatformTenant,
    ResourceProfile,
    ServiceInstance,
)
from app.schemas.workspace import (
    ScenarioNodeRead,
    ScenarioOverviewRead,
    ScenarioSummaryRead,
)

router = APIRouter(prefix="/workspace/scenarios", tags=["scenarios"])


def _visible_assets(db: Session, access: AccessContext) -> list[Asset]:
    return list(
        db.scalars(
            select(Asset).where(
                Asset.archived_at.is_(None), asset_visibility_clause(access)
            )
        )
    )


def _scenario_assets(
    db: Session, scenario: BusinessScenario, access: AccessContext
) -> tuple[list[Asset], list[AssetScenarioLink]]:
    assets = _visible_assets(db, access)
    assets_by_id = {item.id: item for item in assets}
    links = list(
        db.scalars(
            select(AssetScenarioLink).where(
                AssetScenarioLink.scenario_id == scenario.id,
                AssetScenarioLink.asset_id.in_(assets_by_id),
            )
        )
    ) if assets_by_id else []
    return [assets_by_id[item.asset_id] for item in links if item.asset_id in assets_by_id], links


def _directory_maps(db: Session):
    types = {
        item.id: item
        for item in db.scalars(select(AssetType).where(AssetType.archived_at.is_(None)))
    }
    platforms = {
        item.id: item
        for item in db.scalars(select(Platform).where(Platform.archived_at.is_(None)))
    }
    tenants = list(db.scalars(select(PlatformTenant).where(PlatformTenant.archived_at.is_(None))))
    accounts = list(db.scalars(select(Account).where(Account.archived_at.is_(None))))
    services = list(
        db.scalars(select(ServiceInstance).where(ServiceInstance.archived_at.is_(None)))
    )
    resources = list(
        db.scalars(select(ResourceProfile).where(ResourceProfile.archived_at.is_(None)))
    )
    platform_links = list(
        db.scalars(select(AssetPlatformLink).where(AssetPlatformLink.archived_at.is_(None)))
    )
    responsibilities = list(
        db.scalars(
            select(AssetResponsibility).where(
                AssetResponsibility.archived_at.is_(None),
                AssetResponsibility.role_type == "responsible",
            )
        )
    )
    people = {
        item.id: item
        for item in db.scalars(select(Person).where(Person.archived_at.is_(None)))
    }
    departments = {
        item.id: item
        for item in db.scalars(select(Department).where(Department.archived_at.is_(None)))
    }
    return {
        "types": types,
        "platforms": platforms,
        "tenants": tenants,
        "accounts": accounts,
        "services": services,
        "resources": resources,
        "platform_links": platform_links,
        "responsibilities": responsibilities,
        "people": people,
        "departments": departments,
    }


def _platform_id_by_asset(maps: dict) -> dict[UUID, UUID]:
    tenant_by_asset = {item.asset_id: item for item in maps["tenants"]}
    tenant_by_id = {item.id: item for item in maps["tenants"]}
    account_by_asset = {item.asset_id: item for item in maps["accounts"]}
    result: dict[UUID, UUID] = {}
    for asset_id, tenant in tenant_by_asset.items():
        result[asset_id] = tenant.platform_id
    for asset_id, account in account_by_asset.items():
        tenant = tenant_by_id.get(account.platform_tenant_id)
        if tenant:
            result[asset_id] = tenant.platform_id
    for link in maps["platform_links"]:
        result.setdefault(link.asset_id, link.platform_id)
    for service in maps["services"]:
        if service.purchase_platform_id:
            result.setdefault(service.asset_id, service.purchase_platform_id)
        elif service.purchase_tenant_asset_id:
            tenant = tenant_by_asset.get(service.purchase_tenant_asset_id)
            if tenant:
                result.setdefault(service.asset_id, tenant.platform_id)
    return result


def _responsible(asset_id: UUID, maps: dict) -> tuple[str | None, str | None]:
    relation = next((item for item in maps["responsibilities"] if item.asset_id == asset_id), None)
    if relation is None:
        return None, None
    person = maps["people"].get(relation.person_id) if relation.person_id else None
    department = maps["departments"].get(relation.department_id) if relation.department_id else None
    return person.display_name if person else None, department.name if department else None


def _summary(
    scenario: BusinessScenario, assets: list[Asset], maps: dict
) -> ScenarioSummaryRead:
    asset_ids = {item.id for item in assets}
    tenants = {item.asset_id for item in maps["tenants"] if item.asset_id in asset_ids}
    accounts = {item.asset_id for item in maps["accounts"] if item.asset_id in asset_ids}
    platforms = _platform_id_by_asset(maps)
    responsible = {
        item.asset_id
        for item in maps["responsibilities"]
        if item.asset_id in asset_ids
    }
    return ScenarioSummaryRead(
        code=scenario.code,
        name=scenario.name,
        description=scenario.description,
        asset_count=len(asset_ids),
        platform_count=len({platforms[item_id] for item_id in asset_ids if item_id in platforms}),
        account_count=len(accounts),
        resource_count=len(asset_ids - tenants - accounts),
        responsible_count=len(responsible),
    )


@router.get("", response_model=list[ScenarioSummaryRead])
def list_scenarios(
    db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)
) -> list[ScenarioSummaryRead]:
    maps = _directory_maps(db)
    scenarios = list(
        db.scalars(
            select(BusinessScenario)
            .where(BusinessScenario.archived_at.is_(None))
            .order_by(BusinessScenario.sort_order, BusinessScenario.name)
        )
    )
    return [_summary(item, _scenario_assets(db, item, access)[0], maps) for item in scenarios]


@router.get("/{scenario_code}", response_model=ScenarioOverviewRead)
def get_scenario(
    scenario_code: str,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> ScenarioOverviewRead:
    scenario = db.scalar(
        select(BusinessScenario).where(
            BusinessScenario.code == scenario_code,
            BusinessScenario.archived_at.is_(None),
        )
    )
    if scenario is None:
        raise HTTPException(status_code=404, detail="业务场景不存在")

    assets, _ = _scenario_assets(db, scenario, access)
    assets_by_id = {item.id: item for item in assets}
    maps = _directory_maps(db)
    types = maps["types"]
    tenants_by_asset = {item.asset_id: item for item in maps["tenants"]}
    tenants_by_id = {item.id: item for item in maps["tenants"]}
    accounts_by_asset = {item.asset_id: item for item in maps["accounts"]}
    accounts_by_id = {item.id: item for item in maps["accounts"]}
    service_by_asset = {item.asset_id: item for item in maps["services"]}
    resource_by_asset = {item.asset_id: item for item in maps["resources"]}
    platform_by_asset = _platform_id_by_asset(maps)
    root_id = f"scenario:{scenario.code}"
    nodes: list[ScenarioNodeRead] = []
    platform_node_ids: dict[UUID, str] = {}

    def ensure_platform(platform_id: UUID | None) -> str | None:
        if platform_id is None or platform_id not in maps["platforms"]:
            return None
        if platform_id not in platform_node_ids:
            platform = maps["platforms"][platform_id]
            platform_node_ids[platform_id] = f"platform:{platform_id}"
            nodes.append(
                ScenarioNodeRead(
                    id=platform_node_ids[platform_id],
                    parent_id=root_id,
                    kind="platform",
                    label=platform.name,
                    subtitle=platform.category,
                    status=platform.review_status,
                    href=f"/directory/platform/{platform.id}",
                )
            )
        return platform_node_ids[platform_id]

    # Create platform nodes first so all account/resource nodes can refer to them.
    for asset in assets:
        ensure_platform(platform_by_asset.get(asset.id))

    for asset in assets:
        tenant = tenants_by_asset.get(asset.id)
        account = accounts_by_asset.get(asset.id)
        person_name, department_name = _responsible(asset.id, maps)
        asset_type = types.get(asset.asset_type_id)
        parent_id = ensure_platform(platform_by_asset.get(asset.id)) or root_id
        kind = "resource"
        subtitle = asset_type.name if asset_type else "资产"
        metadata: dict[str, str | int | bool | None] = {
            "asset_code": asset.asset_code,
            "asset_type": asset_type.code if asset_type else None,
        }
        if tenant is not None:
            kind = "tenant"
            subtitle = "平台企业账号"
            if tenant.tenant_identifier:
                subtitle = f"平台企业账号 · {tenant.tenant_identifier}"
        elif account is not None:
            kind = "account"
            subtitle = f"账号 · {account.login_identifier}"
            parent_account = accounts_by_id.get(account.parent_account_id)
            if parent_account and parent_account.asset_id in assets_by_id:
                parent_id = f"asset:{parent_account.asset_id}"
            elif account.platform_tenant_id in tenants_by_id:
                tenant_asset_id = tenants_by_id[account.platform_tenant_id].asset_id
                parent_id = (
                    f"asset:{tenant_asset_id}" if tenant_asset_id in assets_by_id else parent_id
                )
            metadata.update(
                {"account_role": account.account_role, "privilege_level": account.privilege_level}
            )
        elif asset.id in service_by_asset:
            kind = "service"
            subtitle = "服务实例"
            service = service_by_asset[asset.id]
            if service.purchase_tenant_asset_id in assets_by_id:
                parent_id = f"asset:{service.purchase_tenant_asset_id}"
        elif asset.id in resource_by_asset:
            resource = resource_by_asset[asset.id]
            subtitle = resource.resource_family or subtitle
            metadata["resource_family"] = resource.resource_family
            if resource.managed_under_account_id in tenants_by_id:
                tenant_asset_id = tenants_by_id[resource.managed_under_account_id].asset_id
                if tenant_asset_id in assets_by_id:
                    parent_id = f"asset:{tenant_asset_id}"
            if resource.parent_resource_asset_id in assets_by_id:
                parent_id = f"asset:{resource.parent_resource_asset_id}"
        else:
            kind = (
                "system"
                if asset_type and asset_type.profile_kind in {"internal_system", "service_instance"}
                else "resource"
            )

        nodes.append(
            ScenarioNodeRead(
                id=f"asset:{asset.id}",
                parent_id=parent_id,
                kind=kind,
                label=asset.name,
                subtitle=subtitle,
                asset_id=asset.id,
                status=asset.status,
                responsible_name=person_name,
                department_name=department_name,
                href=f"/assets/{asset.id}",
                metadata=metadata,
            )
        )

    visible_asset_ids = {item.id for item in _visible_assets(db, access)}
    classified_ids = {
        item.asset_id
        for item in db.scalars(
            select(AssetScenarioLink).where(AssetScenarioLink.asset_id.in_(visible_asset_ids))
        )
    } if visible_asset_ids else set()
    overview = _summary(scenario, assets, maps)
    return ScenarioOverviewRead(
        scenario=overview,
        nodes=nodes,
        unclassified_count=len(visible_asset_ids - classified_ids),
    )
