"""Version-bound primary registry references on the disposable PostgreSQL fixture."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Asset,
    AssetIdentifier,
    AssetRelation,
    AssetResponsibility,
    AuditLog,
    LegalEntity,
    PlatformAccountRegistrationIdentity,
    PlatformTenant,
    RegistrationIdentityProfile,
)
from tests.test_contact_account_governance import contact_body, reconcile
from tests.test_subscription_verification import company_account as company_account

pytest_plugins = ["tests.test_asset_center_integration"]
ACTION = "platform_account.registration_identity.update"


def registry_row(actors, **changes):
    response = reconcile(actors.admin, contact_body(actors, **changes))
    assert response.status_code == 200, response.text
    return response.json()[0]


def endpoint(account):
    return f"/api/v1/assets/{account['asset']}/registration-identity"


def binding_body(account, row, **changes):
    with SessionLocal() as db:
        version = db.get(Asset, UUID(account["asset"])).version
    return {"request_id": str(uuid4()), "version": version,
            "registration_identity_asset_id": row["asset_id"], **changes}


def binding_state(account):
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(account["asset"]))
        links = list(db.execute(select(
            PlatformAccountRegistrationIdentity.id,
            PlatformAccountRegistrationIdentity.registration_identity_asset_id,
            PlatformAccountRegistrationIdentity.role,
            PlatformAccountRegistrationIdentity.status,
            PlatformAccountRegistrationIdentity.starts_at,
            PlatformAccountRegistrationIdentity.ends_at,
        ).where(PlatformAccountRegistrationIdentity.platform_tenant_id == UUID(account["id"]))
            .order_by(PlatformAccountRegistrationIdentity.id)))
        relations = list(db.execute(select(
            AssetRelation.id, AssetRelation.source_asset_id, AssetRelation.target_asset_id,
            AssetRelation.relation_type, AssetRelation.archived_at,
        ).where((AssetRelation.source_asset_id == asset.id) | (AssetRelation.target_asset_id == asset.id))
            .order_by(AssetRelation.id)))
        audits = list(db.scalars(select(AuditLog.id).where(
            AuditLog.object_id == asset.id, AuditLog.action == ACTION,
        ).order_by(AuditLog.id)))
        return (asset.version, asset.outcome_version, asset.legal_entity_id, asset.status,
                asset.owner_department_id, links, relations, audits)


def seed_link(account, row, role="primary"):
    with SessionLocal() as db:
        link = PlatformAccountRegistrationIdentity(
            platform_tenant_id=UUID(account["id"]),
            registration_identity_asset_id=UUID(row["asset_id"]), role=role,
        )
        db.add(link)
        projection = db.scalar(select(AssetRelation).where(
            AssetRelation.source_asset_id == UUID(account["asset"]),
            AssetRelation.target_asset_id == UUID(row["asset_id"]),
            AssetRelation.relation_type == "registered_by",
        ))
        if projection is None:
            projection = AssetRelation(source_asset_id=UUID(account["asset"]),
                target_asset_id=UUID(row["asset_id"]), relation_type="registered_by")
            db.add(projection)
        db.commit()
        return link.id, projection.id


def make_responsible(actors, account):
    with SessionLocal() as db:
        db.add(AssetResponsibility(asset_id=UUID(account["asset"]),
            person_id=actors.person["owner"], role_type="responsible", is_primary=True))
        db.commit()


def test_binding_fills_missing_primary_and_exact_retry_is_audited_once(actors, company_account):
    row = registry_row(actors)
    body = binding_body(company_account, row)
    before = binding_state(company_account)
    saved = actors.admin.put(endpoint(company_account), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["registration_identities"][0]["asset_id"] == row["asset_id"]
    assert actors.admin.get(f"/api/v1/workspace/platform-accounts/by-asset/{company_account['asset']}").json() == saved.json()
    after = binding_state(company_account)
    assert after[0] == before[0] + 1 and after[1:5] == before[1:5]
    assert actors.admin.put(endpoint(company_account), json=body).json() == saved.json()
    assert binding_state(company_account) == after
    with SessionLocal() as db:
        audit = db.scalar(select(AuditLog).where(AuditLog.action == ACTION,
            AuditLog.object_id == UUID(company_account["asset"])))
        assert audit.request_id == body["request_id"]
        assert len(audit.after_data["request_digest"]) == 64
        assert audit.after_data["snapshot"]["context"] == saved.json()
        assert db.get(Asset, UUID(row["asset_id"])).version == row["version"]


def test_replacement_preserves_secondary_reference_and_get_returns_primary_first(actors, company_account):
    old, secondary, chosen = (registry_row(actors) for _ in range(3))
    secondary_link, secondary_relation = seed_link(company_account, secondary, "recovery")
    old_link, old_relation = seed_link(company_account, old)
    saved = actors.admin.put(endpoint(company_account), json=binding_body(company_account, chosen))
    assert saved.status_code == 200, saved.text
    assert [item["asset_id"] for item in saved.json()["registration_identities"]] == [chosen["asset_id"], secondary["asset_id"]]
    readback = actors.admin.get(f"/api/v1/workspace/platform-accounts/by-asset/{company_account['asset']}")
    assert readback.json() == saved.json()
    with SessionLocal() as db:
        assert db.get(PlatformAccountRegistrationIdentity, old_link).status == "inactive"
        assert db.get(AssetRelation, old_relation).archived_at is not None
        assert db.get(PlatformAccountRegistrationIdentity, secondary_link).status == "active"
        assert db.get(AssetRelation, secondary_relation).archived_at is None


def test_rebinding_old_identity_reactivates_historical_unique_rows(actors, company_account):
    first, second = registry_row(actors), registry_row(actors)
    first_link, first_projection = seed_link(company_account, first)
    for row in (second, first):
        saved = actors.admin.put(endpoint(company_account), json=binding_body(company_account, row))
        assert saved.status_code == 200, saved.text
    with SessionLocal() as db:
        links = list(db.scalars(select(PlatformAccountRegistrationIdentity).where(
            PlatformAccountRegistrationIdentity.platform_tenant_id == UUID(company_account["id"]))))
        assert len(links) == 2 and sum(link.status == "active" for link in links) == 1
        assert db.get(PlatformAccountRegistrationIdentity, first_link).status == "active"
        assert db.get(AssetRelation, first_projection).archived_at is None


def test_old_primary_projection_stays_when_identity_also_has_active_secondary_role(actors, company_account):
    old, chosen = registry_row(actors), registry_row(actors)
    old_link, projection = seed_link(company_account, old)
    secondary, _ = seed_link(company_account, old, "recovery")
    saved = actors.admin.put(endpoint(company_account), json=binding_body(company_account, chosen))
    assert saved.status_code == 200, saved.text
    with SessionLocal() as db:
        assert db.get(PlatformAccountRegistrationIdentity, old_link).status == "inactive"
        assert db.get(PlatformAccountRegistrationIdentity, secondary).status == "active"
        assert db.get(AssetRelation, projection).archived_at is None


def test_reused_request_rejects_changed_identity_or_version_and_preserves_state(actors, company_account):
    row, other = registry_row(actors), registry_row(actors)
    body = binding_body(company_account, row)
    assert actors.admin.put(endpoint(company_account), json=body).status_code == 200
    before = binding_state(company_account)
    for changes in ({"registration_identity_asset_id": other["asset_id"]}, {"version": body["version"] + 1}):
        assert actors.admin.put(endpoint(company_account), json={**body, **changes}).status_code == 409
        assert binding_state(company_account) == before


def test_stale_version_with_new_nonce_is_rejected_without_writes(actors, company_account):
    row = registry_row(actors)
    body = binding_body(company_account, row)
    assert actors.admin.put(endpoint(company_account), json=body).status_code == 200
    before = binding_state(company_account)
    assert actors.admin.put(endpoint(company_account), json={**body, "request_id": str(uuid4())}).status_code == 409
    assert binding_state(company_account) == before


def test_exact_retry_rejects_later_unversioned_link_changes(actors, company_account):
    row = registry_row(actors)
    body = binding_body(company_account, row)
    assert actors.admin.put(endpoint(company_account), json=body).status_code == 200
    with SessionLocal() as db:
        link = db.scalar(select(PlatformAccountRegistrationIdentity).where(
            PlatformAccountRegistrationIdentity.platform_tenant_id == UUID(company_account["id"])))
        link.status = "inactive"
        db.commit()
    before = binding_state(company_account)
    assert actors.admin.put(endpoint(company_account), json=body).status_code == 409
    assert binding_state(company_account) == before


@pytest.mark.parametrize("invalid", ["missing", "blocked", "archived_asset", "archived_profile"])
def test_invalid_identity_rejected_atomically(actors, company_account, invalid):
    row = registry_row(actors)
    if invalid == "missing":
        row["asset_id"] = str(uuid4())
    else:
        with SessionLocal() as db:
            if invalid == "blocked":
                db.add(AssetIdentifier(asset_id=UUID(row["asset_id"]), namespace=row["asset_id"],
                    identifier_type="registration_restriction", identifier_value="do_not_use"))
            elif invalid == "archived_asset":
                db.get(Asset, UUID(row["asset_id"])).archived_at = datetime.now(UTC)
            else:
                db.get(RegistrationIdentityProfile, UUID(row["id"])).archived_at = datetime.now(UTC)
            db.commit()
    before = binding_state(company_account)
    assert actors.admin.put(endpoint(company_account), json=binding_body(company_account, row)).status_code == 422
    assert binding_state(company_account) == before


def test_nonmanager_cannot_maintain_unassigned_platform_account(actors, company_account):
    row = registry_row(actors)
    before = binding_state(company_account)
    assert actors.other.put(endpoint(company_account), json=binding_body(company_account, row)).status_code == 403
    assert binding_state(company_account) == before


def test_responsible_can_bind_visible_same_company_identity(actors, company_account):
    row = registry_row(actors)
    make_responsible(actors, company_account)
    saved = actors.owner.put(endpoint(company_account), json=binding_body(company_account, row))
    assert saved.status_code == 200, saved.text


def test_responsible_cannot_bind_hidden_or_cross_company_identity(actors, company_account):
    row = registry_row(actors, custodian_person_id=str(actors.person["stranger"]))
    make_responsible(actors, company_account)
    with SessionLocal() as db:
        identity = db.get(Asset, UUID(row["asset_id"]))
        identity.sharing_scope = "private"
        identity.created_by_person_id = actors.person["stranger"]
        db.commit()
    before = binding_state(company_account)
    body = binding_body(company_account, row)
    assert actors.owner.put(endpoint(company_account), json=body).status_code == 404
    assert binding_state(company_account) == before
    with SessionLocal() as db:
        company = LegalEntity(code="BIND-" + uuid4().hex, name="隔离外部公司")
        db.add(company)
        db.flush()
        identity = db.get(Asset, UUID(row["asset_id"]))
        identity.sharing_scope = "company"
        identity.legal_entity_id = company.id
        db.commit()
        identity_company = company.id
    assert actors.owner.put(endpoint(company_account), json=body).status_code == 422
    assert binding_state(company_account) == before
    assert actors.admin.put(endpoint(company_account), json=body).status_code == 200
    with SessionLocal() as db:
        assert db.get(Asset, UUID(row["asset_id"])).legal_entity_id == identity_company


@pytest.mark.parametrize("inactive", ["asset", "tenant"])
def test_archived_account_or_tenant_cannot_receive_binding(actors, company_account, inactive):
    row = registry_row(actors)
    body = binding_body(company_account, row)
    with SessionLocal() as db:
        model, key = (Asset, company_account["asset"]) if inactive == "asset" else (PlatformTenant, company_account["id"])
        db.get(model, UUID(key)).archived_at = datetime.now(UTC)
        db.commit()
    before = binding_state(company_account)
    assert actors.admin.put(endpoint(company_account), json=body).status_code == (404 if inactive == "asset" else 422)
    assert binding_state(company_account) == before


def test_schema_requires_exact_identity_version_and_nonce(actors, company_account):
    row = registry_row(actors)
    body = binding_body(company_account, row)
    before = binding_state(company_account)
    for field in ("request_id", "version", "registration_identity_asset_id"):
        invalid = {key: value for key, value in body.items() if key != field}
        assert actors.admin.put(endpoint(company_account), json=invalid).status_code == 422
    for changes in ({"registration_identity_asset_id": None}, {"registration_identity_asset_id": ""}, {"request_id": ""}, {"version": 0}):
        assert actors.admin.put(endpoint(company_account), json={**body, **changes}).status_code == 422
    assert binding_state(company_account) == before


def test_binding_requires_session_and_cookie_csrf(actors, company_account):
    row = registry_row(actors)
    body = binding_body(company_account, row)
    before = binding_state(company_account)
    with TestClient(app) as client:
        assert client.put(endpoint(company_account), json=body).status_code == 401
        client.cookies.set(get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"])
        assert client.put(endpoint(company_account), json=body).status_code == 403
        assert binding_state(company_account) == before
        csrf = client.get("/api/v1/sessions/current").json()["csrf_token"]
        saved = client.put(endpoint(company_account), json=body, headers={"X-CSRF-Token": csrf})
        assert saved.status_code == 200, saved.text
