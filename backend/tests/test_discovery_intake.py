import asyncio
import hashlib
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.api.v1.workspace import (
    parse_import_content,
    parse_legacy_json_payload,
    recognized_import_counts,
    suggest_candidate,
)
from app.core.auth import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AccessGrant,
    Asset,
    AssetRelation,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Department,
    ImportBatch,
    InternalSystemProfile,
    LegalEntity,
    Person,
    Platform,
    Provider,
    ResourceProfile,
    Role,
    ServiceInstance,
    ServiceProduct,
    SourceImportRecord,
    User,
    UserRoleScope,
    UserSession,
)


async def login(client: httpx.AsyncClient, username: str) -> None:
    response = await client.post(
        "/api/v1/sessions",
        json={"username": username, "password": "TestPassword123!"},
    )
    assert response.status_code == 200, response.text
    client.headers.update({"X-CSRF-Token": response.json()["user"]["csrf_token"]})


async def exercise_employee_discovery_flow() -> None:
    marker = uuid4().hex[:8]
    ids: dict[str, str] = {}
    with SessionLocal() as db:
        entity = db.scalar(select(LegalEntity).where(LegalEntity.archived_at.is_(None)))
        resource_type = db.scalar(select(AssetType).where(AssetType.code == "cloud_server"))
        employee_role = db.scalar(select(Role).where(Role.code == "employee"))
        manager_role = db.scalar(select(Role).where(Role.code == "department_manager"))
        assert entity and resource_type and employee_role and manager_role

        department = Department(
            legal_entity_id=entity.id,
            code=f"DISC-{marker}",
            name=f"发现流程测试部门 {marker}",
        )
        db.add(department)
        db.flush()
        employee = Person(
            legal_entity_id=entity.id,
            department_id=department.id,
            employee_no=f"DISC-E-{marker}",
            display_name="发现提交人",
        )
        colleague = Person(
            legal_entity_id=entity.id,
            department_id=department.id,
            employee_no=f"DISC-U-{marker}",
            display_name="建议使用人",
        )
        manager = Person(
            legal_entity_id=entity.id,
            department_id=department.id,
            employee_no=f"DISC-M-{marker}",
            display_name="确认主管",
        )
        db.add_all([employee, colleague, manager])
        db.flush()
        employee_user = User(
            person_id=employee.id,
            username=f"discovery-employee-{marker}",
            password_hash=hash_password("TestPassword123!"),
        )
        manager_user = User(
            person_id=manager.id,
            username=f"discovery-manager-{marker}",
            password_hash=hash_password("TestPassword123!"),
        )
        db.add_all([employee_user, manager_user])
        db.flush()
        db.add_all(
            [
                UserRoleScope(
                    user_id=employee_user.id,
                    role_id=employee_role.id,
                    scope_type="self",
                ),
                UserRoleScope(
                    user_id=manager_user.id,
                    role_id=manager_role.id,
                    scope_type="department",
                    scope_id=department.id,
                ),
            ]
        )
        db.commit()
        ids.update(
            entity=str(entity.id),
            resource_type=str(resource_type.id),
            department=str(department.id),
            employee=str(employee.id),
            colleague=str(colleague.id),
            manager=str(manager.id),
            employee_user=str(employee_user.id),
            manager_user=str(manager_user.id),
        )

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as employee_client:
            await login(employee_client, f"discovery-employee-{marker}")
            response = await employee_client.post(
                "/api/v1/workspace/resources",
                json={
                    "legal_entity_id": ids["entity"],
                    "asset_type_id": ids["resource_type"],
                    "resource_family": "cloud_infrastructure",
                    "name": f"员工发现的 ECS {marker}",
                    "business_purpose": "验证普通员工提交发现后由主管确认",
                    "owner_department_id": ids["department"],
                    "responsible_person_id": ids["employee"],
                    "user_person_ids": [ids["employee"], ids["colleague"]],
                    "status": "active",
                },
            )
            assert response.status_code == 201, response.text
            ids["asset"] = response.json()["asset_id"]

            asset = await employee_client.get(f"/api/v1/assets/{ids['asset']}")
            assert asset.status_code == 200, asset.text
            assert asset.json()["status"] == "draft"
            assert asset.json()["review_status"] == "pending_review"
            assert asset.json()["created_by_person_id"] == ids["employee"]

            assignment = await employee_client.get(
                f"/api/v1/assets/{ids['asset']}/assignment"
            )
            assert assignment.status_code == 200, assignment.text
            assert assignment.json() == {
                "owner_department_id": ids["department"],
                "ownership_scope": "pending",
                "responsible_person_id": ids["employee"],
                "user_person_ids": [ids["colleague"]],
            }

            forbidden = await employee_client.put(
                f"/api/v1/assets/{ids['asset']}/assignment",
                json={
                    "version": asset.json()["version"],
                    "owner_department_id": ids["department"],
                    "responsible_person_id": ids["employee"],
                    "user_person_ids": [ids["colleague"]],
                },
            )
            assert forbidden.status_code == 403

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as manager_client:
            await login(manager_client, f"discovery-manager-{marker}")
            approved = await manager_client.put(
                f"/api/v1/assets/{ids['asset']}/assignment",
                json={
                    "version": 1,
                    "owner_department_id": ids["department"],
                    "responsible_person_id": ids["employee"],
                    "user_person_ids": [ids["colleague"]],
                },
            )
            assert approved.status_code == 200, approved.text
            asset = await manager_client.get(f"/api/v1/assets/{ids['asset']}")
            assert asset.json()["status"] == "active"
            assert asset.json()["review_status"] == "approved"
            assert asset.json()["confirmed_by_person_id"] == ids["manager"]
            with SessionLocal() as db:
                actions = set(
                    db.scalars(
                        select(AuditLog.action).where(AuditLog.object_id == ids["asset"])
                    )
                )
                assert {
                    "asset.discovery.create",
                    "asset.assignment.confirm",
                }.issubset(actions)
    finally:
        with SessionLocal() as db:
            if asset_id := ids.get("asset"):
                db.execute(delete(AuditLog).where(AuditLog.object_id == asset_id))
                db.execute(
                    delete(AssetResponsibility).where(
                        AssetResponsibility.asset_id == asset_id
                    )
                )
                db.execute(delete(ResourceProfile).where(ResourceProfile.asset_id == asset_id))
                db.execute(delete(Asset).where(Asset.id == asset_id))
            for user_key in ["employee_user", "manager_user"]:
                if user_id := ids.get(user_key):
                    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                    db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user_id))
                    db.execute(delete(User).where(User.id == user_id))
            for person_key in ["employee", "colleague", "manager"]:
                if person_id := ids.get(person_key):
                    db.execute(delete(Person).where(Person.id == person_id))
            if department_id := ids.get("department"):
                db.execute(delete(Department).where(Department.id == department_id))
            db.commit()


def test_employee_discovery_flow() -> None:
    asyncio.run(exercise_employee_discovery_flow())


async def exercise_legacy_html_preview() -> None:
    html = """<!doctype html><script>const DEFAULT_DATA={employees:[
    {
      员工ID:"EMP001",姓名:"徐征",昵称:"ben",部门:"管理层",
      授权工具:"ChatGPT Team",月费USD:30,状态:"活跃"
    }
    ],transactions:[]};</script>""".encode()
    transport = httpx.ASGITransport(app=app)
    marker = uuid4().hex[:8]
    ids: dict[str, str] = {}
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "system_admin"))
        assert role is not None
        user = User(
            username=f"html-preview-{marker}",
            password_hash=hash_password("TestPassword123!"),
        )
        db.add(user)
        db.flush()
        db.add(UserRoleScope(user_id=user.id, role_id=role.id, scope_type="company"))
        db.commit()
        ids["user"] = str(user.id)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await login(client, f"html-preview-{marker}")
            response = await client.post(
                "/api/v1/imports/analyze",
                files={"file": ("legacy.html", html, "text/html")},
            )
            assert response.status_code == 200, response.text
            assert response.json()["source_kind"] == "html"
            assert response.json()["candidates"][0]["suggested_object_type"] == "access_grant"
            assert (
                response.json()["candidates"][0]["suggested_name"]
                == "徐征 · ChatGPT Team"
            )
    finally:
        with SessionLocal() as db:
            if user_id := ids.get("user"):
                db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user_id))
                db.execute(delete(User).where(User.id == user_id))
                db.commit()


def test_legacy_html_preview() -> None:
    asyncio.run(exercise_legacy_html_preview())


def test_full_legacy_html_data_is_staged_without_payment_secrets() -> None:
    source = next(Path(__file__).resolve().parents[2].glob("*v4(1).html"))
    source_kind, rows = parse_import_content(source.name, source.read_bytes())
    candidates = [suggest_candidate(index, row) for index, row in enumerate(rows, start=1)]

    assert source_kind == "html"
    assert recognized_import_counts(candidates) == {
        "legacy_asset": 15,
        "access_grant": 5,
        "expense_entry": 10,
        "reimbursement_request": 2,
        "payment_method_reference": 4,
        "internal_system": 3,
        "budget_snapshot": 6,
    }
    assert all(
        "CVV" not in candidate.raw and "cvv" not in candidate.raw
        for candidate in candidates
    )
    assert all(
        candidate.source_identifier
        for candidate in candidates
    )


def test_legacy_localstorage_json_is_accepted_without_payment_secrets() -> None:
    rows = parse_legacy_json_payload(
        {
            "assets": [{"ID": "SUB-JSON", "工具服务": "JSON Tool", "套餐用途": "订阅"}],
            "employees": [{"员工ID": "EMP-JSON", "姓名": "Json Person", "授权工具": "JSON Tool"}],
            "payments": [
                {"支付方式": "测试付款方式", "CVV": "must-not-keep", "卡号": "must-not-keep"}
            ],
            "summary": [{"month": "2026-01", "usd": 10, "rmb": 70}],
        }
    )
    candidates = [suggest_candidate(index, row) for index, row in enumerate(rows, start=1)]

    assert recognized_import_counts(candidates) == {
        "legacy_asset": 1,
        "access_grant": 1,
        "payment_method_reference": 1,
        "budget_snapshot": 1,
    }
    payment = next(
        item for item in candidates if item.source_category == "payment_method_reference"
    )
    assert "CVV" not in payment.raw
    assert "卡号" not in payment.raw
    assert "已剔除敏感付款字段" in payment.warnings


async def exercise_boss_pilot_import() -> None:
    marker = uuid4().hex[:8]
    ids: dict[str, str] = {}
    service_name = f"Pilot AI {marker}"
    with SessionLocal() as db:
        entity = db.scalar(select(LegalEntity).where(LegalEntity.archived_at.is_(None)))
        employee_role = db.scalar(select(Role).where(Role.code == "employee"))
        admin_role = db.scalar(select(Role).where(Role.code == "system_admin"))
        assert entity and employee_role and admin_role
        boss = Person(
            legal_entity_id=entity.id,
            employee_no=f"PILOT-B-{marker}",
            display_name=f"Pilot Boss {marker}",
        )
        db.add(boss)
        db.flush()
        boss_user = User(
            person_id=boss.id,
            username=f"pilot-boss-{marker}",
            password_hash=hash_password("TestPassword123!"),
        )
        admin_user = User(
            username=f"pilot-admin-{marker}",
            password_hash=hash_password("TestPassword123!"),
        )
        batch = ImportBatch(
            file_name="pilot.html",
            status="pending_review",
            total_count=5,
            success_count=0,
            error_count=0,
            errors=[],
        )
        db.add_all([boss_user, admin_user, batch])
        db.flush()
        db.add_all(
            [
                UserRoleScope(user_id=boss_user.id, role_id=employee_role.id, scope_type="self"),
                UserRoleScope(user_id=admin_user.id, role_id=admin_role.id, scope_type="company"),
                SourceImportRecord(
                    import_batch_id=batch.id,
                    source_kind="html",
                    source_identifier="assets:API-100",
                    raw_payload={"ID": "API-100", "工具服务": service_name, "套餐用途": "API"},
                    suggested_object_type="service_instance",
                    suggested_name=service_name,
                    confidence=Decimal("0.98"),
                    mapping_status="pending_review",
                ),
                SourceImportRecord(
                    import_batch_id=batch.id,
                    source_kind="html",
                    source_identifier="assets:SUB-100",
                    raw_payload={
                        "ID": "SUB-100",
                        "工具服务": f"{service_name} Seat",
                        "套餐用途": "订阅",
                    },
                    suggested_object_type="service_instance",
                    suggested_name=f"{service_name} Seat",
                    confidence=Decimal("0.98"),
                    mapping_status="pending_review",
                ),
                SourceImportRecord(
                    import_batch_id=batch.id,
                    source_kind="html",
                    source_identifier="dingApps:PILOT",
                    raw_payload={"应用名称": f"Pilot App {marker}", "APIID": "API-100"},
                    suggested_object_type="internal_system",
                    suggested_name=f"Pilot App {marker}",
                    confidence=Decimal("0.98"),
                    mapping_status="pending_review",
                ),
                SourceImportRecord(
                    import_batch_id=batch.id,
                    source_kind="html",
                    source_identifier="employees:PILOT",
                    raw_payload={
                        "姓名": boss.display_name,
                        "授权工具": service_name,
                        "月费USD": 20,
                    },
                    suggested_object_type="access_grant",
                    suggested_name=boss.display_name,
                    confidence=Decimal("0.98"),
                    mapping_status="pending_review",
                ),
                SourceImportRecord(
                    import_batch_id=batch.id,
                    source_kind="html",
                    source_identifier="transactions:PILOT",
                    raw_payload={"流水ID": "TXN-PILOT", "金额USD": 20},
                    suggested_object_type="expense_entry",
                    suggested_name="TXN-PILOT",
                    confidence=Decimal("0.98"),
                    mapping_status="pending_review",
                ),
            ]
        )
        db.commit()
        ids.update(
            entity=str(entity.id),
            boss=str(boss.id),
            boss_user=str(boss_user.id),
            admin_user=str(admin_user.id),
            batch=str(batch.id),
        )

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as admin_client:
            await login(admin_client, f"pilot-admin-{marker}")
            response = await admin_client.post(
                f"/api/v1/imports/{ids['batch']}/commit-boss-pilot",
                json={"legal_entity_id": ids["entity"], "boss_person_id": ids["boss"]},
            )
            assert response.status_code == 200, response.text
            assert response.json() == {
                "batch_id": ids["batch"],
                "created_service_assets": 2,
                "created_internal_system_assets": 1,
                "pending_access_grants": 1,
                "unresolved_access_grants": 0,
                "staged_finance_records": 1,
                "status": "pilot_imported",
            }

        async with httpx.AsyncClient(transport=transport, base_url="http://test") as boss_client:
            await login(boss_client, f"pilot-boss-{marker}")
            assets = await boss_client.get("/api/v1/assets?page_size=100")
            assert assets.status_code == 200, assets.text
            asset_names = {item["name"] for item in assets.json()["data"]}
            assert any(name.startswith(service_name) for name in asset_names)
            assert any(name.startswith(f"{service_name} Seat") for name in asset_names)
            assert f"Pilot App {marker}" in asset_names
            asset_map = await boss_client.get("/api/v1/asset-map")
            assert asset_map.status_code == 200, asset_map.text
            assert any(item["kind"] == "platform" for item in asset_map.json()["nodes"])
            assert any(
                item["label"] == "待补充注册身份" for item in asset_map.json()["nodes"]
            )
            assert any(
                item["label"] == "待登记公司账号" for item in asset_map.json()["nodes"]
            )

        with SessionLocal() as db:
            imported_assets = list(
                db.scalars(
                    select(Asset).where(
                        Asset.created_by_person_id == ids["boss"],
                        Asset.source_type == "legacy_import",
                    )
                )
            )
            assert len(imported_assets) == 3
            assert all(item.owner_department_id is None for item in imported_assets)
            assert all(item.review_status == "pending_review" for item in imported_assets)
            instances = list(
                db.scalars(
                    select(ServiceInstance).where(
                        ServiceInstance.asset_id.in_([item.id for item in imported_assets])
                    )
                )
            )
            assert all(item.purchase_platform_id is not None for item in instances)
            assert db.scalar(
                select(AccessGrant).where(AccessGrant.legacy_source_id == "employees:PILOT")
            ).status == "pending_review"
            assert db.scalar(
                select(AssetRelation).where(AssetRelation.source_type == "legacy_import")
            )
    finally:
        with SessionLocal() as db:
            batch_id = ids.get("batch")
            if batch_id:
                db.execute(
                    delete(SourceImportRecord).where(SourceImportRecord.import_batch_id == batch_id)
                )
            db.execute(delete(AccessGrant).where(AccessGrant.legacy_source_id == "employees:PILOT"))
            imported_assets = list(
                db.scalars(
                    select(Asset).where(
                        Asset.created_by_person_id == ids.get("boss"),
                        Asset.source_type == "legacy_import",
                    )
                )
            )
            asset_ids = [item.id for item in imported_assets]
            if asset_ids:
                db.execute(delete(AssetRelation).where(AssetRelation.source_asset_id.in_(asset_ids)))
                db.execute(delete(AuditLog).where(AuditLog.object_id.in_(asset_ids)))
                db.execute(delete(AssetResponsibility).where(AssetResponsibility.asset_id.in_(asset_ids)))
                db.execute(delete(ServiceInstance).where(ServiceInstance.asset_id.in_(asset_ids)))
                db.execute(delete(InternalSystemProfile).where(InternalSystemProfile.asset_id.in_(asset_ids)))
                db.execute(delete(Asset).where(Asset.id.in_(asset_ids)))
            provider_codes = [
                f"legacy-{hashlib.sha256(name.encode('utf-8')).hexdigest()[:16]}"
                for name in [service_name, f"{service_name} Seat"]
            ]
            provider_ids = list(
                db.scalars(select(Provider.id).where(Provider.code.in_(provider_codes)))
            )
            if provider_ids:
                db.execute(delete(Platform).where(Platform.provider_id.in_(provider_ids)))
                db.execute(delete(ServiceProduct).where(ServiceProduct.provider_id.in_(provider_ids)))
                db.execute(delete(Provider).where(Provider.id.in_(provider_ids)))
            if batch_id:
                db.execute(delete(ImportBatch).where(ImportBatch.id == batch_id))
            for user_key in ["boss_user", "admin_user"]:
                if user_id := ids.get(user_key):
                    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                    db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user_id))
                    db.execute(delete(User).where(User.id == user_id))
            if boss_id := ids.get("boss"):
                db.execute(delete(Person).where(Person.id == boss_id))
            db.commit()


def test_boss_pilot_import_is_private_and_reviewable() -> None:
    asyncio.run(exercise_boss_pilot_import())
