import re
from decimal import Decimal

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Account,
    AppSetting,
    Asset,
    AssetCategory,
    AssetScenarioLink,
    AssetType,
    BusinessScenario,
    ConnectorDefinition,
    MetricDefinition,
    Permission,
    Platform,
    PlatformTenant,
    Role,
    RolePermission,
)

ROLES = [
    ("system_admin", "系统管理员"),
    ("employee", "普通员工"),
    ("department_manager", "部门负责人"),
    ("asset_manager", "平台/资产负责人"),
    ("executive", "公司领导"),
    ("auditor", "审计人员"),
]

PERMISSIONS = [
    ("asset.read", "查看资产与账号"),
    ("asset.write", "维护资产与账号"),
    ("asset.export", "导出资产数据"),
    ("organization.read", "查看组织与人员"),
    ("organization.write", "维护组织与人员"),
    ("governance.read", "查看流程与风险"),
    ("governance.write", "维护流程与风险"),
    ("admin.manage", "管理系统配置与权限"),
]

ROLE_PERMISSION_CODES = {
    "system_admin": {code for code, _ in PERMISSIONS},
    "asset_manager": {
        "asset.read",
        "asset.write",
        "asset.export",
        "organization.read",
        "governance.read",
        "governance.write",
    },
    "department_manager": {
        "asset.read",
        "asset.write",
        "organization.read",
        "governance.read",
        "governance.write",
    },
    "executive": {"asset.read", "asset.export", "organization.read", "governance.read"},
    "auditor": {"asset.read", "organization.read", "governance.read"},
    "employee": {"asset.read", "asset.write", "governance.read"},
}

CATEGORIES = [
    ("platform_account", "平台与账号", 10),
    ("internal_system", "公司自研系统", 20),
    ("saas_software", "外购软件与SaaS", 30),
    ("api_service", "API及按量服务", 40),
    ("cloud_network", "云资源与网络", 50),
    ("data_storage", "数据与存储", 60),
    ("domain_ip", "域名、证书与知识产权", 70),
    ("hardware_license", "硬件与软件许可", 80),
]

TYPES = {
    "platform_account": [
        ("registration_identity", "注册身份", "generic"),
        ("platform_tenant", "平台企业租户", "platform_tenant"),
        ("platform_account", "平台账号", "account"),
    ],
    "internal_system": [
        ("internal_system", "公司自研系统", "internal_system"),
        ("automation_script", "自动化脚本", "internal_system"),
        ("ai_workflow", "AI工作流/智能体", "internal_system"),
        ("code_repository", "代码仓库", "generic"),
    ],
    "saas_software": [
        ("saas_subscription", "SaaS订阅", "service_instance"),
        ("email_service", "邮箱服务", "service_instance"),
        ("software_service", "软件与业务服务", "service_instance"),
        ("business_environment", "业务环境", "service_instance"),
    ],
    "api_service": [("api_service", "API服务实例", "service_instance")],
    "cloud_network": [
        ("cloud_server", "云服务器", "infrastructure"),
        ("cloud_database", "云数据库", "infrastructure"),
        ("nas_storage", "NAS/对象存储", "infrastructure"),
        ("vpn_network", "VPN/网络服务", "infrastructure"),
    ],
    "data_storage": [
        ("business_database", "业务数据库", "generic"),
        ("dataset", "数据集", "generic"),
        ("backup", "数据备份", "generic"),
    ],
    "domain_ip": [
        ("domain", "域名", "domain"),
        ("ssl_certificate", "SSL证书", "domain"),
        ("intellectual_property", "知识产权/资质", "generic"),
    ],
    "hardware_license": [
        ("hardware_device", "硬件设备", "device"),
        ("software_license", "软件许可", "service_instance"),
    ],
}

METRICS = [
    ("balance", "账户余额", "currency", "latest"),
    ("quota_remaining", "剩余额度", "unit", "latest"),
    ("api_calls", "API调用次数", "times", "sum"),
    ("input_tokens", "输入Token", "token", "sum"),
    ("output_tokens", "输出Token", "token", "sum"),
    ("total_tokens", "总Token", "token", "sum"),
    ("cost", "费用", "currency", "sum"),
    ("seats_used", "已用席位", "seat", "latest"),
]

SCENARIOS = [
    ("ecommerce", "电商经营", "店铺、平台账号、子账号、广告、物流与支付资源", 10),
    ("technology", "技术与研发", "AI、API、云服务器、数据库与研发系统", 20),
    ("software", "软件与协作", "公司软件、邮箱、协作工具与业务系统", 30),
]


def seed_scenario_links(db) -> None:
    """Create the first user-facing scenario index without changing source assets.

    Scenario membership is intentionally a reversible, evidence-labelled projection.  It
    uses names and the existing catalog type rather than copying or reclassifying assets,
    so the asset intake and six-layer governance model remain the source of truth.
    """
    scenario_by_code: dict[str, BusinessScenario] = {}
    for code, name, description, sort_order in SCENARIOS:
        scenario = db.scalar(select(BusinessScenario).where(BusinessScenario.code == code))
        if scenario is None:
            scenario = BusinessScenario(
                code=code,
                name=name,
                description=description,
                sort_order=sort_order,
                is_system=True,
            )
            db.add(scenario)
            db.flush()
        scenario_by_code[code] = scenario

    assets = list(db.scalars(select(Asset).where(Asset.archived_at.is_(None))))
    asset_types = {
        item.id: item
        for item in db.scalars(select(AssetType).where(AssetType.archived_at.is_(None)))
    }
    categories = {
        item.id: item
        for item in db.scalars(select(AssetCategory).where(AssetCategory.archived_at.is_(None)))
    }
    platforms = {
        item.id: item
        for item in db.scalars(select(Platform).where(Platform.archived_at.is_(None)))
    }
    tenants = list(db.scalars(select(PlatformTenant).where(PlatformTenant.archived_at.is_(None))))
    tenant_by_asset = {item.asset_id: item for item in tenants}
    tenant_by_id = {item.id: item for item in tenants}
    accounts = list(db.scalars(select(Account).where(Account.archived_at.is_(None))))
    account_by_asset = {item.asset_id: item for item in accounts}

    def platform_name(asset_id) -> str:
        tenant = tenant_by_asset.get(asset_id)
        if tenant is None:
            account = account_by_asset.get(asset_id)
            tenant = tenant_by_id.get(account.platform_tenant_id) if account else None
        platform = platforms.get(tenant.platform_id) if tenant else None
        return platform.name if platform else ""

    ecommerce = re.compile(r"淘宝|天猫|京东|抖音|电商|店铺|广告|物流|支付|拼多多", re.I)
    technology = re.compile(
        r"AI|API|DeepSeek|MiniMax|OpenAI|阿里云|腾讯云|华为云|服务器|数据库|研发|技术|开发|代码|模型|算力",
        re.I,
    )
    software = re.compile(r"软件|邮箱|协作|知识库|办公|系统|SaaS|订阅|飞书|钉钉|企业微信", re.I)
    technology_types = {
        "api_service", "cloud_network", "cloud_server", "cloud_database", "nas_storage",
        "vpn_network", "ai_workflow", "internal_system", "automation_script", "code_repository",
    }
    software_types = {
        "saas_subscription", "email_service", "software_service", "business_environment"
    }

    for asset in assets:
        asset_type = asset_types.get(asset.asset_type_id)
        category = categories.get(asset_type.category_id) if asset_type else None
        haystack = " ".join(
            value
            for value in (
                asset.name,
                asset.description or "",
                asset_type.code if asset_type else "",
                asset_type.name if asset_type else "",
                category.code if category else "",
                category.name if category else "",
                platform_name(asset.id),
            )
            if value
        )
        matches: list[tuple[str, Decimal, str]] = []
        if ecommerce.search(haystack):
            matches.append(("ecommerce", Decimal("0.82"), "名称/平台关键词规则"))
        if technology.search(haystack) or (asset_type and asset_type.code in technology_types):
            matches.append(("technology", Decimal("0.85"), "名称/资产类型规则"))
        if software.search(haystack) or (asset_type and asset_type.code in software_types):
            matches.append(("software", Decimal("0.78"), "名称/资产类型规则"))
        for index, (code, confidence, note) in enumerate(matches):
            scenario = scenario_by_code[code]
            existing = db.scalar(
                select(AssetScenarioLink).where(
                    AssetScenarioLink.asset_id == asset.id,
                    AssetScenarioLink.scenario_id == scenario.id,
                )
            )
            if existing is None:
                db.add(
                    AssetScenarioLink(
                        asset_id=asset.id,
                        scenario_id=scenario.id,
                        is_primary=index == 0,
                        source_type="seed_rule",
                        confidence=confidence,
                        note=note,
                    )
                )


def seed() -> None:
    with SessionLocal() as db:
        for code, name in ROLES:
            if db.scalar(select(Role).where(Role.code == code)) is None:
                db.add(Role(code=code, name=name))
        for code, name in PERMISSIONS:
            if db.scalar(select(Permission).where(Permission.code == code)) is None:
                db.add(Permission(code=code, name=name))
        db.flush()
        roles_by_code = {item.code: item for item in db.scalars(select(Role))}
        permissions_by_code = {item.code: item for item in db.scalars(select(Permission))}
        for role_code, permission_codes in ROLE_PERMISSION_CODES.items():
            role = roles_by_code.get(role_code)
            if role is None:
                continue
            for permission_code in permission_codes:
                permission = permissions_by_code.get(permission_code)
                if permission is None:
                    continue
                if db.get(RolePermission, (role.id, permission.id)) is None:
                    db.add(RolePermission(role_id=role.id, permission_id=permission.id))

        category_by_code: dict[str, AssetCategory] = {}
        for code, name, sort_order in CATEGORIES:
            category = db.scalar(select(AssetCategory).where(AssetCategory.code == code))
            if category is None:
                category = AssetCategory(code=code, name=name, sort_order=sort_order)
                db.add(category)
                db.flush()
            category_by_code[code] = category

        for category_code, type_rows in TYPES.items():
            category = category_by_code[category_code]
            for code, name, profile_kind in type_rows:
                exists = db.scalar(
                    select(AssetType).where(
                        AssetType.category_id == category.id,
                        AssetType.code == code,
                    )
                )
                if exists is None:
                    db.add(
                        AssetType(
                            category_id=category.id,
                            code=code,
                            name=name,
                            profile_kind=profile_kind,
                            is_system=True,
                            completeness_rules={},
                        )
                    )

        for key, name, unit, aggregation in METRICS:
            if (
                db.scalar(select(MetricDefinition).where(MetricDefinition.metric_key == key))
                is None
            ):
                db.add(
                    MetricDefinition(
                        metric_key=key,
                        display_name=name,
                        unit=unit,
                        aggregation=aggregation,
                    )
                )

        connector_rows = [
            ("mock", "模拟连接器", ["health", "balance", "usage"], True),
            ("aliyun", "阿里云连接器", ["accounts", "resources", "billing", "health"], False),
            ("deepseek", "DeepSeek API连接器", ["balance", "quota", "usage", "billing"], True),
            ("minimax", "MiniMax API连接器", ["token_plan_remains", "usage", "health"], True),
        ]
        for code, name, capabilities, enabled in connector_rows:
            if (
                db.scalar(select(ConnectorDefinition).where(ConnectorDefinition.code == code))
                is None
            ):
                db.add(
                    ConnectorDefinition(
                        code=code,
                        name=name,
                        capabilities=capabilities,
                        enabled=enabled,
                    )
                )

        if db.scalar(select(AppSetting).where(AppSetting.key == "ui")) is None:
            db.add(
                AppSetting(
                    key="ui",
                    value={
                        "default_theme": "bitwarden",
                        "allowed_themes": ["bitwarden", "hudu", "ant-pro"],
                        "features": {
                            "governance": True,
                            "connectors": True,
                            "charts": True,
                        },
                    },
                )
            )
        if db.scalar(select(AppSetting).where(AppSetting.key == "organization_bootstrap")) is None:
            db.add(
                AppSetting(
                    key="organization_bootstrap",
                    value={
                        "legal_entity_name": "杭州飞途行远企业管理有限公司",
                        "legal_entity_code": "HZFTXY",
                        "initial_administrator_candidate": "十叶-冯硕硕",
                    },
                )
            )
        seed_scenario_links(db)
        db.commit()
        print("Base asset categories, types, metrics, and scenario index are ready.")


if __name__ == "__main__":
    seed()
