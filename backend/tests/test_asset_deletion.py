"""Recoverable administrative deletion on the disposable PostgreSQL harness."""

from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_asset_center_integration import confirm, draft, prepare

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import Asset, AssetIdentifier, AuditLog, Role, User, UserRoleScope

pytest_plugins = ["test_asset_center_integration"]


def test_delete_permissions_visibility_idempotency_and_audit(actors):
    asset = draft(actors.owner, actors, name="删除隔离 " + uuid4().hex)
    path = f"/api/v1/assets/{asset['id']}"
    assert actors.owner.delete(path, params={"version": asset["version"]}).status_code == 403
    assert actors.other.get("/api/v1/assets", params={"deleted_only": True}).status_code == 403
    assert actors.admin.delete(path, params={"version": 999}).status_code == 409
    removed = actors.admin.delete(path, params={"version": asset["version"]})
    assert removed.status_code == 200, removed.text
    removed = removed.json()
    assert removed["status"] == "deleted" and removed["archived_at"]
    retry = actors.admin.delete(path, params={"version": asset["version"]})
    assert retry.status_code == 200 and retry.json()["version"] == removed["version"]
    for client in (actors.owner, actors.admin):
        assert client.get(path).status_code == 404
        assert client.get(path + "/attachments").status_code == 404
        for include in (False, True):
            rows = client.get(
                "/api/v1/assets", params={"include_archived": include, "keyword": asset["name"]}
            ).json()["data"]
            assert not rows
        assert not client.get("/api/v1/space/assets", params={"keyword": asset["name"]}).json()[
            "data"
        ]
    trash = actors.admin.get(
        "/api/v1/assets", params={"deleted_only": True, "keyword": asset["name"]}
    ).json()
    assert [row["id"] for row in trash["data"]] == [asset["id"]]
    assert (
        actors.owner.patch(
            path, json={"version": removed["version"], "name": "不可更改"}
        ).status_code
        == 404
    )
    with SessionLocal() as db:
        assert db.get(Asset, UUID(asset["id"])) is not None
        assert db.scalar(
            select(AssetIdentifier).where(AssetIdentifier.asset_id == UUID(asset["id"]))
        )
        audits = list(
            db.scalars(
                select(AuditLog).where(
                    AuditLog.object_id == UUID(asset["id"]), AuditLog.action == "asset.delete"
                )
            )
        )
        assert len(audits) == 1
        admin = db.scalar(select(User).where(User.person_id == actors.person["admin"]))
        assert audits[0].actor_user_id == admin.id


def test_restore_and_fresh_registration_do_not_reuse_old_confirmation(actors):
    asset = draft(actors.owner, actors)
    receipt = prepare(actors.owner, asset)
    assert confirm(actors.owner, asset, receipt).status_code == 200
    path = f"/api/v1/assets/{asset['id']}"
    current = actors.admin.get(path).json()
    removed = actors.admin.delete(path, params={"version": current["version"]}).json()
    assert confirm(actors.owner, asset, receipt).status_code == 404
    assert (
        actors.owner.post(path + "/restore", params={"version": removed["version"]}).status_code
        == 403
    )
    assert (
        actors.admin.post(path + "/restore", params={"version": current["version"]}).status_code
        == 409
    )
    restored = actors.admin.post(path + "/restore", params={"version": removed["version"]})
    assert restored.status_code == 200, restored.text
    restored = restored.json()
    assert restored["status"] == "draft" and restored["archived_at"] is None
    assert restored["confirmed_at"] is None and restored["review_status"] == "pending_review"
    assert confirm(actors.owner, asset, receipt).status_code == 409
    assert (
        actors.admin.post(path + "/restore", params={"version": restored["version"]}).status_code
        == 409
    )
    assert actors.admin.delete(path, params={"version": restored["version"]}).status_code == 200
    fresh = draft(actors.owner, actors)
    assert fresh["id"] != asset["id"] and fresh["asset_code"] != asset["asset_code"]


def test_delete_cookie_csrf_and_status_bypass(actors):
    asset = draft(actors.owner, actors)
    path = f"/api/v1/assets/{asset['id']}"
    with TestClient(app) as client:
        client.cookies.set(get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"])
        assert client.delete(path, params={"version": asset["version"]}).status_code == 403
        csrf = client.get("/api/v1/sessions/current").json()["csrf_token"]
        assert (
            client.delete(
                path, params={"version": asset["version"]}, headers={"X-CSRF-Token": csrf}
            ).status_code
            == 200
        )
    fresh = draft(actors.owner, actors)
    assert (
        actors.admin.patch(
            f"/api/v1/assets/{fresh['id']}", json={"version": fresh["version"], "status": "deleted"}
        ).status_code
        == 422
    )
    assert (
        actors.admin.post(
            "/api/v1/assets",
            json={"name": "绕过", "asset_type_id": actors.skill, "status": "deleted"},
        ).status_code
        == 422
    )


def test_department_manager_cannot_delete_or_restore_trash(actors):
    asset = draft(actors.owner, actors)
    path = f"/api/v1/assets/{asset['id']}"
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.person_id == actors.person["owner"]))
        role = db.scalar(select(Role).where(Role.code == "department_manager"))
        db.add(
            UserRoleScope(
                user_id=user.id, role_id=role.id, scope_type="department", scope_id=actors.teams[0]
            )
        )
        db.get(Asset, UUID(asset["id"])).owner_department_id = actors.teams[0]
        db.commit()
    assert actors.owner.delete(path, params={"version": asset["version"]}).status_code == 403
    removed = actors.admin.delete(path, params={"version": asset["version"]}).json()
    assert (
        actors.owner.post(path + "/restore", params={"version": removed["version"]}).status_code
        == 403
    )
