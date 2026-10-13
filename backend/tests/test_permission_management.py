"""Permission mutations on an explicitly disposable PostgreSQL database."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.api.v1.dingtalk import _provision_dingtalk_user
from app.core.auth import get_role_codes
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AccessGrant,
    AppSetting,
    Asset,
    AssetType,
    AuditLog,
    DepartmentMembership,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    Person,
    Role,
    User,
    UserRoleScope,
)
from app.services.organization_leadership import MANUAL_PERMISSION_POLICY_KEY

pytest_plugins = ["tests.test_asset_center_integration"]
PREFIX = "/api/v1/permission-management"


@pytest.fixture
def anonymous_client():
    # Auth/RBAC requests do not require the unrelated periodic monitor lifespan.
    client = TestClient(app)
    yield client
    client.close()


@pytest.fixture
def permission_actors(actors):
    with SessionLocal() as db:
        users = {
            key: db.scalar(select(User).where(User.person_id == person_id)).id
            for key, person_id in actors.person.items()
        }
        kind = db.scalar(select(AssetType).where(AssetType.code == "internal_system"))
        asset = Asset(
            name="隔离权限验证 " + uuid4().hex,
            asset_code="PERM-" + uuid4().hex,
            asset_type_id=kind.id,
            legal_entity_id=UUID(actors.entity),
            sharing_scope="private",
            created_by_person_id=actors.person["stranger"],
            status="active",
        )
        db.add(asset)
        db.commit()
        asset_id = asset.id
    return SimpleNamespace(actors=actors, users=users, asset=asset_id)


def details(client, user_id):
    result = client.get(f"{PREFIX}/users/{user_id}")
    assert result.status_code == 200, result.text
    return result.json()


def mutation(client, user_id, **extra):
    return {
        "request_id": str(uuid4()),
        "expected_revision": details(client, user_id)["revision"],
        "reason": "仅隔离环境权限验证",
        **extra,
    }


def grant_role(client, user_id, code, department_id=None):
    body = mutation(
        client, user_id, role_code=code, department_id=str(department_id) if department_id else None
    )
    result = client.post(f"{PREFIX}/users/{user_id}/roles", json=body)
    assert result.status_code == 200, result.text
    return result, body


def deactivate_other_admins(db, keep):
    for user in db.scalars(select(User)):
        if user.id not in keep and "system_admin" in get_role_codes(db, user.id):
            user.is_active = False


def test_admin_catalog_requires_authentication_and_rejects_employee(
    permission_actors, anonymous_client
):
    rows = permission_actors
    assert anonymous_client.get(f"{PREFIX}/catalog").status_code == 401
    assert rows.actors.owner.get(f"{PREFIX}/catalog").status_code == 403
    catalog = rows.actors.admin.get(f"{PREFIX}/catalog").json()
    roles = {role["code"]: role for role in catalog["roles"]}
    assert roles["system_admin"]["scope_label"] == "全集团"
    assert roles["asset_manager"]["scope_label"] == "全集团"
    assert "developer_supervisor" not in roles
    assert str(rows.asset) in {resource["id"] for resource in catalog["resources"]}
    listing = rows.actors.admin.get(f"{PREFIX}/users", params={"keyword": "测试身份 owner"})
    assert str(rows.users["owner"]) in {user["id"] for user in listing.json()["items"]}
    assert "password_hash" not in listing.text and "session_token" not in listing.text


def test_role_grant_is_idempotent_versioned_and_immediately_effective(permission_actors):
    rows = permission_actors
    user_id = rows.users["owner"]
    result, body = grant_role(rows.actors.admin, user_id, "asset_manager")
    assert "asset_manager" in result.json()["roles"]
    assert rows.actors.owner.get("/api/v1/sessions/current").json()["roles"] == [
        "asset_manager",
        "employee",
    ]
    assert rows.actors.admin.post(f"{PREFIX}/users/{user_id}/roles", json=body).status_code == 200
    assert (
        rows.actors.admin.post(
            f"{PREFIX}/users/{user_id}/roles", json={**body, "reason": "改变同一编号内容"}
        ).status_code
        == 409
    )
    assert (
        rows.actors.admin.post(
            f"{PREFIX}/users/{user_id}/roles", json={**body, "request_id": str(uuid4())}
        ).status_code
        == 409
    )
    grant_role(rows.actors.admin, user_id, "asset_manager")
    with SessionLocal() as db:
        role = db.scalar(select(Role).where(Role.code == "asset_manager"))
        assert (
            db.scalar(
                select(func.count(UserRoleScope.id)).where(
                    UserRoleScope.user_id == user_id, UserRoleScope.role_id == role.id
                )
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(AuditLog.id)).where(
                    AuditLog.action == "permission.role.grant",
                    AuditLog.request_id == body["request_id"],
                )
            )
            == 1
        )


@pytest.mark.parametrize(
    "invalid", ["employee", "unknown_department", "global_scope", "unknown_role", "actor_spoof"]
)
def test_role_writes_reject_forgery_and_invalid_scope(permission_actors, invalid):
    rows = permission_actors
    user_id = rows.users["other"]
    body = mutation(
        rows.actors.admin,
        user_id,
        role_code="department_manager",
        department_id=str(rows.actors.teams[0]),
    )
    client = rows.actors.admin
    if invalid == "employee":
        client = rows.actors.owner
    elif invalid == "unknown_department":
        body["department_id"] = str(uuid4())
    elif invalid == "global_scope":
        body["role_code"] = "system_admin"
    elif invalid == "unknown_role":
        body["role_code"] = "developer_supervisor"
    else:
        body["actor_user_id"] = str(rows.users["admin"])
    result = client.post(f"{PREFIX}/users/{user_id}/roles", json=body)
    assert result.status_code == (403 if invalid == "employee" else 422), result.text


def test_manual_directory_scope_survives_source_projection_and_derived_scope_is_read_only(
    permission_actors,
):
    rows = permission_actors
    user_id = rows.users["owner"]
    with SessionLocal() as db:
        person = db.get(Person, rows.actors.person["owner"])
        department_id = rows.actors.teams[0]
        db.add(
            DingTalkDepartmentLink(department_id=department_id, dingtalk_department_id=uuid4().hex)
        )
        db.add(
            DingTalkPersonProfile(
                person_id=person.id, dingtalk_user_id=uuid4().hex, profile_data={}
            )
        )
        policy = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_leadership_policy"))
        value = {
            "legal_entity_id": str(person.legal_entity_id),
            "department_kinds": {"D0": "department"},
        }
        if policy:
            policy.value = value
        else:
            db.add(AppSetting(key="dingtalk_leadership_policy", value=value))
        db.commit()
    result, _ = grant_role(rows.actors.admin, user_id, "department_manager", department_id)
    assert "department_manager" in result.json()["roles"]
    with SessionLocal() as db:
        db.add(
            DepartmentMembership(
                person_id=rows.actors.person["owner"],
                department_id=department_id,
                is_manager=True,
                is_active=True,
            )
        )
        db.commit()
    current = details(rows.actors.admin, user_id)
    scopes = [role for role in current["assignments"] if role["role_code"] == "department_manager"]
    assert {role["source"] for role in scopes} == {"manual", "directory"}
    assert next(role for role in scopes if role["source"] == "directory")["revocable"] is False
    manual = next(role for role in scopes if role["source"] == "manual")
    result = rows.actors.admin.post(
        f"{PREFIX}/users/{user_id}/roles/{manual['id']}/revoke",
        json=mutation(rows.actors.admin, user_id),
    )
    assert result.status_code == 200, result.text
    scopes = [
        role for role in result.json()["assignments"] if role["role_code"] == "department_manager"
    ]
    assert len(scopes) == 1 and scopes[0]["source"] == "directory"
    assert "department_manager" in result.json()["roles"]


def test_resource_access_grant_and_revoke_preserve_other_sources(permission_actors):
    rows = permission_actors
    user_id = rows.users["owner"]
    assert rows.actors.owner.get(f"/api/v1/assets/{rows.asset}").status_code == 404
    body = mutation(
        rows.actors.admin, user_id, asset_id=str(rows.asset), starts_at=None, ends_at=None
    )
    result = rows.actors.admin.post(f"{PREFIX}/users/{user_id}/resource-grants", json=body)
    assert result.status_code == 200, result.text
    assert rows.actors.owner.get(f"/api/v1/assets/{rows.asset}").status_code == 200
    assert (
        rows.actors.admin.post(f"{PREFIX}/users/{user_id}/resource-grants", json=body).status_code
        == 200
    )
    repeated = rows.actors.admin.post(
        f"{PREFIX}/users/{user_id}/resource-grants",
        json=mutation(
            rows.actors.admin, user_id, asset_id=str(rows.asset), starts_at=None, ends_at=None
        ),
    )
    assert repeated.status_code == 200
    grant = next(
        grant
        for grant in repeated.json()["resource_grants"]
        if grant["asset_id"] == str(rows.asset)
    )
    revoke = mutation(rows.actors.admin, user_id)
    url = f"{PREFIX}/users/{user_id}/resource-grants/{grant['id']}/revoke"
    assert rows.actors.admin.post(url, json=revoke).status_code == 200
    assert rows.actors.admin.post(url, json=revoke).status_code == 200
    assert rows.actors.owner.get(f"/api/v1/assets/{rows.asset}").status_code == 404
    with SessionLocal() as db:
        saved = db.get(AccessGrant, UUID(grant["id"]))
        assert saved.archived_at and saved.status == "revoked"
        assert (
            db.scalar(
                select(func.count(AccessGrant.id)).where(
                    AccessGrant.asset_id == rows.asset,
                    AccessGrant.person_id == rows.actors.person["owner"],
                )
            )
            == 1
        )


def test_cannot_revoke_another_employees_or_department_shared_access(permission_actors):
    rows = permission_actors
    with SessionLocal() as db:
        grant = AccessGrant(
            asset_id=rows.asset,
            department_id=rows.actors.teams[0],
            grant_type="resource_access",
            grant_role="viewer",
        )
        db.add(grant)
        db.commit()
        grant_id = grant.id
    body = mutation(rows.actors.admin, rows.users["owner"])
    result = rows.actors.admin.post(
        f"{PREFIX}/users/{rows.users['owner']}/resource-grants/{grant_id}/revoke", json=body
    )
    assert result.status_code == 422


def test_user_access_pause_revokes_sessions_and_departed_user_cannot_be_reenabled(
    permission_actors,
):
    rows = permission_actors
    user_id = rows.users["other"]
    body = mutation(rows.actors.admin, user_id, enabled=False)
    result = rows.actors.admin.post(f"{PREFIX}/users/{user_id}/access", json=body)
    assert result.status_code == 200 and result.json()["is_active"] is False
    assert rows.actors.other.get("/api/v1/sessions/current").status_code == 401
    with SessionLocal() as db:
        db.get(Person, rows.actors.person["other"]).employment_status = "departed"
        db.commit()
    result = rows.actors.admin.post(
        f"{PREFIX}/users/{user_id}/access", json=mutation(rows.actors.admin, user_id, enabled=True)
    )
    assert result.status_code == 422


def test_cookie_mutations_require_csrf(permission_actors, anonymous_client):
    rows = permission_actors
    user_id = rows.users["owner"]
    body = mutation(rows.actors.admin, user_id, role_code="auditor", department_id=None)
    url = f"{PREFIX}/users/{user_id}/roles"
    client = anonymous_client
    assert client.post(url, json=body).status_code == 401
    client.cookies.set(
        get_settings().session_cookie_name, rows.actors.admin.headers["X-PM-Session"]
    )
    assert client.post(url, json=body).status_code == 403
    csrf = client.get("/api/v1/sessions/current").json()["csrf_token"]
    assert client.post(url, json=body, headers={"X-CSRF-Token": csrf}).status_code == 200


def test_last_effective_admin_cannot_be_removed_disabled_or_departed(permission_actors):
    rows = permission_actors
    user_id = rows.users["admin"]
    with SessionLocal() as db:
        deactivate_other_admins(db, {user_id})
        asset_manager = db.scalar(select(Role).where(Role.code == "asset_manager"))
        db.add(
            UserRoleScope(
                user_id=rows.users["owner"], role_id=asset_manager.id, scope_type="company"
            )
        )
        db.commit()
    current = details(rows.actors.admin, user_id)
    role = next(role for role in current["assignments"] if role["role_code"] == "system_admin")
    assert (
        rows.actors.admin.post(
            f"{PREFIX}/users/{user_id}/roles/{role['id']}/revoke",
            json=mutation(rows.actors.admin, user_id),
        ).status_code
        == 409
    )
    assert (
        rows.actors.admin.post(
            f"{PREFIX}/users/{user_id}/access",
            json=mutation(rows.actors.admin, user_id, enabled=False),
        ).status_code
        == 409
    )
    with SessionLocal() as db:
        person = db.get(Person, rows.actors.person["admin"])
        updated_at = person.updated_at.isoformat()
    departure = rows.actors.owner.post(
        f"/api/v1/people/{rows.actors.person['admin']}/lifecycle",
        json={
            "request_id": str(uuid4()),
            "expected_updated_at": updated_at,
            "employment_status": "departed",
            "departed_on": date.today().isoformat(),
            "evidence_note": "隔离最后管理员保护",
        },
    )
    assert departure.status_code == 409, departure.text
    assert details(rows.actors.admin, user_id)["is_active"] is True


def test_two_concurrent_admin_revocations_leave_one_effective_admin(permission_actors):
    rows = permission_actors
    grant_role(rows.actors.admin, rows.users["owner"], "system_admin")
    with SessionLocal() as db:
        deactivate_other_admins(db, {rows.users["admin"], rows.users["owner"]})
        db.commit()
    operations = []
    for client, target in [
        (rows.actors.admin, rows.users["owner"]),
        (rows.actors.owner, rows.users["admin"]),
    ]:
        role = next(
            role
            for role in details(client, target)["assignments"]
            if role["role_code"] == "system_admin"
        )
        operations.append(
            (client, f"{PREFIX}/users/{target}/roles/{role['id']}/revoke", mutation(client, target))
        )
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(client.post, url, json=body) for client, url, body in operations]
        codes = [future.result().status_code for future in futures]
    assert codes.count(200) == 1 and set(codes) <= {200, 403, 409}, codes
    with SessionLocal() as db:
        assert (
            sum(
                "system_admin" in get_role_codes(db, user_id)
                for user_id in [rows.users["admin"], rows.users["owner"]]
            )
            == 1
        )


def test_bootstrap_revocation_is_not_restored_on_next_verified_login(permission_actors):
    rows = permission_actors
    user_id = rows.users["owner"]
    grant_role(rows.actors.admin, user_id, "system_admin")
    with SessionLocal() as db:
        person = db.get(Person, rows.actors.person["owner"])
        ding_id = "permission-bootstrap-" + uuid4().hex
        db.add(
            DingTalkPersonProfile(person_id=person.id, dingtalk_user_id=ding_id, profile_data={})
        )
        bootstrap = db.scalar(select(AppSetting).where(AppSetting.key == "organization_bootstrap"))
        value = {"initial_administrator_candidate": person.display_name}
        verified_name = person.display_name
        if bootstrap:
            bootstrap.value = value
        else:
            db.add(AppSetting(key="organization_bootstrap", value=value))
        db.commit()
    current = details(rows.actors.admin, user_id)
    role = next(role for role in current["assignments"] if role["role_code"] == "system_admin")
    result = rows.actors.admin.post(
        f"{PREFIX}/users/{user_id}/roles/{role['id']}/revoke",
        json=mutation(rows.actors.admin, user_id),
    )
    assert result.status_code == 200, result.text
    with SessionLocal() as db:
        _provision_dingtalk_user(db, {"userid": ding_id, "name": verified_name, "dept_id_list": []})
        db.commit()
        assert "system_admin" not in get_role_codes(db, user_id)
        assert (
            str(user_id)
            in db.scalar(
                select(AppSetting).where(AppSetting.key == MANUAL_PERMISSION_POLICY_KEY)
            ).value["bootstrap_revoked_user_ids"]
        )


def test_first_legal_bootstrap_remains_available(permission_actors):
    rows = permission_actors
    user_id = rows.users["stranger"]
    with SessionLocal() as db:
        person = db.get(Person, rows.actors.person["stranger"])
        ding_id = "permission-initial-" + uuid4().hex
        db.add(
            DingTalkPersonProfile(person_id=person.id, dingtalk_user_id=ding_id, profile_data={})
        )
        bootstrap = db.scalar(select(AppSetting).where(AppSetting.key == "organization_bootstrap"))
        value = {"initial_administrator_candidate": person.display_name}
        verified_name = person.display_name
        if bootstrap:
            bootstrap.value = value
        else:
            db.add(AppSetting(key="organization_bootstrap", value=value))
        db.commit()
        _provision_dingtalk_user(db, {"userid": ding_id, "name": verified_name, "dept_id_list": []})
        db.commit()
        assert "system_admin" in get_role_codes(db, user_id)
