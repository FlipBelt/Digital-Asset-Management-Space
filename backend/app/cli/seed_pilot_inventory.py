# ruff: noqa: E501
"""Create the first, explicitly-known digital-asset inventory as safe draft records.

This does not create login accounts or store phone numbers, emails, passwords,
access keys, instance IDs, bucket names, or other credentials.  Those facts are
intentionally left as visible follow-up items in each record.
"""

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Asset,
    AssetRelation,
    AssetType,
    AuditLog,
    InternalSystemProfile,
    LegalEntity,
    Platform,
    PlatformTenant,
    Provider,
    ServiceInstance,
    ServiceProduct,
)

ENTITY_CODE = "HZFTXY"


def seed_pilot_inventory() -> None:
    with SessionLocal() as db:
        entity = db.scalar(select(LegalEntity).where(LegalEntity.code == ENTITY_CODE))
        if entity is None:
            raise RuntimeError(f"Legal entity {ENTITY_CODE} is required before seeding the pilot.")

        types = {item.code: item for item in db.scalars(select(AssetType))}
        required_type_codes = {
            "registration_identity",
            "platform_tenant",
            "api_service",
            "nas_storage",
            "cloud_server",
            "internal_system",
        }
        missing = required_type_codes - types.keys()
        if missing:
            raise RuntimeError(
                f"Missing asset types: {', '.join(sorted(missing))}. Run app.cli.seed first."
            )

        def provider(code: str, name: str, website: str) -> Provider:
            item = db.scalar(select(Provider).where(Provider.code == code))
            if item is None:
                item = Provider(code=code, name=name, website=website)
                db.add(item)
                db.flush()
            return item

        def platform(
            item_provider: Provider, code: str, name: str, category: str, website: str
        ) -> Platform:
            item = db.scalar(
                select(Platform).where(
                    Platform.provider_id == item_provider.id,
                    Platform.code == code,
                )
            )
            if item is None:
                item = Platform(
                    provider_id=item_provider.id,
                    code=code,
                    name=name,
                    category=category,
                    website=website,
                )
                db.add(item)
                db.flush()
            return item

        def asset(
            code: str,
            name: str,
            type_code: str,
            description: str,
            *,
            status: str = "draft",
            criticality: str = "important",
            confidentiality: str = "internal",
        ) -> Asset:
            item = db.scalar(
                select(Asset).where(
                    Asset.legal_entity_id == entity.id,
                    Asset.asset_code == code,
                )
            )
            if item is None:
                item = Asset(
                    asset_code=code,
                    name=name,
                    asset_type_id=types[type_code].id,
                    legal_entity_id=entity.id,
                    status=status,
                    criticality=criticality,
                    confidentiality=confidentiality,
                    source_type="pilot_inventory",
                    description=description,
                )
                db.add(item)
                db.flush()
                db.add(
                    AuditLog(
                        action="asset.pilot_inventory.seed",
                        object_type="asset",
                        object_id=item.id,
                        after_data={"asset_code": code, "source": "user-provided pilot inventory"},
                        request_id="pilot-inventory",
                    )
                )
            return item

        def tenant(item_asset: Asset, item_platform: Platform, identifier: str) -> PlatformTenant:
            item = db.scalar(
                select(PlatformTenant).where(
                    PlatformTenant.platform_id == item_platform.id,
                    PlatformTenant.legal_entity_id == entity.id,
                    PlatformTenant.tenant_identifier == identifier,
                )
            )
            if item is None:
                item = PlatformTenant(
                    asset_id=item_asset.id,
                    platform_id=item_platform.id,
                    legal_entity_id=entity.id,
                    tenant_identifier=identifier,
                )
                db.add(item)
                db.flush()
            return item

        def service_product(
            item_provider: Provider, code: str, name: str, category: str
        ) -> ServiceProduct:
            item = db.scalar(
                select(ServiceProduct).where(
                    ServiceProduct.provider_id == item_provider.id,
                    ServiceProduct.code == code,
                )
            )
            if item is None:
                item = ServiceProduct(
                    provider_id=item_provider.id,
                    code=code,
                    name=name,
                    service_category=category,
                    billing_mode="usage",
                )
                db.add(item)
                db.flush()
            return item

        def service_instance(
            item_asset: Asset,
            product: ServiceProduct,
            item_platform: Platform,
            tenant_asset: Asset,
        ) -> None:
            if (
                db.scalar(select(ServiceInstance).where(ServiceInstance.asset_id == item_asset.id))
                is None
            ):
                db.add(
                    ServiceInstance(
                        asset_id=item_asset.id,
                        service_product_id=product.id,
                        purchase_platform_id=item_platform.id,
                        purchase_tenant_asset_id=tenant_asset.id,
                        subscription_name="待补充实例标识",
                    )
                )

        def relation(source: Asset, target: Asset, relation_type: str, note: str) -> None:
            exists = db.scalar(
                select(AssetRelation).where(
                    AssetRelation.source_asset_id == source.id,
                    AssetRelation.target_asset_id == target.id,
                    AssetRelation.relation_type == relation_type,
                )
            )
            if exists is None:
                db.add(
                    AssetRelation(
                        source_asset_id=source.id,
                        target_asset_id=target.id,
                        relation_type=relation_type,
                        source_type="pilot_inventory",
                        note=note,
                    )
                )

        deepseek_provider = provider("deepseek", "DeepSeek", "https://platform.deepseek.com")
        aliyun_provider = provider("aliyun", "阿里云", "https://www.aliyun.com")
        deepseek_platform = platform(
            deepseek_provider,
            "deepseek-platform",
            "DeepSeek 开放平台",
            "ai_platform",
            "https://platform.deepseek.com",
        )
        aliyun_platform = platform(
            aliyun_provider, "aliyun-platform", "阿里云", "cloud", "https://www.aliyun.com"
        )

        technical_identity = asset(
            "PILOT-REG-TECH-PHONE",
            "公司技术专用手机号（标识待补充）",
            "registration_identity",
            "公司所属技术专用注册身份。仅作为关联索引；手机号本体不写入本系统，需在受控密码库或交接材料中核验。",
            status="active",
            confidentiality="sensitive",
        )
        deepseek_tenant = asset(
            "PILOT-DEEPSEEK-TENANT",
            "DeepSeek 公司使用主体（待补充账号标识）",
            "platform_tenant",
            "已知为公司使用的 DeepSeek 账号/租户。待补充租户或账号标识、管理员、余额查询方式与 API Key 清单引用。",
            status="active",
            confidentiality="sensitive",
        )
        aliyun_legacy_tenant = asset(
            "PILOT-ALIYUN-LEGACY",
            "阿里云旧公司邮箱使用主体（待补充账号标识）",
            "platform_tenant",
            "历史公司邮箱注册或管理的阿里云使用主体。待补充实际账号标识、资源清单和费用归属。",
            status="active",
            confidentiality="sensitive",
        )
        aliyun_technical_tenant = asset(
            "PILOT-ALIYUN-TECH",
            "阿里云技术使用主体（待补充账号标识）",
            "platform_tenant",
            "当前技术使用的阿里云使用主体；已知包含 OCR、OSS 与一台 ECS。待补充实际账号标识与资源实例 ID。",
            status="active",
            confidentiality="sensitive",
        )
        aliyun_service_tenant = asset(
            "PILOT-ALIYUN-CS",
            "阿里云客服部门使用主体（待补充账号标识）",
            "platform_tenant",
            "由客服部门个人手机号注册、公司报销的阿里云使用主体；公司资产归属、账号控制权与交接人待核验。",
            status="active",
            confidentiality="sensitive",
        )
        deepseek_api = asset(
            "PILOT-DEEPSEEK-API",
            "DeepSeek API 服务（待补充实例）",
            "api_service",
            "后续 AI 工作流可能使用的 DeepSeek API 服务。待补充 API Key 的外部保管引用、余额与调用量同步配置。",
        )
        aliyun_ocr = asset(
            "PILOT-ALIYUN-OCR",
            "阿里云 OCR 服务（待补充实例）",
            "api_service",
            "已知已开通。待补充地域、服务实例、调用应用、费用负责人和额度/账单获取方式。",
            status="active",
        )
        aliyun_oss = asset(
            "PILOT-ALIYUN-OSS",
            "阿里云 OSS 对象存储（待补充 Bucket）",
            "nas_storage",
            "已知已开通。待补充 Bucket 名称、地域、数据分类、访问策略、备份与业务系统关联。",
            status="active",
            confidentiality="sensitive",
        )
        technical_ecs = asset(
            "PILOT-ALIYUN-ECS-TECH",
            "阿里云 ECS（技术使用主体，待补充实例 ID）",
            "cloud_server",
            "已知存在一台 ECS。待补充实例 ID、地域、公网 IP、操作系统、续费方式、部署系统与维护人。",
            status="active",
            criticality="critical",
            confidentiality="sensitive",
        )
        service_ecs = asset(
            "PILOT-ALIYUN-ECS-CS",
            "阿里云 ECS（客服部门使用主体，待补充实例 ID）",
            "cloud_server",
            "已知存在一台 ECS。待补充实例 ID、地域、公网 IP、实际业务、维护人与费用归属。",
            status="active",
            criticality="critical",
            confidentiality="sensitive",
        )
        account_center = asset(
            "PILOT-SYSTEM-ACCOUNT-CENTER",
            "集团账号管理中台",
            "internal_system",
            "当前正在建设的自研系统。生产部署关联先按已知技术 ECS 登记，需以阿里云实例 ID 最终核验。",
            status="active",
            criticality="critical",
        )

        tenant(deepseek_tenant, deepseek_platform, "PENDING-DEEPSEEK-COMPANY")
        tenant(aliyun_legacy_tenant, aliyun_platform, "PENDING-ALIYUN-LEGACY")
        tenant(aliyun_technical_tenant, aliyun_platform, "PENDING-ALIYUN-TECH")
        tenant(aliyun_service_tenant, aliyun_platform, "PENDING-ALIYUN-CS")

        service_instance(
            deepseek_api,
            service_product(deepseek_provider, "deepseek-api", "DeepSeek API", "ai_api"),
            deepseek_platform,
            deepseek_tenant,
        )
        service_instance(
            aliyun_ocr,
            service_product(aliyun_provider, "aliyun-ocr", "阿里云 OCR", "cloud_api"),
            aliyun_platform,
            aliyun_technical_tenant,
        )
        service_instance(
            aliyun_oss,
            service_product(aliyun_provider, "aliyun-oss", "阿里云 OSS", "object_storage"),
            aliyun_platform,
            aliyun_technical_tenant,
        )

        relation(
            deepseek_tenant,
            technical_identity,
            "REGISTERED_BY",
            "公司技术专用手机号；号码本体待在受控材料核验。",
        )
        relation(
            deepseek_api, deepseek_tenant, "PURCHASED_VIA", "API 服务归属该 DeepSeek 公司使用主体。"
        )
        relation(
            aliyun_ocr,
            aliyun_technical_tenant,
            "PURCHASED_VIA",
            "根据现有描述暂登记，待以账号与服务实例核验。",
        )
        relation(
            aliyun_oss,
            aliyun_technical_tenant,
            "PURCHASED_VIA",
            "根据现有描述暂登记，待以账号与 Bucket 核验。",
        )
        relation(
            technical_ecs,
            aliyun_technical_tenant,
            "PURCHASED_VIA",
            "根据现有描述暂登记，待以账号与 ECS 实例 ID 核验。",
        )
        relation(
            service_ecs,
            aliyun_service_tenant,
            "PURCHASED_VIA",
            "根据现有描述暂登记，待以账号与 ECS 实例 ID 核验。",
        )
        relation(
            account_center,
            technical_ecs,
            "DEPLOYED_ON",
            "根据当前生产部署信息暂登记；待以阿里云实例 ID 最终核验。",
        )

        profile = db.scalar(
            select(InternalSystemProfile).where(InternalSystemProfile.asset_id == account_center.id)
        )
        if profile is None:
            db.add(
                InternalSystemProfile(
                    asset_id=account_center.id,
                    production_url="https://jtzhzt.flipbeltchina.com",
                    tech_stack="Vue 3 / FastAPI / PostgreSQL / Nginx / 阿里云 ECS",
                    backup_description="待补充数据库备份位置、保留周期和恢复演练记录。",
                )
            )

        db.commit()
        print("Pilot inventory is ready: 11 assets, 4 platform tenants, 3 service instances.")


if __name__ == "__main__":
    seed_pilot_inventory()
