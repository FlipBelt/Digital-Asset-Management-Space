"""Typed associations, canonical identity and actionable follow-up on isolated PG."""

from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Account,
    Asset,
    AssetRelation,
    AssetResponsibility,
    AssetType,
    AuditLog,
    Person,
    PlatformTenant,
    RegistrationIdentityProfile,
    ResourceProfile,
    Role,
    ServiceInstance,
    ServiceProduct,
    User,
    UserRoleScope,
)
from tests.test_subscription_verification import company_account as company_account

pytest_plugins = ["tests.test_asset_center_integration"]


@pytest.fixture
def resources(actors, company_account):
    marker = "REL-" + uuid4().hex[:10]
    result = {"marker": marker}
    with SessionLocal() as db:
        type_ids = {row.code: row.id for row in db.scalars(select(AssetType))}
        for key, code in [
            ("system", "internal_system"), ("server", "cloud_server"),
            ("api", "api_service"), ("contact", "registration_identity"),
            ("reclassified_contact", "cloud_server"), ("child", "platform_account"),
            ("catalog", "api_service"), ("subscription", "saas_subscription"),
            ("personal", "saas_subscription"),
        ]:
            asset = Asset(name=f"{marker}-{key}", asset_code=f"{marker}-{key}",
                          asset_type_id=type_ids[code], status="active", sharing_scope="company",
                          legal_entity_id=UUID(actors.entity), ownership_scope="company",
                          created_by_person_id=actors.person["owner"])
            db.add(asset)
            db.flush()
            result[key] = asset.id
        tenant = db.get(PlatformTenant, UUID(company_account["id"]))
        tenant_asset = db.get(Asset, tenant.asset_id)
        tenant_asset.name = marker + "-company-account"
        tenant_asset.status = "active"
        product = db.get(ServiceProduct, UUID(actors.product))
        product.platform_id = tenant.platform_id
        db.add_all([
            Account(asset_id=result["child"], platform_tenant_id=tenant.id,
                    login_identifier=marker + "@example.invalid",
                    normalized_login_identifier=marker.lower() + "@example.invalid",
                    account_type="login", registration_identity_type="email"),
            RegistrationIdentityProfile(asset_id=result["reclassified_contact"],
                identity_type="email", identifier_value=marker + "@example.invalid",
                identifier_masked="***@example.invalid", identifier_fingerprint=uuid4().hex,
                custodian_person_id=actors.person["owner"]),
            ResourceProfile(asset_id=result["catalog"], resource_family="platform_catalog"),
            ServiceInstance(asset_id=result["subscription"], service_product_id=product.id,
                purchase_tenant_asset_id=tenant.asset_id, subscription_name="Plus",
                funding_source="company", expires_at=date.today() + timedelta(days=12)),
            ServiceInstance(asset_id=result["personal"], service_product_id=product.id,
                funding_source="personal"),
        ])
        db.commit()
    return result


def choices(client, asset_id):
    response = client.get(f"/api/v1/assets/{asset_id}/relationship-choices")
    assert response.status_code == 200, response.text
    return {row["key"]: row for row in response.json()}


def connect(client, asset_id, key, target_id, **changes):
    current = client.get(f"/api/v1/assets/{asset_id}").json()
    body = {"request_id": str(uuid4()), "version": current["version"],
            "choice_key": key, "target_id": str(target_id), "note": "隔离验证关系方向"}
    body.update(changes)
    return client.post(f"/api/v1/assets/{asset_id}/relationship-connections", json=body), body


def test_real_objects_are_discovered_and_contact_child_catalog_are_excluded(actors, resources, company_account):
    rows = choices(actors.admin, resources["system"])
    assert str(company_account["platform"]) in {row["id"] for row in rows["DEPLOYED_ON:platform:upstream"]["targets"]}
    assert str(actors.teams[0]) in {row["id"] for row in rows["OWNED_BY:department:upstream"]["targets"]}
    assert actors.entity in {row["id"] for row in rows["OWNED_BY:legal_entity:upstream"]["targets"]}
    assert str(resources["api"]) in {row["id"] for row in rows["CALLS:asset:upstream"]["targets"]}
    available = {row["id"] for choice in rows.values() for row in choice["targets"]}
    assert not available.intersection(str(resources[key]) for key in (
        "contact", "reclassified_contact", "child", "catalog"))
    assert str(resources["server"]) in available
    assert choices(actors.other, resources["system"]) == {}
    response, _ = connect(actors.other, resources["system"], "USES:asset:upstream", resources["api"])
    assert response.status_code == 403


@pytest.mark.parametrize("relation", ["DEPLOYED_ON", "MOUNTED_ON"])
def test_inverse_hosting_has_one_direction_and_exact_retry(actors, resources, company_account, relation):
    asset_id = company_account["asset"]
    response, body = connect(actors.admin, asset_id, f"{relation}:asset:downstream", resources["system"])
    assert response.status_code == 200, response.text
    retry = actors.admin.post(f"/api/v1/assets/{asset_id}/relationship-connections", json=body)
    assert retry.status_code == 200, retry.text
    changed = actors.admin.post(f"/api/v1/assets/{asset_id}/relationship-connections", json={**body, "note": "改变"})
    assert changed.status_code == 409
    with SessionLocal() as db:
        row = db.scalar(select(AssetRelation).where(AssetRelation.source_asset_id == resources["system"],
            AssetRelation.target_asset_id == UUID(asset_id), AssetRelation.relation_type == relation))
        assert row is not None
        relation_id = str(row.id)
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.request_id == body["request_id"])) == 1
    system_view = actors.admin.get(f"/api/v1/assets/{resources['system']}/relationship-view").json()
    edge = next(row for row in system_view["edges"] if row["relation_id"] == relation_id)
    assert edge["source"] == f"asset:{resources['system']}" and edge["target"] == f"asset:{asset_id}"
    assert edge["direction"] == "upstream"


def test_platform_deployment_is_saved_removable_and_rejected_when_stale(actors, resources, company_account):
    asset_id = resources["system"]
    response, body = connect(actors.admin, asset_id, "DEPLOYED_ON:platform:upstream", company_account["platform"])
    assert response.status_code == 200, response.text
    edge = next(row for row in response.json()["edges"] if row["source_model"] == "AssetPlatformLink")
    assert edge["section"] == "business" and edge["source"] == f"asset:{asset_id}"
    stale = actors.admin.post(f"/api/v1/assets/{asset_id}/relationship-connections",
        json={**body, "request_id": str(uuid4())})
    assert stale.status_code == 409
    archived = actors.admin.post(f"/api/v1/assets/{asset_id}/platform-links/{edge['relation_id']}/archive")
    assert archived.status_code == 200, archived.text
    assert not any(row["id"] == edge["id"] for row in actors.admin.get(
        f"/api/v1/assets/{asset_id}/relationship-view").json()["edges"])


def test_canonical_department_and_company_no_duplicate_edges_or_grants(actors, resources):
    asset_id = resources["system"]
    response, _ = connect(actors.admin, asset_id, "OWNED_BY:department:upstream", actors.teams[0])
    assert response.status_code == 200, response.text
    asset = actors.admin.get(f"/api/v1/assets/{asset_id}").json()
    assignment = actors.admin.get(f"/api/v1/assets/{asset_id}/assignment").json()
    assert asset["owner_department_id"] == assignment["owner_department_id"] == str(actors.teams[0])
    assert assignment["ownership_scope"] == "department"
    with SessionLocal() as db:
        assert not db.scalar(select(AssetRelation.id).where(AssetRelation.source_asset_id == asset_id,
            AssetRelation.relation_type == "OWNED_BY"))


def test_inverse_candidates_respect_source_authority_and_forgery_fails(actors, resources):
    with SessionLocal() as db:
        db.get(Asset, resources["api"]).created_by_person_id = actors.person["other"]
        db.commit()
    rows = choices(actors.owner, resources["server"])
    assert str(resources["api"]) not in {row["id"] for row in rows["USES:asset:downstream"]["targets"]}
    response, _ = connect(actors.owner, resources["server"], "USES:asset:downstream", resources["api"])
    assert response.status_code == 422
    forged, _ = connect(actors.admin, resources["server"], "DEPLOYED_ON:asset:upstream", uuid4())
    assert forged.status_code == 422


def test_legacy_lowercase_relationship_is_reused(actors, resources):
    with SessionLocal() as db:
        db.add(AssetRelation(source_asset_id=resources["system"], target_asset_id=resources["api"],
                            relation_type="calls"))
        db.commit()
    response, _ = connect(actors.admin, resources["system"], "CALLS:asset:upstream", resources["api"])
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        assert db.scalar(select(func.count(AssetRelation.id)).where(
            AssetRelation.source_asset_id == resources["system"],
            AssetRelation.target_asset_id == resources["api"],
            func.lower(AssetRelation.relation_type) == "calls")) == 1


def test_owner_proposal_confirmation_syncs_overview_assignment_and_followup(actors, resources):
    asset_id = resources["system"]
    with SessionLocal() as db:
        db.add(AssetResponsibility(asset_id=asset_id, person_id=actors.person["owner"],
                                   role_type="proposed_responsible"))
        db.commit()
    assignment = actors.admin.get(f"/api/v1/assets/{asset_id}/assignment").json()
    assert assignment["responsible_status"] == "proposed"
    assert assignment["confirmed_responsible_person_id"] is None
    followup = actors.admin.get("/api/v1/hudu/expirations").json()["items"]
    item = next(row for row in followup if row["id"] == str(asset_id))
    assert item["proposed_responsible_name"] == "测试身份 owner" and not item["has_owner"]
    current = actors.admin.get(f"/api/v1/assets/{asset_id}").json()
    saved = actors.admin.put(f"/api/v1/assets/{asset_id}/assignment", json={
        "version": current["version"], "owner_department_id": None,
        "ownership_scope": "company", "responsible_person_id": str(actors.person["owner"]),
        "user_person_ids": []})
    assert saved.status_code == 200, saved.text
    assert saved.json()["responsible_status"] == "confirmed"
    assert saved.json()["confirmed_responsible_person_id"] == str(actors.person["owner"])
    assert actors.admin.get(f"/api/v1/hudu/assets/{asset_id}").json()["asset"]["responsible_person_name"] == "测试身份 owner"
    assert str(asset_id) not in {row["id"] for row in actors.admin.get("/api/v1/hudu/expirations").json()["items"]}


def test_single_platform_id_entry_is_audited_version_bound_and_deduplicated(actors, company_account):
    asset_id = company_account["asset"]
    payload = {"request_id": str(uuid4()), "version": company_account["version"],
               "identifier": " UID-" + uuid4().hex + " ", "identifier_type": "uid"}
    url = f"/api/v1/assets/{asset_id}/platform-identifier"
    assert actors.owner.put(url, json=payload).status_code == 403
    saved = actors.admin.put(url, json=payload)
    assert saved.status_code == 200, saved.text
    assert actors.admin.put(url, json=payload).status_code == 200
    context = actors.admin.get(f"/api/v1/workspace/platform-accounts/by-asset/{asset_id}").json()
    assert context["tenant_identifier"] == payload["identifier"].strip()
    assert context["external_identifier_type"] == "uid"
    assert actors.admin.put(url, json={**payload, "request_id": str(uuid4())}).status_code == 409
    with SessionLocal() as db:
        original = db.get(Asset, UUID(asset_id))
        duplicate = Asset(name="隔离重复账号", asset_code="DUP-" + uuid4().hex,
            asset_type_id=original.asset_type_id, legal_entity_id=original.legal_entity_id,
            status="active")
        db.add(duplicate)
        db.flush()
        db.add(PlatformTenant(asset_id=duplicate.id, platform_id=company_account["platform"],
                              legal_entity_id=original.legal_entity_id))
        db.commit()
        duplicate_id = duplicate.id
    rejected = actors.admin.put(f"/api/v1/assets/{duplicate_id}/platform-identifier", json={
        **payload, "request_id": str(uuid4()), "version": 1})
    assert rejected.status_code == 409


def test_contacts_hidden_from_all_business_and_personal_projections_but_references_survive(actors, resources):
    marker = resources["marker"]
    for path, array in [("/api/v1/assets", "data"), ("/api/v1/hudu/assets", "items")]:
        result = actors.admin.get(path, params={"keyword": marker, "library_only": True, "page_size": 100})
        assert result.status_code == 200, result.text
        ids = {row["id"] for row in result.json()[array]}
        assert not ids.intersection(str(resources[key]) for key in ("contact", "reclassified_contact", "child", "catalog"))
    space = actors.owner.get("/api/v1/space/assets", params={"keyword": marker, "category": "created"}).json()
    assert str(resources["contact"]) not in {row["id"] for row in space["data"]}
    assert str(resources["reclassified_contact"]) not in {row["id"] for row in space["data"]}
    assert actors.admin.get(f"/api/v1/assets/{resources['contact']}").status_code == 200


def test_followup_groups_real_subscriptions_and_excludes_catalog_contacts_personal_children(actors, resources, company_account):
    response = actors.admin.get("/api/v1/hudu/expirations")
    assert response.status_code == 200, response.text
    items = {row["id"]: row for row in response.json()["items"]}
    assert not set(items).intersection(str(resources[key]) for key in (
        "contact", "reclassified_contact", "child", "catalog", "personal"))
    account = items[company_account["asset"]]
    subscription = items[str(resources["subscription"])]
    assert account["group_key"] == subscription["group_key"] == f"account:{company_account['asset']}"
    assert subscription["plan_name"] == "Plus" and subscription["parent_account_name"] == account["name"]
    assert subscription["expires_at"][:10] == (date.today() + timedelta(days=12)).isoformat()
    assert items[str(resources["system"])]["group_section"] == "assets"
    assert response.json()["total"] == len(items)


def test_departed_owner_is_never_reported_as_confirmed(actors, resources):
    with SessionLocal() as db:
        db.get(Person, actors.person["owner"]).employment_status = "departed"
        db.add(AssetResponsibility(asset_id=resources["system"], person_id=actors.person["owner"],
                                   role_type="responsible"))
        db.commit()
    response = actors.admin.get(f"/api/v1/assets/{resources['system']}/assignment")
    assert response.status_code == 200, response.text
    assert response.json()["responsible_status"] == "inactive"
    assert response.json()["confirmed_responsible_person_id"] is None
    assert response.json()["responsibility_issue"] == "负责人已离职"


@pytest.mark.parametrize("entry", ["relationship-connections", "platform-identifier"])
def test_new_writes_require_login_and_cookie_csrf(actors, resources, company_account, entry):
    asset_id = company_account["asset"]
    payload = {"request_id": str(uuid4()), "version": company_account["version"]}
    if entry == "relationship-connections":
        payload.update(choice_key="USES:asset:upstream", target_id=str(resources["system"]))
    else:
        payload.update(identifier="isolated-csrf-" + uuid4().hex, identifier_type="uid")
    with TestClient(app) as client:
        method = client.post if entry == "relationship-connections" else client.put
        url = f"/api/v1/assets/{asset_id}/{entry}"
        assert method(url, json=payload).status_code == 401
        client.cookies.set(get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"])
        assert method(url, json=payload).status_code == 403
        csrf = client.get("/api/v1/sessions/current").json()["csrf_token"]
        assert method(url, json=payload, headers={"X-CSRF-Token": csrf}).status_code == 200


def test_department_governance_cannot_move_assets_outside_its_scope(actors, resources):
    with SessionLocal() as db:
        db.get(Asset, resources["system"]).owner_department_id = actors.teams[0]
        user = db.scalar(select(User).where(User.person_id == actors.person["other"]))
        role = db.scalar(select(Role).where(Role.code == "department_manager"))
        db.add(UserRoleScope(user_id=user.id, role_id=role.id, scope_type="department", scope_id=actors.teams[0]))
        db.commit()
    rows = choices(actors.other, resources["system"])
    assert {row["id"] for row in rows["OWNED_BY:legal_entity:upstream"]["targets"]} == {actors.entity}
    assert {row["id"] for row in rows["OWNED_BY:department:upstream"]["targets"]} == {str(actors.teams[0])}
