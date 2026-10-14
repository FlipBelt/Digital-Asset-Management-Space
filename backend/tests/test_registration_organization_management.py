"""Recoverable registry maintenance and source-backed group ownership on isolated PG."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AppSetting,
    Asset,
    AssetResponsibility,
    AuditLog,
    Department,
    DingTalkPersonProfile,
    LegalEntity,
    Person,
    PlatformAccountRegistrationIdentity,
    PlatformTenant,
    RegistrationIdentityProfile,
)
from tests.test_contact_account_governance import contact_body, reconcile
from tests.test_relationship_governance import choices, connect
from tests.test_subscription_verification import company_account as company_account

pytest_plugins = ["tests.test_asset_center_integration"]


def registry_row(actors):
    response = reconcile(actors.admin, contact_body(actors))
    assert response.status_code == 200, response.text
    return response.json()[0]


def test_separate_name_endpoint_rejects_alias_without_changing_reference(actors, company_account):
    row = registry_row(actors)
    with SessionLocal() as db:
        link = PlatformAccountRegistrationIdentity(platform_tenant_id=UUID(company_account["id"]),
            registration_identity_asset_id=UUID(row["asset_id"]))
        db.add(link)
        db.commit()
        link_id = link.id
    url = f"/api/v1/workspace/registration-identities/{row['asset_id']}/name"
    body = {"name": " 团队测试登录标识 ", "version": row["version"], "request_id": str(uuid4())}
    assert actors.owner.patch(url, json=body).status_code == 403
    response = actors.admin.patch(url, json=body)
    assert response.status_code == 422 and "标识即为名称" in response.json()["detail"]
    assert actors.admin.patch(url, json=body).status_code == 422
    with SessionLocal() as db:
        assert db.get(PlatformAccountRegistrationIdentity, link_id).registration_identity_asset_id == UUID(row["asset_id"])
        assert db.get(Asset, UUID(row["asset_id"])).version == row["version"]
        assert db.get(RegistrationIdentityProfile, UUID(row["id"])).identifier_value == row["identifier"]
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.request_id == body["request_id"])) == 0


def test_username_name_alias_and_cookie_write_rejected(actors):
    row = registry_row(actors)
    with SessionLocal() as db:
        profile = db.scalar(select(RegistrationIdentityProfile).where(
            RegistrationIdentityProfile.asset_id == UUID(row["asset_id"])))
        profile.identity_type = "other"
        profile.identifier_value = profile.identifier_masked = "test-user-" + uuid4().hex
        db.commit()
        identifier = profile.identifier_value
    url = f"/api/v1/workspace/registration-identities/{row['asset_id']}/name"
    body = {"name": "共用用户名", "version": row["version"], "request_id": str(uuid4())}
    assert actors.admin.patch(url, json={**body, "name": "  "}).status_code == 422
    cookie = TestClient(app)
    cookie.cookies.set(get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"])
    try:
        assert cookie.patch(url, json=body).status_code == 403
    finally:
        cookie.close()
    response = actors.admin.patch(url, json=body)
    assert response.status_code == 422, response.text
    values = actors.admin.get("/api/v1/workspace/registration-identities").json()
    assert next(item for item in values if item["asset_id"] == row["asset_id"])["name"] == identifier


def test_referenced_registry_deletion_blocked_then_recoverable(actors, company_account):
    row = registry_row(actors)
    with SessionLocal() as db:
        link = PlatformAccountRegistrationIdentity(platform_tenant_id=UUID(company_account["id"]),
            registration_identity_asset_id=UUID(row["asset_id"]))
        db.add(link)
        db.commit()
        link_id = link.id
    url = f"/api/v1/assets/{row['asset_id']}"
    assert actors.owner.delete(url, params={"version": row["version"]}).status_code == 403
    blocked = actors.admin.delete(url, params={"version": row["version"]})
    assert blocked.status_code == 409 and "引用" in blocked.text
    with SessionLocal() as db:
        db.get(PlatformAccountRegistrationIdentity, link_id).status = "inactive"
        db.commit()
    deleted = actors.admin.delete(url, params={"version": row["version"]})
    assert deleted.status_code == 200, deleted.text
    assert actors.admin.delete(url, params={"version": row["version"]}).json() == deleted.json()
    registry = "/api/v1/workspace/registration-identities"
    assert row["asset_id"] not in {item["asset_id"] for item in actors.admin.get(registry).json()}
    assert row["asset_id"] in {item["asset_id"] for item in actors.admin.get(registry + "?deleted_only=true").json()}
    assert actors.owner.get(registry + "?deleted_only=true").status_code == 403
    assert actors.admin.post(url + "/restore", params={"version": row["version"]}).status_code == 409
    restored = actors.admin.post(url + "/restore", params={"version": deleted.json()["version"]})
    assert restored.status_code == 200, restored.text
    assert restored.json()["id"] == row["asset_id"] and restored.json()["status"] == "active"
    assert restored.json()["review_status"] == "not_required"
    assert row["asset_id"] in {item["asset_id"] for item in actors.admin.get(registry).json()}
    assert row["asset_id"] not in {item["id"] for item in actors.admin.get(
        "/api/v1/hudu/assets?library_only=true").json()["items"]}


@pytest.fixture
def group_directory(actors):
    marker = uuid4().hex[:8]
    keys = ("organization_bootstrap", "dingtalk_directory_snapshot")
    originals = {}
    with SessionLocal() as db:
        root = db.get(LegalEntity, UUID(actors.entity))
        business = LegalEntity(code="BUS-" + marker, name=marker + "体育用品有限公司")
        db.add(business)
        db.flush()
        source = Department(legal_entity_id=root.id, code="DT-source-" + marker,
            name=marker + "企业管理有限公司")
        historical = Department(legal_entity_id=root.id, code="DT-stale-" + marker, name="历史部门")
        db.add_all([source, historical])
        db.flush()
        db.add(DingTalkPersonProfile(person_id=actors.person["owner"], dingtalk_user_id="mapping-" + marker,
            profile_data={"company_affiliation": {"name": business.name, "status": "available",
                "source_field": "主体（社保公司）", "checked_at": datetime.now(UTC).isoformat()}}))
        values = [{"legal_entity_code": root.code, "legal_entity_name": root.name},
                  {"legal_entity_id": str(root.id), "department_codes": [source.code],
                   "current_person_ids": [str(actors.person["owner"])]}]
        for key, value in zip(keys, values):
            setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
            originals[key] = setting.value if setting else None
            if setting:
                setting.value = value
            else:
                db.add(AppSetting(key=key, value=value))
        db.commit()
        result = {"business": business.id, "source_name": source.name, "root": root.id,
                  "historical": historical.id, "source_department": source.id}
    yield result
    with SessionLocal() as db:
        for key, value in originals.items():
            setting = db.scalar(select(AppSetting).where(AppSetting.key == key))
            if value is None:
                db.delete(setting)
            else:
                setting.value = value
        db.commit()


def test_group_department_discovered_without_company_nodes_or_stale_nodes(actors, company_account, group_directory):
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(company_account["asset"]))
        tenant = db.get(PlatformTenant, UUID(company_account["id"]))
        asset.legal_entity_id = tenant.legal_entity_id = group_directory["business"]
        db.commit()
    rows = choices(actors.admin, company_account["asset"])
    targets = {item["id"] for item in rows["OWNED_BY:department:upstream"]["targets"]}
    assert str(actors.teams[0]) in targets
    assert str(group_directory["historical"]) not in targets
    assert str(group_directory["source_department"]) not in targets
    saved, _ = connect(actors.admin, company_account["asset"], "OWNED_BY:department:upstream", actors.teams[0])
    assert saved.status_code == 200, saved.text
    with SessionLocal() as db:
        assert db.get(Asset, UUID(company_account["asset"])).legal_entity_id == group_directory["business"]
        assert db.get(PlatformTenant, UUID(company_account["id"])).legal_entity_id == group_directory["business"]
        assert db.get(Department, actors.teams[0]).legal_entity_id == group_directory["root"]
        assert db.get(Person, actors.person["owner"]).legal_entity_id == group_directory["root"]


def test_group_company_mapping_is_source_bound_versioned_audited_and_retry_safe(actors, group_directory):
    url = "/api/v1/organization/company-mappings"
    assert actors.owner.get(url).status_code == 403
    before = actors.admin.get(url).json()
    source = next(item for item in before["companies"] if item["name"] == group_directory["source_name"])
    assert not source["mapped"]
    body = {"request_id": str(uuid4()), "fingerprint": before["fingerprint"]}
    assert actors.owner.post(url, json=body).status_code == 403
    assert actors.admin.post(url, json={**body, "fingerprint": "0" * 64}).status_code == 409
    saved = actors.admin.post(url, json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["mapped_count"] >= 1
    assert actors.admin.post(url, json=body).json() == saved.json()
    after = actors.admin.get(url).json()
    assert next(item for item in after["companies"] if item["name"] == source["name"])["mapped"]
    with SessionLocal() as db:
        assert db.get(LegalEntity, UUID(source["id"])).name == source["name"]
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.request_id == body["request_id"])) == 1
        assert db.get(Person, actors.person["owner"]).legal_entity_id == group_directory["root"]


@pytest.mark.parametrize("conflict_kind", ["archived", "archived_source_id", "inactive", "duplicate"])
def test_group_company_mapping_preserves_conflicts_and_maps_other_sources(actors, group_directory, conflict_kind):
    marker = uuid4().hex[:8]
    source_id = uuid5(NAMESPACE_URL, "digital-center/company/" + group_directory["source_name"])
    safe_name = marker + "无冲突企业有限公司"
    safe_id = uuid5(NAMESPACE_URL, "digital-center/company/" + safe_name)
    with SessionLocal() as db:
        archived_at = datetime.now(UTC) if conflict_kind != "inactive" else None
        conflict = LegalEntity(id=source_id if conflict_kind == "archived_source_id" else uuid4(),
            code="OLD-" + marker, name=group_directory["source_name"], archived_at=archived_at,
            status="inactive" if conflict_kind == "inactive" else "active")
        db.add(conflict)
        if conflict_kind == "duplicate":
            db.add(LegalEntity(code="COPY-" + marker, name=conflict.name, archived_at=archived_at))
        code = "DT-safe-" + marker
        db.add(Department(legal_entity_id=group_directory["root"], code=code, name=safe_name))
        snapshot = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot"))
        snapshot.value = {**snapshot.value, "department_codes": [*snapshot.value["department_codes"], code]}
        db.commit()
        conflict_id = conflict.id
    url = "/api/v1/organization/company-mappings"
    before = actors.admin.get(url).json()
    source = next(item for item in before["companies"] if item["name"] == group_directory["source_name"])
    assert source["mapped"] is False and source["conflict_reason"]
    body = {"request_id": str(uuid4()), "fingerprint": before["fingerprint"]}
    saved = actors.admin.post(url, json=body)
    assert saved.status_code == 200, saved.text
    result = saved.json()
    assert result["mapped_count"] >= 1
    assert {item["name"] for item in result["conflicts"]} == {source["name"]}
    assert actors.admin.post(url, json=body).json() == result
    after = actors.admin.get(url).json()
    assert next(item for item in after["companies"] if item["id"] == str(safe_id))["mapped"]
    assert not next(item for item in after["companies"] if item["id"] == str(source_id))["mapped"]
    again = actors.admin.post(url, json={"request_id": str(uuid4()), "fingerprint": after["fingerprint"]})
    assert again.status_code == 200 and again.json()["mapped_count"] == 0
    with SessionLocal() as db:
        unchanged = db.get(LegalEntity, conflict_id)
        assert bool(unchanged.archived_at) == bool(archived_at)
        assert unchanged.status == ("inactive" if conflict_kind == "inactive" else "active")
        assert db.get(LegalEntity, safe_id).name == safe_name
        assert db.get(Person, actors.person["owner"]).legal_entity_id == group_directory["root"]
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.request_id == body["request_id"])) == 1


@pytest.mark.parametrize("archived", [True, False])
def test_company_punctuation_variants_reuse_active_or_preserve_archived_records(actors, group_directory, archived):
    marker = uuid4().hex[:8]
    company_name = marker + "体育科技（宁波）有限公司"
    variant_name = company_name.replace("（", "(").replace("）", ")")
    with SessionLocal() as db:
        company = LegalEntity(code="PUNCT-" + marker, name=company_name,
            archived_at=datetime.now(UTC) if archived else None)
        db.add(company)
        codes = ["DT-punct-full-" + marker, "DT-punct-half-" + marker]
        for code, name in zip(codes, [company_name, variant_name]):
            db.add(Department(legal_entity_id=group_directory["root"], code=code, name=name))
        snapshot = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot"))
        snapshot.value = {**snapshot.value, "department_codes": [*snapshot.value["department_codes"], *codes]}
        db.commit()
        company_id = company.id
    url = "/api/v1/organization/company-mappings"
    before = actors.admin.get(url).json()
    source = [item for item in before["companies"] if item["name"] in [company_name, variant_name]]
    assert len(source) == 1
    assert source[0]["mapped"] is not archived
    assert bool(source[0]["conflict_reason"]) is archived
    saved = actors.admin.post(url, json={"request_id": str(uuid4()), "fingerprint": before["fingerprint"]})
    assert saved.status_code == 200, saved.text
    if archived:
        assert len([item for item in saved.json()["conflicts"] if item["name"] in [company_name, variant_name]]) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.count(LegalEntity.id)).where(
            LegalEntity.name.in_([company_name, variant_name]))) == 1
        assert bool(db.get(LegalEntity, company_id).archived_at) is archived


def test_confirmed_responsibility_still_blocks_cross_company_reassignment(actors, company_account, group_directory):
    with SessionLocal() as db:
        db.add(AssetResponsibility(asset_id=UUID(company_account["asset"]),
            person_id=actors.person["owner"], role_type="responsible"))
        db.commit()
    rows = choices(actors.admin, company_account["asset"])
    target = next(item for item in rows["OWNED_BY:legal_entity:upstream"]["targets"]
                  if item["label"] == group_directory["source_name"])
    rejected, _ = connect(actors.admin, company_account["asset"], "OWNED_BY:legal_entity:upstream", target["id"])
    assert rejected.status_code == 422 and "交接" in rejected.text
    with SessionLocal() as db:
        assert db.get(LegalEntity, UUID(target["id"])) is None
        assert db.get(Asset, UUID(company_account["asset"])).legal_entity_id == group_directory["root"]
