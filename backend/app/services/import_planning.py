"""Rule-based, reviewable six-layer planning for incoming source records.

The planner deliberately creates proposals only.  It never writes canonical assets,
people, accounts, or relations; a later explicit commit service is responsible for
that transition after dry-run and human review.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from decimal import Decimal
from typing import Any

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import (
    Asset,
    AssetIdentifier,
    Department,
    ImportAnalysis,
    ImportBatch,
    ImportProposedObject,
    ImportProposedRelation,
    Person,
    Platform,
    RelationDefinition,
    SourceImportRecord,
)

ANALYZER_VERSION = "six-layer-rules-v1"
AI_ANALYZER_VERSION = "deepseek-six-layer-v1"
AI_OBJECT_TYPES = {
    "registration_identity", "platform", "platform_account", "access_grant", "service_instance",
    "resource", "internal_system", "expense_entry", "workflow_request",
    "payment_method_reference", "budget_snapshot", "reimbursement_request",
}
FINANCE_OBJECT_TYPES = {
    "expense_entry",
    "workflow_request",
    "payment_method_reference",
    "budget_snapshot",
    "reimbursement_request",
}
PLATFORM_ALIASES = (
    ("阿里云", "阿里云"),
    ("腾讯云", "腾讯云"),
    ("华为云", "华为云"),
    ("openai", "OpenAI"),
    ("chatgpt", "OpenAI"),
    ("anthropic", "Anthropic"),
    ("claude", "Anthropic"),
    ("google", "Google"),
    ("gemini", "Google"),
    ("yishangcloud", "yishangcloud"),
    ("xai", "xAI"),
    ("grok", "xAI"),
    ("deepseek", "DeepSeek"),
    ("钉钉", "钉钉"),
    ("悟空", "钉钉"),
)


class AIImportError(Exception):
    """An AI enhancement error that must not affect the rule-based plan."""


def _ai_row(record: SourceImportRecord) -> dict[str, object]:
    return {
        "source_record_id": str(record.id),
        "source_identifier": record.source_identifier,
        "raw": record.raw_payload,
        "current_suggestion": {
            "object_type": record.suggested_object_type,
            "name": record.suggested_name,
            "confidence": float(record.confidence or 0),
        },
    }


def _ai_catalog(db: Session) -> dict[str, list[str]]:
    """Supply a compact catalogue, never unrelated raw records or secrets."""
    return {
        "platforms": [f"{item.code}: {item.name}" for item in db.scalars(select(Platform))],
        "assets": [f"{item.asset_code}: {item.name}" for item in db.scalars(select(Asset))],
        "people": [item.display_name for item in db.scalars(select(Person))],
        "departments": [item.name for item in db.scalars(select(Department))],
    }


def _ai_response_content(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        result = json.loads(content)
    except (IndexError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AIImportError("模型未返回可解析的 JSON 分类结果") from exc
    if not isinstance(result, dict) or not isinstance(result.get("records"), list):
        raise AIImportError("模型结果缺少 records 数组")
    return result


def enhance_import_records_with_ai(db: Session, batch: ImportBatch) -> dict[str, object]:
    """Use DeepSeek to enrich source hints before the normal rule planner runs."""
    settings = get_settings()
    if not settings.ai_import_enabled:
        raise AIImportError("AI 资料分析尚未启用")
    if missing := settings.ai_import_missing_settings():
        raise AIImportError(f"AI 资料分析缺少配置：{', '.join(missing)}")
    records = list(db.scalars(select(SourceImportRecord).where(
        SourceImportRecord.import_batch_id == batch.id,
        SourceImportRecord.archived_at.is_(None),
    )))
    if not records:
        raise AIImportError("该批次没有可分析的原始资料")

    by_id = {str(record.id): record for record in records}
    updated = 0
    request_count = 0
    system_prompt = (
        "你是集团账号与数字资产管理中台的资料接入分类器。对象类型只能是："
        "registration_identity、platform、platform_account、access_grant、service_instance、"
        "resource、internal_system、expense_entry、workflow_request、payment_method_reference、"
        "budget_snapshot、reimbursement_request。只返回 JSON："
        "{\"records\":[{\"source_record_id\":\"...\",\"object_type\":\"...\","
        "\"suggested_name\":\"...\",\"confidence\":0到1的小数,\"field_roles\":{},\"reasoning\":\"不超过80字\"}]}。"
        "无法可靠判断时保留 current_suggestion，confidence 不得高于 0.55。不得编造公司、人员、"
        "账号、资源或关系；财务/报销资料只能识别为历史资料。"
    )
    headers = {
        "Authorization": f"Bearer {settings.ai_import_api_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{settings.ai_import_base_url.rstrip('/')}/chat/completions"
    with httpx.Client(timeout=settings.ai_import_timeout_seconds) as client:
        for offset in range(0, len(records), settings.ai_import_max_rows_per_request):
            chunk = records[offset : offset + settings.ai_import_max_rows_per_request]
            body = {
                "model": settings.ai_import_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "catalog": _ai_catalog(db),
                                "records": [_ai_row(record) for record in chunk],
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
            }
            try:
                response = client.post(endpoint, headers=headers, json=body)
                response.raise_for_status()
                result = _ai_response_content(response)
            except httpx.HTTPError as exc:
                raise AIImportError("DeepSeek 请求失败，规则版规划未被修改") from exc
            request_count += 1
            for item in result["records"]:
                record_id = str(item.get("source_record_id")) if isinstance(item, dict) else ""
                record = by_id.get(record_id)
                if not isinstance(item, dict) or record is None:
                    continue
                object_type = str(item.get("object_type") or "")
                suggested_name = str(item.get("suggested_name") or "").strip()[:300]
                try:
                    confidence = min(1.0, max(0.0, float(item.get("confidence", 0))))
                except (TypeError, ValueError):
                    confidence = 0.0
                if object_type not in AI_OBJECT_TYPES or not suggested_name:
                    continue
                record.suggested_object_type = object_type
                record.suggested_name = suggested_name
                record.confidence = Decimal(str(confidence))
                raw = dict(record.raw_payload)
                field_roles = item.get("field_roles")
                raw["__ai_field_roles"] = field_roles if isinstance(field_roles, dict) else {}
                raw["__ai_reasoning"] = str(item.get("reasoning") or "")[:500]
                record.raw_payload = raw
                record.mapping_status = "ai_enhanced"
                updated += 1
    return {"updated_records": updated, "request_count": request_count}


def normalize(value: object) -> str:
    return re.sub(r"[\s_\-·.()（）]+", "", str(value or "")).casefold()


def string_value(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def source_evidence(record: SourceImportRecord, *fields: str) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    for field in fields:
        if value := record.raw_payload.get(field):
            evidence.append(
                {"source_record_id": str(record.id), "field": field, "value": str(value)[:500]}
            )
    if not evidence:
        evidence.append(
            {
                "source_record_id": str(record.id),
                "field": "row",
                "value": record.source_identifier or "",
            }
        )
    return evidence


def layer_for_object_type(object_type: str) -> str:
    return {
        "registration_identity": "registration_identity",
        "platform": "platform_directory",
        "platform_account": "company_platform_account",
        "access_grant": "access_authorization",
        "service_instance": "service_resource_system",
        "resource": "service_resource_system",
        "internal_system": "service_resource_system",
    }.get(object_type, "historical_reference")


def catalog_fingerprint(db: Session) -> str:
    values: list[str] = []
    values.extend(f"platform:{item.code}:{item.name}" for item in db.scalars(select(Platform)))
    values.extend(f"asset:{item.asset_code}:{item.name}" for item in db.scalars(select(Asset)))
    values.extend(
        f"person:{item.employee_no}:{item.display_name}:{item.email or ''}"
        for item in db.scalars(select(Person))
    )
    values.extend(f"department:{item.code}:{item.name}" for item in db.scalars(select(Department)))
    return hashlib.sha256("\n".join(sorted(values)).encode()).hexdigest()


def find_platform(db: Session, name: str) -> tuple[Platform | None, float]:
    target = normalize(name)
    if not target:
        return None, 0.0
    for item in db.scalars(select(Platform).where(Platform.archived_at.is_(None))):
        if target in {normalize(item.name), normalize(item.code)}:
            return item, 1.0
    return None, 0.0


def find_person(db: Session, name: str) -> tuple[Person | None, float]:
    target = normalize(name)
    if not target:
        return None, 0.0
    for item in db.scalars(select(Person).where(Person.archived_at.is_(None))):
        if target in {
            normalize(item.display_name),
            normalize(item.employee_no),
            normalize(item.email),
        }:
            return item, 1.0
    return None, 0.0


def find_department(db: Session, name: str) -> tuple[Department | None, float]:
    target = normalize(name)
    if not target:
        return None, 0.0
    for item in db.scalars(select(Department).where(Department.archived_at.is_(None))):
        if target in {normalize(item.name), normalize(item.code)}:
            return item, 1.0
    return None, 0.0


def find_asset(db: Session, name: str, identifiers: list[str]) -> tuple[Asset | None, float]:
    normalized_name = normalize(name)
    identifier_values = {normalize(item) for item in identifiers if item}
    for identifier in db.scalars(
        select(AssetIdentifier).where(AssetIdentifier.archived_at.is_(None))
    ):
        if normalize(identifier.identifier_value) in identifier_values:
            asset = db.get(Asset, identifier.asset_id)
            if asset and asset.archived_at is None:
                return asset, 1.0
    if not normalized_name:
        return None, 0.0
    for item in db.scalars(select(Asset).where(Asset.archived_at.is_(None))):
        if normalized_name in {normalize(item.name), normalize(item.asset_code)}:
            return item, 0.98
    return None, 0.0


def detected_platform_name(row: dict[str, Any]) -> str:
    explicit = string_value(row, "平台", "平台服务", "工具服务", "授权工具", "接入平台", "provider")
    lower = explicit.casefold()
    for alias, canonical in PLATFORM_ALIASES:
        if alias.casefold() in lower:
            return canonical
    return explicit


def looks_like_identity(value: str) -> bool:
    return bool(
        re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value)
        or re.fullmatch(r"1\d{10}", value)
        or re.fullmatch(r"1\d{2}\*{4}\d{4}", value)
        or value.strip() == "[邮箱已脱敏]"
        or value.strip() == "[手机号已脱敏]"
    )


def looks_like_protected_reference(value: str) -> bool:
    """Return true for placeholders that point to a vault or secret.

    These values are evidence that a credential exists, not registration
    identities.  They must never become L2 candidates merely because they
    appear in an ``account`` column.
    """
    normalized = value.strip().casefold()
    return (
        not normalized
        or normalized in {"-", "—", "n/a", "na"}
        or any(token in normalized for token in ("vault", "password", "passwd", "cookie", "api key", "apikey", "密钥", "密码", "验证码"))
    )


def object_type_code(object_type: str) -> str | None:
    return {
        "registration_identity": "registration_identity",
        "platform_account": "platform_tenant",
        "service_instance": "saas_subscription",
        "resource": "cloud_server",
        "internal_system": "internal_system",
    }.get(object_type)


def classify_l6_asset_type(*, object_type: str, name: str, payload: dict[str, Any]) -> str:
    """Classify an instantiated L6 proposal from explicit source facts.

    This is deliberately conservative: an identity is never classified here,
    and an ordinary login/credential value is not evidence of a service type.
    """
    if object_type == "internal_system":
        return "internal_system"
    if object_type == "registration_identity":
        return "registration_identity"

    service_facts = " ".join(
        str(payload.get(key) or "")
        for key in ("service_name", "resource_family", "platform_name", "legacy_id")
    )
    # "API 接入" can describe how a SaaS product is used (for example,
    # DingTalk Wukong), so the purpose alone must not turn a subscription into
    # an API service. A legacy API row has an explicit API-shaped ID or API
    # wording in the service facts themselves.
    purpose = str(payload.get("purpose") or "").casefold()
    explicit_api_purpose = purpose and not payload.get("service_name")
    if (
        re.search(r"\bapi[-_]?\d+\b", service_facts, re.IGNORECASE)
        or any(
            token in service_facts.casefold() for token in ("api service", "api/key", "接口服务")
        )
        or "api" in name.casefold()
        or "接口" in name
        or (explicit_api_purpose and any(token in purpose for token in ("api", "接口", "token")))
    ):
        return "api_service"

    text = " ".join(
        str(payload.get(key) or "")
        for key in ("service_name", "purpose", "resource_family", "platform_name")
    )
    text = f"{name} {text}".casefold()
    if any(token in text for token in ("vpn", "网络代理", "虚拟专网")):
        return "vpn_network"
    if any(token in text for token in ("邮箱", "邮件", "mail", "email")):
        return "email_service"
    if any(token in text for token in ("真理时刻", "样板房", "业务环境", "环境入口")):
        return "business_environment"
    if any(token in text for token in ("钉钉应用", "内部应用", "内部系统", "组织与应用")):
        return "internal_system"
    if any(token in text for token in ("ecs", "云服务器", "云资源", "服务器", "cloud server")):
        return "cloud_server"
    if any(
        token in text
        for token in (
            "影刀", "聚水潭", "管易", "用友", "京东", "知产", "商标", "专利",
            "微博", "店铺", "企业购", "云仓", "安捷云", "software", "erp",
        )
    ):
        return "software_service"
    return "saas_subscription"


class BatchPlanner:
    def __init__(self, db: Session, batch: ImportBatch, records: list[SourceImportRecord]) -> None:
        self.db = db
        self.batch = batch
        self.records = records
        self.objects: dict[str, ImportProposedObject] = {}
        self.relations: list[tuple[str, str, str, list[dict[str, object]], float]] = []

    def add_object(
        self,
        *,
        record: SourceImportRecord,
        object_type: str,
        name: str,
        payload: dict[str, Any],
        confidence: float,
        evidence_fields: tuple[str, ...],
        shared: bool = False,
    ) -> ImportProposedObject | None:
        clean_name = name.strip()[:300]
        if not clean_name:
            return None
        suffix = normalize(clean_name) if shared else f"{record.id}:{normalize(clean_name)}"
        proposal_key = f"{object_type}:{suffix}"[:200]
        if proposal_key in self.objects:
            return self.objects[proposal_key]

        item = ImportProposedObject(
            import_batch_id=self.batch.id,
            source_import_record_id=record.id,
            proposal_key=proposal_key,
            layer_code=layer_for_object_type(object_type),
            object_type=object_type,
            suggested_name=clean_name,
            normalized_payload=payload,
            evidence=source_evidence(record, *evidence_fields),
            extraction_confidence=Decimal(str(confidence)),
            match_confidence=Decimal("0"),
            match_status="new",
            review_status="pending_review",
        )
        if object_type == "platform":
            matched, score = find_platform(self.db, clean_name)
            if matched:
                item.matched_platform_id = matched.id
                item.match_confidence = Decimal(str(score))
                item.match_status = "matched"
        elif object_type == "access_grant":
            matched, score = find_person(self.db, payload.get("person_name", ""))
            if matched:
                item.matched_person_id = matched.id
                item.match_confidence = Decimal(str(score))
                item.match_status = "matched"
        elif object_type == "department_reference":
            matched, score = find_department(self.db, clean_name)
            if matched:
                item.matched_department_id = matched.id
                item.match_confidence = Decimal(str(score))
                item.match_status = "matched"
        elif object_type not in FINANCE_OBJECT_TYPES:
            identifiers = [
                str(payload.get(key) or "")
                for key in ("legacy_id", "external_identifier", "account_reference")
            ]
            matched, score = find_asset(self.db, clean_name, identifiers)
            if matched:
                item.matched_asset_id = matched.id
                item.match_confidence = Decimal(str(score))
                item.match_status = "matched"
        if object_type in FINANCE_OBJECT_TYPES:
            item.review_status = "historical_only"
            item.match_status = "not_applicable"
        self.db.add(item)
        self.objects[proposal_key] = item
        return item

    def add_relation(
        self,
        source: ImportProposedObject | None,
        target: ImportProposedObject | None,
        relation_type: str,
        evidence: list[dict[str, object]],
        confidence: float,
    ) -> None:
        if source is None or target is None or source is target:
            return
        self.relations.append(
            (source.proposal_key, target.proposal_key, relation_type, evidence, confidence)
        )

    def plan_record(self, record: SourceImportRecord) -> None:
        row = record.raw_payload
        source_type = record.suggested_object_type or "resource"
        if source_type in FINANCE_OBJECT_TYPES:
            self.add_object(
                record=record,
                object_type=source_type,
                name=record.suggested_name or record.source_identifier or "待核对历史资料",
                payload={"source_category": record.suggested_object_type, "raw": row},
                confidence=float(record.confidence or Decimal("0.7")),
                evidence_fields=tuple(str(key) for key in row),
            )
            return

        platform_name = detected_platform_name(row)
        platform_obj = None
        if platform_name:
            platform_obj = self.add_object(
                record=record,
                object_type="platform",
                name=platform_name,
                payload={"platform_name": platform_name},
                confidence=0.9,
                evidence_fields=("平台", "平台服务", "工具服务", "授权工具", "接入平台"),
                shared=True,
            )

        # A generic account/login reference is an L2 fact.  Only explicitly
        # labelled tenant/merchant/workspace fields are allowed to become an
        # L4 candidate; the planner never infers a company platform account
        # from an email, phone number, username, or a generic ``账号`` field.
        account_ref = string_value(row, "账号引用", "账号", "用户名", "登录账号", "登录名")
        l4_ref = string_value(
            row,
            "租户",
            "workspace",
            "Workspace",
            "商户号",
            "企业账号",
            "企业账户",
            "主账号",
        )
        identity_value = string_value(row, "注册邮箱", "邮箱", "手机号", "注册身份")
        if not identity_value:
            identity_value = next(
                (
                    str(value).strip()
                    for value in row.values()
                    if looks_like_identity(str(value).strip())
                ),
                "",
            )
        if not identity_value and account_ref and not looks_like_protected_reference(account_ref):
            identity_value = account_ref
        identity = (
            self.add_object(
                record=record,
                object_type="registration_identity",
                name=identity_value,
                payload={
                    "identifier": identity_value,
                    "identity_type": "login_identity",
                    "platform_name": platform_name,
                },
                confidence=0.95,
                evidence_fields=("注册邮箱", "邮箱", "手机号", "注册身份", "账号引用", "账号", "用户名", "登录账号", "登录名"),
            )
            if identity_value
            else None
        )
        account = (
            self.add_object(
                record=record,
                object_type="platform_account",
                name=l4_ref,
                payload={"account_reference": l4_ref, "platform_name": platform_name},
                confidence=0.78,
                evidence_fields=("租户", "workspace", "Workspace", "商户号", "企业账号", "企业账户", "主账号"),
            )
            if l4_ref and not looks_like_protected_reference(l4_ref)
            else None
        )
        self.add_relation(
            account,
            identity,
            "REGISTERED_BY",
            source_evidence(record, "账号引用", "邮箱", "手机号"),
            0.82,
        )
        # A source identity can be linked directly to the L3 platform. This is
        # an explicit candidate relation, never an instruction to create L4.
        self.add_relation(
            identity,
            platform_obj,
            "REGISTERED_ON",
            source_evidence(record, "平台", "平台服务", "注册邮箱", "邮箱", "手机号"),
            0.78,
        )

        # A source row explicitly classified as an identity may also provide
        # platform evidence, but it must never create a second, synthetic L6
        # resource merely because the row has an account-like value.
        if source_type == "registration_identity":
            return

        system_name = string_value(row, "应用名称", "系统", "appName", "application")
        if source_type == "internal_system" or system_name:
            system = self.add_object(
                record=record,
                object_type="internal_system",
                name=system_name or record.suggested_name,
                payload={
                    "legacy_id": string_value(row, "APIID", "apiId"),
                    "description": string_value(row, "说明", "描述"),
                },
                confidence=float(record.confidence or Decimal("0.86")),
                evidence_fields=("应用名称", "系统", "APIID", "apiId"),
            )
            api_ref = string_value(row, "APIID", "apiId")
            if api_ref:
                api_asset = self.add_object(
                    record=record,
                    object_type="service_instance",
                    name=f"API {api_ref}",
                    payload={"legacy_id": api_ref, "inferred": True},
                    confidence=0.58,
                    evidence_fields=("APIID", "apiId"),
                    shared=True,
                )
                self.add_relation(
                    system, api_asset, "CALLS", source_evidence(record, "APIID", "apiId"), 0.78
                )
        else:
            service_name = string_value(row, "工具服务", "平台服务", "授权工具", "服务", "名称")
            candidate_name = service_name or record.suggested_name
            resource = self.add_object(
                record=record,
                object_type="service_instance"
                if source_type in {"service_instance", "access_grant"}
                else "resource",
                name=candidate_name,
                payload={
                    "legacy_id": string_value(row, "ID", "id"),
                    "external_identifier": string_value(row, "实例ID", "资源ID", "APIID"),
                    "platform_name": platform_name,
                    "service_name": candidate_name,
                    "account_reference": l4_ref,
                    "login_identifier": identity_value,
                    "purpose": string_value(row, "套餐用途", "用途", "说明", "备注"),
                },
                confidence=float(record.confidence or Decimal("0.7")),
                evidence_fields=("工具服务", "平台服务", "授权工具", "ID", "实例ID", "资源ID"),
            )
            self.add_relation(
                resource,
                account,
                "PURCHASED_VIA",
                source_evidence(record, "账号引用", "工具服务"),
                0.8,
            )
            self.add_relation(
                resource,
                platform_obj,
                "PROVIDED_BY",
                source_evidence(record, "平台", "平台服务", "工具服务"),
                0.78,
            )

            person_name = string_value(row, "使用人", "姓名", "昵称", "申请人")
            if person_name:
                grant = self.add_object(
                    record=record,
                    object_type="access_grant",
                    name=f"{person_name} · {candidate_name}",
                    payload={"person_name": person_name, "resource_name": candidate_name},
                    confidence=0.82,
                    evidence_fields=("使用人", "姓名", "昵称", "申请人", "授权工具", "工具服务"),
                )
                self.add_relation(
                    grant, resource, "USES", source_evidence(record, "使用人", "工具服务"), 0.8
                )
            department_name = string_value(row, "部门")
            if department_name:
                self.add_object(
                    record=record,
                    object_type="department_reference",
                    name=department_name,
                    payload={"department_name": department_name},
                    confidence=0.88,
                    evidence_fields=("部门",),
                    shared=True,
                )

    def persist(self) -> tuple[int, int, dict[str, object]]:
        for record in self.records:
            self.plan_record(record)
        self.db.flush()
        by_key = self.objects
        seen_relations: set[tuple[str, str, str]] = set()
        for source_key, target_key, relation_type, evidence, confidence in self.relations:
            key = (source_key, target_key, relation_type)
            if key in seen_relations:
                continue
            seen_relations.add(key)
            source, target = by_key[source_key], by_key[target_key]
            validation = relation_validation(self.db, source, target, relation_type)
            self.db.add(
                ImportProposedRelation(
                    import_batch_id=self.batch.id,
                    source_proposal_id=source.id,
                    target_proposal_id=target.id,
                    relation_type=relation_type,
                    evidence=evidence,
                    confidence=Decimal(str(confidence)),
                    validation_status=validation,
                    review_status="pending_review",
                )
            )
        self.db.flush()
        object_counts = Counter(item.layer_code for item in self.objects.values())
        summary: dict[str, object] = {
            "object_counts": dict(object_counts),
            "matched_count": sum(item.match_status == "matched" for item in self.objects.values()),
            "pending_review_count": sum(
                item.review_status == "pending_review" for item in self.objects.values()
            ),
            "historical_only_count": sum(
                item.review_status == "historical_only" for item in self.objects.values()
            ),
            "relation_count": len(seen_relations),
        }
        return len(self.objects), len(seen_relations), summary


def relation_validation(
    db: Session, source: ImportProposedObject, target: ImportProposedObject, relation_type: str
) -> str:
    source_type = object_type_code(source.object_type)
    target_type = object_type_code(target.object_type)
    if source_type is None or target_type is None:
        return "informational"
    definitions = list(
        db.scalars(select(RelationDefinition).where(RelationDefinition.archived_at.is_(None)))
    )
    for definition in definitions:
        if (
            definition.relation_type.casefold() == relation_type.casefold()
            and definition.source_type_code == source_type
            and definition.target_type_code == target_type
        ):
            return "valid"
    return "requires_configuration"


def rebuild_import_plan(
    db: Session,
    batch: ImportBatch,
    *,
    analysis_mode: str = "rules",
    analyzer_version: str = ANALYZER_VERSION,
    provider: str | None = None,
    model: str | None = None,
    analysis_details: dict[str, object] | None = None,
) -> tuple[int, int]:
    records = list(
        db.scalars(
            select(SourceImportRecord).where(
                SourceImportRecord.import_batch_id == batch.id,
                SourceImportRecord.archived_at.is_(None),
            )
        )
    )
    db.execute(
        delete(ImportProposedRelation).where(ImportProposedRelation.import_batch_id == batch.id)
    )
    db.execute(delete(ImportProposedObject).where(ImportProposedObject.import_batch_id == batch.id))
    planner = BatchPlanner(db, batch, records)
    object_count, relation_count, summary = planner.persist()
    db.add(
        ImportAnalysis(
            import_batch_id=batch.id,
            analysis_mode=analysis_mode,
            analyzer_version=analyzer_version,
            catalog_fingerprint=catalog_fingerprint(db),
            provider=provider,
            model=model,
            status="completed",
            summary={**summary, **(analysis_details or {})},
        )
    )
    batch.status = "planned"
    return object_count, relation_count


def dry_run_import_plan(db: Session, batch: ImportBatch) -> dict[str, object]:
    objects = list(
        db.scalars(
            select(ImportProposedObject).where(ImportProposedObject.import_batch_id == batch.id)
        )
    )
    relations = list(
        db.scalars(
            select(ImportProposedRelation).where(ImportProposedRelation.import_batch_id == batch.id)
        )
    )
    create_count = sum(
        item.match_status == "new" and item.review_status == "approved" for item in objects
    )
    reuse_count = sum(
        item.match_status == "matched" and item.review_status == "approved" for item in objects
    )
    pending = sum(item.review_status == "pending_review" for item in objects)
    invalid_relations = sum(
        item.validation_status == "requires_configuration" for item in relations
    )
    messages: list[str] = []
    if pending:
        messages.append(f"仍有 {pending} 个候选对象待人工确认。")
    if invalid_relations:
        messages.append(f"仍有 {invalid_relations} 条关系未通过当前关系规则校验。")
    if not messages:
        messages.append("规划已通过预检；正式提交仍会再次核验当前数据库状态。")
    return {
        "can_commit": not pending and not invalid_relations,
        "create_count": create_count,
        "reuse_count": reuse_count,
        "pending_review_count": pending,
        "invalid_relation_count": invalid_relations,
        "messages": messages,
    }
