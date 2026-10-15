"""Responsibility confirmation policy on an explicitly isolated PostgreSQL database."""

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
    AssetResponsibility,
    AuditLog,
    LegalEntity,
    Person,
    Role,
    User,
    UserRoleScope,
)
from tests.test_subscription_verification import company_account as company_account

pytest_plugins = ["tests.test_asset_center_integration"]


def assignment_url(account):
    return f"/api/v1/assets/{account['asset']}/assignment"


def assignment_body(actors, account, **changes):
    current = actors.admin.get(f"/api/v1/assets/{account['asset']}")
    assert current.status_code == 200, current.text
    return {
        "version": current.json()["version"],
        "ownership_scope": "company",
        "owner_department_id": None,
        "responsible_person_id": str(actors.person["owner"]),
        "user_person_ids": [],
        **changes,
    }


def grant_role(actors, person_key, role_code, department_id=None):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.person_id == actors.person[person_key]))
        role_id = db.scalar(select(Role.id).where(Role.code == role_code))
        assert user is not None and role_id is not None
        db.add(
            UserRoleScope(
                user_id=user.id,
                role_id=role_id,
                scope_type="department" if department_id else "company",
                scope_id=department_id,
            )
        )
        db.commit()


def assignment_state(account):
    """Include archived rows and audit IDs so rejected writes cannot silently mutate history."""
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(account["asset"]))
        responsibilities = list(
            db.execute(
                select(
                    AssetResponsibility.id,
                    AssetResponsibility.person_id,
                    AssetResponsibility.role_type,
                    AssetResponsibility.archived_at,
                )
                .where(AssetResponsibility.asset_id == asset.id)
                .order_by(AssetResponsibility.id)
            )
        )
        audits = list(
            db.scalars(
                select(AuditLog.id)
                .where(AuditLog.object_id == asset.id)
                .order_by(AuditLog.id)
            )
        )
        return (
            asset.version,
            asset.legal_entity_id,
            asset.owner_department_id,
            asset.ownership_scope,
            asset.status,
            asset.review_status,
            asset.confirmed_by_person_id,
            asset.confirmed_at,
            responsibilities,
            audits,
        )


@pytest.fixture
def foreign_people(actors):
    with SessionLocal() as db:
        entity = LegalEntity(code="ASSIGN-" + uuid4().hex, name="隔离协作公司")
        db.add(entity)
        db.flush()
        people = []
        for label in ("负责人", "协同人"):
            person = Person(
                legal_entity_id=entity.id,
                employee_no=uuid4().hex,
                display_name="隔离跨公司" + label,
                employment_status="active",
                person_type="employee",
            )
            db.add(person)
            people.append(person)
        db.commit()
        return {
            "company": entity.id,
            "responsible": people[0].id,
            "user": people[1].id,
        }


@pytest.mark.parametrize("role_code", ["system_admin", "asset_manager"])
def test_global_manager_confirms_cross_company_employees_and_preserves_directory(
    actors, company_account, foreign_people, role_code
):
    if role_code == "system_admin":
        client, actor_key = actors.admin, "admin"
    else:
        grant_role(actors, "other", "asset_manager")
        client, actor_key = actors.other, "other"
        roles = client.get("/api/v1/sessions/current").json()["roles"]
        assert "asset_manager" in roles and "system_admin" not in roles
    body = assignment_body(
        actors,
        company_account,
        responsible_person_id=str(foreign_people["responsible"]),
        user_person_ids=[str(foreign_people["user"])],
    )
    saved = client.put(assignment_url(company_account), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["responsible_status"] == "confirmed"
    assert saved.json()["confirmed_responsible_person_id"] == body["responsible_person_id"]
    assert saved.json()["user_person_ids"] == body["user_person_ids"]
    assert client.get(assignment_url(company_account)).json() == saved.json()
    current = client.get(f"/api/v1/assets/{company_account['asset']}").json()
    assert current["version"] == body["version"] + 1
    assert current["legal_entity_id"] == actors.entity
    overview = client.get(f"/api/v1/hudu/assets/{company_account['asset']}").json()["asset"]
    assert overview["has_owner"]
    assert overview["responsible_person_id"] == body["responsible_person_id"]
    assert overview["responsible_person_name"] == "隔离跨公司负责人"
    with SessionLocal() as db:
        for key in ("responsible", "user"):
            person = db.get(Person, foreign_people[key])
            assert person.legal_entity_id == foreign_people["company"]
            assert person.department_id is None
            assert person.employment_status == "active" and person.person_type == "employee"
        actor = db.scalar(select(User).where(User.person_id == actors.person[actor_key]))
        audits = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.object_id == UUID(company_account["asset"]),
                    AuditLog.action == "asset.assignment.confirm",
                )
            )
        )
        assert len(audits) == 1
        assert audits[0].actor_user_id == actor.id
        assert audits[0].after_data["responsible_person_id"] == body["responsible_person_id"]
        assert audits[0].after_data["user_person_ids"] == body["user_person_ids"]


@pytest.fixture
def department_account(actors, company_account):
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(company_account["asset"]))
        asset.owner_department_id = actors.teams[0]
        asset.ownership_scope = "department"
        db.commit()
    return company_account


def department_body(actors, account, **changes):
    return assignment_body(
        actors,
        account,
        ownership_scope="department",
        owner_department_id=str(actors.teams[0]),
        **changes,
    )


@pytest.mark.parametrize("role_code", ["department_manager", "group_leader"])
def test_department_leadership_can_confirm_same_company_employees(
    actors, department_account, role_code
):
    grant_role(actors, "owner", role_code, actors.teams[0])
    body = department_body(
        actors, department_account, user_person_ids=[str(actors.person["other"])]
    )
    saved = actors.owner.put(assignment_url(department_account), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["responsible_status"] == "confirmed"
    assert saved.json()["confirmed_responsible_person_id"] == str(actors.person["owner"])
    assert saved.json()["user_person_ids"] == body["user_person_ids"]


@pytest.mark.parametrize("role_code", ["department_manager", "group_leader"])
@pytest.mark.parametrize("selection", ["responsible", "user"])
def test_department_leadership_cannot_assign_cross_company_people(
    actors, department_account, foreign_people, role_code, selection
):
    grant_role(actors, "owner", role_code, actors.teams[0])
    existing = department_body(actors, department_account)
    saved = actors.owner.put(assignment_url(department_account), json=existing)
    assert saved.status_code == 200, saved.text
    changes = (
        {"responsible_person_id": str(foreign_people["responsible"])}
        if selection == "responsible"
        else {"user_person_ids": [str(foreign_people["user"])]}
    )
    body = department_body(actors, department_account, **changes)
    before = assignment_state(department_account)
    denied = actors.owner.put(assignment_url(department_account), json=body)
    assert denied.status_code == 422, denied.text
    assert assignment_state(department_account) == before


@pytest.mark.parametrize("invalid", ["departed", "inactive", "archived", "contractor", "missing"])
@pytest.mark.parametrize("selection", ["responsible", "user"])
def test_global_manager_cannot_confirm_invalid_people_and_rejection_is_atomic(
    actors, company_account, foreign_people, invalid, selection
):
    saved = actors.admin.put(
        assignment_url(company_account), json=assignment_body(actors, company_account)
    )
    assert saved.status_code == 200, saved.text
    invalid_id = foreign_people[selection]
    if invalid == "missing":
        invalid_id = uuid4()
    else:
        with SessionLocal() as db:
            person = db.get(Person, invalid_id)
            if invalid in {"departed", "inactive"}:
                person.employment_status = invalid
            elif invalid == "archived":
                person.archived_at = datetime.now(UTC)
            else:
                person.person_type = "contractor"
            db.commit()
    changes = (
        {"responsible_person_id": str(invalid_id)}
        if selection == "responsible"
        else {"user_person_ids": [str(invalid_id)]}
    )
    body = assignment_body(actors, company_account, **changes)
    before = assignment_state(company_account)
    denied = actors.admin.put(assignment_url(company_account), json=body)
    assert denied.status_code == 422, denied.text
    assert assignment_state(company_account) == before


def test_existing_responsible_can_update_collaborators_but_cannot_reassign_owner(
    actors, company_account
):
    saved = actors.admin.put(
        assignment_url(company_account), json=assignment_body(actors, company_account)
    )
    assert saved.status_code == 200, saved.text
    body = assignment_body(
        actors, company_account, user_person_ids=[str(actors.person["other"])]
    )
    saved = actors.owner.put(assignment_url(company_account), json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["user_person_ids"] == body["user_person_ids"]
    body = assignment_body(
        actors,
        company_account,
        responsible_person_id=str(actors.person["stranger"]),
        user_person_ids=[str(actors.person["other"])],
    )
    before = assignment_state(company_account)
    denied = actors.owner.put(assignment_url(company_account), json=body)
    assert denied.status_code == 403, denied.text
    assert assignment_state(company_account) == before


def test_stale_assignment_version_preserves_saved_responsibility_and_audit(actors, company_account):
    body = assignment_body(actors, company_account)
    saved = actors.admin.put(assignment_url(company_account), json=body)
    assert saved.status_code == 200, saved.text
    before = assignment_state(company_account)
    rejected = actors.admin.put(assignment_url(company_account), json=body)
    assert rejected.status_code == 409, rejected.text
    assert assignment_state(company_account) == before


def test_assignment_requires_authentication_and_cookie_csrf(actors, company_account):
    body = assignment_body(actors, company_account)
    before = assignment_state(company_account)
    with TestClient(app) as client:
        assert client.put(assignment_url(company_account), json=body).status_code == 401
        assert assignment_state(company_account) == before
        client.cookies.set(
            get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"]
        )
        assert client.put(assignment_url(company_account), json=body).status_code == 403
        assert assignment_state(company_account) == before
        csrf = client.get("/api/v1/sessions/current").json()["csrf_token"]
        saved = client.put(
            assignment_url(company_account), json=body, headers={"X-CSRF-Token": csrf}
        )
        assert saved.status_code == 200, saved.text
