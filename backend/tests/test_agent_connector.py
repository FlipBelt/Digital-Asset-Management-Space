"""Run only with the existing disposable PostgreSQL integration harness."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.agent_auth import _buckets, digest, now
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    AgentGrant,
    AgentIncubation,
    Asset,
    Person,
    User,
    UserRoleScope,
)

pytest_plugins = ["test_asset_center_integration"]


@pytest.fixture
def agent_clients(actors, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_connector_enabled", True)
    monkeypatch.setattr(settings, "agent_frontend_url", "https://jtzhzt.flipbeltchina.com")
    _buckets.clear()
    result = {}
    with SessionLocal() as db:
        for key in ("owner", "other", "admin"):
            user = db.scalar(select(User).where(User.person_id == actors.person[key]))
            token = "agt_" + uuid4().hex + uuid4().hex
            grant = AgentGrant(
                device_hash=digest(uuid4().hex),
                user_code_hash=digest(uuid4().hex),
                client_name="Codex",
                user_id=user.id,
                device_expires_at=now() + timedelta(minutes=10),
                token_hash=digest(token),
                token_expires_at=now() + timedelta(hours=1),
            )
            db.add(grant)
            db.flush()
            result[key] = TestClient(app, headers={"Authorization": "Bearer " + token})
            result[key + "_grant"] = grant.id
        db.commit()
    yield result
    for value in result.values():
        if isinstance(value, TestClient):
            value.close()


def draft_payload(actors, **changes):
    payload = dict(
        request_id=str(uuid4()),
        name="连接器隔离成果",
        description="合成数据，非真实验收",
        asset_type_id=actors.skill,
        source_type="connector",
        source_agent="Codex",
    )
    return payload | changes


def create(client, actors, **changes):
    response = client.post("/api/v1/agent/drafts", json=draft_payload(actors, **changes))
    assert response.status_code == 200, response.text
    return response.json()


def test_auth_boundary(actors, agent_clients):
    machine = agent_clients["owner"]
    assert machine.get("/api/v1/agent/capabilities").status_code == 200
    assert actors.owner.get("/api/v1/agent/capabilities").status_code == 401
    assert machine.get("/api/v1/assets").status_code == 401
    assert machine.post(f"/api/v1/assets/{uuid4()}/confirm", json={}).status_code == 401
    assert (
        machine.post(
            "/api/v1/agent/device/approve", json={"user_code": "ABCD2345", "approved": True}
        ).status_code
        == 401
    )


def test_feature_flag(actors, agent_clients, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_connector_enabled", False)
    assert agent_clients["owner"].get("/api/v1/agent/capabilities").status_code == 404
    assert actors.owner.get("/api/v1/agent/grants").status_code == 404


@pytest.mark.parametrize("state", ["expired", "revoked", "inactive", "departed", "role_removed"])
def test_live_authorization(state, actors, agent_clients):
    with SessionLocal() as db:
        grant = db.get(AgentGrant, agent_clients["owner_grant"])
        user = db.get(User, grant.user_id)
        if state == "expired":
            grant.token_expires_at = now() - timedelta(seconds=1)
        elif state == "revoked":
            grant.revoked_at = now()
        elif state == "inactive":
            user.is_active = False
        elif state == "departed":
            db.get(Person, user.person_id).employment_status = "inactive"
        else:
            for row in db.scalars(select(UserRoleScope).where(UserRoleScope.user_id == user.id)):
                db.delete(row)
        db.commit()
    assert agent_clients["owner"].get("/api/v1/agent/capabilities").status_code in (401, 403)


def test_create_replay_and_unknown_result(actors, agent_clients):
    client = agent_clients["owner"]
    payload = draft_payload(actors)
    first = client.post("/api/v1/agent/drafts", json=payload)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["status"] == "draft" and result["sharing_scope"] == "private"
    assert result["confirmation_url"] == "https://jtzhzt.flipbeltchina.com/discover/" + result["id"]
    assert client.post("/api/v1/agent/drafts", json=payload).json() == result
    assert (
        client.post("/api/v1/agent/drafts", json=payload | {"name": "不同内容"}).status_code == 409
    )
    op = "/api/v1/agent/operations/draft.create/" + payload["request_id"]
    assert client.get(op).json()["result"] == result
    assert agent_clients["other"].get(op).status_code == 404
    changed = client.patch(
        "/api/v1/agent/drafts/" + result["id"],
        json={
            "request_id": str(uuid4()),
            "version": 1,
            "name": "已修改",
            "description": "仍为私有草稿",
        },
    )
    assert changed.status_code == 200, changed.text
    # A delayed original create retry returns its exact receipt, not an extra Asset.
    assert client.post("/api/v1/agent/drafts", json=payload).json() == result
    assert client.get("/api/v1/agent/assets/" + result["id"]).json()["version"] == 2


def test_private_asset_and_admin_delegation(actors, agent_clients):
    item = create(agent_clients["owner"], actors)
    for role in ("other", "admin"):
        client = agent_clients[role]
        assert client.get("/api/v1/agent/assets/" + item["id"]).status_code == 404
        assert item["id"] not in {
            r["id"] for r in client.get("/api/v1/agent/assets").json()["items"]
        }
        assert (
            client.patch(
                "/api/v1/agent/drafts/" + item["id"],
                json={
                    "request_id": str(uuid4()),
                    "version": 1,
                    "name": "越权",
                    "description": "拒绝",
                },
            ).status_code
            == 404
        )
    with SessionLocal() as db:
        assert db.get(Asset, UUID(item["id"])).name == item["name"]


def test_strict_draft_input_and_type_dictionary(actors, agent_clients):
    client = agent_clients["owner"]
    capabilities = client.get("/api/v1/agent/capabilities").json()
    assert any(t["id"] == actors.skill for t in capabilities["asset_types"])
    assert capabilities["confirmation"] == "web_only"
    for changes in (
        {"actor_user_id": str(uuid4())},
        {"confirmed": True},
        {"asset_type_id": str(uuid4())},
        {"source_type": "manual"},
    ):
        assert (
            client.post("/api/v1/agent/drafts", json=draft_payload(actors, **changes)).status_code
            == 422
        )


def test_stale_preview_requires_fresh_web_confirmation(actors, agent_clients):
    client = agent_clients["owner"]
    item = create(client, actors)
    path = "/api/v1/assets/" + item["id"]
    receipt = actors.owner.post(
        path + "/confirmation",
        json={
            "request_id": str(uuid4()),
            "version": 1,
            "sharing_scope": "company",
        },
    )
    assert receipt.status_code == 200, receipt.text
    preview = receipt.json()
    update = {
        "request_id": str(uuid4()),
        "version": 1,
        "name": "本人草稿二版",
        "description": "修改后的描述",
    }
    response = client.patch("/api/v1/agent/drafts/" + item["id"], json=update)
    assert response.status_code == 200, response.text
    assert client.patch("/api/v1/agent/drafts/" + item["id"], json=update).json() == response.json()
    assert (
        client.patch(
            "/api/v1/agent/drafts/" + item["id"], json=update | {"request_id": str(uuid4())}
        ).status_code
        == 409
    )
    assert (
        actors.owner.post(
            path + "/confirm",
            json={
                "confirmation_id": preview["id"],
                "version": 1,
                "content_digest": preview["content_digest"],
                "confirmed": True,
            },
        ).status_code
        == 409
    )
    fresh = actors.owner.post(
        path + "/confirmation",
        json={
            "request_id": str(uuid4()),
            "version": 2,
            "sharing_scope": "company",
        },
    ).json()
    final = actors.owner.post(
        path + "/confirm",
        json={
            "confirmation_id": fresh["id"],
            "version": 2,
            "content_digest": fresh["content_digest"],
            "confirmed": True,
        },
    )
    assert final.status_code == 200, final.text
    assert final.json()["status"] == "active"
    assert final.json()["review_status"] == "pending_review"
    assert agent_clients["other"].get("/api/v1/agent/assets/" + item["id"]).status_code == 200
    assert (
        client.patch(
            "/api/v1/agent/drafts/" + item["id"],
            json=update | {"request_id": str(uuid4()), "version": 3},
        ).status_code
        == 404
    )


def test_incubation_privacy_revision_and_idempotency(actors, agent_clients):
    client = agent_clients["owner"]
    payload = dict(
        request_id=str(uuid4()),
        title="报价单位核对",
        stage="discovering",
        workflow_summary="只保存必要结构化摘要",
    )
    first = client.post("/api/v1/agent/incubations", json=payload)
    assert first.status_code == 200, first.text
    item = first.json()
    assert item["version"] == 1
    assert client.post("/api/v1/agent/incubations", json=payload).json() == item
    for role in ("other", "admin"):
        assert agent_clients[role].get("/api/v1/agent/incubations/" + item["id"]).status_code == 404
        assert agent_clients[role].get("/api/v1/agent/incubations").json()["items"] == []
    update = payload | {
        "request_id": str(uuid4()),
        "id": item["id"],
        "version": 1,
        "stage": "blueprint",
        "blueprint_summary": "人工统一表格后核对",
    }
    changed = client.post("/api/v1/agent/incubations", json=update)
    assert changed.status_code == 200, changed.text
    assert changed.json()["version"] == 2
    assert client.post("/api/v1/agent/incubations", json=update).json() == changed.json()
    assert (
        client.post(
            "/api/v1/agent/incubations", json=update | {"request_id": str(uuid4())}
        ).status_code
        == 409
    )
    assert client.post("/api/v1/agent/incubations", json=payload | {"chat": []}).status_code == 422
    assert (
        client.post(
            "/api/v1/agent/incubations",
            json=payload | {"request_id": str(uuid4()), "asset_id": str(uuid4())},
        ).status_code
        == 404
    )
    with SessionLocal() as db:
        # Failed writes do not leave idempotency rows or incomplete incubation rows.
        assert db.get(AgentIncubation, UUID(item["id"])).version == 2


def test_pairing_approval_poll_once_and_revoke(actors, agent_clients):
    public = TestClient(app)
    start = public.post("/api/v1/agent/device/start", json={"client_name": "Qoder-CN"})
    assert start.status_code == 200, start.text
    challenge = start.json()
    assert start.headers["cache-control"] == "no-store"
    assert "?" not in challenge["verification_uri"]
    assert (
        public.post(
            "/api/v1/agent/device/poll", json={"device_code": challenge["device_code"]}
        ).json()["status"]
        == "pending"
    )
    assert (
        public.post(
            "/api/v1/agent/device/poll", json={"device_code": challenge["device_code"]}
        ).status_code
        == 429
    )
    preview = actors.owner.post(
        "/api/v1/agent/device/preview", json={"user_code": challenge["user_code"]}
    )
    assert preview.json()["client_name"] == "Qoder-CN"
    approve = actors.owner.post(
        "/api/v1/agent/device/approve", json={"user_code": challenge["user_code"], "approved": True}
    )
    assert approve.status_code == 200, approve.text
    with SessionLocal() as db:
        grant = db.scalar(
            select(AgentGrant).where(AgentGrant.device_hash == digest(challenge["device_code"]))
        )
        grant.last_polled_at = now() - timedelta(seconds=6)
        grant_id = grant.id
        assert grant.user_code_hash != challenge["user_code"]
        db.commit()
    received = public.post(
        "/api/v1/agent/device/poll", json={"device_code": challenge["device_code"]}
    )
    assert received.status_code == 200, received.text
    assert received.headers["cache-control"] == "no-store"
    token = received.json()["access_token"]
    paired = TestClient(app, headers={"Authorization": "Bearer " + token})
    assert paired.get("/api/v1/agent/capabilities").status_code == 200
    assert (
        public.post(
            "/api/v1/agent/device/poll", json={"device_code": challenge["device_code"]}
        ).status_code
        == 400
    )
    assert actors.other.delete("/api/v1/agent/grants/" + str(grant_id)).status_code == 404
    assert actors.owner.delete("/api/v1/agent/grants/" + str(grant_id)).status_code == 200
    assert paired.get("/api/v1/agent/capabilities").status_code == 401


def test_cookie_approval_requires_csrf(actors, agent_clients):
    token = actors.owner.headers["X-PM-Session"]
    cookie = TestClient(app, cookies={get_settings().session_cookie_name: token})
    assert (
        cookie.post(
            "/api/v1/agent/device/approve", json={"user_code": "ABCD2345", "approved": True}
        ).status_code
        == 403
    )


def test_disconnect(actors, agent_clients):
    client = agent_clients["owner"]
    assert client.post("/api/v1/agent/disconnect").status_code == 200
    assert client.get("/api/v1/agent/capabilities").status_code == 401


def test_no_operation_for_failed_write(actors, agent_clients):
    client = agent_clients["owner"]
    payload = draft_payload(actors, asset_type_id=str(uuid4()))
    assert client.post("/api/v1/agent/drafts", json=payload).status_code == 422
    assert (
        client.get("/api/v1/agent/operations/draft.create/" + payload["request_id"]).status_code
        == 404
    )


def test_update_key_cannot_cross_assets(actors, agent_clients):
    client = agent_clients["owner"]
    one = create(client, actors, name="成果一")
    two = create(client, actors, name="成果二")
    update = {
        "request_id": str(uuid4()),
        "version": 1,
        "name": "修改",
        "description": "同一请求不能串到另一个目标",
    }
    assert client.patch("/api/v1/agent/drafts/" + one["id"], json=update).status_code == 200
    assert client.patch("/api/v1/agent/drafts/" + two["id"], json=update).status_code == 409
    assert client.get("/api/v1/agent/assets/" + two["id"]).json()["name"] == "成果二"


def test_concurrent_create_and_update_are_single_effect(actors, agent_clients):
    from concurrent.futures import ThreadPoolExecutor

    headers = dict(agent_clients["owner"].headers)
    payload = draft_payload(actors)

    def create_once(_):
        client = TestClient(app, headers=headers)
        try:
            return client.post("/api/v1/agent/drafts", json=payload)
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        replies = list(executor.map(create_once, range(2)))
    assert {r.status_code for r in replies} == {200}
    assert replies[0].json() == replies[1].json()
    asset = replies[0].json()

    def update_once(_):
        client = TestClient(app, headers=headers)
        try:
            return client.patch(
                "/api/v1/agent/drafts/" + asset["id"],
                json={
                    "request_id": str(uuid4()),
                    "version": 1,
                    "name": "二版",
                    "description": "只更新一次",
                },
            )
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        replies = list(executor.map(update_once, range(2)))
    assert sorted(r.status_code for r in replies) == [200, 409]
    assert agent_clients["owner"].get("/api/v1/agent/assets/" + asset["id"]).json()["version"] == 2


def test_pairing_expiry_denial_and_rate_limit(actors, agent_clients):
    public = TestClient(app)
    challenge = public.post("/api/v1/agent/device/start", json={}).json()
    assert (
        actors.owner.post(
            "/api/v1/agent/device/approve",
            json={"user_code": challenge["user_code"], "approved": False},
        ).status_code
        == 200
    )
    assert (
        public.post(
            "/api/v1/agent/device/poll", json={"device_code": challenge["device_code"]}
        ).status_code
        == 400
    )
    challenge = public.post("/api/v1/agent/device/start", json={}).json()
    with SessionLocal() as db:
        item = db.scalar(
            select(AgentGrant).where(AgentGrant.device_hash == digest(challenge["device_code"]))
        )
        item.device_expires_at = now() - timedelta(seconds=1)
        db.commit()
    assert (
        actors.owner.post(
            "/api/v1/agent/device/preview", json={"user_code": challenge["user_code"]}
        ).status_code
        == 404
    )
    for _ in range(3):
        assert public.post("/api/v1/agent/device/start", json={}).status_code == 200
    assert public.post("/api/v1/agent/device/start", json={}).status_code == 429


@pytest.mark.parametrize("method", ["traditional", None])
def test_connector_cannot_edit_non_ai_system_draft(actors, agent_clients, method):
    from app.models import AssetType

    with SessionLocal() as db:
        type_id = db.scalar(select(AssetType.id).where(AssetType.code == "internal_system"))
        item = Asset(
            asset_code="LEGACY-" + uuid4().hex[:8],
            name="传统系统草稿",
            asset_type_id=type_id,
            legal_entity_id=UUID(actors.entity),
            created_by_person_id=actors.person["owner"],
            ownership_scope="pending",
            sharing_scope="private",
            confidentiality="personal",
            status="draft",
            development_method=method,
            source_type="manual",
        )
        db.add(item)
        db.commit()
        identity = str(item.id)
    client = agent_clients["owner"]
    assert client.get("/api/v1/agent/assets/" + identity).status_code == 404
    assert (
        client.patch(
            "/api/v1/agent/drafts/" + identity,
            json={"request_id": str(uuid4()), "version": 1, "name": "越界", "description": "拒绝"},
        ).status_code
        == 404
    )
