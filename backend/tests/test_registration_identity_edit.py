"""Corrections update the existing registry object and its live account references."""

import hashlib
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Asset,
    AssetRelation,
    AuditLog,
    PlatformAccountRegistrationIdentity,
    RegistrationIdentityProfile,
)
from tests.test_contact_account_governance import contact_body, reconcile
from tests.test_subscription_verification import company_account as company_account

pytest_plugins = ["tests.test_asset_center_integration"]


def registry_row(actors):
    response = reconcile(actors.admin, contact_body(actors))
    assert response.status_code == 200, response.text
    return response.json()[0]


def edit_body(row, **changes):
    body = {key: row[key] for key in (
        "identifier", "identity_type", "legal_entity_id", "custodian_person_id",
        "owner_department_id", "source_nature", "registration_blocked", "note",
    )}
    return {**body, "expected_version": row["version"], "verification_status": "documented",
            "source_note": "隔离更正依据", "request_id": str(uuid4()), **changes}


def endpoint(row):
    return f"/api/v1/workspace/registration-identities/{row['asset_id']}"


@pytest.mark.parametrize("kind", ["phone", "email", "username"])
def test_correction_preserves_code_profile_and_live_reference(actors, company_account, kind):
    row = registry_row(actors)
    value = {"phone": "189" + str(uuid4().int)[-8:], "email": uuid4().hex + "@example.invalid",
             "username": "login-" + uuid4().hex}[kind]
    with SessionLocal() as db:
        link = PlatformAccountRegistrationIdentity(platform_tenant_id=UUID(company_account["id"]),
            registration_identity_asset_id=UUID(row["asset_id"]))
        db.add(link)
        db.commit()
        link_id = link.id
        count = db.scalar(select(func.count(RegistrationIdentityProfile.id)))
    raw = "+86 " + value if kind == "phone" else value.upper() if kind == "email" else value
    body = edit_body(row, identifier=raw, identity_type=kind)
    response = actors.admin.patch(endpoint(row), json=body)
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["identifier"] == value and updated["identity_type"] == kind
    assert updated["version"] == row["version"] + 1
    assert (updated["id"], updated["asset_id"], updated["asset_code"]) == (row["id"], row["asset_id"], row["asset_code"])
    assert updated["name"] == value
    assert actors.admin.patch(endpoint(row), json=body).json() == updated
    assert actors.admin.patch(endpoint(row), json={**body, "source_note": "changed"}).status_code == 409
    assert actors.admin.patch(endpoint(row), json={**body, "request_id": str(uuid4())}).status_code == 409
    readback = actors.admin.get("/api/v1/workspace/registration-identities").json()
    assert next(item for item in readback if item["asset_id"] == row["asset_id"])["identifier"] == value
    context = actors.admin.get(f"/api/v1/workspace/platform-accounts/by-asset/{company_account['asset']}")
    assert context.status_code == 200, context.text
    identity = next(item for item in context.json()["registration_identities"] if item["asset_id"] == row["asset_id"])
    assert identity["name"] == identity["identifier"] == value
    with SessionLocal() as db:
        profile = db.get(RegistrationIdentityProfile, UUID(row["id"]))
        assert profile.identifier_masked == value
        assert db.get(Asset, UUID(row["asset_id"])).name == value
        assert profile.identifier_fingerprint == hashlib.sha256(value.lower().encode()).hexdigest()
        assert db.get(PlatformAccountRegistrationIdentity, link_id).registration_identity_asset_id == UUID(row["asset_id"])
        assert db.scalar(select(func.count(RegistrationIdentityProfile.id))) == count
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.request_id == body["request_id"])) == 1
        audit = db.scalar(select(AuditLog).where(AuditLog.action == "registration_identity.update.row",
                                              AuditLog.object_id == UUID(row["asset_id"])))
        assert audit.before_data["identifier"] == row["identifier"] and audit.after_data["identifier"] == value


@pytest.mark.parametrize("deleted", [False, True])
def test_duplicate_correction_keeps_both_records_and_versions(actors, deleted):
    row, other = registry_row(actors), registry_row(actors)
    if deleted:
        assert actors.admin.delete(f"/api/v1/assets/{other['asset_id']}", params={"version": other["version"]}).status_code == 200
    # Different formatting must not bypass an existing phone identifier.
    body = edit_body(row, identifier="+86 " + other["identifier"])
    response = actors.admin.patch(endpoint(row), json=body)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "registration_identifier_conflict"
    assert response.json()["detail"]["conflict"]["asset_id"] == other["asset_id"]
    assert response.json()["detail"]["conflict"]["deleted"] is deleted
    with SessionLocal() as db:
        assert db.get(Asset, UUID(row["asset_id"])).version == row["version"]
        assert db.get(RegistrationIdentityProfile, UUID(row["id"])).identifier_value == row["identifier"]
        assert db.get(RegistrationIdentityProfile, UUID(other["id"])).identifier_value == other["identifier"]
        assert not db.scalar(select(AuditLog.id).where(AuditLog.request_id == body["request_id"]))


def test_legacy_name_is_derived_from_identifier_and_correction_replaces_cache(actors):
    row = registry_row(actors)
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(row["asset_id"]))
        asset.name = "共享测试登录名"
        asset.legal_entity_id = asset.owner_department_id = None
        profile = db.get(RegistrationIdentityProfile, UUID(row["id"]))
        profile.identity_type = "other"
        profile.custodian_person_id = None
        profile.identifier_value = profile.identifier_masked = "old-" + uuid4().hex
        profile.identifier_fingerprint = hashlib.sha256(profile.identifier_value.encode()).hexdigest()
        db.commit()
    row = next(item for item in actors.admin.get("/api/v1/workspace/registration-identities").json() if item["id"] == row["id"])
    assert row["name"] == row["identifier"]
    assert actors.admin.get(f"/api/v1/assets/{row['asset_id']}").json()["name"] == row["identifier"]
    value = "new-" + uuid4().hex
    response = actors.admin.patch(endpoint(row), json=edit_body(row, identifier=value, identity_type="username"))
    assert response.status_code == 200, response.text
    assert response.json()["name"] == value
    assert response.json()["identifier"] == value and response.json()["legal_entity_id"] is None
    with SessionLocal() as db:
        assert db.get(Asset, UUID(row["asset_id"])).name == value


def test_legacy_name_cannot_be_written_through_basic_asset_editor(actors):
    row = registry_row(actors)
    response = actors.admin.patch(f"/api/v1/assets/{row['asset_id']}", json={
        "name": "独立别名", "version": row["version"], "description": "不应保存",
    })
    assert response.status_code == 422
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(row["asset_id"]))
        assert asset.version == row["version"] and asset.description == row["note"]
        assert asset.name == row["identifier"]


def test_full_identifier_is_name_for_create_edit_context_and_relationships(actors, company_account):
    value = "login-" + uuid4().hex + "a" * 462
    assert len(value) == 500
    response = actors.admin.post("/api/v1/workspace/registration-identities", json={
        "identifier": value, "identity_type": "username", "legal_entity_id": actors.entity,
    })
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["name"] == row["identifier"] == value
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(row["asset_id"]))
        assert asset.name == value[:200]
        # An old independent name must not leak into any current read projection.
        asset.name = "历史别名"
        db.add(PlatformAccountRegistrationIdentity(platform_tenant_id=UUID(company_account["id"]),
            registration_identity_asset_id=asset.id))
        db.commit()
    assert actors.admin.get(f"/api/v1/assets/{row['asset_id']}").json()["name"] == value
    context = actors.admin.get(f"/api/v1/workspace/platform-accounts/by-asset/{company_account['asset']}").json()
    assert next(item for item in context["registration_identities"] if item["asset_id"] == row["asset_id"])["name"] == value
    relationship = actors.admin.get(f"/api/v1/assets/{company_account['asset']}/relationship-view").json()
    assert next(item for item in relationship["nodes"] if item["asset_id"] == row["asset_id"])["label"] == value
    updated = actors.admin.patch(endpoint(row), json=edit_body(row, identifier=value[:-1] + "b"))
    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == updated.json()["identifier"] == value[:-1] + "b"


@pytest.mark.parametrize("value", ["   ", "login\nvalue"])
def test_create_rejects_empty_or_control_character_identifier(actors, value):
    with SessionLocal() as db:
        count = db.scalar(select(func.count(RegistrationIdentityProfile.id)))
    response = actors.admin.post("/api/v1/workspace/registration-identities", json={
        "identifier": value, "identity_type": "username", "legal_entity_id": actors.entity,
    })
    assert response.status_code == 422
    with SessionLocal() as db:
        assert db.scalar(select(func.count(RegistrationIdentityProfile.id))) == count


@pytest.mark.parametrize("changes", [
    {"identifier": "not-a-phone"}, {"identifier": "not-an-email", "identity_type": "email"},
    {"identifier": "  ", "identity_type": "username"},
])
def test_invalid_correction_is_atomic(actors, changes):
    row = registry_row(actors)
    body = edit_body(row, **changes)
    assert actors.admin.patch(endpoint(row), json=body).status_code == 422
    with SessionLocal() as db:
        assert db.get(Asset, UUID(row["asset_id"])).version == row["version"]
        assert db.get(RegistrationIdentityProfile, UUID(row["id"])).identifier_value == row["identifier"]


def test_identifier_edit_authorization_csrf_and_deleted_record_guards(actors):
    row = registry_row(actors)
    body = edit_body(row)
    assert actors.owner.patch(endpoint(row), json=body).status_code == 403
    cookie = TestClient(app)
    cookie.cookies.set(get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"])
    try:
        assert cookie.patch(endpoint(row), json=body).status_code == 403
    finally:
        cookie.close()
    deleted = actors.admin.delete(f"/api/v1/assets/{row['asset_id']}", params={"version": row["version"]})
    assert deleted.status_code == 200, deleted.text
    assert actors.admin.patch(endpoint(row), json=edit_body(row, expected_version=deleted.json()["version"])).status_code == 404


@pytest.mark.parametrize("omitted", [False, True])
def test_source_is_optional_for_edit_and_batch_reconciliation(actors, omitted):
    body = contact_body(actors)
    if omitted:
        body.pop("source_note")
    else:
        body["source_note"] = ""
    response = reconcile(actors.admin, body)
    assert response.status_code == 200, response.text
    row = response.json()[0]
    update = edit_body(row, identifier="189" + str(uuid4().int)[-8:], source_note="")
    if omitted:
        update.pop("source_note")
    saved = actors.admin.patch(endpoint(row), json=update)
    assert saved.status_code == 200, saved.text
    assert saved.json()["asset_id"] == row["asset_id"] and saved.json()["note"] == row["note"]


def archive_identity(row, *, profile_archived=True, asset_archived=True):
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(row["asset_id"]))
        profile = db.get(RegistrationIdentityProfile, UUID(row["id"]))
        if asset_archived:
            asset.archived_at = datetime.now(UTC)
            asset.status = "archived"
        if profile_archived:
            profile.archived_at = datetime.now(UTC)
        db.commit()


def test_dormant_archived_claim_can_be_reused_preserving_history_and_retry(actors):
    row, historical = registry_row(actors), registry_row(actors)
    archive_identity(historical)
    body = edit_body(row, identifier=historical["identifier"], source_note="")
    saved = actors.admin.patch(endpoint(row), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["asset_id"] == row["asset_id"] and saved.json()["identifier"] == historical["identifier"]
    assert actors.admin.patch(endpoint(row), json=body).json() == saved.json()
    with SessionLocal() as db:
        old_asset = db.get(Asset, UUID(historical["asset_id"]))
        old_profile = db.get(RegistrationIdentityProfile, UUID(historical["id"]))
        current = db.get(RegistrationIdentityProfile, UUID(row["id"]))
        assert old_asset.status == "archived" and old_asset.archived_at is not None
        assert old_asset.name == historical["name"] and old_asset.asset_code == historical["asset_code"]
        assert old_profile.archived_at is not None and old_profile.identifier_value == historical["identifier"]
        assert old_profile.identifier_fingerprint != current.identifier_fingerprint
        assert db.scalar(select(func.count(AuditLog.id)).where(
            AuditLog.action == "registration_identity.release_archived_claim", AuditLog.request_id == body["request_id"])) == 1


@pytest.mark.parametrize("reference_kind", ["account", "asset"])
def test_archived_claim_with_effective_reference_still_blocks_correction(actors, company_account, reference_kind):
    row, historical = registry_row(actors), registry_row(actors)
    archive_identity(historical)
    with SessionLocal() as db:
        if reference_kind == "account":
            db.add(PlatformAccountRegistrationIdentity(platform_tenant_id=UUID(company_account["id"]),
                registration_identity_asset_id=UUID(historical["asset_id"])))
        else:
            db.add(AssetRelation(source_asset_id=UUID(company_account["asset"]),
                target_asset_id=UUID(historical["asset_id"]), relation_type="uses"))
        db.commit()
    response = actors.admin.patch(endpoint(row), json=edit_body(row, identifier=historical["identifier"]))
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["conflict"]["historical"]
    with SessionLocal() as db:
        assert db.get(RegistrationIdentityProfile, UUID(historical["id"])).identifier_fingerprint == hashlib.sha256(historical["identifier"].encode()).hexdigest()


@pytest.mark.parametrize("profile_archived", [False, True])
def test_partial_archival_does_not_release_a_claim(actors, profile_archived):
    row, historical = registry_row(actors), registry_row(actors)
    archive_identity(historical, profile_archived=profile_archived, asset_archived=not profile_archived)
    assert actors.admin.patch(endpoint(row), json=edit_body(row, identifier=historical["identifier"])).status_code == 409


def test_stale_correction_rolls_back_archived_claim_release(actors):
    row, historical = registry_row(actors), registry_row(actors)
    archive_identity(historical)
    body = edit_body(row, identifier=historical["identifier"], expected_version=row["version"] + 1)
    assert actors.admin.patch(endpoint(row), json=body).status_code == 409
    with SessionLocal() as db:
        profile = db.get(RegistrationIdentityProfile, UUID(historical["id"]))
        assert profile.identifier_fingerprint == hashlib.sha256(historical["identifier"].encode()).hexdigest()
        assert not db.scalar(select(AuditLog.id).where(AuditLog.request_id == body["request_id"]))
