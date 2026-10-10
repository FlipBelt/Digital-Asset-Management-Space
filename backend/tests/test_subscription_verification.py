"""Registration exemptions and evidence-based account verification on isolated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import Asset, AssetType, AuditLog, Platform, PlatformTenant
from tests.test_asset_center_integration import confirm, draft, membership, prepare

pytest_plugins = ["tests.test_asset_center_integration"]


@pytest.mark.parametrize("funding", ["personal", "company", "department", "free", "trial"])
def test_membership_is_registered_without_review_and_keeps_private_access(actors, funding):
    asset, instance = membership(actors.owner, actors, funding)
    assert asset["status"] == "active" and asset["review_status"] == "not_required"
    assert asset["is_personal_subscription"] and asset["ownership_scope"] == "personal"
    assert asset["sharing_scope"] == "private" and instance["funding_source"] == funding
    assert actors.owner.get(f"/api/v1/assets/{asset['id']}").status_code == 200
    assert actors.other.get(f"/api/v1/assets/{asset['id']}").status_code == 404
    assert actors.owner.get("/api/v1/space/summary").json()["drafts"] == 0
    item = actors.admin.get(f"/api/v1/hudu/assets/{asset['id']}").json()["asset"]
    assert item["is_personal_subscription"] and item["review_status"] == "not_required"
    assert (
        actors.owner.post(
            f"/api/v1/assets/{asset['id']}/confirmation",
            json={
                "request_id": str(uuid4()),
                "version": asset["version"],
                "sharing_scope": "private",
            },
        ).status_code
        == 409
    )


def test_old_membership_reads_and_edits_do_not_require_review(actors):
    asset, _ = membership(actors.owner, actors)
    with SessionLocal() as db:
        old = db.get(Asset, UUID(asset["id"]))
        old.status = "draft"
        old.review_status = "pending_review"
        old.ownership_scope = "pending"
        db.commit()
    item = actors.owner.get(f"/api/v1/assets/{asset['id']}").json()
    assert item["is_personal_subscription"] and item["review_status"] == "not_required"
    drafts = actors.owner.get("/api/v1/space/assets?scope=mine&category=drafts").json()["data"]
    assert asset["id"] not in {item["id"] for item in drafts}
    edit = actors.owner.patch(
        f"/api/v1/assets/{asset['id']}",
        json={
            "version": asset["version"],
            "name": "修改个人订阅说明",
        },
    )
    assert edit.status_code == 200, edit.text
    assert edit.json()["status"] == "active" and edit.json()["review_status"] == "not_required"
    deleted = actors.admin.delete(f"/api/v1/assets/{asset['id']}?version={edit.json()['version']}")
    assert deleted.status_code == 200, deleted.text
    restored = actors.admin.post(
        f"/api/v1/assets/{asset['id']}/restore",
        params={
            "version": deleted.json()["version"],
        },
    )
    assert restored.status_code == 200, restored.text
    assert (
        restored.json()["status"] == "active" and restored.json()["review_status"] == "not_required"
    )


def test_user_supplied_source_does_not_exempt_ai_outcomes(actors):
    asset = draft(actors.owner, actors, source_system="membership-registration")
    assert not asset["is_personal_subscription"] and asset["review_status"] == "pending_review"
    receipt = prepare(actors.owner, asset)
    result = confirm(actors.owner, asset, receipt)
    assert result.status_code == 200, result.text
    assert result.json()["review_status"] == "pending_review"


@pytest.fixture
def company_account(actors):
    with SessionLocal() as db:
        platform = Platform(
            code="verify-" + uuid4().hex, name="隔离核验平台", review_status="pending_review"
        )
        db.add(platform)
        db.flush()
        asset = Asset(
            name="隔离公司账号",
            asset_code="VERIFY-" + uuid4().hex[:12],
            asset_type_id=db.scalar(
                select(AssetType.id).where(AssetType.code == "platform_tenant")
            ),
            legal_entity_id=UUID(actors.entity),
            ownership_scope="company",
            status="draft",
            created_by_person_id=actors.person["admin"],
        )
        db.add(asset)
        db.flush()
        tenant = PlatformTenant(
            asset_id=asset.id,
            platform_id=platform.id,
            legal_entity_id=UUID(actors.entity),
            verification_status="pending",
        )
        db.add(tenant)
        db.commit()
        return {
            "id": str(tenant.id),
            "asset": str(asset.id),
            "version": asset.version,
            "platform": platform.id,
        }


def verification_body(account, **changes):
    payload = {
        "request_id": str(uuid4()),
        "version": account["version"],
        "decision": "verified",
        "tenant_identifier": "test-uid-" + uuid4().hex[:12],
        "ownership_nature": "company_owned",
        "platform_confirmed": True,
        "company_confirmed": True,
        "identifier_confirmed": True,
        "evidence_note": "隔离测试：已核对账号后台与公司归属资料。",
    }
    return {**payload, **changes}


def verify(client, account, body):
    return client.post(f"/api/v1/platform-tenants/{account['id']}/verification", json=body)


def test_account_verification_persists_facts_and_exact_retry_once(actors, company_account):
    body = verification_body(company_account)
    response = verify(actors.admin, company_account, body)
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == "verified"
    assert response.json()["evidence_note"] == body["evidence_note"]
    assert verify(actors.admin, company_account, body).json() == response.json()
    assert (
        verify(actors.admin, company_account, {**body, "evidence_note": "改变内容"}).status_code
        == 409
    )
    current = actors.admin.get(f"/api/v1/assets/{company_account['asset']}").json()
    assert current["version"] == company_account["version"] + 1
    assert current["status"] == "active" and current["last_verified_at"]
    context = actors.admin.get(
        f"/api/v1/workspace/platform-accounts/by-asset/{company_account['asset']}"
    ).json()
    assert (
        context["verification_status"] == "verified"
        and context["tenant_identifier"] == body["tenant_identifier"]
    )
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.object_id == UUID(company_account["id"]),
                    AuditLog.action == "platform_tenant.verify",
                )
            )
            == 1
        )
        assert db.get(Platform, company_account["platform"]).review_status == "pending_review"
        asset = db.get(Asset, UUID(company_account["asset"]))
        asset.version += 1
        db.commit()
    assert verify(actors.admin, company_account, body).status_code == 409


@pytest.mark.parametrize(
    "changes",
    [
        {"company_confirmed": False},
        {"platform_confirmed": False},
        {"identifier_confirmed": False},
        {"tenant_identifier": None},
        {"evidence_note": "   "},
        {"ownership_nature": "pending"},
        {"identifier_unavailable": True},
        {"is_personal_subscription": True},
    ],
)
def test_incomplete_verification_is_rejected(actors, company_account, changes):
    response = verify(actors.admin, company_account, verification_body(company_account, **changes))
    assert response.status_code == 422, response.text
    with SessionLocal() as db:
        assert db.get(PlatformTenant, UUID(company_account["id"])).verification_status == "pending"
        assert db.get(Asset, UUID(company_account["asset"])).version == company_account["version"]


def test_missing_identifier_requires_explanation_or_can_remain_pending(actors, company_account):
    body = verification_body(
        company_account,
        tenant_identifier=None,
        decision="pending",
        company_confirmed=False,
        evidence_note="待补充公司归属和账号后台信息。",
    )
    response = verify(actors.admin, company_account, body)
    assert response.status_code == 200, response.text
    assert response.json()["verification_status"] == "pending"
    body = verification_body(
        company_account,
        version=company_account["version"] + 1,
        tenant_identifier=None,
        identifier_unavailable=True,
        evidence_note="隔离平台不提供统一账号编号，已用注册身份与公司授权资料核对。",
    )
    result = verify(actors.admin, company_account, body)
    assert result.status_code == 200, result.text
    assert result.json()["verification_status"] == "verified"


def test_verification_permissions_csrf_and_stale_version(actors, company_account):
    body = verification_body(company_account)
    assert verify(actors.owner, company_account, body).status_code == 403
    with TestClient(app) as anonymous:
        assert verify(anonymous, company_account, body).status_code == 401
        anonymous.cookies.set(
            get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"]
        )
        assert verify(anonymous, company_account, body).status_code == 403
        csrf = anonymous.get("/api/v1/sessions/current").json()["csrf_token"]
        anonymous.headers["X-CSRF-Token"] = csrf
        assert verify(anonymous, company_account, {**body, "version": 999}).status_code == 409
        assert verify(anonymous, company_account, body).status_code == 200


@pytest.mark.parametrize(
    "invalid", ["archived", "company_mismatch", "platform_archived", "duplicate_uid"]
)
def test_verification_preserves_valid_company_and_identifier_boundaries(
    actors, company_account, invalid
):
    body = verification_body(company_account)
    with SessionLocal() as db:
        from datetime import UTC, datetime

        asset = db.get(Asset, UUID(company_account["asset"]))
        if invalid == "archived":
            asset.archived_at = datetime.now(UTC)
        elif invalid == "company_mismatch":
            asset.legal_entity_id = None
        elif invalid == "platform_archived":
            db.get(Platform, company_account["platform"]).archived_at = datetime.now(UTC)
        else:
            other = Asset(
                name="另一个隔离账号",
                asset_code="VERIFY-" + uuid4().hex[:12],
                asset_type_id=asset.asset_type_id,
                legal_entity_id=asset.legal_entity_id,
            )
            db.add(other)
            db.flush()
            db.add(
                PlatformTenant(
                    asset_id=other.id,
                    platform_id=company_account["platform"],
                    legal_entity_id=asset.legal_entity_id,
                    tenant_identifier=body["tenant_identifier"],
                )
            )
        db.commit()
    expected = {
        "archived": 404,
        "company_mismatch": 422,
        "platform_archived": 422,
        "duplicate_uid": 409,
    }
    response = verify(actors.admin, company_account, body)
    assert response.status_code == expected[invalid], response.text


def test_concurrent_verification_changes_one_version_and_one_audit(actors, company_account):
    body = verification_body(company_account)

    def submit():
        with TestClient(
            app, headers={"X-PM-Session": actors.admin.headers["X-PM-Session"]}
        ) as client:
            return verify(client, company_account, body)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert all(response.status_code == 200 for response in results)
    with SessionLocal() as db:
        assert (
            db.get(Asset, UUID(company_account["asset"])).version == company_account["version"] + 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.object_id == UUID(company_account["id"]),
                    AuditLog.action == "platform_tenant.verify",
                )
            )
            == 1
        )
