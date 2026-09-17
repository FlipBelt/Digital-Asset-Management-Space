"""Platform-specific usage monitoring adapters, limited to published APIs."""

from __future__ import annotations

from base64 import b64encode
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha1
from hmac import new as hmac_new
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ConnectorDefinition,
    MetricDefinition,
    MetricSample,
    ProviderConnection,
    ServiceInstance,
    SyncJob,
    SyncJobRun,
)

PLATFORM_CATALOG = {
    "deepseek": {
        "name": "DeepSeek 账户余额",
        "capabilities": ["account_balance", "health"],
        "default_key_type": "api_key",
        "connection_kind": "account_balance",
        "capability_summary": "官方 API 仅查询开放平台账号当前余额，不返回各 API Key 的历史用量。",
    },
    "minimax": {
        "name": "MiniMax Token Plan 额度",
        "capabilities": ["token_plan_remains", "health"],
        "default_key_type": "token_plan",
        "connection_kind": "token_plan_quota",
        "capability_summary": (
            "仅支持 Token Plan 订阅 Key 的套餐、额度与积分状态；普通按量 API Key 没有公开查询接口。"
        ),
    },
    "aliyun": {
        "name": "阿里云账户余额",
        "capabilities": ["account_balance", "health"],
        "default_key_type": "ram_access_key",
        "connection_kind": "account_balance",
        "capability_summary": (
            "BSS OpenAPI 查询阿里云账号可用额度、现金余额与信控余额；"
            "不提供单次 API 调用级别的消费明细。"
        ),
    },
}

METRIC_CATALOG = [
    ("balance", "账户余额", "currency", "latest"),
    ("quota_remaining", "剩余额度", "unit", "latest"),
    ("input_tokens", "输入 Token", "token", "sum"),
    ("output_tokens", "输出 Token", "token", "sum"),
    ("total_tokens", "总 Token", "token", "sum"),
    ("cost", "费用", "currency", "sum"),
]


class UsageConnectorError(Exception):
    pass


def ensure_usage_catalog(db: Session) -> None:
    """Make this feature self-contained for existing installations and fresh databases."""
    changed = False
    for code, item in PLATFORM_CATALOG.items():
        connector = db.scalar(select(ConnectorDefinition).where(ConnectorDefinition.code == code))
        if connector is None:
            db.add(
                ConnectorDefinition(
                    code=code,
                    name=item["name"],
                    capabilities=item["capabilities"],
                    enabled=True,
                )
            )
            changed = True
        else:
            if not connector.enabled:
                connector.enabled = True
                changed = True
            if connector.name != item["name"] or connector.capabilities != item["capabilities"]:
                connector.name = item["name"]
                connector.capabilities = item["capabilities"]
                changed = True
    for key, name, unit, aggregation in METRIC_CATALOG:
        if db.scalar(select(MetricDefinition).where(MetricDefinition.metric_key == key)) is None:
            db.add(
                MetricDefinition(
                    metric_key=key,
                    display_name=name,
                    unit=unit,
                    aggregation=aggregation,
                )
            )
            changed = True
    if changed:
        db.commit()


def platform_code_for(connection: ProviderConnection, db: Session) -> str:
    definition = db.get(ConnectorDefinition, connection.connector_definition_id)
    if definition is None or definition.code not in PLATFORM_CATALOG:
        raise HTTPException(status_code=404, detail="用量连接不存在")
    return definition.code


def mask_api_key(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * max(4, len(value) - 8)}{value[-4:]}"


def serialize_connection(connection: ProviderConnection, platform_code: str) -> dict[str, Any]:
    configuration = dict(connection.configuration or {})
    api_key = str(configuration.pop("api_key", "") or "")
    access_key_id = str(configuration.pop("access_key_id", "") or "")
    access_key_secret = str(configuration.pop("access_key_secret", "") or "")
    configuration["key_configured"] = bool(api_key or access_key_secret)
    configuration["api_key_masked"] = mask_api_key(api_key)
    configuration["access_key_id_masked"] = mask_api_key(access_key_id)
    configuration["access_key_secret_configured"] = bool(access_key_secret)
    configuration.setdefault("key_type", PLATFORM_CATALOG[platform_code]["default_key_type"])
    configuration.setdefault("connection_kind", PLATFORM_CATALOG[platform_code]["connection_kind"])
    configuration.setdefault(
        "capability_summary", PLATFORM_CATALOG[platform_code]["capability_summary"]
    )
    return {
        "id": connection.id,
        "platform_code": platform_code,
        "platform_name": PLATFORM_CATALOG[platform_code]["name"],
        "legal_entity_id": connection.legal_entity_id,
        "service_instance_id": connection.service_instance_id,
        "name": connection.name,
        "status": connection.status,
        "configuration": configuration,
        "last_synced_at": connection.last_synced_at,
        "last_error": connection.last_error,
    }


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _deepseek_snapshot(
    api_key: str,
) -> tuple[datetime, list[tuple[str, Decimal, str | None]], dict[str, Any]]:
    response = httpx.get(
        "https://api.deepseek.com/user/balance",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("is_available", False):
        raise UsageConnectorError("DeepSeek 账户当前不可用")
    metrics: list[tuple[str, Decimal, str | None]] = []
    balances: list[dict[str, str | None]] = []
    for balance in payload.get("balance_infos", []):
        value = _decimal(balance.get("total_balance"))
        if value is not None:
            metrics.append(("balance", value, balance.get("currency")))
        balances.append(
            {
                "currency": balance.get("currency"),
                "total_balance": str(balance.get("total_balance", "")),
                "granted_balance": str(balance.get("granted_balance", "")),
                "topped_up_balance": str(balance.get("topped_up_balance", "")),
            }
        )
    return datetime.now(UTC), metrics, {"kind": "account_balance", "balances": balances}


def _find_remaining_values(value: Any, path: str = "") -> list[tuple[str, Decimal]]:
    """Accept documented MiniMax variants without inventing a quota number."""
    found: list[tuple[str, Decimal]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(_find_remaining_values(child, f"{path}.{key}" if path else key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_find_remaining_values(child, f"{path}[{index}]"))
    elif "remain" in path.lower() or "remaining" in path.lower():
        number = _decimal(value)
        if number is not None:
            found.append((path, number))
    return found


def _minimax_token_plan_snapshot(
    api_key: str,
) -> tuple[datetime, list[tuple[str, Decimal, str | None]], dict[str, Any]]:
    response = httpx.get(
        "https://www.minimaxi.com/v1/token_plan/remains",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    status_code = payload.get("base_resp", {}).get("status_code")
    if status_code not in (None, 0):
        raise UsageConnectorError(
            payload.get("base_resp", {}).get("status_msg") or "MiniMax 返回失败"
        )
    remaining_values = _find_remaining_values(payload)
    metrics = [("quota_remaining", value, None) for _, value in remaining_values]
    snapshot = {
        "kind": "token_plan_quota",
        "items": [{"label": path, "remaining": str(value)} for path, value in remaining_values],
    }
    return datetime.now(UTC), metrics, snapshot


def _aliyun_percent_encode(value: str) -> str:
    return quote(value, safe="~")


def _aliyun_account_balance_snapshot(
    access_key_id: str, access_key_secret: str
) -> tuple[datetime, list[tuple[str, Decimal, str | None]], dict[str, Any]]:
    """Call the documented BssOpenApi QueryAccountBalance RPC endpoint."""
    params = {
        "Action": "QueryAccountBalance",
        "Format": "JSON",
        "Version": "2017-12-14",
        "AccessKeyId": access_key_id,
        "SignatureMethod": "HMAC-SHA1",
        "Timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid4().hex,
    }
    canonical = "&".join(
        f"{_aliyun_percent_encode(key)}={_aliyun_percent_encode(value)}"
        for key, value in sorted(params.items())
    )
    string_to_sign = f"GET&%2F&{_aliyun_percent_encode(canonical)}"
    signature = b64encode(
        hmac_new(f"{access_key_secret}&".encode(), string_to_sign.encode(), sha1).digest()
    ).decode()
    response = httpx.get(
        "https://business.aliyuncs.com/",
        params={**params, "Signature": signature},
        timeout=15.0,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload.get("Success", False):
        raise UsageConnectorError(str(payload.get("Message") or "阿里云账户余额查询失败"))
    data = payload.get("Data")
    if not isinstance(data, dict):
        raise UsageConnectorError("阿里云未返回账户余额数据")
    currency = str(data.get("Currency") or "") or None
    labels = {
        "AvailableAmount": "可用额度",
        "AvailableCashAmount": "现金余额",
        "CreditAmount": "信控余额",
        "MybankCreditAmount": "网商银行信用额度",
    }
    values: list[dict[str, str | None]] = []
    metrics: list[tuple[str, Decimal, str | None]] = []
    for field, label in labels.items():
        raw = data.get(field)
        value = _decimal(raw)
        if value is not None:
            values.append({"key": field, "label": label, "value": str(raw), "currency": currency})
            if field == "AvailableAmount":
                metrics.append(("balance", value, currency))
    return (
        datetime.now(UTC),
        metrics,
        {
            "kind": "account_balance",
            "currency": currency,
            "balances": values,
        },
    )


def collect_snapshot(
    connection: ProviderConnection, platform_code: str
) -> tuple[datetime, list[tuple[str, Decimal, str | None]], dict[str, Any]]:
    configuration = connection.configuration or {}
    api_key = str(configuration.get("api_key", "") or "").strip()
    if platform_code == "deepseek":
        if not api_key:
            raise UsageConnectorError("请先保存 API Key")
        return _deepseek_snapshot(api_key)
    if platform_code == "aliyun":
        access_key_id = str(configuration.get("access_key_id", "") or "").strip()
        access_key_secret = str(configuration.get("access_key_secret", "") or "").strip()
        if not access_key_id or not access_key_secret:
            raise UsageConnectorError("请先保存阿里云 AccessKey ID 和 AccessKey Secret")
        return _aliyun_account_balance_snapshot(access_key_id, access_key_secret)
    if not api_key:
        raise UsageConnectorError("请先保存 Token Plan 订阅 Key")
    if configuration.get("key_type", "token_plan") != "token_plan":
        raise UsageConnectorError("MiniMax 仅支持 Token Plan 订阅 Key 的额度查询")
    return _minimax_token_plan_snapshot(api_key)


def test_connection(connection: ProviderConnection, platform_code: str) -> dict[str, Any]:
    try:
        observed_at, metrics, snapshot = collect_snapshot(connection, platform_code)
    except httpx.HTTPStatusError as exc:
        return {
            "status": "failed",
            "message": f"平台返回 HTTP {exc.response.status_code}",
            "observed_at": None,
            "snapshot": None,
        }
    except (httpx.HTTPError, UsageConnectorError) as exc:
        return {"status": "failed", "message": str(exc), "observed_at": None, "snapshot": None}
    return {
        "status": "connected",
        "message": (
            "连接成功，已读取账户当前余额。"
            if platform_code in {"deepseek", "aliyun"}
            else "连接成功，已读取 Token Plan 当前套餐额度。"
        ),
        "observed_at": observed_at,
        "snapshot": snapshot,
    }


def _sync_job(db: Session, connection: ProviderConnection) -> SyncJob:
    job = db.scalar(
        select(SyncJob).where(
            SyncJob.provider_connection_id == connection.id,
            SyncJob.capability == "usage_monitoring",
            SyncJob.archived_at.is_(None),
        )
    )
    if job is None:
        interval = int((connection.configuration or {}).get("sync_interval_minutes", 60))
        job = SyncJob(
            provider_connection_id=connection.id,
            name=f"{connection.name} 用量同步",
            capability="usage_monitoring",
            schedule=f"every {interval} minutes",
            enabled=connection.status == "enabled",
        )
        db.add(job)
        db.flush()
    return job


def sync_connection(
    db: Session, connection: ProviderConnection, platform_code: str
) -> dict[str, Any]:
    job = _sync_job(db, connection)
    run = SyncJobRun(sync_job_id=job.id, status="running", started_at=datetime.now(UTC))
    db.add(run)
    db.flush()
    if (
        connection.service_instance_id is not None
        and db.get(ServiceInstance, connection.service_instance_id) is None
    ):
        message = "绑定的服务实例不存在"
        run.status, run.error_summary, run.finished_at = "failed", message, datetime.now(UTC)
        connection.last_error = message
        db.commit()
        return {"status": "failed", "message": message, "metrics_written": 0, "observed_at": None}
    # Persist the running marker and release the SQL connection before any
    # provider HTTP request. External latency must not consume an application
    # database connection from the request pool.
    connection_id = connection.id
    run_id = run.id
    service_instance_id = connection.service_instance_id
    snapshot_input = SimpleNamespace(
        configuration=dict(connection.configuration or {}),
        service_instance_id=service_instance_id,
    )
    db.commit()
    try:
        observed_at, metrics, snapshot = collect_snapshot(snapshot_input, platform_code)
    except httpx.HTTPStatusError as exc:
        message = f"平台返回 HTTP {exc.response.status_code}"
        connection = db.get(ProviderConnection, connection_id)
        run = db.get(SyncJobRun, run_id)
        if connection is None or run is None:
            return {"status": "failed", "message": message, "metrics_written": 0, "observed_at": None}
        run.status, run.error_summary, run.finished_at = "failed", message, datetime.now(UTC)
        connection.last_error = message
        db.commit()
        return {
            "status": "failed",
            "message": message,
            "metrics_written": 0,
            "observed_at": None,
            "snapshot": None,
        }
    except (httpx.HTTPError, UsageConnectorError) as exc:
        message = str(exc)
        connection = db.get(ProviderConnection, connection_id)
        run = db.get(SyncJobRun, run_id)
        if connection is None or run is None:
            return {"status": "failed", "message": message, "metrics_written": 0, "observed_at": None}
        run.status, run.error_summary, run.finished_at = "failed", message, datetime.now(UTC)
        connection.last_error = message
        db.commit()
        return {
            "status": "failed",
            "message": message,
            "metrics_written": 0,
            "observed_at": None,
            "snapshot": None,
        }
    connection = db.get(ProviderConnection, connection_id)
    run = db.get(SyncJobRun, run_id)
    if connection is None or run is None:
        return {"status": "failed", "message": "同步记录不存在", "metrics_written": 0, "observed_at": None}
    definitions = {
        item.metric_key: item
        for item in db.scalars(
            select(MetricDefinition).where(MetricDefinition.archived_at.is_(None))
        )
    }
    metrics_written = 0
    if service_instance_id is not None:
        for metric_key, value, currency in metrics:
            definition = definitions.get(metric_key)
            if definition is not None:
                db.add(
                    MetricSample(
                        service_instance_id=service_instance_id,
                        metric_definition_id=definition.id,
                        value=value,
                        currency=currency,
                        collected_at=observed_at,
                        source_type=f"{platform_code}_api",
                    )
                )
                metrics_written += 1
    configuration = dict(connection.configuration or {})
    configuration["latest_snapshot"] = snapshot
    configuration["latest_snapshot_at"] = observed_at.isoformat()
    connection.configuration = configuration
    run.status, run.processed_count, run.finished_at = (
        "succeeded",
        metrics_written,
        datetime.now(UTC),
    )
    connection.last_synced_at, connection.last_error = observed_at, None
    db.commit()
    return {
        "status": "succeeded",
        "message": "账户余额已同步"
        if platform_code in {"deepseek", "aliyun"}
        else "Token Plan 额度已同步",
        "metrics_written": metrics_written,
        "observed_at": observed_at,
        "snapshot": snapshot,
    }


def record_usage_event(
    db: Session,
    connection: ProviderConnection,
    values: dict[str, Decimal | None],
    currency: str | None,
    collected_at: datetime | None,
) -> int:
    if connection.service_instance_id is None:
        raise HTTPException(status_code=422, detail="请先绑定服务实例")
    instance = db.get(ServiceInstance, connection.service_instance_id)
    if instance is None:
        raise HTTPException(status_code=404, detail="绑定的服务实例不存在")
    definitions = {
        item.metric_key: item
        for item in db.scalars(
            select(MetricDefinition).where(MetricDefinition.archived_at.is_(None))
        )
    }
    written = 0
    for metric_key, value in values.items():
        if value is None or metric_key not in definitions:
            continue
        db.add(
            MetricSample(
                service_instance_id=connection.service_instance_id,
                metric_definition_id=definitions[metric_key].id,
                value=value,
                currency=currency if metric_key == "cost" else None,
                collected_at=collected_at or datetime.now(UTC),
                source_type="application_usage",
            )
        )
        written += 1
    db.commit()
    return written
