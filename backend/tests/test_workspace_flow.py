import asyncio
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

from app.core.auth import hash_password
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Asset,
    AssetPlatformLink,
    AssetRelation,
    AssetResponsibility,
    AssetType,
    ImportBatch,
    LegalEntity,
    Person,
    Platform,
    PlatformAccountRegistrationIdentity,
    PlatformTenant,
    RegistrationIdentityProfile,
    ResourceProfile,
    Role,
    SourceImportRecord,
    User,
    UserRoleScope,
    UserSession,
)


async def exercise_workspace_flow() -> None:
    marker = uuid4().hex[:8]
    ids: dict[str, str] = {}
    with SessionLocal() as db:
        entity = db.scalar(select(LegalEntity).where(LegalEntity.archived_at.is_(None)))
        resource_type = db.scalar(select(AssetType).where(AssetType.code == "cloud_server"))
        assert entity is not None
        assert resource_type is not None
        ids["entity"] = str(entity.id)
        ids["resource_type"] = str(resource_type.id)
        role = db.scalar(select(Role).where(Role.code == "system_admin"))
        if role is None:
            role = Role(code="system_admin", name="Test administrator")
            db.add(role)
            db.flush()
        person = Person(
            legal_entity_id=entity.id,
            employee_no=f"WORK-{marker}",
            display_name=f"Workspace operator {marker}",
        )
        db.add(person)
        db.flush()
        user = User(
            person_id=person.id,
            username=f"workspace-{marker}",
            password_hash=hash_password("TestPassword123!"),
        )
        db.add(user)
        db.flush()
        db.add(UserRoleScope(user_id=user.id, role_id=role.id, scope_type="company"))
        db.commit()
        ids["user"] = str(user.id)
        ids["person"] = str(person.id)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            session = await client.post(
                "/api/v1/sessions",
                json={"username": f"workspace-{marker}", "password": "TestPassword123!"},
            )
            assert session.status_code == 200, session.text
            client.headers.update({"X-CSRF-Token": session.json()["user"]["csrf_token"]})
            platform = await client.post(
                "/api/v1/platforms",
                json={
                    "code": f"TEST-{marker}",
                    "name": f"测试平台 {marker}",
                    "category": "cloud",
                },
            )
            assert platform.status_code == 201, platform.text
            ids["platform"] = platform.json()["id"]

            platform_relationship_view = await client.get(
                f"/api/v1/platforms/{ids['platform']}/relationship-view"
            )
            assert platform_relationship_view.status_code == 200, platform_relationship_view.text
            assert platform_relationship_view.json()["current_node"]["layer"] == 3

            identity = await client.post(
                "/api/v1/workspace/registration-identities",
                json={
                    "identifier": f"demo-{marker}@example.com",
                    "legal_entity_id": ids["entity"],
                },
            )
            assert identity.status_code == 201, identity.text
            ids["identity_asset"] = identity.json()["asset_id"]
            assert identity.json()["asset_code"]
            assert identity.json()["legal_entity_id"] == ids["entity"]

            account = await client.post(
                "/api/v1/workspace/platform-accounts",
                json={
                    "platform_id": ids["platform"],
                    "legal_entity_id": ids["entity"],
                    "internal_name": f"测试公司平台账号 {marker}",
                    "registration_identity_asset_id": ids["identity_asset"],
                },
            )
            assert account.status_code == 201, account.text
            ids["tenant"] = account.json()["id"]
            ids["tenant_asset"] = account.json()["asset_id"]
            assert account.json()["object_type"] == "platform_account"
            assert account.json()["asset_code"]
            assert {row["kind"] for row in account.json()["links"]} == {
                "platform",
                "registration_identity",
                "person",
            }
            assert account.json()["next_actions"][0]["required"] is True

            platform_relationship_view = await client.get(
                f"/api/v1/platforms/{ids['platform']}/relationship-view"
            )
            assert platform_relationship_view.status_code == 200, platform_relationship_view.text
            assert any(
                row["label"] == "企业平台账号"
                and row["source_model"] == "PlatformTenant.platform_id"
                for row in platform_relationship_view.json()["edges"]
            )

            context = await client.get(
                f"/api/v1/workspace/platform-accounts/by-asset/{ids['tenant_asset']}"
            )
            assert context.status_code == 200, context.text
            assert context.json()["platform_id"] == ids["platform"]
            assert (
                context.json()["registration_identities"][0]["asset_id"]
                == ids["identity_asset"]
            )
            assert context.json()["registration_identities"][0]["asset_code"]

            relationship_view = await client.get(
                f"/api/v1/assets/{ids['tenant_asset']}/relationship-view"
            )
            assert relationship_view.status_code == 200, relationship_view.text
            relationship_edges = relationship_view.json()["edges"]
            assert any(
                row["label"] == "所属平台"
                and row["source_model"] == "PlatformTenant.platform_id"
                and row["editable"] is True
                for row in relationship_edges
            )
            assert any(
                row["label"] == "注册身份"
                and row["source_model"] == "PlatformAccountRegistrationIdentity"
                and row["editable"] is True
                for row in relationship_edges
            )
            platform_relation_update = await client.put(
                f"/api/v1/assets/{ids['tenant_asset']}/relationship-links/platform",
                json={"target_id": ids["platform"]},
            )
            assert (
                platform_relation_update.status_code == 200
            ), platform_relation_update.text
            assert any(
                row["edit_kind"] == "platform"
                and row["edit_target_id"] == ids["platform"]
                for row in platform_relation_update.json()["edges"]
            )

            with SessionLocal() as db:
                assert db.scalar(
                    select(AssetRelation).where(
                        AssetRelation.source_asset_id == ids["tenant_asset"],
                        AssetRelation.target_asset_id == ids["identity_asset"],
                        AssetRelation.relation_type == "registered_by",
                    )
                )
                responsibility = db.scalar(
                    select(AssetResponsibility).where(
                        AssetResponsibility.asset_id == ids["tenant_asset"],
                        AssetResponsibility.person_id == ids["person"],
                    )
                )
                assert responsibility is not None
                assert responsibility.role_type == "proposed_responsible"

            resource = await client.post(
                "/api/v1/workspace/resources",
                json={
                    "legal_entity_id": ids["entity"],
                    "asset_type_id": ids["resource_type"],
                    "resource_family": "cloud_infrastructure",
                    "name": f"测试云服务器 {marker}",
                    "business_purpose": "验证统一登记与资产地图",
                    "managed_under_account_id": ids["tenant"],
                },
            )
            assert resource.status_code == 201, resource.text
            ids["resource_asset"] = resource.json()["asset_id"]

            relationship_view = await client.get(
                f"/api/v1/assets/{ids['tenant_asset']}/relationship-view"
            )
            assert relationship_view.status_code == 200, relationship_view.text
            assert all(node["href"] for node in relationship_view.json()["nodes"])
            assert any(
                row["label"] == "管理资源"
                and row["section"] == "business"
                and row["source_model"]
                == "ResourceProfile.managed_under_account_id"
                for row in relationship_view.json()["edges"]
            )

            asset_map = await client.get("/api/v1/asset-map")
            assert asset_map.status_code == 200, asset_map.text
            node_ids = {row["asset_id"] for row in asset_map.json()["nodes"]}
            assert ids["tenant_asset"] in node_ids
            assert ids["resource_asset"] in node_ids
            platform_map = await client.get(
                "/api/v1/asset-map", params={"platform_id": ids["platform"]}
            )
            assert platform_map.status_code == 200, platform_map.text
            platform_nodes = platform_map.json()["nodes"]
            assert any(row["asset_id"] == ids["tenant_asset"] for row in platform_nodes)
            assert any(row["asset_id"] == ids["resource_asset"] for row in platform_nodes)
            matching_edges = [
                row
                for row in platform_map.json()["edges"]
                if row["source"] == f"asset:{ids['tenant_asset']}"
                and row["target"] == f"asset:{ids['resource_asset']}"
                and row["relation"] == "管理资源"
            ]
            assert len(matching_edges) == 1
            assert {
                row["id"] for row in platform_nodes if row["kind"] == "platform"
            } == {f"platform:{ids['platform']}"}

            optional_identity = await client.post(
                "/api/v1/workspace/registration-identities",
                json={
                    "identifier": f"optional-{marker}@example.com",
                    "platform_id": ids["platform"],
                },
            )
            assert optional_identity.status_code == 201, optional_identity.text
            ids["optional_identity_asset"] = optional_identity.json()["asset_id"]
            assert optional_identity.json()["legal_entity_id"] is None
            with SessionLocal() as db:
                assert db.scalar(
                    select(AssetPlatformLink).where(
                        AssetPlatformLink.asset_id == ids["optional_identity_asset"],
                        AssetPlatformLink.platform_id == ids["platform"],
                    )
                )

            optional_resource = await client.post(
                "/api/v1/workspace/resources",
                json={
                    "asset_type_id": ids["resource_type"],
                    "resource_family": "cloud_infrastructure",
                    "name": f"未归属云资源 {marker}",
                    "platform_id": ids["platform"],
                },
            )
            assert optional_resource.status_code == 201, optional_resource.text
            ids["optional_resource_asset"] = optional_resource.json()["asset_id"]
            with SessionLocal() as db:
                assert db.scalar(
                    select(AssetPlatformLink).where(
                        AssetPlatformLink.asset_id == ids["optional_resource_asset"],
                        AssetPlatformLink.platform_id == ids["platform"],
                    )
                )

            preview = await client.post(
                "/api/v1/imports/analyze",
                data={"pasted_text": "阿里云 ECS 生产服务器\n员工张三 ChatGPT Team 月费25美元"},
            )
            assert preview.status_code == 200, preview.text
            assert len(preview.json()["candidates"]) == 2
            assert preview.json()["candidates"][1]["suggested_object_type"] == "access_grant"
            staged = await client.post("/api/v1/imports/stage", json=preview.json())
            assert staged.status_code == 200, staged.text
            ids["batch"] = staged.json()["batch_id"]
            assert staged.json()["proposed_object_count"] >= 2
            batches = await client.get("/api/v1/imports/batches")
            assert batches.status_code == 200, batches.text
            assert any(item["id"] == ids["batch"] for item in batches.json())
            plan = await client.get(f"/api/v1/imports/{ids['batch']}/plan")
            assert plan.status_code == 200, plan.text
            assert len(plan.json()["objects"]) >= 2
            dry_run = await client.post(f"/api/v1/imports/{ids['batch']}/dry-run")
            assert dry_run.status_code == 200, dry_run.text
            assert dry_run.json()["pending_review_count"] >= 2
            ai_disabled = await client.post(f"/api/v1/imports/{ids['batch']}/ai-analyze")
            assert ai_disabled.status_code == 503, ai_disabled.text
            assert "尚未启用" in ai_disabled.json()["detail"]
            deprecated_commit = await client.post(
                "/api/v1/imports/commit", json={"file_name": "legacy.xlsx", "rows": []}
            )
            assert deprecated_commit.status_code == 409, deprecated_commit.text
        finally:
            with SessionLocal() as db:
                if batch_id := ids.get("batch"):
                    db.execute(
                        delete(SourceImportRecord).where(
                            SourceImportRecord.import_batch_id == batch_id
                        )
                    )
                    db.execute(delete(ImportBatch).where(ImportBatch.id == batch_id))
                if resource_asset := ids.get("resource_asset"):
                    db.execute(
                        delete(AssetRelation).where(
                            (AssetRelation.source_asset_id == resource_asset)
                            | (AssetRelation.target_asset_id == resource_asset)
                        )
                    )
                    db.execute(
                        delete(ResourceProfile).where(ResourceProfile.asset_id == resource_asset)
                    )
                    db.execute(delete(Asset).where(Asset.id == resource_asset))
                if tenant_id := ids.get("tenant"):
                    db.execute(
                        delete(PlatformAccountRegistrationIdentity).where(
                            PlatformAccountRegistrationIdentity.platform_tenant_id == tenant_id
                        )
                    )
                    db.execute(delete(PlatformTenant).where(PlatformTenant.id == tenant_id))
                if tenant_asset := ids.get("tenant_asset"):
                    db.execute(
                        delete(AssetResponsibility).where(
                            AssetResponsibility.asset_id == tenant_asset
                        )
                    )
                    db.execute(
                        delete(AssetRelation).where(
                            (AssetRelation.source_asset_id == tenant_asset)
                            | (AssetRelation.target_asset_id == tenant_asset)
                        )
                    )
                    db.execute(delete(Asset).where(Asset.id == tenant_asset))
                for optional_asset_key in (
                    "optional_resource_asset",
                    "optional_identity_asset",
                ):
                    if optional_asset := ids.get(optional_asset_key):
                        db.execute(
                            delete(AssetPlatformLink).where(
                                AssetPlatformLink.asset_id == optional_asset
                            )
                        )
                        db.execute(
                            delete(RegistrationIdentityProfile).where(
                                RegistrationIdentityProfile.asset_id == optional_asset
                            )
                        )
                        db.execute(
                            delete(ResourceProfile).where(
                                ResourceProfile.asset_id == optional_asset
                            )
                        )
                        db.execute(delete(Asset).where(Asset.id == optional_asset))
                if identity_asset := ids.get("identity_asset"):
                    db.execute(
                        delete(RegistrationIdentityProfile).where(
                            RegistrationIdentityProfile.asset_id == identity_asset
                        )
                    )
                    db.execute(delete(Asset).where(Asset.id == identity_asset))
                if platform_id := ids.get("platform"):
                    db.execute(delete(Platform).where(Platform.id == platform_id))
                if user_id := ids.get("user"):
                    db.execute(delete(UserSession).where(UserSession.user_id == user_id))
                    db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user_id))
                    db.execute(delete(User).where(User.id == user_id))
                if person_id := ids.get("person"):
                    db.execute(delete(Person).where(Person.id == person_id))
                db.commit()


def test_workspace_flow() -> None:
    asyncio.run(exercise_workspace_flow())
