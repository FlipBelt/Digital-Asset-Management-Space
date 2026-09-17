import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.core.auth import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import Asset, Role, User, UserRoleScope, UserSession


async def exercise_hudu_workspace() -> None:
    transport = httpx.ASGITransport(app=app)
    marker = uuid4().hex[:8]
    username = f"hudu-{marker}"
    password = "TestPassword123!"
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "system_admin"))
        assert role is not None
        user = User(username=username, password_hash=hash_password(password))
        db.add(user)
        db.flush()
        db.add(UserRoleScope(user_id=user.id, role_id=role.id, scope_type="company"))
        db.commit()
        user_id = user.id

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            session = await client.post("/api/v1/sessions", json={"username": username, "password": password})
            assert session.status_code == 200, session.text
            client.headers.update({"X-CSRF-Token": session.json()["user"]["csrf_token"]})
            client.headers.update({"X-PM-Session": session.json()["session_token"]})

            overview = await client.get("/api/v1/hudu/overview")
            assert overview.status_code == 200, overview.text
            assert {"total_assets", "active_assets", "category_counts", "recent_assets"}.issubset(overview.json())

            listing = await client.get("/api/v1/hudu/assets?page_size=10")
            assert listing.status_code == 200, listing.text
            body = listing.json()
            assert {"items", "total", "categories", "types"}.issubset(body)
            assert len(body["items"]) <= 10

            if body["items"]:
                asset_id = body["items"][0]["id"]
                detail = await client.get(f"/api/v1/hudu/assets/{asset_id}")
                assert detail.status_code == 200, detail.text
                assert {"asset", "responsibilities", "relations", "identifiers", "history"}.issubset(detail.json())

            expirations = await client.get("/api/v1/hudu/expirations")
            assert expirations.status_code == 200, expirations.text
            assert isinstance(expirations.json()["items"], list)
        finally:
            with SessionLocal() as db:
                db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
                db.commit()


def test_hudu_workspace() -> None:
    asyncio.run(exercise_hudu_workspace())
