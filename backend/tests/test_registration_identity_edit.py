"""Corrections update the existing registry object and its live account references."""

import hashlib
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Asset,
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
    assert value in updated["name"] and row["identifier"] not in updated["name"]
    assert actors.admin.patch(endpoint(row), json=body).json() == updated
    assert actors.admin.patch(endpoint(row), json={**body, "source_note": "changed"}).status_code == 409
    assert actors.admin.patch(endpoint(row), json={**body, "request_id": str(uuid4())}).status_code == 409
    readback = actors.admin.get("/api/v1/workspace/registration-identities").json()
    assert next(item for item in readback if item["asset_id"] == row["asset_id"])["identifier"] == value
    context = actors.admin.get(f"/api/v1/workspace/platform-accounts/by-asset/{company_account['asset']}")
    assert context.status_code == 200, context.text
    assert next(item for item in context.json()["registration_identities"] if item["asset_id"] == row["asset_id"])["identifier"] == value
    with SessionLocal() as db:
        profile = db.get(RegistrationIdentityProfile, UUID(row["id"]))
        assert profile.identifier_masked == value
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
    assert response.status_code == 409 and "已登记" in response.text
    with SessionLocal() as db:
        assert db.get(Asset, UUID(row["asset_id"])).version == row["version"]
        assert db.get(RegistrationIdentityProfile, UUID(row["id"])).identifier_value == row["identifier"]
        assert db.get(RegistrationIdentityProfile, UUID(other["id"])).identifier_value == other["identifier"]
        assert not db.scalar(select(AuditLog.id).where(AuditLog.request_id == body["request_id"]))


def test_legacy_username_without_holder_can_be_corrected_without_changing_custom_name(actors):
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
    value = "new-" + uuid4().hex
    response = actors.admin.patch(endpoint(row), json=edit_body(row, identifier=value, identity_type="username"))
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "共享测试登录名"
    assert response.json()["identifier"] == value and response.json()["legal_entity_id"] is None


@pytest.mark.parametrize("changes", [
    {"identifier": "not-a-phone"}, {"identifier": "not-an-email", "identity_type": "email"},
    {"identifier": "  ", "identity_type": "username"}, {"source_note": " "},
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
