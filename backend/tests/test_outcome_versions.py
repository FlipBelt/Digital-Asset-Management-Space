"""Authenticated registration and intentional publication over disposable data."""

import io
from uuid import UUID, uuid4

import pytest
from PIL import Image
from sqlalchemy import func, select
from test_agent_connector import create, draft_payload
from test_asset_center_integration import confirm, prepare

from app.db.session import SessionLocal
from app.models import AssetResponsibility, AuditLog

pytest_plugins = ["test_agent_connector"]


def current(actors, item):
    return actors.owner.get("/api/v1/assets/" + item["id"]).json()


def assignment(actors, item, responsible="owner"):
    return {
        "version": item["version"],
        "ownership_scope": "department",
        "owner_department_id": str(actors.teams[0]),
        "responsible_person_id": str(actors.person[responsible]),
        "user_person_ids": [],
    }


@pytest.mark.parametrize("mode", ["web", "agent"])
def test_verified_registrant_is_default_owner_and_retry_is_idempotent(mode, actors, agent_clients):
    client = actors.owner if mode == "web" else agent_clients["owner"]
    path = "/api/v1/assets/draft" if mode == "web" else "/api/v1/agent/drafts"
    payload = draft_payload(actors)
    response = client.post(path, json=payload)
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["created_by_person_id"] == str(actors.person["owner"])
    assert item["outcome_version"] == 0
    assert client.post(path, json=payload).json() == item
    actual = actors.owner.get(f"/api/v1/assets/{item['id']}/assignment").json()
    assert actual["responsible_person_id"] == str(actors.person["owner"])
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(AssetResponsibility)
                .where(
                    AssetResponsibility.asset_id == UUID(item["id"]),
                    AssetResponsibility.role_type == "responsible",
                    AssetResponsibility.archived_at.is_(None),
                )
            )
            == 1
        )
        log = db.scalar(
            select(AuditLog).where(
                AuditLog.object_id == UUID(item["id"]),
                AuditLog.action == "asset.draft.create",
            )
        )
        assert log.actor_user_id is not None
        assert log.after_data["responsible_person_id"] == str(actors.person["owner"])
    for key in ("created_by_person_id", "responsible_person_id", "outcome_version"):
        assert (
            client.post(path, json={**payload, "request_id": str(uuid4()), key: 9}).status_code
            == 422
        )


def test_admin_reassignment_keeps_registrant_and_private_maintenance_separate(
    actors, agent_clients
):
    item = create(agent_clients["owner"], actors)
    path = f"/api/v1/assets/{item['id']}/assignment"
    payload = assignment(actors, item, "other")
    assert actors.owner.put(path, json=payload).status_code == 403
    assert actors.admin.put(path, json=payload).status_code == 200
    item = current(actors, item)
    assert item["created_by_person_id"] == str(actors.person["owner"])
    assert item["outcome_version"] == 0
    assert actors.other.get(f"/api/v1/assets/{item['id']}").status_code == 200
    # The actual responsible person can maintain a private asset; strangers cannot.
    update = {"version": item["version"], "name": "改派后的合成成果"}
    assert actors.stranger.patch(f"/api/v1/assets/{item['id']}", json=update).status_code == 404
    assert actors.other.patch(f"/api/v1/assets/{item['id']}", json=update).status_code == 200
    receipt = prepare(actors.owner, current(actors, item))
    assert confirm(actors.other, item, receipt).status_code == 403
    detail = actors.owner.get(f"/api/v1/hudu/assets/{item['id']}").json()
    assert detail["asset"]["created_by_person_name"] == "测试身份 owner"
    assert {
        r["person_name"] for r in detail["responsibilities"] if r["role_type"] == "responsible"
    } == {"测试身份 other"}


def upload(actors, item):
    stream = io.BytesIO()
    Image.new("RGB", (3, 3), (int(item["version"]) % 255, 44, 88)).save(stream, format="PNG")
    response = actors.owner.post(
        f"/api/v1/assets/{item['id']}/attachments",
        files={
            "file": ("synthetic.png", stream.getvalue()),
        },
    )
    assert response.status_code == 200, response.text
    return current(actors, item)


def test_only_explicit_publication_advances_outcome_version(
    actors, agent_clients, tmp_path, monkeypatch
):
    import app.api.v1.asset_attachments as attachments

    monkeypatch.setattr(attachments, "STORAGE", tmp_path)
    item = create(agent_clients["owner"], actors)
    item = upload(actors, item)
    assert item["version"] > 1 and item["outcome_version"] == 0
    receipt = prepare(actors.owner, item)
    assert receipt["outcome_version"] == 1
    assert receipt["preview"]["asset"]["created_by_person_name"] == "测试身份 owner"
    result = confirm(actors.owner, item, receipt)
    assert result.status_code == 200, result.text
    item = result.json()
    assert item["outcome_version"] == 1
    assert confirm(actors.owner, item, receipt).json() == item
    review = actors.admin.post(
        f"/api/v1/asset-reviews/{item['id']}",
        json={
            "version": item["version"],
            "decision": "approved",
        },
    )
    assert review.status_code == 200, review.text
    assert review.json()["outcome_version"] == 1
    item = review.json()
    # An unchanged save does not reset an approval or advance even the lock revision.
    assert (
        actors.owner.patch(
            f"/api/v1/assets/{item['id']}",
            json={
                "version": item["version"],
                "name": item["name"],
            },
        ).json()
        == item
    )
    assert (
        actors.admin.put(
            f"/api/v1/assets/{item['id']}/assignment", json=assignment(actors, item)
        ).status_code
        == 200
    )
    item = current(actors, item)
    assigned_revision = item["version"]
    assert item["outcome_version"] == 1
    assert (
        actors.admin.put(
            f"/api/v1/assets/{item['id']}/assignment", json=assignment(actors, item)
        ).status_code
        == 200
    )
    assert current(actors, item)["version"] == assigned_revision
    item = upload(actors, item)
    assert item["outcome_version"] == 1 and item["status"] == "draft"
    # Reconfirming documentation retains V1 by default.
    item = confirm(actors.owner, item, prepare(actors.owner, item)).json()
    assert item["outcome_version"] == 1
    item = upload(actors, item)
    payload = {"request_id": str(uuid4()), "version": item["version"], "publish_new_version": True}
    endpoint = f"/api/v1/assets/{item['id']}/confirmation"
    response = actors.owner.post(endpoint, json=payload)
    assert response.status_code == 200, response.text
    receipt = response.json()
    assert receipt["outcome_version"] == 2 and current(actors, item)["outcome_version"] == 1
    assert (
        actors.owner.post(endpoint, json=payload | {"publish_new_version": False}).status_code
        == 409
    )
    assert (
        actors.owner.post(
            f"/api/v1/assets/{item['id']}/confirm",
            json={
                "confirmation_id": receipt["id"],
                "version": receipt["asset_version"],
                "content_digest": receipt["content_digest"],
                "confirmed": True,
                "outcome_version": 8,
            },
        ).status_code
        == 422
    )
    result = confirm(actors.owner, item, receipt)
    assert result.status_code == 200, result.text
    item = result.json()
    assert item["outcome_version"] == 2
    assert confirm(actors.owner, item, receipt).json() == item
    assert confirm(actors.owner, item, receipt | {"content_digest": "0" * 64}).status_code == 409


def test_cancelled_and_stale_previews_cannot_publish(actors, agent_clients):
    item = create(agent_clients["owner"], actors)
    receipt = prepare(actors.owner, item)
    path = f"/api/v1/assets/{item['id']}/confirmation/{receipt['id']}"
    assert actors.owner.delete(path).status_code == 204
    assert confirm(actors.owner, item, receipt).status_code == 409
    receipt = prepare(actors.owner, item)
    response = agent_clients["owner"].patch(
        f"/api/v1/agent/drafts/{item['id']}",
        json={
            "request_id": str(uuid4()),
            "version": item["version"],
            "name": item["name"],
            "description": "新的合成资料",
        },
    )
    assert response.status_code == 200, response.text
    assert confirm(actors.owner, item, receipt).status_code == 409
    assert current(actors, item)["outcome_version"] == 0


def test_reassigned_owner_edits_registered_content_without_publishing(actors, agent_clients):
    item = create(agent_clients["owner"], actors)
    item = confirm(actors.owner, item, prepare(actors.owner, item)).json()
    assert actors.admin.put(
        f"/api/v1/assets/{item['id']}/assignment", json=assignment(actors, item, "other"),
    ).status_code == 200
    item = current(actors, item)
    response = actors.other.patch(f"/api/v1/assets/{item['id']}", json={
        "version": item["version"], "description": "改派后的负责人补充合成说明",
    })
    assert response.status_code == 200, response.text
    item = response.json()
    assert item["status"] == "draft" and item["outcome_version"] == 1
    assert item["created_by_person_id"] == str(actors.person["owner"])
    receipt = prepare(actors.owner, item)
    assert receipt["outcome_version"] == 1
    response = confirm(actors.owner, item, receipt)
    assert response.status_code == 200, response.text
    assert response.json()["outcome_version"] == 1
