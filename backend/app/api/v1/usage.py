from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, get_access_context, require_asset_write
from app.db.session import get_db
from app.models import Asset, AuditLog, ConnectorDefinition, ProviderConnection, ServiceInstance
from app.schemas.usage import (
    UsageConnectionActionResult,
    UsageConnectionCreate,
    UsageConnectionRead,
    UsageConnectionUpdate,
    UsageEventCreate,
)
from app.services.usage_connectors import (
    PLATFORM_CATALOG,
    ensure_usage_catalog,
    platform_code_for,
    record_usage_event,
    serialize_connection,
    sync_connection,
    test_connection,
)

router = APIRouter(prefix="/usage-connections", tags=["usage-connections"])


def _connection(db: Session, connection_id: UUID) -> tuple[ProviderConnection, str]:
    item = db.get(ProviderConnection, connection_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(status_code=404, detail="用量连接不存在")
    return item, platform_code_for(item, db)


def _validate_instance(
    db: Session, service_instance_id: UUID | None, legal_entity_id: UUID
) -> None:
    if service_instance_id is None:
        return
    instance = db.get(ServiceInstance, service_instance_id)
    if instance is None or instance.archived_at is not None:
        raise HTTPException(status_code=422, detail="服务实例不存在")
    asset = db.get(Asset, instance.asset_id)
    if asset is not None and asset.legal_entity_id not in (None, legal_entity_id):
        raise HTTPException(status_code=422, detail="服务实例不属于所选公司主体")


@router.get("/catalog")
def usage_catalog(
    db: Session = Depends(get_db), _: AccessContext = Depends(get_access_context)
) -> list[dict]:
    ensure_usage_catalog(db)
    return [
        {
            "code": code,
            "name": item["name"],
            "connection_kind": item["connection_kind"],
            "capability_summary": item["capability_summary"],
            "credential_label": (
                "账户 API 访问凭证（Bearer Key）"
                if code == "deepseek"
                else "Token Plan 订阅 Key"
                if code == "minimax"
                else "RAM AccessKey ID / AccessKey Secret"
            ),
            "safe_test": (
                "查询账号当前余额"
                if code in {"deepseek", "aliyun"}
                else "查询 Token Plan 当前套餐、额度与积分状态"
            ),
        }
        for code, item in PLATFORM_CATALOG.items()
    ]


@router.get("", response_model=list[UsageConnectionRead])
def list_usage_connections(
    db: Session = Depends(get_db), _: AccessContext = Depends(get_access_context)
) -> list[dict]:
    ensure_usage_catalog(db)
    rows = list(
        db.scalars(
            select(ProviderConnection)
            .join(ConnectorDefinition)
            .where(
                ProviderConnection.archived_at.is_(None),
                ConnectorDefinition.code.in_(PLATFORM_CATALOG),
            )
            .order_by(ProviderConnection.created_at.desc())
        )
    )
    return [serialize_connection(row, platform_code_for(row, db)) for row in rows]


@router.get("/{connection_id}", response_model=UsageConnectionRead)
def get_usage_connection(
    connection_id: UUID,
    db: Session = Depends(get_db),
    _: AccessContext = Depends(get_access_context),
) -> dict:
    item, platform_code = _connection(db, connection_id)
    return serialize_connection(item, platform_code)


@router.post("", response_model=UsageConnectionRead, status_code=status.HTTP_201_CREATED)
def create_usage_connection(
    payload: UsageConnectionCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> dict:
    ensure_usage_catalog(db)
    _validate_instance(db, payload.service_instance_id, payload.legal_entity_id)
    if payload.platform_code == "deepseek" and payload.key_type is not None:
        raise HTTPException(status_code=422, detail="DeepSeek 不需要选择 MiniMax Key 类型")
    if payload.platform_code == "minimax" and payload.key_type not in (None, "token_plan"):
        raise HTTPException(status_code=422, detail="MiniMax 此模块仅支持 Token Plan 订阅 Key")
    if payload.platform_code in {"deepseek", "minimax"} and not payload.api_key:
        raise HTTPException(status_code=422, detail="请填写平台访问凭证")
    if payload.platform_code == "aliyun" and (
        not payload.access_key_id or not payload.access_key_secret
    ):
        raise HTTPException(status_code=422, detail="请填写阿里云 AccessKey ID 和 AccessKey Secret")
    definition = db.scalar(
        select(ConnectorDefinition).where(ConnectorDefinition.code == payload.platform_code)
    )
    if definition is None:
        raise HTTPException(status_code=500, detail="连接器目录未初始化")
    configuration = {
        "api_key": payload.api_key,
        "access_key_id": payload.access_key_id,
        "access_key_secret": payload.access_key_secret,
        "key_type": payload.key_type or PLATFORM_CATALOG[payload.platform_code]["default_key_type"],
        "connection_kind": PLATFORM_CATALOG[payload.platform_code]["connection_kind"],
        "capability_summary": PLATFORM_CATALOG[payload.platform_code]["capability_summary"],
        "group_id": payload.group_id,
        "low_balance_threshold": str(payload.low_balance_threshold)
        if payload.low_balance_threshold is not None
        else None,
        "currency": payload.currency,
        "sync_interval_minutes": payload.sync_interval_minutes,
    }
    item = ProviderConnection(
        connector_definition_id=definition.id,
        legal_entity_id=payload.legal_entity_id,
        service_instance_id=payload.service_instance_id,
        name=payload.name,
        status=payload.status,
        configuration=configuration,
    )
    db.add(item)
    db.flush()
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="usage_connection.create",
            object_type="provider_connection",
            object_id=item.id,
            after_data={"platform_code": payload.platform_code, "name": item.name},
            request_id="api",
        )
    )
    db.commit()
    db.refresh(item)
    return serialize_connection(item, payload.platform_code)


@router.patch("/{connection_id}", response_model=UsageConnectionRead)
def update_usage_connection(
    connection_id: UUID,
    payload: UsageConnectionUpdate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_asset_write),
) -> dict:
    item, platform_code = _connection(db, connection_id)
    _validate_instance(db, payload.service_instance_id, item.legal_entity_id)
    changes = payload.model_dump(exclude_unset=True)
    configuration = dict(item.configuration or {})
    for field in (
        "api_key",
        "access_key_id",
        "access_key_secret",
        "key_type",
        "group_id",
        "currency",
        "sync_interval_minutes",
    ):
        if field in changes:
            configuration[field] = changes.pop(field)
    if "low_balance_threshold" in changes:
        value = changes.pop("low_balance_threshold")
        configuration["low_balance_threshold"] = str(value) if value is not None else None
    for field in ("service_instance_id", "name", "status"):
        if field in changes:
            setattr(item, field, changes[field])
    item.configuration = configuration
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="usage_connection.update",
            object_type="provider_connection",
            object_id=item.id,
            after_data={"platform_code": platform_code, "name": item.name},
            request_id="api",
        )
    )
    db.commit()
    db.refresh(item)
    return serialize_connection(item, platform_code)


@router.post("/{connection_id}/test", response_model=UsageConnectionActionResult)
def test_usage_connection(
    connection_id: UUID,
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_asset_write),
) -> dict:
    item, platform_code = _connection(db, connection_id)
    return test_connection(item, platform_code)


@router.post("/{connection_id}/sync", response_model=UsageConnectionActionResult)
def sync_usage_connection(
    connection_id: UUID,
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_asset_write),
) -> dict:
    item, platform_code = _connection(db, connection_id)
    if item.status != "enabled":
        return {"status": "disabled", "message": "该连接已停用", "metrics_written": 0}
    return sync_connection(db, item, platform_code)


@router.post("/{connection_id}/usage-events", response_model=UsageConnectionActionResult)
def create_usage_event(
    connection_id: UUID,
    payload: UsageEventCreate,
    db: Session = Depends(get_db),
    _: AccessContext = Depends(require_asset_write),
) -> dict:
    item, _ = _connection(db, connection_id)
    written = record_usage_event(
        db,
        item,
        {
            "input_tokens": payload.input_tokens,
            "output_tokens": payload.output_tokens,
            "total_tokens": payload.total_tokens,
            "cost": payload.cost,
        },
        payload.currency,
        payload.collected_at,
    )
    return {"status": "recorded", "message": "用量已记录", "metrics_written": written}
