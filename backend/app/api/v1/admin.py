from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import (
    AppSetting,
    AuditLog,
    ConnectorDefinition,
    ProviderConnection,
    SyncJob,
    SyncJobRun,
)
from app.schemas.inventory import (
    AuditLogRead,
    ConnectorDefinitionRead,
    ProviderConnectionCreate,
    ProviderConnectionRead,
)

router = APIRouter(tags=["admin"])

DEFAULT_UI = {
    "default_theme": "bitwarden",
    "allowed_themes": ["bitwarden", "hudu", "ant-pro"],
    "features": {"governance": True, "connectors": True, "charts": True},
}


@router.get("/app-config/ui")
def get_ui_config(db: Session = Depends(get_db)) -> dict:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "ui"))
    return setting.value if setting else DEFAULT_UI


@router.patch("/admin/ui-settings")
def patch_ui_config(payload: dict, db: Session = Depends(get_db)) -> dict:
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "ui"))
    if setting is None:
        setting = AppSetting(key="ui", value={**DEFAULT_UI, **payload})
        db.add(setting)
    else:
        setting.value = {**setting.value, **payload}
    db.add(
        AuditLog(
            action="ui_settings.update",
            object_type="app_setting",
            object_id=setting.id,
            after_data=setting.value,
            request_id="local-development",
        )
    )
    db.commit()
    return setting.value


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(db: Session = Depends(get_db)) -> list[AuditLog]:
    return list(db.scalars(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(200)))


@router.get(
    "/connector-definitions",
    response_model=list[ConnectorDefinitionRead],
)
def list_connector_definitions(db: Session = Depends(get_db)) -> list[ConnectorDefinition]:
    return list(
        db.scalars(
            select(ConnectorDefinition)
            .where(ConnectorDefinition.archived_at.is_(None))
            .order_by(ConnectorDefinition.name)
        )
    )


@router.get(
    "/provider-connections",
    response_model=list[ProviderConnectionRead],
)
def list_connections(db: Session = Depends(get_db)) -> list[ProviderConnection]:
    return list(
        db.scalars(
            select(ProviderConnection)
            .where(ProviderConnection.archived_at.is_(None))
            .order_by(ProviderConnection.name)
        )
    )


@router.post(
    "/provider-connections",
    response_model=ProviderConnectionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_connection(
    payload: ProviderConnectionCreate, db: Session = Depends(get_db)
) -> ProviderConnection:
    item = ProviderConnection(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post("/provider-connections/{connection_id}/test")
def test_connection(connection_id: UUID, db: Session = Depends(get_db)) -> dict:
    item = db.get(ProviderConnection, connection_id)
    if item is None or item.archived_at is not None:
        raise HTTPException(status_code=404, detail="连接配置不存在")
    definition = db.get(ConnectorDefinition, item.connector_definition_id)
    if definition is None:
        raise HTTPException(status_code=409, detail="连接器定义不存在")
    # 第一阶段提供安全模拟器；真实连接器不在未配置凭证时发出外部请求。
    return {
        "status": "ok" if definition.code == "mock" else "configuration_required",
        "message": "模拟连接成功"
        if definition.code == "mock"
        else "连接器已预留，请配置安全凭证引用",
        "capabilities": definition.capabilities,
    }


@router.post("/provider-connections/{connection_id}/sync")
def run_mock_sync(connection_id: UUID, db: Session = Depends(get_db)) -> dict:
    item = db.get(ProviderConnection, connection_id)
    if item is None:
        raise HTTPException(status_code=404, detail="连接配置不存在")
    definition = db.get(ConnectorDefinition, item.connector_definition_id)
    if definition is None or definition.code != "mock":
        raise HTTPException(status_code=409, detail="真实平台同步需要外部凭证和接口配置")
    job = db.scalar(select(SyncJob).where(SyncJob.provider_connection_id == item.id))
    if job is None:
        job = SyncJob(
            provider_connection_id=item.id,
            name=f"{item.name} 手动同步",
            capability="health",
            enabled=True,
        )
        db.add(job)
        db.flush()
    now = datetime.now(UTC)
    run = SyncJobRun(
        sync_job_id=job.id,
        status="success",
        started_at=now,
        finished_at=now,
        processed_count=0,
    )
    item.last_synced_at = now
    item.status = "healthy"
    db.add(run)
    db.commit()
    return {"status": "success", "processed_count": 0, "finished_at": now}
