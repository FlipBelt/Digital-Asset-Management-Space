"""API integration on an explicitly opted-in, disposable PostgreSQL database."""

import io
import os
import zipfile
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.auth import create_session
from app.core.config import get_settings
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import (
    AccessGrant,
    Account,
    Asset,
    AssetBookmark,
    AssetCategory,
    AssetConfirmation,
    AssetEvidence,
    AssetType,
    AuditLog,
    Department,
    DepartmentMembership,
    LegalEntity,
    Person,
    Platform,
    Provider,
    Role,
    ServiceInstance,
    ServiceProduct,
    User,
    UserRoleScope,
)


@pytest.fixture
def actors():
    if os.environ.get("ASSET_CENTER_ISOLATED_TESTS") != "1":
        pytest.skip("Set ASSET_CENTER_ISOLATED_TESTS=1 only for the disposable rehearsal DB.")
    assert engine.url.host == "127.0.0.1" and engine.url.port == 55433
    assert (engine.url.database or "").startswith("dam_v13_tests_")
    assert get_settings().app_env == "local"
    marker = uuid4().hex[:10]
    clients = {}
    with SessionLocal() as db:
        entity = LegalEntity(code="API-" + marker, name="隔离 API 测试公司")
        db.add(entity)
        db.flush()
        teams = [
            Department(legal_entity_id=entity.id, code=f"D{i}", name=f"测试部门 {i}")
            for i in range(3)
        ]
        db.add_all(teams)
        db.flush()
        people = {}
        for key, team, role in [
            ("owner", teams[0], "employee"),
            ("other", teams[1], "employee"),
            ("stranger", teams[2], "employee"),
            ("admin", teams[2], "system_admin"),
        ]:
            person = Person(
                legal_entity_id=entity.id,
                department_id=team.id,
                employee_no=key,
                display_name="测试身份 " + key,
            )
            db.add(person)
            db.flush()
            people[key] = person.id
            user = User(
                person_id=person.id,
                username=f"{key}-{marker}",
                password_hash="!disabled-test-login!",
            )
            db.add(user)
            db.flush()
            role_id = db.scalar(select(Role.id).where(Role.code == role))
            db.add(UserRoleScope(user_id=user.id, role_id=role_id, scope_type="company"))
            db.commit()
            token, _ = create_session(db, user, "isolated-test")
            clients[key] = TestClient(app, headers={"X-PM-Session": token})
        db.add(
            DepartmentMembership(
                person_id=people["owner"], department_id=teams[1].id, is_active=True
            )
        )
        provider = Provider(code="P-" + marker, name="隔离测试供应商")
        db.add(provider)
        db.flush()
        product = ServiceProduct(
            provider_id=provider.id,
            code="ai",
            name="测试 AI 服务",
            service_category="ai",
            billing_mode="subscription",
        )
        db.add(product)
        db.commit()
        ids = dict(
            person=people,
            entity=str(entity.id),
            teams=[team.id for team in teams],
            product=str(product.id),
            skill=str(db.scalar(select(AssetType.id).where(AssetType.code == "ai_skill"))),
        )
    yield SimpleNamespace(**clients, **ids)
    for client in clients.values():
        client.close()


def draft(client, actors, **fields):
    payload = dict(
        request_id=str(uuid4()),
        name="测试成果",
        description="只用于隔离验证",
        asset_type_id=actors.skill,
    )
    payload.update(fields)
    response = client.post("/api/v1/assets/draft", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def prepare(client, asset, scope="private"):
    response = client.post(
        f"/api/v1/assets/{asset['id']}/confirmation",
        json=dict(request_id=str(uuid4()), version=asset["version"], sharing_scope=scope),
    )
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, asset, receipt):
    return client.post(
        f"/api/v1/assets/{asset['id']}/confirm",
        json=dict(
            confirmation_id=receipt["id"],
            version=receipt["asset_version"],
            content_digest=receipt["content_digest"],
            confirmed=True,
        ),
    )


def membership(client, actors, funding="personal"):
    response = client.post(
        "/api/v1/space/memberships",
        json=dict(
            request_id=str(uuid4()),
            service_product_id=actors.product,
            plan="测试套餐",
            funding_source=funding,
            starts_at="2026-09-28",
            usage_frequency="weekly",
            primary_purpose="只用于本地验证",
        ),
    )
    assert response.status_code == 200, response.text
    rows = client.get("/api/v1/space/memberships").json()
    return response.json(), next(row for row in rows if row["asset_id"] == response.json()["id"])


def evidence(instance):
    return dict(
        request_id=str(uuid4()),
        kind="exploration",
        subscription_id=instance["id"],
        title="测试探索",
        problem="测试问题",
        method="测试方法",
        output="测试成果",
    )


def test_draft_actor_privacy_and_extra_claims(actors):
    asset = draft(actors.owner, actors)
    assert asset["created_by_person_id"] == str(actors.person["owner"])
    assert asset["sharing_scope"] == "private" and asset["status"] == "draft"
    assert actors.other.get(f"/api/v1/assets/{asset['id']}").status_code == 404
    assert actors.other.get(f"/api/v1/assets/{asset['id']}/attachments").status_code == 404
    assert actors.admin.get(f"/api/v1/assets/{asset['id']}").status_code == 200
    response = actors.owner.post(
        "/api/v1/assets/draft",
        json=dict(
            request_id=str(uuid4()),
            name="X",
            description="Y",
            asset_type_id=actors.skill,
            created_by_person_id=str(actors.person["other"]),
            status="active",
        ),
    )
    assert response.status_code == 422
    direct = actors.owner.post(
        "/api/v1/assets", json=dict(name="Bypass", asset_type_id=actors.skill, status="active")
    )
    assert direct.status_code == 403


def test_cookie_write_requires_csrf(actors):
    cookie_client = TestClient(app)
    cookie_client.cookies.set(
        get_settings().session_cookie_name, actors.owner.headers["X-PM-Session"]
    )
    body = dict(
        request_id=str(uuid4()), name="CSRF", description="Test", asset_type_id=actors.skill
    )
    assert cookie_client.post("/api/v1/assets/draft", json=body).status_code == 403
    csrf = cookie_client.get("/api/v1/sessions/current").json()["csrf_token"]
    assert (
        cookie_client.post(
            "/api/v1/assets/draft", json=body, headers={"X-CSRF-Token": csrf}
        ).status_code
        == 200
    )
    cookie_client.close()


def test_confirmation_exact_version_repeat_and_verified_audit(actors):
    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    assert receipt["preview"]["asset"]["name"] == asset["name"]
    assert receipt["preview"]["attachments"] == []
    result = confirm(actors.owner, asset, receipt)
    assert result.status_code == 200, result.text
    assert result.json()["version"] == asset["version"] + 1
    assert result.json()["review_status"] == "pending_review"
    assert confirm(actors.owner, asset, receipt).json()["id"] == asset["id"]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action == "asset.registration.confirm",
                    AuditLog.object_id == UUID(asset["id"]),
                )
            )
            == 1
        )


def test_changed_draft_invalidates_confirmation(actors):
    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    changed = actors.owner.patch(
        f"/api/v1/assets/{asset['id']}", json=dict(version=asset["version"], name="新名称")
    )
    assert changed.status_code == 200, changed.text
    assert confirm(actors.owner, asset, receipt).status_code == 409


def test_attachment_invalidates_confirmation(actors, tmp_path, monkeypatch):
    from app.api.v1 import asset_attachments

    monkeypatch.setattr(asset_attachments, "STORAGE", tmp_path)
    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("SKILL.md", "Test fixture")
    response = actors.owner.post(
        f"/api/v1/assets/{asset['id']}/attachments",
        files={"file": ("test.zip", buffer.getvalue(), "application/zip")},
    )
    assert response.status_code == 200, response.text
    assert confirm(actors.owner, asset, receipt).status_code == 409
    assert (
        actors.other.get(
            f"/api/v1/assets/{asset['id']}/attachments/{response.json()['id']}/download"
        ).status_code
        == 404
    )


def test_cancelled_or_other_actor_confirmation_rejected(actors):
    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    assert confirm(actors.other, asset, receipt).status_code in (403, 404)
    assert (
        actors.owner.delete(
            f"/api/v1/assets/{asset['id']}/confirmation/{receipt['id']}"
        ).status_code
        == 204
    )
    assert confirm(actors.owner, asset, receipt).status_code == 409


def test_bookmarks_idempotent_and_personal(actors):
    asset = draft(actors.owner, actors)
    path = f"/api/v1/assets/{asset['id']}/bookmark"
    assert actors.owner.put(path).status_code == 204
    assert actors.owner.put(path).status_code == 204
    assert actors.other.put(path).status_code == 404
    assert actors.owner.get("/api/v1/space/bookmarks").json() == [asset["id"]]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AssetBookmark)
                .where(AssetBookmark.asset_id == UUID(asset["id"]))
            )
            == 1
        )
    assert actors.owner.delete(path).status_code == 204
    assert actors.owner.get("/api/v1/space/bookmarks").json() == []


def test_subscription_exploration_is_self_funded_and_persistent(actors):
    asset, instance = membership(actors.owner, actors)
    payload = evidence(instance)
    response = actors.owner.post("/api/v1/space/evidence", json=payload)
    assert response.status_code == 200, response.text
    assert (
        actors.owner.post("/api/v1/space/evidence", json=payload).json()["id"]
        == response.json()["id"]
    )
    changed = actors.owner.post("/api/v1/space/evidence", json={**payload, "title": "不同内容"})
    assert changed.status_code == 409
    assert actors.owner.get("/api/v1/space/evidence").json()["pagination"]["total"] == 1
    assert actors.other.get("/api/v1/space/evidence").json()["data"] == []
    assert actors.other.post("/api/v1/space/evidence", json=evidence(instance)).status_code == 404
    refused = actors.owner.post(
        f"/api/v1/assets/{asset['id']}/confirmation",
        json=dict(request_id=str(uuid4()), version=asset["version"], sharing_scope="company"),
    )
    assert refused.status_code == 422
    with SessionLocal() as db:
        row = db.get(AssetEvidence, UUID(response.json()["id"]))
        assert row.person_id == actors.person["owner"] and row.review_status == "pending_review"


def test_company_subscription_is_not_self_funded_exploration(actors):
    _, instance = membership(actors.owner, actors, "company")
    assert actors.owner.post("/api/v1/space/evidence", json=evidence(instance)).status_code == 422
    payload = {**evidence(instance), "kind": "case"}
    assert actors.owner.post("/api/v1/space/evidence", json=payload).status_code == 200


def test_team_membership_and_revocation_are_enforced(actors):
    asset = draft(actors.other, actors)
    receipt = prepare(actors.other, asset, "team")
    assert confirm(actors.other, asset, receipt).status_code == 200
    path = f"/api/v1/assets/{asset['id']}"
    assert actors.owner.get(path).status_code == 200
    assert actors.stranger.get(path).status_code == 404
    assert actors.owner.put(path + "/bookmark").status_code == 204
    with SessionLocal() as db:
        membership_row = db.scalar(
            select(DepartmentMembership).where(
                DepartmentMembership.person_id == actors.person["owner"],
                DepartmentMembership.department_id == actors.teams[1],
            )
        )
        membership_row.is_active = False
        db.commit()
    assert actors.owner.get(path).status_code == 404
    assert actors.owner.get("/api/v1/space/bookmarks").json() == []
    assert actors.owner.delete(path + "/bookmark").status_code == 204


def test_expired_and_revoked_grants_are_excluded(actors):
    asset = draft(actors.other, actors)
    with SessionLocal() as db:
        grant = AccessGrant(
            asset_id=UUID(asset["id"]),
            person_id=actors.person["owner"],
            grant_type="use",
            status="active",
            ends_at=date.today() - timedelta(days=1),
        )
        db.add(grant)
        db.commit()
        grant_id = grant.id
    path = f"/api/v1/assets/{asset['id']}"
    assert actors.owner.get(path).status_code == 404
    with SessionLocal() as db:
        row = db.get(AccessGrant, grant_id)
        row.ends_at = None
        db.commit()
    assert actors.owner.get(path).status_code == 200
    with SessionLocal() as db:
        row = db.get(AccessGrant, grant_id)
        row.status = "inactive"
        db.commit()
    assert actors.owner.get(path).status_code == 404


def test_employee_cannot_read_management_audit(actors):
    assert actors.owner.get("/api/v1/audit-logs").status_code == 403
    assert actors.admin.get("/api/v1/audit-logs").status_code == 200
    assert actors.owner.get("/api/v1/sessions/current").json()["roles"] == ["employee"]


def test_confirmed_result_edit_invalidates_old_retry(actors):
    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    result = confirm(actors.owner, asset, receipt).json()
    changed = actors.owner.patch(
        f"/api/v1/assets/{asset['id']}",
        json=dict(version=result["version"], description="更新成果"),
    )
    assert changed.status_code == 200, changed.text
    assert confirm(actors.owner, asset, receipt).status_code == 409


def test_relation_change_invalidates_confirmation(actors):
    asset = draft(actors.owner, actors)
    related = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    result = actors.owner.post(
        f"/api/v1/assets/{asset['id']}/relations",
        json=dict(target_asset_id=related["id"], relation_type="uses"),
    )
    assert result.status_code == 201, result.text
    assert confirm(actors.owner, asset, receipt).status_code == 409


def test_expired_or_mismatched_confirmation_is_rejected(actors):
    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    assert confirm(actors.owner, asset, {**receipt, "content_digest": "0" * 64}).status_code == 409
    with SessionLocal() as db:
        row = db.get(AssetConfirmation, UUID(receipt["id"]))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert confirm(actors.owner, asset, receipt).status_code == 409


def test_subscription_snapshot_and_changes_are_bound_to_confirmation(actors):
    asset, instance = membership(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    assert receipt["preview"]["subscriptions"][0]["funding_source"] == "personal"
    with SessionLocal() as db:
        row = db.get(ServiceInstance, UUID(instance["id"]))
        row.primary_purpose = "后来改变的用途"
        db.commit()
    assert confirm(actors.owner, asset, receipt).status_code == 409


def test_concurrent_confirmation_has_one_version_and_one_audit(actors):
    from concurrent.futures import ThreadPoolExecutor

    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    # Independent clients submit the same verified receipt concurrently.
    with ThreadPoolExecutor(max_workers=2) as executor:

        def send():
            with TestClient(
                app, headers={"X-PM-Session": actors.owner.headers["X-PM-Session"]}
            ) as client:
                return confirm(client, asset, receipt)

        results = list(executor.map(lambda _: send(), range(2)))
    assert [result.status_code for result in results] == [200, 200]
    assert {result.json()["version"] for result in results} == {asset["version"] + 1}
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action == "asset.registration.confirm",
                    AuditLog.object_id == UUID(asset["id"]),
                )
            )
            == 1
        )


def test_restoring_registered_draft_cannot_skip_confirmation(actors):
    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    archived = actors.admin.post(
        f"/api/v1/assets/{asset['id']}/archive", params={"version": asset["version"]}
    )
    assert archived.status_code == 200, archived.text
    restored = actors.admin.post(
        f"/api/v1/assets/{asset['id']}/restore", params={"version": archived.json()["version"]}
    )
    assert restored.status_code == 200, restored.text
    assert restored.json()["status"] == "draft" and restored.json()["confirmed_at"] is None
    assert confirm(actors.owner, asset, receipt).status_code == 409
    assert (
        actors.other.patch(
            f"/api/v1/assets/{asset['id']}",
            json={"version": restored.json()["version"], "name": "X"},
        ).status_code
        == 404
    )


def test_department_manager_scope_reads_team_but_not_private_assets(actors):
    asset = draft(actors.other, actors)
    receipt = prepare(actors.other, asset, "team")
    assert confirm(actors.other, asset, receipt).status_code == 200
    private_asset = draft(actors.other, actors)
    with SessionLocal() as db:
        member = db.scalar(
            select(DepartmentMembership).where(
                DepartmentMembership.person_id == actors.person["owner"],
                DepartmentMembership.department_id == actors.teams[1],
            )
        )
        member.is_active = False
        owner_user = db.scalar(select(User).where(User.person_id == actors.person["owner"]))
        manager_role = db.scalar(select(Role.id).where(Role.code == "department_manager"))
        db.add(
            UserRoleScope(
                user_id=owner_user.id,
                role_id=manager_role,
                scope_type="department",
                scope_id=actors.teams[1],
            )
        )
        db.commit()
    assert actors.owner.get(f"/api/v1/assets/{asset['id']}").status_code == 200
    assert actors.owner.get(f"/api/v1/assets/{private_asset['id']}").status_code == 404


def test_concurrent_cancel_and_confirm_have_one_outcome(actors):
    from concurrent.futures import ThreadPoolExecutor

    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)

    def send(action):
        with TestClient(
            app, headers={"X-PM-Session": actors.owner.headers["X-PM-Session"]}
        ) as client:
            if action == "confirm":
                return confirm(client, asset, receipt)
            return client.delete(f"/api/v1/assets/{asset['id']}/confirmation/{receipt['id']}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        confirmation, cancellation = list(executor.map(send, ("confirm", "cancel")))
    assert (confirmation.status_code, cancellation.status_code) in ((200, 409), (409, 204))
    with SessionLocal() as db:
        row = db.get(AssetConfirmation, UUID(receipt["id"]))
        assert bool(row.consumed_at) != bool(row.cancelled_at)


# Discovery and self-service applications must not weaken the registration boundary.
def employee_request_payload(**fields):
    body = dict(
        request_id=str(uuid4()),
        request_type="seat",
        resource_name="隔离测试工具",
        purpose="仅用于隔离申请验证",
    )
    body.update(fields)
    return body


def test_employee_request_is_self_bound_idempotent_and_does_not_allocate(actors):
    with SessionLocal() as db:
        before = [
            db.scalar(select(func.count()).select_from(model))
            for model in (Asset, Account, Platform, AccessGrant)
        ]
    payload = employee_request_payload()
    response = actors.owner.post("/api/v1/space/requests", json=payload)
    assert response.status_code == 201, response.text
    request = response.json()
    assert request["requester_person_id"] == str(actors.person["owner"])
    assert request["status"] == "pending"
    assert actors.owner.post("/api/v1/space/requests", json=payload).json()["id"] == request["id"]
    assert (
        actors.owner.post(
            "/api/v1/space/requests", json={**payload, "purpose": "变更内容"}
        ).status_code
        == 409
    )
    own = actors.owner.get("/api/v1/space/requests").json()
    assert [item["id"] for item in own] == [request["id"]]
    assert actors.other.get("/api/v1/space/requests").json() == []
    with SessionLocal() as db:
        after = [
            db.scalar(select(func.count()).select_from(model))
            for model in (Asset, Account, Platform, AccessGrant)
        ]
        assert after == before
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.object_id == UUID(request["id"]), AuditLog.action == "request.submit"
                )
            )
            == 1
        )


def test_employee_cannot_claim_another_requester_or_approve(actors):
    for field, value in [
        ("requester_person_id", str(actors.person["other"])),
        ("status", "approved"),
        ("detail", {"admin": True}),
    ]:
        response = actors.owner.post(
            "/api/v1/space/requests", json=employee_request_payload(**{field: value})
        )
        assert response.status_code == 422
    assert (
        actors.owner.post(
            "/api/v1/space/requests", json=employee_request_payload(request_type="permission")
        ).status_code
        == 422
    )
    request = actors.owner.post("/api/v1/space/requests", json=employee_request_payload()).json()
    assert actors.owner.get("/api/v1/requests").status_code == 403
    assert actors.owner.get("/api/v1/risk-findings").status_code == 403
    assert (
        actors.owner.post(
            f"/api/v1/requests/{request['id']}/transition?target_status=approved&version=1"
        ).status_code
        == 403
    )
    assert actors.owner.post(
        "/api/v1/access-grants",
        json={"person_id": str(actors.person["owner"]), "asset_id": str(uuid4())},
    ).status_code in {403, 404, 422}
    approved = actors.admin.post(
        f"/api/v1/requests/{request['id']}/transition?target_status=approved&version=1"
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["version"] == 2
    assert actors.owner.get("/api/v1/space/requests").json()[0]["status"] == "approved"
    assert (
        actors.owner.post(
            f"/api/v1/space/requests/{request['id']}/cancel", json={"version": 2}
        ).status_code
        == 409
    )


def test_employee_request_private_asset_and_cancel_version_boundaries(actors):
    hidden = draft(actors.other, actors)
    assert (
        actors.owner.post(
            "/api/v1/space/requests", json=employee_request_payload(asset_id=hidden["id"])
        ).status_code
        == 404
    )
    assert (
        actors.owner.post(
            "/api/v1/space/requests", json=employee_request_payload(platform_id=str(uuid4()))
        ).status_code
        == 422
    )
    request = actors.owner.post(
        "/api/v1/space/requests", json=employee_request_payload(request_type="account")
    ).json()
    url = f"/api/v1/space/requests/{request['id']}/cancel"
    assert actors.other.post(url, json={"version": 1}).status_code == 404
    assert actors.owner.post(url, json={"version": 2}).status_code == 409
    cancelled = actors.owner.post(url, json={"version": 1})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "cancelled"
    assert cancelled.json()["version"] == 2
    assert actors.owner.post(url, json={"version": 1}).status_code == 409


def test_employee_application_cookie_requires_csrf_and_login(actors):
    with TestClient(app) as anonymous:
        assert anonymous.get("/api/v1/space/requests").status_code == 401
        assert (
            anonymous.post("/api/v1/space/requests", json=employee_request_payload()).status_code
            == 401
        )
        anonymous.cookies.set(
            get_settings().session_cookie_name, actors.owner.headers["X-PM-Session"]
        )
        assert (
            anonymous.post("/api/v1/space/requests", json=employee_request_payload()).status_code
            == 403
        )


def test_management_applications_respect_department_scope(actors):
    own = actors.owner.post("/api/v1/space/requests", json=employee_request_payload()).json()
    other = actors.other.post("/api/v1/space/requests", json=employee_request_payload()).json()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.person_id == actors.person["owner"]))
        role_id = db.scalar(select(Role.id).where(Role.code == "department_manager"))
        db.add(
            UserRoleScope(
                user_id=user.id, role_id=role_id, scope_type="department", scope_id=actors.teams[0]
            )
        )
        db.commit()
    response = actors.owner.get("/api/v1/requests")
    assert response.status_code == 200, response.text
    ids = {item["id"] for item in response.json()}
    assert own["id"] in ids and other["id"] not in ids


def test_category_projection_preserves_private_drafts_and_custom_ai_types(actors):
    with SessionLocal() as db:
        category = db.scalar(select(AssetCategory).where(AssetCategory.code == "internal_system"))
        group_id = str(category.id)
    custom = actors.admin.post(
        "/api/v1/asset-types",
        json=dict(
            category_id=group_id,
            code="ai_test_" + uuid4().hex[:10],
            name="隔离 AI 类型",
            profile_kind="generic",
            code_prefix="TST",
            ownership_default="manual",
        ),
    )
    assert custom.status_code == 201, custom.text
    custom_id = custom.json()["id"]
    before = actors.other.get("/api/v1/space/groups?scope=discover").json()
    own = draft(actors.owner, actors, asset_type_id=custom_id)
    own_groups = actors.owner.get("/api/v1/space/groups?scope=discover").json()
    other_groups = actors.other.get("/api/v1/space/groups?scope=discover").json()
    assert other_groups == before
    assert own_groups["total"] == other_groups["total"] + 1
    assert sum(item["count"] for item in own_groups["categories"]) == own_groups["total"]
    url = (
        f"/api/v1/space/assets?scope=discover&asset_category_id={group_id}"
        f"&asset_type_id={custom_id}"
    )
    assert [item["id"] for item in actors.owner.get(url).json()["data"]] == [own["id"]]
    assert actors.other.get(url).json()["data"] == []
    wrong_group = next(item["id"] for item in own_groups["categories"] if item["id"] != group_id)
    assert actors.owner.get(url.replace(group_id, wrong_group)).json()["data"] == []
    receipt = prepare(actors.owner, own)
    assert confirm(actors.owner, own, receipt).status_code == 200
    assert actors.other.get(url).json()["data"] == []


def test_employee_ai_registration_rejects_non_ai_and_keeps_management_creation(actors):
    catalog = actors.owner.get("/api/v1/space/registration-types")
    assert catalog.status_code == 200
    rows = catalog.json()
    codes = {row["code"] for row in rows}
    assert {"ai_skill", "ai_workflow", "internal_system", "automation_script"} <= codes
    assert (
        not {"saas_subscription", "registration_identity", "cloud_server", "code_repository"}
        & codes
    )
    assert all(
        row["requires_ai_development"]
        for row in rows
        if row["code"] in {"internal_system", "automation_script"}
    )
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Asset))
        rejected = list(
            db.scalars(
                select(AssetType).where(
                    AssetType.code.in_(
                        (
                            "saas_subscription",
                            "registration_identity",
                            "cloud_server",
                            "code_repository",
                        )
                    )
                )
            )
        )
        type_ids = [str(row.id) for row in rejected]
    assert len(type_ids) == 4
    for type_id in type_ids:
        response = actors.owner.post(
            "/api/v1/assets/draft",
            json=dict(
                request_id=str(uuid4()),
                name="不应登记",
                description="隔离负向检查",
                asset_type_id=type_id,
            ),
        )
        assert response.status_code == 403, response.text
        assert (
            actors.owner.post(
                "/api/v1/assets", json=dict(name="绕过员工入口", asset_type_id=type_id)
            ).status_code
            == 403
        )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Asset)) == before
    managed = actors.admin.post(
        "/api/v1/assets",
        json=dict(name="后台管理登记", asset_type_id=type_ids[0], legal_entity_id=actors.entity),
    )
    assert managed.status_code == 201, managed.text
    assert actors.owner.get(f"/api/v1/assets/{managed.json()['id']}").status_code == 200


def test_ai_assisted_systems_require_ai_method_and_ai_projection_is_exact(actors):
    with SessionLocal() as db:
        type_ids = {
            row.code: str(row.id)
            for row in db.scalars(
                select(AssetType).where(
                    AssetType.code.in_(("internal_system", "automation_script"))
                )
            )
        }
    for type_id in type_ids.values():
        for method in (None, "traditional", "low_code"):
            response = actors.owner.post(
                "/api/v1/assets/draft",
                json=dict(
                    request_id=str(uuid4()),
                    name="非 AI 开发",
                    description="隔离负向检查",
                    asset_type_id=type_id,
                    development_method=method,
                ),
            )
            assert response.status_code == 422, response.text
    system = draft(
        actors.owner,
        actors,
        asset_type_id=type_ids["internal_system"],
        development_method="vibe_coding",
    )
    script = draft(
        actors.owner,
        actors,
        asset_type_id=type_ids["automation_script"],
        development_method="mixed",
    )
    assert system["sharing_scope"] == "private" and script["status"] == "draft"
    with SessionLocal() as db:
        legacy = Asset(
            name="历史传统系统",
            asset_type_id=UUID(type_ids["internal_system"]),
            asset_code="AI-LEGACY-" + uuid4().hex[:10],
            legal_entity_id=UUID(actors.entity),
            created_by_person_id=actors.person["owner"],
            sharing_scope="private",
            development_method="traditional",
        )
        db.add(legacy)
        db.commit()
        legacy_id = str(legacy.id)
    result = actors.owner.get("/api/v1/space/assets?scope=mine&category=ai").json()
    ids = {row["id"] for row in result["data"]}
    assert {system["id"], script["id"]} <= ids and legacy_id not in ids
    assert actors.owner.get(f"/api/v1/assets/{legacy_id}").status_code == 200
    assert actors.other.get(f"/api/v1/assets/{system['id']}").status_code == 404


def test_subscription_registration_remains_separate_from_ai_outcome_registration(actors):
    with SessionLocal() as db:
        type_id = str(db.scalar(select(AssetType.id).where(AssetType.code == "saas_subscription")))
    rejected = actors.owner.post(
        "/api/v1/assets/draft",
        json=dict(
            request_id=str(uuid4()),
            name="重复订阅入口",
            description="不能作为 AI 成果",
            asset_type_id=type_id,
        ),
    )
    assert rejected.status_code == 403
    asset, instance = membership(actors.owner, actors)
    own = actors.owner.get("/api/v1/space/assets?scope=mine&category=subscriptions").json()
    assert [row["id"] for row in own["data"]] == [asset["id"]]
    ai = actors.owner.get("/api/v1/space/assets?scope=mine&category=ai").json()
    assert asset["id"] not in {row["id"] for row in ai["data"]}
    assert actors.other.get("/api/v1/space/memberships").json() == []
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(ServiceInstance)
                .where(ServiceInstance.asset_id == UUID(asset["id"]))
            )
            == 1
        )
        assert db.get(ServiceInstance, UUID(instance["id"])).funding_source == "personal"


def test_workflow_views_only_return_visible_workflows_and_preserve_personal_scope(actors):
    with SessionLocal() as db:
        workflow_type = str(db.scalar(select(AssetType.id).where(AssetType.code == "ai_workflow")))
    marker = "工作流隔离-" + uuid4().hex[:10]
    own = draft(actors.owner, actors, asset_type_id=workflow_type, name=marker + "-本人")
    hidden = draft(actors.other, actors, asset_type_id=workflow_type, name=marker + "-私有")
    shared = draft(actors.other, actors, asset_type_id=workflow_type, name=marker + "-团队")
    receipt = prepare(actors.other, shared, "team")
    assert confirm(actors.other, shared, receipt).status_code == 200
    skill = draft(actors.owner, actors, name=marker + "-技能")
    for item in (shared, skill):
        assert actors.owner.put(f"/api/v1/assets/{item['id']}/bookmark").status_code == 204
    path = "/api/v1/space/assets?scope=discover&category=workflows&keyword=" + marker

    def ids(view):
        response = actors.owner.get(path + "&workflow_view=" + view)
        assert response.status_code == 200, response.text
        return {row["id"] for row in response.json()["data"]}

    assert ids("all") == {own["id"], shared["id"]}
    assert ids("created") == {own["id"]}
    assert ids("bookmarks") == {shared["id"]}
    assert hidden["id"] not in ids("all") and skill["id"] not in ids("all")
    assert actors.owner.get(path + "&workflow_view=invalid").status_code == 422
    assert (
        actors.owner.get("/api/v1/space/assets?category=all&workflow_view=created").status_code
        == 422
    )


def test_historical_non_ai_draft_retry_is_read_only_but_cannot_create_another(actors):
    from app.api.v1.asset_space import draft_id

    nonce = uuid4()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.person_id == actors.person["owner"]))
        type_id = db.scalar(select(AssetType.id).where(AssetType.code == "code_repository"))
        item = Asset(
            id=draft_id(user.id, nonce),
            asset_code="LEGACY-" + uuid4().hex[:10],
            name="旧登记草稿",
            description="隔离历史兼容资料",
            asset_type_id=type_id,
            legal_entity_id=UUID(actors.entity),
            created_by_person_id=actors.person["owner"],
            sharing_scope="private",
            source_type="manual",
            status="draft",
        )
        db.add(item)
        db.commit()
        item_id, version = str(item.id), item.version
        before = db.scalar(select(func.count()).select_from(Asset))
    payload = dict(
        request_id=str(nonce),
        name="旧登记草稿",
        description="隔离历史兼容资料",
        asset_type_id=str(type_id),
    )
    retry = actors.owner.post("/api/v1/assets/draft", json=payload)
    assert retry.status_code == 200 and retry.json()["id"] == item_id
    assert retry.json()["version"] == version
    assert actors.other.post("/api/v1/assets/draft", json=payload).status_code == 403
    assert (
        actors.owner.post(
            "/api/v1/assets/draft", json={**payload, "request_id": str(uuid4())}
        ).status_code
        == 403
    )
    assert (
        actors.owner.post("/api/v1/assets/draft", json={**payload, "name": "新内容"}).status_code
        == 409
    )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Asset)) == before
        assert db.get(Asset, UUID(item_id)).version == version
