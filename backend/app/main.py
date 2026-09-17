import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from uuid import uuid4

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.api.v1 import developer, dingtalk, workspace
from app.core.auth import require_authenticated
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.usage_notifications import run_monitoring_cycle

settings = get_settings()
logger = logging.getLogger("account_center.usage_monitoring")


async def _usage_monitoring_loop() -> None:
    """Run periodic monitoring in the single deployed Uvicorn worker."""
    while True:
        try:
            with SessionLocal() as db:
                await asyncio.to_thread(run_monitoring_cycle, db)
        except Exception:
            # Never make availability depend on an external platform.
            logger.exception("usage monitoring cycle failed")
        await asyncio.sleep(60)


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(_usage_monitoring_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("x-request-id", uuid4().hex)
    response = await call_next(request)
    response.headers["x-request-id"] = request_id
    return response


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "release": "2026-08-07-workspace-rebuild",
        "docs": "/docs",
        "health": "/api/v1/health/ready",
    }


app.include_router(api_router)
app.include_router(developer.console_router)
# Public DingTalk bootstrap endpoints intentionally live outside /api/v1 for
# compatibility with the micro-app contract. They expose configuration only
# and establish an authenticated application session on successful login.
app.include_router(dingtalk.public_router)
# Keep the workspace router at one inclusion level. This avoids nested-router
# matching differences across the Python runtimes used locally and in production.
app.include_router(
    workspace.router,
    prefix="/api/v1",
    dependencies=[Depends(require_authenticated)],
)
