import asyncio
from unittest.mock import patch
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.core.auth import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AuditLog,
    Department,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    LegalEntity,
    Role,
    User,
    UserRoleScope,
    UserSession,
)


async def exercise_pm_session_security() -> None:
    marker = uuid4().hex[:8]
    ids: dict[str, str] = {}
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "system_admin"))
        assert role is not None
        user = User(
            username=f"pm-session-{marker}", password_hash=hash_password("TestPassword123!")
        )
        db.add(user)
        db.flush()
        db.add(UserRoleScope(user_id=user.id, role_id=role.id, scope_type="company"))
        db.commit()
        ids["user"] = str(user.id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            config = await client.get("/api/dingtalk/config")
            assert config.status_code == 200
            assert set(config.json()) == {"corpId", "agentId", "configured"}

            session = await client.post(
                "/api/v1/sessions",
                json={"username": f"pm-session-{marker}", "password": "TestPassword123!"},
            )
            assert session.status_code == 200, session.text
            session_token = session.json()["session_token"]
            assert isinstance(session_token, str) and len(session_token) >= 48

            current = await client.get(
                "/api/v1/sessions/current", headers={"X-PM-Session": session_token}
            )
            assert current.status_code == 200, current.text

            async with httpx.AsyncClient(
                transport=transport, base_url="http://test"
            ) as browser_client:
                unauthenticated_write = await browser_client.post(
                    "/api/v1/legal-entities",
                    headers={"X-Role": "system_admin", "X-User-Id": "forged"},
                    json={"code": f"F{marker}", "name": "forged request"},
                )
            assert unauthenticated_write.status_code == 401

            protected_write = await client.post(
                "/api/v1/legal-entities",
                headers={"X-PM-Session": session_token, "X-Role": "employee"},
                json={"code": f"S{marker}", "name": "可信会话测试公司"},
            )
            assert protected_write.status_code == 201, protected_write.text
            ids["entity"] = protected_write.json()["id"]
        finally:
            with SessionLocal() as db:
                if entity_id := ids.get("entity"):
                    db.execute(delete(LegalEntity).where(LegalEntity.id == entity_id))
                if user_id := ids.get("user"):
                    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                    db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user_id))
                    db.execute(delete(User).where(User.id == user_id))
                db.commit()


def test_pm_session_security() -> None:
    asyncio.run(exercise_pm_session_security())


async def exercise_dingtalk_auth_code_exchange() -> None:
    marker = uuid4().hex[:8]
    ids: dict[str, str] = {}
    dingtalk_user_id = f"test-dingtalk-{marker}"
    dingtalk_department_id = str(900000000 + int(marker[:4], 16))
    with SessionLocal() as db:
        entity = LegalEntity(code=f"DT{marker}", name="钉钉会话测试公司")
        db.add(entity)
        db.flush()
        department = Department(
            legal_entity_id=entity.id,
            code=f"DD{marker}",
            name="钉钉测试部门",
        )
        db.add(department)
        db.flush()
        db.add(
            DingTalkDepartmentLink(
                department_id=department.id,
                dingtalk_department_id=dingtalk_department_id,
            )
        )
        db.commit()
        ids["entity"] = str(entity.id)
        ids["department"] = str(department.id)

    transport = httpx.ASGITransport(app=app)
    profile_data = {
        "userid": dingtalk_user_id,
        "name": "钉钉验证用户",
        "dept_id_list": [int(dingtalk_department_id)],
        "job_number": f"JOB{marker}",
    }
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            with patch(
                "app.api.v1.dingtalk.DingTalkClient.user_from_auth_code",
                return_value=profile_data,
            ):
                response = await client.post(
                    "/api/dingtalk/login", json={"authCode": "one-time-test-code"}
                )
            assert response.status_code == 200, response.text
            user = response.json()["user"]
            assert user["dingUserId"] == dingtalk_user_id
            assert user["name"] == "钉钉验证用户"
            assert isinstance(user["sessionToken"], str) and len(user["sessionToken"]) >= 48
            assert "authCode" not in response.text

            current = await client.get(
                "/api/v1/sessions/current",
                headers={"X-PM-Session": user["sessionToken"]},
            )
            assert current.status_code == 200, current.text
            ids["user"] = current.json()["id"]
            ids["person"] = current.json()["person_id"]
    finally:
        with SessionLocal() as db:
            user_id = ids.get("user")
            person_id = ids.get("person")
            if user_id:
                db.execute(delete(AuditLog).where(AuditLog.actor_user_id == user_id))
                db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
            if person_id:
                db.execute(
                    delete(DingTalkPersonProfile).where(
                        DingTalkPersonProfile.person_id == person_id
                    )
                )
                from app.models import Person

                db.execute(delete(Person).where(Person.id == person_id))
            if department_id := ids.get("department"):
                db.execute(
                    delete(DingTalkDepartmentLink).where(
                        DingTalkDepartmentLink.department_id == department_id
                    )
                )
                db.execute(delete(Department).where(Department.id == department_id))
            if entity_id := ids.get("entity"):
                db.execute(delete(LegalEntity).where(LegalEntity.id == entity_id))
            db.commit()


def test_dingtalk_auth_code_exchange() -> None:
    asyncio.run(exercise_dingtalk_auth_code_exchange())
