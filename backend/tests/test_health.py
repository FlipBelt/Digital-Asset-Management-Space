import asyncio

import httpx

from app.main import app


async def get(path: str) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(path)


def test_live() -> None:
    response = asyncio.run(get("/api/v1/health/live"))
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root() -> None:
    response = asyncio.run(get("/"))
    assert response.status_code == 200
    assert response.json()["docs"] == "/docs"


def test_business_api_requires_authentication() -> None:
    response = asyncio.run(get("/api/v1/assets"))
    assert response.status_code == 401


def test_dingtalk_status_is_safe_without_configuration() -> None:
    response = asyncio.run(get("/api/v1/dingtalk/status"))
    assert response.status_code == 200
    assert response.json()["enabled"] is False
