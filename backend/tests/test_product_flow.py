import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.core.auth import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Asset,
    AssetRelation,
    AssetResponsibility,
    AuditLog,
    Department,
    LegalEntity,
    Person,
    RiskFinding,
    Role,
    User,
    UserRoleScope,
    UserSession,
    WorkflowRequest,
)


async def exercise_product_flow() -> None:
    transport = httpx.ASGITransport(app=app)
    marker = uuid4().hex[:8]
    ids: dict[str, str] = {}
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "system_admin"))
        if role is None:
            role = Role(code="system_admin", name="Test administrator")
            db.add(role)
            db.flush()
        user = User(username=f"test-{marker}", password_hash=hash_password("TestPassword123!"))
        db.add(user)
        db.flush()
        db.add(UserRoleScope(user_id=user.id, role_id=role.id, scope_type="company"))
        db.commit()
        ids["user"] = str(user.id)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            session = await client.post(
                "/api/v1/sessions",
                json={"username": f"test-{marker}", "password": "TestPassword123!"},
            )
            assert session.status_code == 200, session.text
            csrf_headers = {"X-CSRF-Token": session.json()["user"]["csrf_token"]}
            client.headers.update(csrf_headers)
            entity = await client.post(
                "/api/v1/legal-entities",
                json={"code": f"T{marker}", "name": f"端到端测试公司 {marker}"},
            )
            assert entity.status_code == 201, entity.text
            ids["entity"] = entity.json()["id"]

            department = await client.post(
                "/api/v1/departments",
                json={
                    "legal_entity_id": ids["entity"],
                    "code": f"D{marker}",
                    "name": "测试IT部",
                },
            )
            assert department.status_code == 201, department.text
            ids["department"] = department.json()["id"]

            person = await client.post(
                "/api/v1/people",
                json={
                    "legal_entity_id": ids["entity"],
                    "department_id": ids["department"],
                    "employee_no": f"E{marker}",
                    "display_name": "测试管理员",
                },
            )
            assert person.status_code == 201, person.text
            ids["person"] = person.json()["id"]

            type_rows = (await client.get("/api/v1/asset-types")).json()
            asset_type = next(row for row in type_rows if row["code"] == "internal_system")
            asset = await client.post(
                "/api/v1/assets",
                json={
                    "name": f"测试接管系统 {marker}",
                    "asset_type_id": asset_type["id"],
                    "legal_entity_id": ids["entity"],
                    "owner_department_id": ids["department"],
                    "status": "active",
                    "criticality": "critical",
                },
            )
            assert asset.status_code == 201, asset.text
            ids["asset"] = asset.json()["id"]

            related_asset = await client.post(
                "/api/v1/assets",
                json={
                    "name": f"测试云服务器 {marker}",
                    "asset_type_id": asset_type["id"],
                    "legal_entity_id": ids["entity"],
                },
            )
            assert related_asset.status_code == 201, related_asset.text
            ids["related_asset"] = related_asset.json()["id"]
            relation = await client.post(
                f"/api/v1/assets/{ids['asset']}/relations",
                json={
                    "target_asset_id": ids["related_asset"],
                    "relation_type": "DEPLOYED_ON",
                },
            )
            assert relation.status_code == 201, relation.text
            neighborhood = await client.get(
                f"/api/v1/assets/{ids['related_asset']}/relation-neighborhood"
            )
            assert neighborhood.status_code == 200, neighborhood.text
            assert neighborhood.json()[0]["source_asset_id"] == ids["asset"]

            responsibility = await client.post(
                f"/api/v1/assets/{ids['asset']}/responsibilities",
                json={
                    "person_id": ids["person"],
                    "role_type": "maintainer",
                    "is_primary": True,
                },
            )
            assert responsibility.status_code == 201, responsibility.text

            profile = await client.put(
                f"/api/v1/assets/{ids['asset']}/internal-system-profile",
                json={"tech_stack": "Vue/FastAPI", "backup_description": "每日备份"},
            )
            assert profile.status_code == 200, profile.text

            request = await client.post(
                "/api/v1/requests",
                json={"request_type": "permission", "title": "测试权限申请"},
            )
            assert request.status_code == 201, request.text
            ids["request"] = request.json()["id"]
            transition = await client.post(
                f"/api/v1/requests/{ids['request']}/transition",
                params={"target_status": "pending", "version": 1},
            )
            assert transition.status_code == 200, transition.text

            scan = await client.post("/api/v1/risk-findings/scan")
            assert scan.status_code == 200, scan.text
            dashboard = await client.get("/api/v1/dashboard")
            assert dashboard.status_code == 200
            assert dashboard.json()["metrics"]["assets"] >= 1
        finally:
            with SessionLocal() as db:
                if asset_id := ids.get("asset"):
                    db.execute(
                        delete(AssetRelation).where(
                            (AssetRelation.source_asset_id == asset_id)
                            | (AssetRelation.target_asset_id == asset_id)
                        )
                    )
                    related_asset_id = ids.get("related_asset")
                    db.execute(
                        delete(RiskFinding).where(
                            (RiskFinding.asset_id == asset_id)
                            | (RiskFinding.asset_id == related_asset_id)
                        )
                    )
                    db.execute(
                        delete(AssetResponsibility).where(AssetResponsibility.asset_id == asset_id)
                    )
                    from app.models import InternalSystemProfile

                    db.execute(
                        delete(InternalSystemProfile).where(
                            InternalSystemProfile.asset_id == asset_id
                        )
                    )
                    db.execute(delete(AuditLog).where(AuditLog.object_id == asset_id))
                    db.execute(delete(Asset).where(Asset.id == asset_id))
                if related_asset_id := ids.get("related_asset"):
                    db.execute(delete(AuditLog).where(AuditLog.object_id == related_asset_id))
                    db.execute(delete(Asset).where(Asset.id == related_asset_id))
                if request_id := ids.get("request"):
                    db.execute(delete(WorkflowRequest).where(WorkflowRequest.id == request_id))
                if person_id := ids.get("person"):
                    db.execute(delete(Person).where(Person.id == person_id))
                if department_id := ids.get("department"):
                    db.execute(delete(Department).where(Department.id == department_id))
                if entity_id := ids.get("entity"):
                    db.execute(delete(LegalEntity).where(LegalEntity.id == entity_id))
                if user_id := ids.get("user"):
                    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                    db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user_id))
                    db.execute(delete(User).where(User.id == user_id))
                db.commit()


def test_product_flow() -> None:
    asyncio.run(exercise_product_flow())
