"""Contact holders may use the shared directory without changing business ownership."""

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
    AssetResponsibility,
    AuditLog,
    Department,
    LegalEntity,
    Person,
    PlatformAccountRegistrationIdentity,
    RegistrationIdentityProfile,
)
from tests.test_asset_assignment_policy import grant_role
from tests.test_contact_account_governance import contact_body, reconcile
from tests.test_registration_identity_edit import edit_body, endpoint
from tests.test_subscription_verification import company_account as company_account

pytest_plugins = ["tests.test_asset_center_integration"]


@pytest.fixture
def business_company(actors):
    with SessionLocal() as db:
        company = LegalEntity(code="CONTACT-" + uuid4().hex, name="隔离业务公司")
        db.add(company)
        db.commit()
        return str(company.id)


def manager_client(actors, role):
    if role == "system_admin":
        return actors.admin
    grant_role(actors, "other", "asset_manager")
    roles = actors.other.get("/api/v1/sessions/current").json()["roles"]
    assert "asset_manager" in roles and "system_admin" not in roles
    return actors.other


def current_identity(client, row):
    rows = client.get("/api/v1/workspace/registration-identities")
    assert rows.status_code == 200, rows.text
    return next(item for item in rows.json() if item["asset_id"] == row["asset_id"])


@pytest.mark.parametrize("role", ["system_admin", "asset_manager"])
def test_manager_cross_company_create_update_retry_and_reference_readback(
    actors, business_company, company_account, role
):
    client = manager_client(actors, role)
    body = contact_body(actors, legal_entity_id=business_company)
    created = reconcile(client, body)
    assert created.status_code == 200, created.text
    row = created.json()[0]
    assert row["legal_entity_id"] == business_company
    assert row["custodian_person_id"] == str(actors.person["owner"])
    assert row["owner_department_id"] == str(actors.teams[0])
    assert reconcile(client, body).json() == created.json()
    assert reconcile(client, {**body, "source_note": "变更来源"}).status_code == 409
    with SessionLocal() as db:
        reference = PlatformAccountRegistrationIdentity(
            platform_tenant_id=UUID(company_account["id"]),
            registration_identity_asset_id=UUID(row["asset_id"]),
        )
        db.add(reference)
        db.commit()
        reference_id = reference.id
    update = edit_body(
        row,
        identifier=uuid4().hex + "@example.invalid",
        identity_type="email",
        custodian_person_id=str(actors.person["stranger"]),
        owner_department_id=str(actors.teams[1]),
    )
    saved = client.patch(endpoint(row), json=update)
    assert saved.status_code == 200, saved.text
    updated = saved.json()
    assert updated["version"] == row["version"] + 1
    assert updated["identifier"] == update["identifier"]
    assert updated["custodian_person_id"] == update["custodian_person_id"]
    assert updated["owner_department_id"] == update["owner_department_id"]
    for key in ("id", "asset_id", "asset_code", "legal_entity_id"):
        assert updated[key] == row[key]
    assert client.patch(endpoint(row), json=update).json() == updated
    assert client.patch(endpoint(row), json={**update, "note": "变更内容"}).status_code == 409
    assert client.patch(endpoint(row), json={**update, "request_id": str(uuid4())}).status_code == 409
    assert current_identity(client, row) == updated
    context = client.get(f"/api/v1/workspace/platform-accounts/by-asset/{company_account['asset']}")
    assert context.status_code == 200, context.text
    identity = next(item for item in context.json()["registration_identities"] if item["asset_id"] == row["asset_id"])
    assert identity["identifier"] == updated["identifier"]
    with SessionLocal() as db:
        assert db.get(PlatformAccountRegistrationIdentity, reference_id).registration_identity_asset_id == UUID(row["asset_id"])
        assert db.get(Person, actors.person["owner"]).legal_entity_id == UUID(actors.entity)
        assert db.get(Person, actors.person["stranger"]).legal_entity_id == UUID(actors.entity)
        assert db.get(Department, actors.teams[1]).legal_entity_id == UUID(actors.entity)
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.request_id == body["request_id"])) == 1
        assert db.scalar(select(func.count(AuditLog.id)).where(AuditLog.request_id == update["request_id"])) == 1


@pytest.mark.parametrize("role", ["system_admin", "asset_manager"])
def test_manager_shared_contact_uses_cross_company_department(actors, business_company, role):
    client = manager_client(actors, role)
    response = reconcile(client, contact_body(actors, legal_entity_id=business_company, custodian_person_id=None))
    assert response.status_code == 200, response.text
    row = response.json()[0]
    assert row["custodian_person_id"] is None
    assert row["legal_entity_id"] == business_company
    assert row["owner_department_id"] == str(actors.teams[0])
    assert current_identity(client, row) == row
    with SessionLocal() as db:
        responsibility = db.scalar(select(AssetResponsibility).where(
            AssetResponsibility.asset_id == UUID(row["asset_id"]),
            AssetResponsibility.role_type == "responsible",
        ))
        assert responsibility.person_id is None
        assert responsibility.department_id == actors.teams[0]


@pytest.mark.parametrize("invalid", ["departed", "inactive", "archived", "missing"])
def test_invalid_custodian_rejected_on_create_and_update(actors, business_company, invalid):
    created = reconcile(actors.admin, contact_body(actors, legal_entity_id=business_company))
    assert created.status_code == 200, created.text
    row = created.json()[0]
    person_id = actors.person["stranger"]
    with SessionLocal() as db:
        if invalid == "missing":
            person_id = uuid4()
        else:
            person = db.get(Person, person_id)
            if invalid == "archived":
                person.archived_at = datetime.now(UTC)
            else:
                person.employment_status = invalid
            db.commit()
    body = contact_body(actors, legal_entity_id=business_company, custodian_person_id=str(person_id))
    assert reconcile(actors.admin, body).status_code == 422
    assert actors.admin.post("/api/v1/workspace/registration-identities", json=body["rows"][0]).status_code == 422
    update = edit_body(row, custodian_person_id=str(person_id))
    assert actors.admin.patch(endpoint(row), json=update).status_code == 422
    assert current_identity(actors.admin, row) == row
    with SessionLocal() as db:
        assert not db.scalar(select(RegistrationIdentityProfile.id).where(
            RegistrationIdentityProfile.identifier_value == body["rows"][0]["identifier"],
        ))
        assert not db.scalar(select(AuditLog.id).where(AuditLog.request_id.in_([
            body["request_id"], update["request_id"],
        ])))


@pytest.mark.parametrize("invalid", ["archived", "missing"])
def test_invalid_shared_department_rejected_atomically(actors, business_company, invalid):
    created = reconcile(actors.admin, contact_body(actors, legal_entity_id=business_company))
    assert created.status_code == 200, created.text
    row = created.json()[0]
    department_id = actors.teams[1]
    if invalid == "missing":
        department_id = uuid4()
    else:
        with SessionLocal() as db:
            db.get(Department, department_id).archived_at = datetime.now(UTC)
            db.commit()
    body = contact_body(actors, legal_entity_id=business_company, custodian_person_id=None, owner_department_id=str(department_id))
    assert reconcile(actors.admin, body).status_code == 422
    update = edit_body(row, custodian_person_id=None, owner_department_id=str(department_id))
    assert actors.admin.patch(endpoint(row), json=update).status_code == 422
    assert current_identity(actors.admin, row) == row


@pytest.mark.parametrize("role", ["employee", "department_manager"])
def test_nonmanager_cannot_bypass_cross_company_policy(actors, business_company, role):
    if role == "department_manager":
        grant_role(actors, "owner", role, actors.teams[0])
    created = reconcile(actors.admin, contact_body(actors))
    assert created.status_code == 200, created.text
    row = created.json()[0]
    body = contact_body(actors, legal_entity_id=business_company)
    assert reconcile(actors.owner, body).status_code == 403
    assert actors.owner.patch(endpoint(row), json=edit_body(row, legal_entity_id=business_company)).status_code == 403
    assert actors.owner.post("/api/v1/workspace/registration-identities", json=body["rows"][0]).status_code == 422
    same_company = contact_body(actors)["rows"][0]
    allowed = actors.owner.post("/api/v1/workspace/registration-identities", json=same_company)
    assert allowed.status_code == 201, allowed.text
    assert current_identity(actors.admin, row) == row


@pytest.mark.parametrize("role", ["system_admin", "asset_manager"])
def test_legacy_create_preserves_draft_for_cross_company_custodian(actors, business_company, role):
    client = manager_client(actors, role)
    body = contact_body(actors, legal_entity_id=business_company)["rows"][0]
    response = client.post("/api/v1/workspace/registration-identities", json=body)
    assert response.status_code == 201, response.text
    row = response.json()
    assert row["legal_entity_id"] == business_company
    assert row["custodian_person_id"] == str(actors.person["owner"])
    assert current_identity(client, row) == row
    with SessionLocal() as db:
        assert db.get(Asset, UUID(row["asset_id"])).status == "draft"


@pytest.mark.parametrize("operation", ["reconcile", "patch", "legacy"])
def test_contact_mutations_require_session_and_cookie_csrf(actors, business_company, operation):
    row = reconcile(actors.admin, contact_body(actors)).json()[0]
    body = contact_body(actors, legal_entity_id=business_company)
    method, path, payload = (
        ("patch", endpoint(row), edit_body(row, legal_entity_id=business_company))
        if operation == "patch"
        else ("post", "/api/v1/workspace/registration-identities" + ("/reconcile" if operation == "reconcile" else ""),
              body if operation == "reconcile" else body["rows"][0])
    )
    client = TestClient(app)
    try:
        assert client.request(method, path, json=payload).status_code == 401
        client.cookies.set(
            get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"]
        )
        assert client.request(method, path, json=payload).status_code == 403
        csrf = client.get("/api/v1/sessions/current").json()["csrf_token"]
        response = client.request(method, path, json=payload, headers={"X-CSRF-Token": csrf})
        assert response.status_code == (201 if operation == "legacy" else 200), response.text
    finally:
        client.close()


def test_contact_batch_rolls_back_valid_cross_company_row_when_later_holder_is_invalid(actors, business_company):
    body = contact_body(actors, legal_entity_id=business_company)
    other = contact_body(actors, legal_entity_id=business_company, custodian_person_id=str(uuid4()))["rows"][0]
    body["rows"].append(other)
    rejected = reconcile(actors.admin, body)
    assert rejected.status_code == 422, rejected.text
    with SessionLocal() as db:
        assert not db.scalar(select(RegistrationIdentityProfile.id).where(
            RegistrationIdentityProfile.identifier_value.in_([item["identifier"] for item in body["rows"]]),
        ))
        assert not db.scalar(select(AuditLog.id).where(AuditLog.request_id == body["request_id"]))


def test_existing_active_nonemployee_contact_holder_rule_is_preserved(actors, business_company):
    with SessionLocal() as db:
        db.get(Person, actors.person["stranger"]).person_type = "contractor"
        db.commit()
    response = reconcile(actors.admin, contact_body(
        actors, legal_entity_id=business_company, custodian_person_id=str(actors.person["stranger"]),
    ))
    assert response.status_code == 200, response.text
