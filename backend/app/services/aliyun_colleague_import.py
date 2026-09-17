"""Confirmed, evidence-bounded import for the colleague-provided Aliyun directory.

This importer deliberately separates two results:

* every sanitized source row is retained in a normal ``ImportBatch``;
* only legal entities with a name + unified social credit code, and named external
  platforms, become canonical directory records.

It never copies passwords, keys, cookies, verification codes, or raw source text.
It also never turns a login identity into an L4 tenant, or a user name into an L5
authorization.  The operation is idempotent and records exactly which objects it
created so it can be rolled back without touching pre-existing inventory.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AssetIdentifier,
    AssetResponsibility,
    Account,
    AuditLog,
    DeveloperIntakeBatch,
    ImportBatch,
    LegalEntity,
    LegalEntityIdentifier,
    LegalEntityProfile,
    Person,
    Platform,
    PlatformTenant,
    Provider,
    RegistrationIdentityProfile,
    ServiceInstance,
    ServiceProduct,
    SourceImportRecord,
)
from app.services.assets import ensure_internal_identifier

BATCH_FILE_NAME = "阿里云目录同事资料（惜君负责，确认入库）"
DEVELOPER_BATCH_TITLE = "同事资料：阿里云目录（脱敏开发者预览）"
RESPONSIBLE_PERSON_NAME = "惜君-吴旭骏"
SOURCE_LOCATION = r"C:\Users\rulai\Desktop\阿里云"

# Only values that are safe to retain in the production asset system appear here.
# In particular, no raw credential value is copied from the original files.
SOURCE_ROWS: tuple[dict[str, Any], ...] = (
    {
        "key": "aliyun",
        "file": "阿里云.txt",
        "name": "阿里云与163邮箱访问资料",
        "layers": ["L2候选", "L3", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.86",
        "evidence": ["明确平台名和登录身份", "没有企业租户或主账号证据"],
        "note": "仅建立阿里云、163邮箱平台目录；不建L2/L4/L6。",
    },
    {
        "key": "dingtalk",
        "file": "钉钉.txt",
        "name": "钉钉访问资料",
        "layers": ["L2候选", "L3"],
        "disposition": "pending_confirmation",
        "confidence": "0.76",
        "evidence": ["手机号登录资料"],
        "note": "仅建立钉钉平台目录；不建L2/L4/L5。",
    },
    {
        "key": "guanyi",
        "file": "管易.txt",
        "name": "管易ERP",
        "layers": ["L2候选", "L3", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.88",
        "evidence": ["官方入口", "多组登录身份"],
        "note": "仅建立管易ERP平台目录；确认在用后才建L6。",
    },
    {
        "key": "jd",
        "file": "京东旗舰店.txt",
        "name": "京东店铺运营与商户资料",
        "layers": ["L2候选", "L3", "L4候选", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.90",
        "evidence": ["京东旗舰店", "商户号", "运营与VC入口"],
        "note": "仅建立京东平台目录；L4需补法人、店铺名和有效状态。",
    },
    {
        "key": "jushuitan",
        "file": "聚水潭.txt",
        "name": "聚水潭、影刀、安捷云及云仓资料",
        "layers": ["L2候选", "L3", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.86",
        "evidence": ["系统名、服务入口、云仓命名"],
        "note": "仅建立具名平台目录；不建L4。",
    },
    {
        "key": "sina",
        "file": "新浪邮箱.txt",
        "name": "新浪邮箱与微博资料",
        "layers": ["L2候选", "L3", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.74",
        "evidence": ["邮箱和微博身份"],
        "note": "仅建立新浪邮箱、微博平台目录。",
    },
    {
        "key": "yindao",
        "file": "影刀.txt",
        "name": "影刀与VPN服务",
        "layers": ["L2候选", "L3", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.84",
        "evidence": ["影刀管理员资料", "VPN服务入口"],
        "note": "仅建立影刀平台目录；VPN供应商未知，不建平台对象。",
    },
    {
        "key": "yonyou",
        "file": "用友YS.txt",
        "name": "用友云服务",
        "layers": ["L2候选", "L3", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.80",
        "evidence": ["官方服务入口", "登录身份"],
        "note": "仅建立用友云平台目录；不建L4。",
    },
    {
        "key": "yuce",
        "file": "预策.txt",
        "name": "预策业务环境",
        "layers": ["L3", "L6候选"],
        "disposition": "pending_confirmation",
        "confidence": "0.87",
        "evidence": ["真理时刻和样板房的具体环境入口"],
        "note": "仅建立预策平台目录；需确认现役环境后才建L6。",
    },
    {
        "key": "ipr_platforms",
        "file": "知蝉网及平台账号.txt",
        "name": "知识产权维权平台资料",
        "layers": ["L2候选", "L3", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.89",
        "evidence": ["中国商标网、知蝉及多个电商知产平台"],
        "note": "仅建立具名平台目录；权利人账号须补法人后再评估L4。",
    },
    {
        "key": "ipr_master",
        "file": "知产维权账号密码总 飞比特.txt",
        "name": "公司知产维权与登记账号",
        "layers": ["L1候选", "L2候选", "L3", "L4候选", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.94",
        "evidence": ["公司名称与京东知产、著作权登记账号组合"],
        "note": "仅建立具名平台目录；L4需核验有效性和负责人。",
    },
    {
        "key": "gs1",
        "file": "中国物品编码中心.txt",
        "name": "GS1企业账户",
        "layers": ["L2候选", "L3", "L4候选", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.93",
        "evidence": ["明确标为GS1企业账户"],
        "note": "仅建立GS1平台目录；L4需补归属法人和管理员。",
    },
    {
        "key": "patent",
        "file": "专利查询.txt",
        "name": "专利查询及法人资料",
        "layers": ["L1", "L2候选", "L3", "L6待确认"],
        "disposition": "committed_catalog",
        "confidence": "0.95",
        "evidence": ["3个公司名称与统一社会信用代码"],
        "note": "已建立3个待核验L1；仅建立专利查询平台目录。",
    },
    {
        "key": "mail",
        "file": "flipbelt邮箱.txt",
        "name": "企业邮箱与邮箱通讯录资料",
        "layers": ["L2候选", "L3", "L4候选", "L6待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.92",
        "evidence": ["网易企业邮箱管理员及企业域名"],
        "note": "仅建立具名邮箱平台目录；L4需补企业租户标识和接管人。",
    },
    {
        "key": "nas",
        "file": "NAS系统注册.png",
        "name": "NAS企业注册截图",
        "layers": ["L1辅助证据", "L2候选", "L3待确认"],
        "disposition": "pending_confirmation",
        "confidence": "0.72",
        "evidence": ["企业注册表单、公司名、联系人信息"],
        "note": "注册表单不证明注册完成，不建L3/L4/L6。",
    },
    {
        "key": "invalid_trademark",
        "file": "模拟商标查询内容.txt",
        "name": "模拟商标查询内容",
        "layers": ["历史跳过"],
        "disposition": "skipped",
        "confidence": "0.99",
        "evidence": ["包含模拟问答和推理文字，不是原始业务证据"],
        "note": "仅保留来源判定，不进入资产目录。",
    },
)

LEGAL_ENTITIES: tuple[dict[str, str], ...] = (
    {"code": "COL-L1-001", "name": "杭州众智新控股有限公司", "uscc": "91330105MAE972055U"},
    {"code": "COL-L1-002", "name": "飞将体育科技（宁波）有限公司", "uscc": "91330205MA7JRNAP54"},
    {"code": "COL-L1-003", "name": "宁波飞比特体育用品有限公司", "uscc": "91330205074937402U"},
)

PLATFORM_NAMES: tuple[str, ...] = (
    "阿里云", "163邮箱", "钉钉", "管易ERP", "京东", "聚水潭", "影刀", "安捷云",
    "新浪邮箱", "微博", "用友云", "预策", "中国商标网", "知蝉", "抖音", "小红书",
    "拼多多", "京东知识产权保护中心", "著作权登记系统", "12315", "中国物品编码中心（GS1）",
    "专利查询系统", "网易企业邮箱", "搜狐邮箱",
)

# These are identifiers that the original files themselves show as login or
# registration values.  Passwords and other credentials are intentionally not
# represented here.  A value can be independently useful as L2 even when its
# legal entity, tenant, or user authorization is unknown.
IDENTITY_SOURCES: dict[str, tuple[str, ...]] = {
    "aliyun": ("18958354558@163.com",),
    "dingtalk": ("18958354558",),
    "guanyi": ("183569364@qq.com", "416910908@qq.com", "18770808500", "18958354558"),
    "jd": ("flipbelt@qq.com",),
    "jushuitan": (
        "flipbelt@qq.com", "harry1@flipbeltchina.com", "harry2@flipbeltchina.com",
        "harry3@flipbeltchina.com", "harry8@flipbeltchina.com", "18770808500", "18958354558",
    ),
    "sina": ("cathee@flipbelt.com", "flipbelt@sina.com"),
    "yindao": ("destiny@flipbeltchina.com",),
    "yonyou": ("18958354558",),
    "ipr_platforms": ("2108804499@qq.com", "flipbelt@qq.com", "17365822471", "18958354558"),
    "ipr_master": (
        "2108804499@qq.com", "flipbelt@qq.com", "17629637042", "17767138101",
        "18058512831", "18958354558", "19106859583",
    ),
    "gs1": ("18958354558",),
    "patent": ("18958354558",),
    "mail": (
        "19106859583@163.com", "372311341@qq.com", "416910908@qq.com", "448141555@qq.com",
        "862590135@qq.com", "admin@flipbeltchina.com", "ben@flipbeltchina.com",
        "ben@gtpremium.com", "cathee@flipbeltchina.com", "cathee@gtpremium.com",
        "destiny@flipbeltchina.com", "dys@flipbeltchina.com", "emily@flipbeltchina.com",
        "flipbelt@sohu.com", "jane@flipbeltchina.com", "listen@flipbeltchina.com",
        "panpan@flipbeltchina.com", "raul@flipbeltchina.com", "retail@flipbeltchina.com",
        "shawn@flipbeltchina.com", "sherry@flipbeltchina.com", "thomas@flipbeltchina.com",
        "zxuqq@flipbeltchina.com", "19106859583",
    ),
}

# L6 is registered whenever a source names a concrete service or environment.
# Its platform relation is filled only where the source identifies that platform.
SERVICE_ROWS: tuple[dict[str, str | None], ...] = (
    {"key": "aliyun-cloud", "source": "aliyun", "name": "阿里云服务", "platform": "阿里云"},
    {"key": "aliyun-163-mail", "source": "aliyun", "name": "163邮箱服务", "platform": "163邮箱"},
    {"key": "guanyi-erp", "source": "guanyi", "name": "管易ERP服务", "platform": "管易ERP"},
    {"key": "jd-store", "source": "jd", "name": "京东店铺运营服务", "platform": "京东"},
    {"key": "jd-vc", "source": "jd", "name": "京东VC服务", "platform": "京东"},
    {"key": "jd-enterprise", "source": "jd", "name": "京东企业购服务", "platform": "京东"},
    {"key": "jushuitan", "source": "jushuitan", "name": "聚水潭服务", "platform": "聚水潭"},
    {"key": "yindao-assistant", "source": "jushuitan", "name": "影刀助手服务", "platform": "影刀"},
    {"key": "anjieyun", "source": "jushuitan", "name": "安捷云服务", "platform": "安捷云"},
    {"key": "cloud-warehouse", "source": "jushuitan", "name": "云仓服务", "platform": None},
    {"key": "sina-mail", "source": "sina", "name": "新浪邮箱服务", "platform": "新浪邮箱"},
    {"key": "weibo", "source": "sina", "name": "微博服务", "platform": "微博"},
    {"key": "yindao", "source": "yindao", "name": "影刀服务", "platform": "影刀"},
    {"key": "vpn", "source": "yindao", "name": "VPN服务（供应商待确认）", "platform": None},
    {"key": "yonyou", "source": "yonyou", "name": "用友YS云服务", "platform": "用友云"},
    {"key": "yuce", "source": "yuce", "name": "预策服务", "platform": "预策"},
    {"key": "yuce-zhenli", "source": "yuce", "name": "真理时刻业务环境", "platform": "预策"},
    {"key": "yuce-model", "source": "yuce", "name": "样板房业务环境", "platform": "预策"},
    {"key": "trademark", "source": "ipr_platforms", "name": "中国商标网服务", "platform": "中国商标网"},
    {"key": "zhichan", "source": "ipr_platforms", "name": "知蝉知识产权服务", "platform": "知蝉"},
    {"key": "douyin-ipr", "source": "ipr_platforms", "name": "抖音知识产权维权服务", "platform": "抖音"},
    {"key": "xiaohongshu-ipr", "source": "ipr_platforms", "name": "小红书知识产权维权服务", "platform": "小红书"},
    {"key": "pinduoduo-ipr", "source": "ipr_platforms", "name": "拼多多知识产权维权服务", "platform": "拼多多"},
    {"key": "jd-ipr", "source": "ipr_platforms", "name": "京东知识产权维权服务", "platform": "京东知识产权保护中心"},
    {"key": "copyright", "source": "ipr_master", "name": "著作权登记服务", "platform": "著作权登记系统"},
    {"key": "consumer-complaint", "source": "ipr_master", "name": "12315维权服务", "platform": "12315"},
    {"key": "gs1-service", "source": "gs1", "name": "中国物品编码中心GS1服务", "platform": "中国物品编码中心（GS1）"},
    {"key": "patent-search", "source": "patent", "name": "专利查询服务", "platform": "专利查询系统"},
    {"key": "netease-mail", "source": "mail", "name": "网易企业邮箱服务", "platform": "网易企业邮箱"},
    {"key": "sohu-mail", "source": "mail", "name": "搜狐邮箱服务", "platform": "搜狐邮箱"},
)

# The following L4 records are the narrow exception: their source combines a
# named company, a named platform and an account record.  Current validity and
# administrator are explicitly left pending rather than being invented.
NAMED_LEGAL_ENTITIES: tuple[dict[str, str], ...] = (
    {"code": "COL-L1-004", "name": "杭州京跑体育用品有限公司", "source": "ipr_master"},
    {"code": "COL-L1-005", "name": "杭州飞比特体育科技有限公司", "source": "ipr_master"},
)
TENANT_ROWS: tuple[dict[str, str], ...] = (
    {"key": "nb-feibit-jd-ipr", "source": "ipr_master", "name": "宁波飞比特体育用品有限公司 · 知产维权账号", "legal_entity": "宁波飞比特体育用品有限公司", "platform": "京东知识产权保护中心"},
    {"key": "hz-jingpao-jd-ipr", "source": "ipr_master", "name": "杭州京跑体育用品有限公司 · 知产维权账号", "legal_entity": "杭州京跑体育用品有限公司", "platform": "京东知识产权保护中心"},
    {"key": "hz-feibit-copyright", "source": "ipr_master", "name": "杭州飞比特体育科技有限公司 · 著作权登记账号", "legal_entity": "杭州飞比特体育科技有限公司", "platform": "著作权登记系统"},
)

# These are the only login accounts in the supplied files whose owning company
# platform account is also directly evidenced.  They are L4 child details,
# not L2 identities or L6 services.
ACCOUNT_ROWS: tuple[dict[str, str], ...] = (
    {
        "key": "nb-feibit-jd-ipr-2026",
        "tenant_key": "nb-feibit-jd-ipr",
        "source": "ipr_master",
        "display_name": "法务维权账号（2026）",
        "login_identifier": "flipbelt法务2026",
        "account_kind": "member_login",
        "account_role": "member",
    },
    {
        "key": "hz-jingpao-jd-ipr-2025",
        "tenant_key": "hz-jingpao-jd-ipr",
        "source": "ipr_master",
        "display_name": "法务维权账号（2025）",
        "login_identifier": "flipbelt法务2025",
        "account_kind": "member_login",
        "account_role": "member",
    },
    {
        "key": "hz-feibit-copyright",
        "tenant_key": "hz-feibit-copyright",
        "source": "ipr_master",
        "display_name": "著作权登记账号",
        "login_identifier": "hzfbt",
        "account_kind": "member_login",
        "account_role": "member",
    },
)

# These are redacted login facts from the source files.  They deliberately stay
# in the intake batch until an owning company and its L4 account are evidenced.
# A label containing multiple platforms means the file proves the login fact but
# does not prove which named platform it belongs to.
ACCOUNT_CANDIDATE_PLATFORM: dict[str, str] = {
    "aliyun": "阿里云 / 163邮箱（待确认具体平台）",
    "dingtalk": "钉钉",
    "guanyi": "管易ERP",
    "jd": "京东",
    "jushuitan": "聚水潭 / 影刀 / 安捷云（待确认具体平台）",
    "sina": "新浪邮箱 / 微博（待确认具体平台）",
    "yindao": "影刀",
    "yonyou": "用友云",
    "ipr_platforms": "知识产权维权平台（待确认具体平台）",
    "gs1": "中国物品编码中心（GS1）",
    "mail": "网易企业邮箱 / 搜狐邮箱（待确认具体平台）",
}


def _account_candidates_for_source(source_key: str) -> list[dict[str, Any]]:
    """Return safe candidate facts only; credentials are never represented."""
    source = next(row for row in SOURCE_ROWS if row["key"] == source_key)
    candidates = [
        {
            "platform_name": ACCOUNT_CANDIDATE_PLATFORM[source_key],
            "login_identifier": identifier,
            "evidence": [
                f"来源文件：{source['file']}",
                *source["evidence"],
            ],
            "confidence": float(source["confidence"]),
            "status": "待确认所属公司L4",
            "pending_reason": "原始资料仅证明平台与登录标识，未证明所属公司及公司平台账号。",
        }
        for identifier in IDENTITY_SOURCES.get(source_key, ())
        if source_key in ACCOUNT_CANDIDATE_PLATFORM
    ]
    for row in ACCOUNT_ROWS:
        if row["source"] != source_key:
            continue
        tenant = next(item for item in TENANT_ROWS if item["key"] == row["tenant_key"])
        candidates.append(
            {
                "platform_name": tenant["platform"],
                "login_identifier": row["login_identifier"],
                "evidence": [
                    f"来源文件：{source['file']}",
                    "公司名称、平台及账号标识同时出现。",
                ],
                "confidence": float(source["confidence"]),
                "status": "已归入L4",
                "pending_reason": "已由明确公司、平台和账号证据归入 L4 的账号与席位明细。",
                "assigned_l4_marker": f"l4:{tenant['key']}",
            }
        )
    return candidates


def refresh_aliyun_colleague_account_candidates(db: Session) -> dict[str, int]:
    """Persist redacted candidate facts without creating or reclassifying assets."""
    batch = _active_batch(db)
    if batch is None:
        raise ValueError("阿里云目录正式接入批次不存在")
    records = list(
        db.scalars(
            select(SourceImportRecord).where(
                SourceImportRecord.import_batch_id == batch.id,
                SourceImportRecord.archived_at.is_(None),
            )
        )
    )
    source_key_by_file = {row["file"]: row["key"] for row in SOURCE_ROWS}
    candidate_count = 0
    for record in records:
        source_key = source_key_by_file.get(record.source_identifier or "")
        if source_key is None:
            continue
        candidates = _account_candidates_for_source(source_key)
        for candidate in candidates:
            marker = candidate.pop("assigned_l4_marker", None)
            if marker:
                tenant_asset = _asset_for_marker(db, batch=batch, key=marker)
                if tenant_asset is not None:
                    candidate["assigned_l4_asset_id"] = str(tenant_asset.id)
                    candidate["assigned_l4_name"] = tenant_asset.name
        payload = dict(record.raw_payload or {})
        payload["account_candidates"] = candidates
        record.raw_payload = payload
        candidate_count += len(candidates)
    return {"source_records": len(records), "account_candidates": candidate_count}


def _normalize(value: str) -> str:
    return re.sub(r"[\s_\-·.()（）]+", "", value).casefold()


def _source_payload(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_file": row["file"],
        "suggested_layers": row["layers"],
        "evidence": row["evidence"],
        "safety": "已脱敏；未保存密码、密钥、Cookie、验证码或原始凭据文本",
    }


def _responsible_person(db: Session) -> Person:
    person = db.scalar(
        select(Person).where(Person.display_name == RESPONSIBLE_PERSON_NAME, Person.archived_at.is_(None))
    )
    if person is None:
        raise ValueError(f"缺少本批负责人：{RESPONSIBLE_PERSON_NAME}")
    return person


def _active_batch(db: Session) -> ImportBatch | None:
    return db.scalar(
        select(ImportBatch)
        .where(ImportBatch.file_name == BATCH_FILE_NAME, ImportBatch.status != "rolled_back")
        .order_by(ImportBatch.created_at.desc())
    )


def _identity_type(value: str) -> str:
    return "email" if "@" in value else "phone"


def _mask_identifier(value: str) -> str:
    if "@" in value:
        local, domain = value.split("@", 1)
        return f"{local[:2]}***@{domain}"
    return f"{value[:3]}****{value[-4:]}" if len(value) >= 7 else "***"


def _asset_type_id(db: Session, code: str) -> UUID:
    from app.models import AssetType

    asset_type = db.scalar(
        select(AssetType).where(AssetType.code == code, AssetType.archived_at.is_(None))
    )
    if asset_type is None:
        raise ValueError(f"缺少资产类型：{code}")
    return asset_type.id


def _next_asset_code(db: Session, prefix: str) -> str:
    number = 1
    while True:
        candidate = f"{prefix}-{number:03d}"
        if db.scalar(select(Asset.id).where(Asset.asset_code == candidate)) is None:
            return candidate
        number += 1


def _summary(batch: ImportBatch) -> dict[str, Any]:
    summary = next((item for item in batch.errors if item.get("kind") == "commit_summary"), None)
    if summary is None:
        raise ValueError("批次缺少可回滚清单")
    return summary


def _asset_for_marker(db: Session, *, batch: ImportBatch, key: str) -> Asset | None:
    marker = db.scalar(
        select(AssetIdentifier).where(
            AssetIdentifier.namespace == f"colleague_aliyun:{batch.id}",
            AssetIdentifier.identifier_type == "import_key",
            AssetIdentifier.identifier_value == key,
            AssetIdentifier.archived_at.is_(None),
        )
    )
    return db.get(Asset, marker.asset_id) if marker is not None else None


def _mark_asset(
    db: Session,
    *,
    batch: ImportBatch,
    source: SourceImportRecord,
    key: str,
    asset: Asset,
) -> None:
    if _asset_for_marker(db, batch=batch, key=key) is None:
        db.add(
            AssetIdentifier(
                asset_id=asset.id,
                namespace=f"colleague_aliyun:{batch.id}",
                identifier_type="import_key",
                identifier_value=key,
                verification_status="pending",
                source_import_record_id=source.id,
                confidentiality="internal",
            )
        )


def _ensure_responsible(db: Session, *, asset: Asset, person: Person) -> None:
    row = db.scalar(
        select(AssetResponsibility).where(
            AssetResponsibility.asset_id == asset.id,
            AssetResponsibility.role_type == "responsible",
            AssetResponsibility.archived_at.is_(None),
        )
    )
    if row is None:
        db.add(
            AssetResponsibility(
                asset_id=asset.id,
                person_id=person.id,
                role_type="responsible",
                is_primary=True,
            )
        )


def _new_asset(
    db: Session,
    *,
    batch: ImportBatch,
    source: SourceImportRecord,
    key: str,
    name: str,
    asset_type_code: str,
    legal_entity_id: UUID | None,
    responsible: Person,
    description: str,
) -> tuple[Asset, bool]:
    existing = _asset_for_marker(db, batch=batch, key=key)
    if existing is not None:
        return existing, False
    asset = Asset(
        asset_code=_next_asset_code(db, f"COL-{asset_type_code.upper()[:8]}"),
        name=name[:200],
        asset_type_id=_asset_type_id(db, asset_type_code),
        legal_entity_id=legal_entity_id,
        ownership_scope="pending",
        created_by_person_id=responsible.id,
        review_status="pending_review",
        status="draft",
        criticality="normal",
        confidentiality="internal",
        source_type="import",
        description=description,
    )
    db.add(asset)
    db.flush()
    ensure_internal_identifier(db, asset)
    _mark_asset(db, batch=batch, source=source, key=key, asset=asset)
    _ensure_responsible(db, asset=asset, person=responsible)
    return asset, True


def _get_or_create_provider(db: Session, platform: Platform) -> tuple[Provider, bool]:
    if platform.provider_id:
        provider = db.get(Provider, platform.provider_id)
        if provider is not None and provider.archived_at is None:
            return provider, False
    provider = db.scalar(
        select(Provider).where(Provider.name == platform.name, Provider.archived_at.is_(None))
    )
    if provider is not None:
        return provider, False
    code = f"intake-{hashlib.sha256(platform.name.encode('utf-8')).hexdigest()[:16]}"
    provider = Provider(code=code, name=platform.name, website=platform.website)
    db.add(provider)
    db.flush()
    return provider, True


def _get_or_create_product(
    db: Session, *, provider: Provider, name: str
) -> tuple[ServiceProduct, bool]:
    code = f"intake-{hashlib.sha256(name.encode('utf-8')).hexdigest()[:16]}"
    product = db.scalar(
        select(ServiceProduct).where(
            ServiceProduct.provider_id == provider.id,
            ServiceProduct.code == code,
            ServiceProduct.archived_at.is_(None),
        )
    )
    if product is not None:
        return product, False
    product = ServiceProduct(
        provider_id=provider.id,
        code=code,
        name=name[:200],
        service_category="external_service",
        billing_mode="unknown",
    )
    db.add(product)
    db.flush()
    return product, True


def _archive_batch_assets_by_marker_prefix(
    db: Session, *, batch: ImportBatch, prefix: str
) -> list[UUID]:
    """Archive only a previous interpretation, keeping the source rows intact."""
    markers = list(
        db.scalars(
            select(AssetIdentifier).where(
                AssetIdentifier.namespace == f"colleague_aliyun:{batch.id}",
                AssetIdentifier.identifier_type == "import_key",
                AssetIdentifier.identifier_value.like(f"{prefix}%"),
                AssetIdentifier.archived_at.is_(None),
            )
        )
    )
    asset_ids = {row.asset_id for row in markers}
    if not asset_ids:
        return []
    now = datetime.now(UTC)
    for profile in db.scalars(
        select(RegistrationIdentityProfile).where(
            RegistrationIdentityProfile.asset_id.in_(asset_ids),
            RegistrationIdentityProfile.archived_at.is_(None),
        )
    ):
        profile.archived_at = now
    for instance in db.scalars(
        select(ServiceInstance).where(
            ServiceInstance.asset_id.in_(asset_ids),
            ServiceInstance.archived_at.is_(None),
        )
    ):
        instance.archived_at = now
    for responsibility in db.scalars(
        select(AssetResponsibility).where(
            AssetResponsibility.asset_id.in_(asset_ids),
            AssetResponsibility.archived_at.is_(None),
        )
    ):
        responsibility.archived_at = now
    for identifier in db.scalars(
        select(AssetIdentifier).where(
            AssetIdentifier.asset_id.in_(asset_ids),
            AssetIdentifier.archived_at.is_(None),
        )
    ):
        identifier.archived_at = now
    for asset in db.scalars(
        select(Asset).where(Asset.id.in_(asset_ids), Asset.archived_at.is_(None))
    ):
        asset.archived_at = now
        asset.status = "archived"
    return list(asset_ids)


def reclassify_aliyun_colleague_as_l4_accounts(
    db: Session, *, actor_user_id: UUID
) -> dict[str, Any]:
    """Replace generic imported L2/L6 guesses with verified L4 child accounts.

    This is deliberately narrow: platform-login material is retained in the
    source batch until it can be attached to an evidenced company L4.  It does
    not turn every email or password-bearing line into a canonical object.
    """
    batch = _active_batch(db)
    if batch is None:
        raise ValueError("阿里云目录正式接入批次不存在")
    # This only adds redacted intake visibility.  It never turns an unassigned
    # login fact into an L2, L4, or L6 object.
    refresh_aliyun_colleague_account_candidates(db)
    responsible = _responsible_person(db)
    source_records = {
        record.source_identifier: record
        for record in db.scalars(
            select(SourceImportRecord).where(
                SourceImportRecord.import_batch_id == batch.id,
                SourceImportRecord.archived_at.is_(None),
            )
        )
    }
    source_by_key = {
        row["key"]: source_records[row["file"]]
        for row in SOURCE_ROWS
        if row["file"] in source_records
    }
    if len(source_by_key) != len(SOURCE_ROWS):
        raise ValueError("批次来源记录不完整，不能重分类")

    summary = _summary(batch)
    retired_l2 = _archive_batch_assets_by_marker_prefix(db, batch=batch, prefix="l2:")
    # Any legacy automatic L6 interpretation is also retired if it is ever
    # present again; a login credential alone must not recreate it.
    retired_l6 = _archive_batch_assets_by_marker_prefix(db, batch=batch, prefix="l6:")
    tracked_asset_ids = [
        raw_id
        for raw_id in summary.get("created_asset_ids", [])
        if UUID(raw_id) not in {*retired_l2, *retired_l6}
    ]
    tenant_by_key: dict[str, PlatformTenant] = {}
    tenant_asset_by_key: dict[str, Asset] = {}
    for row in TENANT_ROWS:
        tenant_asset = _asset_for_marker(db, batch=batch, key=f"l4:{row['key']}")
        tenant = (
            db.scalar(
                select(PlatformTenant).where(
                    PlatformTenant.asset_id == tenant_asset.id,
                    PlatformTenant.archived_at.is_(None),
                )
            )
            if tenant_asset is not None
            else None
        )
        if tenant is None or tenant_asset is None:
            raise ValueError(f"缺少可承接账号的L4证据对象：{row['name']}")
        tenant_by_key[row["key"]] = tenant
        tenant_asset_by_key[row["key"]] = tenant_asset

    created_accounts: list[str] = list(summary.get("created_account_ids", []))
    added_accounts = 0
    for row in ACCOUNT_ROWS:
        source = source_by_key[row["source"]]
        tenant = tenant_by_key[row["tenant_key"]]
        tenant_asset = tenant_asset_by_key[row["tenant_key"]]
        account_asset, created = _new_asset(
            db,
            batch=batch,
            source=source,
            key=f"account:{row['key']}",
            name=f"{tenant_asset.name} · {row['display_name']}",
            asset_type_code="platform_account",
            legal_entity_id=tenant.legal_entity_id,
            responsible=responsible,
            description=(
                f"来源：阿里云目录/{source.source_identifier}明确出现的L4子账号。"
                "仅登记登录标识；密码不入库，L6服务需另有独立证据。"
            ),
        )
        account = db.scalar(select(Account).where(Account.asset_id == account_asset.id))
        if account is None:
            account = Account(
                asset_id=account_asset.id,
                platform_tenant_id=tenant.id,
                login_identifier=row["login_identifier"],
                normalized_login_identifier=row["login_identifier"].lower(),
                account_type="shared_business",
                registration_identity_type="account_detail",
                mfa_status="unknown",
                privilege_level="normal",
                account_kind=row["account_kind"],
                login_method="password_vault",
                account_role=row["account_role"],
                legacy_source_id=source.source_identifier,
            )
            db.add(account)
            db.flush()
            created_accounts.append(str(account.id))
        if created:
            tracked_asset_ids.append(str(account_asset.id))
            added_accounts += 1

    summary.update(
        {
            "created_asset_ids": tracked_asset_ids,
            "created_account_ids": created_accounts,
            "created_registration_identity_profile_ids": [],
            "l2_created": 0,
            "l6_created": 0,
            "l5_created": 0,
            "account_details_created": len(created_accounts),
            "generic_l2_retired": len(retired_l2),
            "generic_l6_retired": len(retired_l6),
            "account_first_principle": (
                "平台下的登录账号、管理员和子账号是L4账号明细；"
                "仅凭账号资料不创建L2或L6。L6必须有独立套餐、资源、API、环境或等效生命周期证据。"
            ),
        }
    )
    batch.errors = [summary]
    batch.status = "partially_committed"
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="import.aliyun_colleague.reclassify_account_first",
            object_type="import_batch",
            object_id=batch.id,
            after_data={
                "retired_l2": len(retired_l2),
                "retired_l6": len(retired_l6),
                "new_account_details": added_accounts,
                "preserved_layers": [1, 3, 4],
            },
        )
    )
    db.commit()
    return {
        "batch_id": str(batch.id),
        "status": batch.status,
        "retired_l2": len(retired_l2),
        "retired_l6": len(retired_l6),
        "account_details": len(created_accounts),
        "new_account_details": added_accounts,
        "l6_created": 0,
    }


def reconcile_aliyun_colleague_import(db: Session, *, actor_user_id: UUID) -> dict[str, Any]:
    """Complete this batch under the independent-six-layer evidence rule.

    A layer is created whenever its own source evidence is sufficient.  It is
    never withheld merely because another layer (especially L4) is unknown.
    """
    batch = _active_batch(db)
    if batch is None:
        return commit_aliyun_colleague_import(db, actor_user_id=actor_user_id)
    responsible = _responsible_person(db)
    source_records = {
        record.source_identifier: record
        for record in db.scalars(
            select(SourceImportRecord).where(
                SourceImportRecord.import_batch_id == batch.id,
                SourceImportRecord.archived_at.is_(None),
            )
        )
    }
    source_by_key = {
        row["key"]: source_records[row["file"]]
        for row in SOURCE_ROWS
        if row["file"] in source_records
    }
    if len(source_by_key) != len(SOURCE_ROWS):
        raise ValueError("批次来源记录不完整，不能执行增量确认入库")
    summary = _summary(batch)
    created_assets: list[str] = list(summary.get("created_asset_ids", []))
    created_profiles: list[str] = list(summary.get("created_registration_identity_profile_ids", []))
    created_tenants: list[str] = list(summary.get("created_platform_tenant_ids", []))
    created_instances: list[str] = list(summary.get("created_service_instance_ids", []))
    created_products: list[str] = list(summary.get("created_service_product_ids", []))
    created_providers: list[str] = list(summary.get("created_provider_ids", []))
    created_legal_ids: list[str] = list(summary.get("created_legal_entity_ids", []))

    entities = {
        entity.name: entity
        for entity in db.scalars(select(LegalEntity).where(LegalEntity.archived_at.is_(None)))
    }
    for row in NAMED_LEGAL_ENTITIES:
        if row["name"] in entities:
            continue
        entity = LegalEntity(code=row["code"], name=row["name"], status="pending_verification")
        db.add(entity)
        db.flush()
        db.add(
            LegalEntityProfile(
                legal_entity_id=entity.id,
                entity_type="company",
                jurisdiction="中国",
                registration_status="pending_verification",
                source_note=(
                    f"来源：阿里云目录/{source_by_key[row['source']].source_identifier}；"
                    "名称随公司账号资料出现，待补充统一社会信用代码与登记状态。"
                ),
                verification_status="pending",
            )
        )
        entities[entity.name] = entity
        created_legal_ids.append(str(entity.id))

    platforms = {
        _normalize(platform.name): platform
        for platform in db.scalars(select(Platform).where(Platform.archived_at.is_(None)))
    }
    identity_count = 0
    for source_key, values in IDENTITY_SOURCES.items():
        source = source_by_key[source_key]
        for value in values:
            normalized = value.strip().lower()
            fingerprint = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
            profile = db.scalar(
                select(RegistrationIdentityProfile).where(
                    RegistrationIdentityProfile.identifier_fingerprint == fingerprint
                )
            )
            if profile is not None:
                continue
            asset, created = _new_asset(
                db,
                batch=batch,
                source=source,
                key=f"l2:{fingerprint}",
                name=f"{_identity_type(value) == 'email' and '邮箱' or '手机号'} · {value}",
                asset_type_code="registration_identity",
                legal_entity_id=None,
                responsible=responsible,
                description=(
                    f"来源：阿里云目录/{source.source_identifier}明确出现的"
                    f"{_identity_type(value) == 'email' and '邮箱' or '手机号'}身份；"
                    "仅登记L2，不据此推导法人、L4平台账号或L5授权。"
                ),
            )
            if not created:
                continue
            profile = RegistrationIdentityProfile(
                asset_id=asset.id,
                identity_type=_identity_type(value),
                identifier_value=value,
                identifier_masked=_mask_identifier(value),
                identifier_fingerprint=fingerprint,
                source_nature="unknown",
                verification_status="pending",
            )
            db.add(profile)
            db.flush()
            created_assets.append(str(asset.id))
            created_profiles.append(str(profile.id))
            identity_count += 1

    tenant_assets: dict[str, Asset] = {}
    tenant_count = 0
    for row in TENANT_ROWS:
        source = source_by_key[row["source"]]
        platform = platforms.get(_normalize(row["platform"]))
        entity = entities.get(row["legal_entity"])
        if platform is None or entity is None:
            raise ValueError(f"L4依赖的法人或平台不存在：{row['name']}")
        asset, created = _new_asset(
            db,
            batch=batch,
            source=source,
            key=f"l4:{row['key']}",
            name=row["name"],
            asset_type_code="platform_tenant",
            legal_entity_id=entity.id,
            responsible=responsible,
            description=(
                f"来源：阿里云目录/{source.source_identifier}，明确同时出现公司、平台和账号事实。"
                "当前有效性、主管理员及账号标识待核验；未保存任何凭据。"
            ),
        )
        tenant_assets[row["key"]] = asset
        tenant = db.scalar(select(PlatformTenant).where(PlatformTenant.asset_id == asset.id))
        if tenant is None:
            tenant = PlatformTenant(
                asset_id=asset.id,
                platform_id=platform.id,
                legal_entity_id=entity.id,
                external_identifier_type="企业账号（账号标识见受控来源）",
                ownership_nature="company_owned",
                account_scope="primary_account",
                verification_status="pending",
                evidence_note=(
                    f"来源：阿里云目录/{source.source_identifier}；"
                    "仅确认公司+平台+账号事实，不保存账号密码或其他凭据。"
                ),
            )
            db.add(tenant)
            db.flush()
            created_tenants.append(str(tenant.id))
        if created:
            created_assets.append(str(asset.id))
            tenant_count += 1

    service_count = 0
    for row in SERVICE_ROWS:
        source = source_by_key[str(row["source"])]
        platform_name = row["platform"]
        platform = platforms.get(_normalize(str(platform_name))) if platform_name else None
        asset, created = _new_asset(
            db,
            batch=batch,
            source=source,
            key=f"l6:{row['key']}",
            name=str(row["name"]),
            asset_type_code="saas_subscription",
            legal_entity_id=None,
            responsible=responsible,
            description=(
                f"来源：阿里云目录/{source.source_identifier}明确出现的具体服务或业务环境；"
                + ("已关联明确平台。" if platform else "平台供应商未明确，暂不虚构L3关系。")
                + " 当前是否在用、法人归属及人员授权待核验。",
            ),
        )
        instance = db.scalar(select(ServiceInstance).where(ServiceInstance.asset_id == asset.id))
        if instance is None:
            if platform is None:
                provider = db.scalar(
                    select(Provider).where(
                        Provider.code == "intake-unknown-provider", Provider.archived_at.is_(None)
                    )
                )
                provider_created = False
                if provider is None:
                    provider = Provider(code="intake-unknown-provider", name="供应商待确认")
                    db.add(provider)
                    db.flush()
                    provider_created = True
            else:
                provider, provider_created = _get_or_create_provider(db, platform)
            if provider_created:
                created_providers.append(str(provider.id))
            product, product_created = _get_or_create_product(db, provider=provider, name=str(row["name"]))
            if product_created:
                created_products.append(str(product.id))
            instance = ServiceInstance(
                asset_id=asset.id,
                service_product_id=product.id,
                purchase_platform_id=platform.id if platform else None,
                subscription_name=str(row["name"]),
            )
            db.add(instance)
            db.flush()
            created_instances.append(str(instance.id))
        if created:
            created_assets.append(str(asset.id))
            service_count += 1

    summary.update(
        {
            "created_legal_entity_ids": created_legal_ids,
            "created_asset_ids": created_assets,
            "created_registration_identity_profile_ids": created_profiles,
            "created_platform_tenant_ids": created_tenants,
            "created_service_instance_ids": created_instances,
            "created_service_product_ids": created_products,
            "created_provider_ids": created_providers,
            "independent_layer_principle": (
                "每条来源事实独立映射至可证明层级；缺少L1/L3/L4或上下游关系，不阻断L2/L6入库；"
                "关系仅在来源明确时写入。"
            ),
            "l2_created": len(created_profiles),
            "l4_created": len(created_tenants),
            "l6_created": len(created_instances),
            "l5_created": 0,
        }
    )
    batch.errors = [summary]
    batch.status = "partially_committed"
    batch.success_count = len(SOURCE_ROWS)
    batch.error_count = 0
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="import.aliyun_colleague.reconcile_independent_layers",
            object_type="import_batch",
            object_id=batch.id,
            after_data={
                "batch_id": str(batch.id),
                "new_l2": identity_count,
                "new_l4": tenant_count,
                "new_l6": service_count,
                "l5_created": 0,
            },
        )
    )
    db.commit()
    return {
        "batch_id": str(batch.id),
        "status": batch.status,
        "l2_created": len(created_profiles),
        "l4_created": len(created_tenants),
        "l6_created": len(created_instances),
        "l5_created": 0,
        "new_l2": identity_count,
        "new_l4": tenant_count,
        "new_l6": service_count,
        "principle": summary["independent_layer_principle"],
    }


def commit_aliyun_colleague_import(db: Session, *, actor_user_id: UUID) -> dict[str, Any]:
    """Write the confirmed batch; safely returns its prior result when re-run."""
    if existing := _active_batch(db):
        # Counts in ImportBatch describe processed source rows, not the number of
        # directory records derived from those rows.
        if existing.total_count != len(SOURCE_ROWS) or existing.success_count != len(SOURCE_ROWS):
            existing.total_count = len(SOURCE_ROWS)
            existing.success_count = len(SOURCE_ROWS)
            existing.error_count = 0
            db.commit()
        result = reclassify_aliyun_colleague_as_l4_accounts(db, actor_user_id=actor_user_id)
        result["idempotent"] = True
        return result

    responsible = _responsible_person(db)
    batch = ImportBatch(
        file_name=BATCH_FILE_NAME,
        status="committing",
        total_count=len(SOURCE_ROWS),
        success_count=0,
        error_count=0,
        errors=[],
    )
    db.add(batch)
    db.flush()

    source_records: dict[str, SourceImportRecord] = {}
    for row in SOURCE_ROWS:
        record = SourceImportRecord(
            import_batch_id=batch.id,
            source_kind="colleague_aliyun_directory",
            source_identifier=row["file"],
            raw_payload=_source_payload(row),
            suggested_object_type="intake_evidence",
            suggested_name=row["name"],
            confidence=Decimal(row["confidence"]),
            mapping_status=row["disposition"],
            review_note=row["note"],
        )
        db.add(record)
        source_records[row["key"]] = record
    db.flush()

    created_legal_ids: list[str] = []
    reused_legal_ids: list[str] = []
    for item in LEGAL_ENTITIES:
        identifier = db.scalar(
            select(LegalEntityIdentifier).where(
                LegalEntityIdentifier.namespace == "cn",
                LegalEntityIdentifier.identifier_type == "统一社会信用代码",
                LegalEntityIdentifier.identifier_value == item["uscc"],
                LegalEntityIdentifier.archived_at.is_(None),
            )
        )
        entity = db.get(LegalEntity, identifier.legal_entity_id) if identifier else None
        if entity is None:
            entity = db.scalar(
                select(LegalEntity).where(
                    LegalEntity.name == item["name"], LegalEntity.archived_at.is_(None)
                )
            )
        if entity is None:
            entity = LegalEntity(code=item["code"], name=item["name"], status="pending_verification")
            db.add(entity)
            db.flush()
            db.add(
                LegalEntityProfile(
                    legal_entity_id=entity.id,
                    entity_type="company",
                    jurisdiction="中国",
                    registration_status="pending_verification",
                    source_note=(
                        "来源：阿里云目录/专利查询.txt；接入负责人：惜君-吴旭骏。"
                        "仅有名称与统一社会信用代码证据，待补充登记状态等法人资料。"
                    ),
                    verification_status="pending",
                )
            )
            db.add(
                LegalEntityIdentifier(
                    legal_entity_id=entity.id,
                    namespace="cn",
                    identifier_type="统一社会信用代码",
                    identifier_value=item["uscc"],
                    is_primary=True,
                    verification_status="pending",
                    source_note="来源：阿里云目录/专利查询.txt",
                )
            )
            created_legal_ids.append(str(entity.id))
        else:
            reused_legal_ids.append(str(entity.id))

    existing_platforms = {
        _normalize(platform.name): platform
        for platform in db.scalars(select(Platform).where(Platform.archived_at.is_(None)))
    }
    created_platform_ids: list[str] = []
    reused_platform_ids: list[str] = []
    for index, name in enumerate(PLATFORM_NAMES, start=1):
        platform = existing_platforms.get(_normalize(name))
        if platform is None:
            platform = Platform(
                code=f"colleague-aliyun-{index:02d}",
                name=name,
                category="external_platform",
                review_status="pending_verification",
                description=(
                    "来源：惜君负责的阿里云目录资料；仅确认平台名称出现。"
                    "未据此推导公司租户、账号、服务实例或人员授权。"
                ),
                submitted_by_person_id=responsible.id,
            )
            db.add(platform)
            db.flush()
            created_platform_ids.append(str(platform.id))
            existing_platforms[_normalize(name)] = platform
        else:
            reused_platform_ids.append(str(platform.id))

    summary = {
        "kind": "commit_summary",
        "source_location": SOURCE_LOCATION,
        "responsible_person": RESPONSIBLE_PERSON_NAME,
        "source_records_retained": len(source_records),
        "legal_entities_created": len(created_legal_ids),
        "legal_entities_reused": len(reused_legal_ids),
        "platforms_created": len(created_platform_ids),
        "platforms_reused": len(reused_platform_ids),
        "rows_pending_confirmation": 14,
        "rows_skipped": 1,
        "created_legal_entity_ids": created_legal_ids,
        "created_platform_ids": created_platform_ids,
        "principle": "仅写入有明确实体证据的L1和L3；不以登录资料推导L4，不以名称推导L5。",
    }
    batch.status = "partially_committed"
    batch.success_count = len(SOURCE_ROWS)
    batch.errors = [summary]

    developer_batch = db.scalar(
        select(DeveloperIntakeBatch).where(DeveloperIntakeBatch.title == DEVELOPER_BATCH_TITLE)
    )
    if developer_batch is not None:
        developer_batch.status = "partially_committed"
        developer_batch.review_note = (
            "正式接入批次已建立：L1和L3已按证据入库；"
            "L2/L4/L5/L6候选继续待人工确认，未保存任何凭据。"
        )
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="import.aliyun_colleague.commit",
            object_type="import_batch",
            object_id=batch.id,
            after_data=summary,
        )
    )
    db.commit()
    result = reclassify_aliyun_colleague_as_l4_accounts(db, actor_user_id=actor_user_id)
    result["idempotent"] = False
    return result


def rollback_aliyun_colleague_import(db: Session, *, batch_id: UUID, actor_user_id: UUID) -> dict[str, Any]:
    """Archive only objects explicitly created by this import batch."""
    batch = db.get(ImportBatch, batch_id)
    if batch is None or batch.file_name != BATCH_FILE_NAME:
        raise ValueError("不是阿里云目录同事资料正式接入批次")
    if batch.status == "rolled_back":
        return {"batch_id": str(batch.id), "status": batch.status, "idempotent": True}
    summary = _summary(batch)

    now = datetime.now(UTC)
    blocked: list[str] = []
    created_asset_ids = {UUID(raw_id) for raw_id in summary.get("created_asset_ids", [])}
    created_instance_ids = {UUID(raw_id) for raw_id in summary.get("created_service_instance_ids", [])}
    created_product_ids = {UUID(raw_id) for raw_id in summary.get("created_service_product_ids", [])}

    # Do not partially roll back if someone has already attached new, unrelated
    # records to an entity, platform, product, or provider created by this batch.
    for raw_id in summary.get("created_legal_entity_ids", []):
        entity = db.get(LegalEntity, raw_id)
        if entity is None or entity.archived_at is not None:
            continue
        foreign_asset = db.scalar(
            select(Asset.id).where(
                Asset.legal_entity_id == entity.id,
                Asset.archived_at.is_(None),
                Asset.id.not_in(created_asset_ids) if created_asset_ids else True,
            )
        )
        if foreign_asset:
            blocked.append(f"法人 {entity.name} 已新增非本批资产")
    for raw_id in summary.get("created_platform_ids", []):
        platform = db.get(Platform, raw_id)
        if platform is None or platform.archived_at is not None:
            continue
        foreign_tenant = db.scalar(
            select(PlatformTenant.id)
            .join(Asset, Asset.id == PlatformTenant.asset_id)
            .where(
                PlatformTenant.platform_id == platform.id,
                PlatformTenant.archived_at.is_(None),
                Asset.id.not_in(created_asset_ids) if created_asset_ids else True,
            )
        )
        if foreign_tenant:
            blocked.append(f"平台 {platform.name} 已新增非本批L4")
    for raw_id in summary.get("created_service_product_ids", []):
        product = db.get(ServiceProduct, raw_id)
        if product is None or product.archived_at is not None:
            continue
        foreign_instance = db.scalar(
            select(ServiceInstance.id).where(
                ServiceInstance.service_product_id == product.id,
                ServiceInstance.archived_at.is_(None),
                ServiceInstance.id.not_in(created_instance_ids) if created_instance_ids else True,
            )
        )
        if foreign_instance:
            blocked.append(f"服务产品 {product.name} 已新增非本批实例")
    archived_legal = 0
    if blocked:
        return {"batch_id": str(batch.id), "status": batch.status, "blocked": blocked}

    archived_assets = 0
    if created_asset_ids:
        for asset in db.scalars(select(Asset).where(Asset.id.in_(created_asset_ids))):
            if asset.archived_at is None:
                asset.archived_at = now
                asset.status = "archived"
                archived_assets += 1
        for row in db.scalars(
            select(AssetIdentifier).where(
                AssetIdentifier.asset_id.in_(created_asset_ids),
                AssetIdentifier.archived_at.is_(None),
            )
        ):
            row.archived_at = now
        for row in db.scalars(
            select(AssetResponsibility).where(
                AssetResponsibility.asset_id.in_(created_asset_ids),
                AssetResponsibility.archived_at.is_(None),
            )
        ):
            row.archived_at = now
        for row in db.scalars(
            select(RegistrationIdentityProfile).where(
                RegistrationIdentityProfile.asset_id.in_(created_asset_ids),
                RegistrationIdentityProfile.archived_at.is_(None),
            )
        ):
            row.archived_at = now
        for row in db.scalars(
            select(PlatformTenant).where(
                PlatformTenant.asset_id.in_(created_asset_ids),
                PlatformTenant.archived_at.is_(None),
            )
        ):
            row.archived_at = now
        for row in db.scalars(
            select(Account).where(
                Account.asset_id.in_(created_asset_ids),
                Account.archived_at.is_(None),
            )
        ):
            row.archived_at = now
        for row in db.scalars(
            select(ServiceInstance).where(
                ServiceInstance.asset_id.in_(created_asset_ids),
                ServiceInstance.archived_at.is_(None),
            )
        ):
            row.archived_at = now

    for raw_id in summary.get("created_service_product_ids", []):
        product = db.get(ServiceProduct, raw_id)
        if product is not None and product.archived_at is None:
            product.archived_at = now
    for raw_id in summary.get("created_provider_ids", []):
        provider = db.get(Provider, raw_id)
        if provider is not None and provider.archived_at is None:
            provider.archived_at = now

    for raw_id in summary.get("created_legal_entity_ids", []):
        entity = db.get(LegalEntity, raw_id)
        if entity is None or entity.archived_at is not None:
            continue
        entity.archived_at = now
        for identifier in db.scalars(
            select(LegalEntityIdentifier).where(
                LegalEntityIdentifier.legal_entity_id == entity.id,
                LegalEntityIdentifier.archived_at.is_(None),
            )
        ):
            identifier.archived_at = now
        profile = db.scalar(
            select(LegalEntityProfile).where(LegalEntityProfile.legal_entity_id == entity.id)
        )
        if profile is not None:
            profile.archived_at = now
        archived_legal += 1

    archived_platforms = 0
    for raw_id in summary.get("created_platform_ids", []):
        platform = db.get(Platform, raw_id)
        if platform is not None and platform.archived_at is None:
            platform.archived_at = now
            archived_platforms += 1

    for record in db.scalars(
        select(SourceImportRecord).where(
            SourceImportRecord.import_batch_id == batch.id,
            SourceImportRecord.archived_at.is_(None),
        )
    ):
        record.archived_at = now
    batch.status = "rolled_back"
    developer_batch = db.scalar(
        select(DeveloperIntakeBatch).where(DeveloperIntakeBatch.title == DEVELOPER_BATCH_TITLE)
    )
    if developer_batch is not None:
        developer_batch.status = "staged"
    result = {
        "batch_id": str(batch.id),
        "status": batch.status,
        "archived_legal_entities": archived_legal,
        "archived_platforms": archived_platforms,
        "archived_assets": archived_assets,
        "archived_source_records": len(SOURCE_ROWS),
    }
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action="import.aliyun_colleague.rollback",
            object_type="import_batch",
            object_id=batch.id,
            after_data=result,
        )
    )
    db.commit()
    return result
