from fastapi import APIRouter, Depends

from app.api.v1 import (
    admin,
    assets,
    catalog,
    dashboard,
    developer,
    dingtalk,
    governance,
    health,
    hudu,
    inventory,
    organizations,
    scenarios,
    sessions,
    transfers,
    usage,
    usage_monitoring,
)
from app.core.auth import require_authenticated, require_system_admin

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router)
api_router.include_router(sessions.router)
api_router.include_router(dingtalk.router)

authenticated = [Depends(require_authenticated)]
api_router.include_router(organizations.router, dependencies=authenticated)
api_router.include_router(catalog.router, dependencies=authenticated)
api_router.include_router(assets.router, dependencies=authenticated)
api_router.include_router(inventory.router, dependencies=authenticated)
api_router.include_router(usage.router, dependencies=authenticated)
api_router.include_router(usage_monitoring.router, dependencies=authenticated)
api_router.include_router(scenarios.router, dependencies=authenticated)
api_router.include_router(dashboard.router, dependencies=authenticated)
api_router.include_router(developer.router)
api_router.include_router(admin.router, dependencies=[Depends(require_system_admin)])
api_router.include_router(governance.router, dependencies=authenticated)
api_router.include_router(transfers.router, dependencies=authenticated)
api_router.include_router(hudu.router, dependencies=authenticated)
