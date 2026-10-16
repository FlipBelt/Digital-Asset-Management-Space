"""Remote MCP regression tests for the opted-in disposable PostgreSQL harness."""

import base64
import hashlib
import io
import json
import zipfile
from contextlib import closing
from datetime import timedelta
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.agent_auth import _buckets, digest, now
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import AgentGrant, AgentIncubation, Asset, Person, User, UserRoleScope

pytest_plugins = ["test_asset_center_integration"]

RESOURCE = "https://jtzhzt.flipbeltchina.com/mcp"
CALLBACK = "https://chatgpt.com/connector_platform_oauth_redirect"
SCOPES = "asset:read asset:draft incubation:read incubation:write"
TOOLS = {
    "get_capabilities", "search_assets", "get_asset", "create_asset_draft",
    "update_asset_draft", "get_my_incubations", "get_incubation", "save_snapshot",
    "operation_status", "get_asset_details", "save_asset_details", "search_people",
    "upload_asset_attachment",
}


@pytest.fixture
def mcp_settings(actors, monkeypatch):
    # actors performs the opt-in, loopback port, DB-name and app-env checks first.
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_connector_enabled", True)
    monkeypatch.setattr(settings, "agent_frontend_url", RESOURCE.removesuffix("/mcp"))
    monkeypatch.setattr(settings, "agent_mcp_enabled", True)
    monkeypatch.setattr(settings, "agent_mcp_public_url", RESOURCE)
    monkeypatch.setattr(settings, "agent_mcp_allowed_redirect_uris", [CALLBACK])
    monkeypatch.setattr(settings, "agent_mcp_allowed_origins", ["https://chatgpt.com"])
    _buckets.clear()
    return settings


@pytest.fixture
def issue_mcp_token(actors, mcp_settings):
    clients = []

    def issue(actor="owner", scopes=SCOPES):
        transport = TestClient(app)
        clients.append(transport)
        registration = transport.post(
            "/mcp-oauth/register",
            json={
                "client_name": "Synthetic MCP integration",
                "redirect_uris": [CALLBACK],
                "token_endpoint_auth_method": "none",
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
            },
        )
        assert registration.status_code == 201, registration.text
        client_id = registration.json()["client_id"]
        verifier = uuid4().hex + uuid4().hex
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        state = uuid4().hex
        authorization = transport.get(
            "/mcp-oauth/authorize",
            params={
                "response_type": "code", "client_id": client_id,
                "redirect_uri": CALLBACK, "scope": scopes, "resource": RESOURCE,
                "state": state, "code_challenge": challenge.decode().rstrip("="),
                "code_challenge_method": "S256",
            },
            follow_redirects=False,
        )
        assert authorization.status_code == 302, authorization.text
        location = urlsplit(authorization.headers["location"])
        assert f"{location.scheme}://{location.netloc}" == RESOURCE.removesuffix("/mcp")
        request_token = parse_qs(location.query)["request_token"][0]
        portal = getattr(actors, actor)
        preview = portal.post("/api/v1/agent/oauth/preview", json={"request_token": request_token})
        assert preview.status_code == 200, preview.text
        approval = portal.post(
            "/api/v1/agent/oauth/approve",
            json={"request_token": request_token, "approved": True},
        )
        assert approval.status_code == 200, approval.text
        redirect = urlsplit(approval.json()["redirect_url"])
        assert f"{redirect.scheme}://{redirect.netloc}{redirect.path}" == CALLBACK
        query = parse_qs(redirect.query)
        assert query["state"] == [state]
        token_response = transport.post(
            "/mcp-oauth/token",
            data={
                "grant_type": "authorization_code", "client_id": client_id,
                "code": query["code"][0], "redirect_uri": CALLBACK,
                "code_verifier": verifier, "resource": RESOURCE,
            },
        )
        assert token_response.status_code == 200, token_response.text
        tokens = token_response.json()
        assert tokens["token_type"].lower() == "bearer"
        assert set(tokens["scope"].split()) == set(scopes.split())
        machine = TestClient(app, headers={"Authorization": "Bearer " + tokens["access_token"]})
        clients.append(machine)
        return SimpleNamespace(client=machine, transport=transport, client_id=client_id, **tokens)

    yield issue
    for client in clients:
        client.close()


def rpc(client, method, params=None, **kwargs):
    return client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        **kwargs,
    )


def call(client, name, arguments=None):
    return rpc(client, "tools/call", {"name": name, "arguments": arguments or {}})


def result(response, *, error=None):
    assert response.status_code == 200, response.text
    envelope = response.json()
    assert envelope["jsonrpc"] == "2.0" and envelope["id"] == 1
    assert "error" not in envelope, envelope
    tool = envelope["result"]
    assert tool["isError"] is (error is not None), tool
    value = tool["structuredContent"]
    assert json.loads(tool["content"][0]["text"]) == value
    if error is not None:
        assert value["status"] == error, value
    return value


def rpc_error(response, code, status=200):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code, response.text


def draft_input(actors, **changes):
    return {
        "request_id": str(uuid4()), "name": "远程 MCP 合成成果",
        "description": "仅隔离测试，不代表真人业务验收", "asset_type_id": actors.skill,
    } | changes


def create(client, actors, **changes):
    return result(call(client, "create_asset_draft", draft_input(actors, **changes)))


def test_remote_feature_is_disabled_independently(mcp_settings, monkeypatch):
    monkeypatch.setattr(mcp_settings, "agent_mcp_enabled", False)
    with closing(TestClient(app)) as client:
        assert rpc(client, "initialize").status_code == 404


def test_anonymous_portal_and_valid_legacy_token_cannot_authenticate(actors, mcp_settings):
    with closing(TestClient(app)) as anonymous:
        response = rpc(anonymous, "tools/list")
        assert response.status_code == 401
        assert "oauth-protected-resource/mcp" in response.headers["www-authenticate"]
        for method in (anonymous.get, anonymous.delete):
            assert method("/mcp").status_code == 401
    assert rpc(actors.owner, "tools/list").status_code == 401
    with closing(TestClient(app)) as cookie_client:
        cookie_client.cookies.set(
            get_settings().session_cookie_name, actors.owner.headers["X-PM-Session"]
        )
        assert rpc(cookie_client, "tools/list").status_code == 401
    token = "agt_" + uuid4().hex + uuid4().hex
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.person_id == actors.person["owner"]))
        db.add(AgentGrant(
            device_hash=digest(uuid4().hex), user_code_hash=digest(uuid4().hex),
            client_name="Codex", user_id=user.id, device_expires_at=now() + timedelta(minutes=5),
            token_hash=digest(token), token_expires_at=now() + timedelta(hours=1),
        ))
        db.commit()
    with closing(TestClient(app, headers={"Authorization": "Bearer " + token})) as legacy:
        assert legacy.get("/api/v1/agent/capabilities").status_code == 200
        assert rpc(legacy, "tools/list").status_code == 401


@pytest.mark.parametrize("protocol", ["2025-06-18", "2025-03-26", "2024-11-05"])
def test_real_oauth_initialize_notifications_and_stateless_transport(issue_mcp_token, protocol):
    client = issue_mcp_token().client
    response = rpc(client, "initialize", {
        "protocolVersion": protocol, "capabilities": {},
        "clientInfo": {"name": "Synthetic integration", "version": "1.0"},
    })
    assert response.status_code == 200, response.text
    assert response.json()["result"]["protocolVersion"] == protocol
    assert "tools" in response.json()["result"]["capabilities"]
    assert "mcp-session-id" not in response.headers
    assert "set-cookie" not in response.headers
    notification = client.post(
        "/mcp", json={"jsonrpc": "2.0", "method": "notifications/initialized"}
    )
    assert notification.status_code == 202 and not notification.content
    for method in (client.get, client.delete):
        unsupported = method("/mcp")
        assert unsupported.status_code == 405
        assert unsupported.headers["allow"] == "POST"
    assert client.get("/api/v1/assets").status_code == 401
    assert client.get("/api/v1/agent/capabilities").status_code == 401


def test_discovery_exposes_only_bounded_business_tools(actors, issue_mcp_token):
    client = issue_mcp_token().client
    response = rpc(client, "tools/list")
    assert response.status_code == 200, response.text
    tools = {tool["name"]: tool for tool in response.json()["result"]["tools"]}
    assert set(tools) == TOOLS
    for tool in tools.values():
        assert tool["inputSchema"]["additionalProperties"] is False
        assert tool["annotations"]["openWorldHint"] is False
    schema_text = json.dumps(tools)
    for forbidden in ("file_path", "confirmed", "actor_user_id", "sharing_scope", "source_agent"):
        assert forbidden not in schema_text
    upload = tools["upload_asset_attachment"]["inputSchema"]
    assert set(upload["properties"]) == {
        "asset_id", "request_id", "version", "file_name", "content_base64",
    }
    details = tools["save_asset_details"]["inputSchema"]["properties"]
    assert "asset_id" in details and "profile" in details and "details" not in details
    capabilities = result(call(client, "get_capabilities"))
    assert capabilities["protocol"] == "flipbelt-agent-mcp-v1"
    assert capabilities["remote_tool_count"] == 13
    assert capabilities["confirmation"] == "web_only"
    assert capabilities["attachment_input"] == "content_base64"
    assert capabilities["attachment_max_bytes"] == 1_000_000
    assert capabilities["user"]["person_id"] == str(actors.person["owner"])
    assert any(item["id"] == actors.skill for item in capabilities["asset_types"])


@pytest.mark.parametrize("name", [
    "confirm", "confirm_asset", "publish", "approve", "delete_asset", "read_file",
    "start_connection", "complete_connection", "disconnect",
])
def test_unexposed_machine_or_privileged_tools_are_rejected(issue_mcp_token, name):
    rpc_error(call(issue_mcp_token().client, name), -32602)


def test_draft_replay_conflict_receipt_and_server_owned_identity(actors, issue_mcp_token):
    client = issue_mcp_token().client
    other = issue_mcp_token("other").client
    payload = draft_input(actors)
    item = result(call(client, "create_asset_draft", payload))
    assert item["status"] == "draft" and item["sharing_scope"] == "private"
    assert item["created_by_person_id"] == str(actors.person["owner"])
    assert item["confirmation_url"] == RESOURCE.removesuffix("/mcp") + "/discover/" + item["id"]
    assert result(call(client, "create_asset_draft", payload)) == item
    result(call(client, "create_asset_draft", payload | {"name": "错误的重复内容"}), error=409)
    operation = {"operation": "draft.create", "request_id": payload["request_id"]}
    assert result(call(client, "operation_status", operation))["result"] == item
    result(call(other, "operation_status", operation), error=404)
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(item["id"]))
        assert asset.name == payload["name"]
        assert asset.source_type == "connector" and asset.source_agent == "remote-mcp"
        assert db.scalar(select(func.count()).select_from(Asset).where(
            Asset.created_by_person_id == actors.person["owner"], Asset.name == payload["name"],
        )) == 1


def test_other_employee_and_admin_cannot_read_or_change_private_draft(actors, issue_mcp_token):
    owner = issue_mcp_token().client
    item = create(owner, actors)
    for role in ("other", "admin"):
        client = issue_mcp_token(role).client
        rows = result(call(client, "search_assets"))["items"]
        assert item["id"] not in {row["id"] for row in rows}
        result(call(client, "get_asset", {"asset_id": item["id"]}), error=404)
        result(call(client, "get_asset_details", {"asset_id": item["id"]}), error=404)
        result(call(client, "update_asset_draft", {
            "asset_id": item["id"], "request_id": str(uuid4()), "version": item["version"],
            "name": "越权改名", "description": "拒绝",
        }), error=404)
        result(call(client, "save_asset_details", {
            "asset_id": item["id"], "request_id": str(uuid4()), "version": item["version"],
            "identifiers": [],
        }), error=404)
    assert result(call(owner, "get_asset", {"asset_id": item["id"]})) == item


def test_version_conflict_and_web_confirmation_cannot_be_bypassed(actors, issue_mcp_token):
    client = issue_mcp_token().client
    item = create(client, actors)
    path = "/api/v1/assets/" + item["id"]
    receipt = actors.owner.post(path + "/confirmation", json={
        "request_id": str(uuid4()), "version": item["version"], "sharing_scope": "company",
    })
    assert receipt.status_code == 200, receipt.text
    confirmation = receipt.json()
    update = {
        "asset_id": item["id"], "request_id": str(uuid4()), "version": item["version"],
        "name": "远程更新后的新稿", "description": "必须重新本人预览",
    }
    changed = result(call(client, "update_asset_draft", update))
    assert changed["version"] == item["version"] + 1 and changed["status"] == "draft"
    assert result(call(client, "update_asset_draft", update)) == changed
    result(call(client, "update_asset_draft", update | {"request_id": str(uuid4())}), error=409)
    confirm = {
        "confirmation_id": confirmation["id"], "version": confirmation["asset_version"],
        "content_digest": confirmation["content_digest"], "confirmed": True,
    }
    assert client.post(path + "/confirm", json=confirm).status_code == 401
    assert actors.owner.post(path + "/confirm", json=confirm).status_code == 409
    assert result(call(client, "get_asset", {"asset_id": item["id"]})) == changed


def test_incubation_privacy_replay_and_version_conflicts(actors, issue_mcp_token):
    owner = issue_mcp_token().client
    other = issue_mcp_token("other").client
    payload = {
        "request_id": str(uuid4()), "version": 0, "title": "合成孵化摘要",
        "stage": "blueprint", "workflow_summary": "授权范围内的结构化摘要",
        "next_step": "待真人试用",
    }
    item = result(call(owner, "save_snapshot", payload))
    assert item["version"] == 1
    assert result(call(owner, "save_snapshot", payload)) == item
    result(call(owner, "save_snapshot", payload | {"title": "冲突内容"}), error=409)
    identity = {"incubation_id": item["id"]}
    assert result(call(owner, "get_incubation", identity)) == item
    assert item["id"] in {row["id"] for row in result(call(owner, "get_my_incubations"))["items"]}
    other_rows = result(call(other, "get_my_incubations"))["items"]
    assert item["id"] not in {row["id"] for row in other_rows}
    result(call(other, "get_incubation", identity), error=404)
    changed_payload = payload | {"request_id": str(uuid4()), "id": item["id"], "version": 1}
    result(call(other, "save_snapshot", changed_payload), error=404)
    changed = result(call(owner, "save_snapshot", changed_payload))
    assert changed["version"] == 2
    result(call(owner, "save_snapshot", changed_payload | {"request_id": str(uuid4())}), error=409)
    with SessionLocal() as db:
        assert db.get(AgentIncubation, UUID(item["id"])).version == 2


def test_oauth_scopes_are_enforced_before_business_operations(actors, issue_mcp_token):
    read = issue_mcp_token(scopes="asset:read").client
    result(call(read, "get_capabilities"))
    denied = call(read, "create_asset_draft", draft_input(actors))
    assert denied.status_code == 403
    assert 'error="insufficient_scope"' in denied.headers["www-authenticate"]
    assert "asset:draft" in denied.headers["www-authenticate"]
    assert call(read, "get_my_incubations").status_code == 403
    incubation = issue_mcp_token(scopes="incubation:read incubation:write").client
    result(call(incubation, "get_my_incubations"))
    assert call(incubation, "get_capabilities").status_code == 403
    result(call(incubation, "operation_status", {
        "operation": "incubation.save", "request_id": str(uuid4()),
    }), error=404)
    assert call(incubation, "operation_status", {
        "operation": "draft.create", "request_id": str(uuid4()),
    }).status_code == 403


@pytest.mark.parametrize("state", ["inactive", "departed", "role_removed"])
def test_employee_changes_invalidate_existing_remote_access(actors, issue_mcp_token, state):
    client = issue_mcp_token().client
    result(call(client, "get_capabilities"))
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.person_id == actors.person["owner"]))
        if state == "inactive":
            user.is_active = False
        elif state == "departed":
            db.get(Person, user.person_id).employment_status = "inactive"
        else:
            for role in db.scalars(select(UserRoleScope).where(UserRoleScope.user_id == user.id)):
                db.delete(role)
        db.commit()
    denied = rpc(client, "tools/list")
    assert denied.status_code in (401, 403)
    assert "Bearer" in denied.headers["www-authenticate"]


def test_revocation_invalidates_access_and_refresh_token(issue_mcp_token):
    identity = issue_mcp_token()
    result(call(identity.client, "get_capabilities"))
    revoked = identity.transport.post("/mcp-oauth/revoke", data={
        "client_id": identity.client_id, "token": identity.refresh_token,
    })
    assert revoked.status_code == 200, revoked.text
    assert rpc(identity.client, "tools/list").status_code == 401
    refresh = identity.transport.post("/mcp-oauth/token", data={
        "grant_type": "refresh_token", "client_id": identity.client_id,
        "refresh_token": identity.refresh_token, "resource": RESOURCE,
    })
    assert refresh.status_code in (400, 401)
    assert refresh.json()["error"] == "invalid_grant"


def test_origin_media_type_protocol_and_body_are_bounded(issue_mcp_token):
    client = issue_mcp_token().client
    untrusted = rpc(client, "tools/list", headers={"Origin": "https://untrusted.invalid"})
    assert untrusted.status_code == 403
    assert rpc(client, "tools/list", headers={"Origin": "https://chatgpt.com"}).status_code == 200
    assert rpc(client, "tools/list", headers={"MCP-Protocol-Version": "invalid"}).status_code == 400
    wrong_media = client.post("/mcp", content="{}", headers={"Content-Type": "text/plain"})
    assert wrong_media.status_code == 415
    huge = client.post(
        "/mcp", content=b" " * 1_500_001, headers={"Content-Type": "application/json"}
    )
    assert huge.status_code == 413
    broken_json = client.post("/mcp", content=b"{", headers={"Content-Type": "application/json"})
    rpc_error(broken_json, -32700, 400)
    for malformed in ([], {}, {"jsonrpc": "2.0", "id": True, "method": "tools/list"}, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "actor_user_id": str(uuid4()),
    }):
        rpc_error(client.post("/mcp", json=malformed), -32600, 400)
    rpc_error(client.post("/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": [],
    }), -32602)
    rpc_error(rpc(client, "not/a/method"), -32601)


def test_strict_tool_parameters_reject_identity_and_path_injection(actors, issue_mcp_token):
    client = issue_mcp_token().client
    payload = draft_input(actors)
    for extra in (
        {"created_by_person_id": str(actors.person["other"])}, {"actor_user_id": str(uuid4())},
        {"confirmed": True}, {"sharing_scope": "company"}, {"source_type": "manual"},
        {"source_agent": "trusted-admin"}, {"development_method": "traditional"},
    ):
        rpc_error(call(client, "create_asset_draft", payload | extra), -32602)
    rpc_error(call(client, "get_capabilities", {"actor": "admin"}), -32602)
    rpc_error(call(client, "search_assets", {"query": "x" * 201}), -32602)
    rpc_error(call(client, "get_asset", {"asset_id": "not-a-uuid"}), -32602)
    rpc_error(call(client, "upload_asset_attachment", {
        "asset_id": str(uuid4()), "request_id": str(uuid4()), "version": 1,
        "file_name": "private.zip", "file_path": "/etc/passwd", "content_base64": "eA==",
    }), -32602)
    result(call(client, "create_asset_draft", payload | {"asset_type_id": str(uuid4())}), error=422)


def test_remote_attachment_base64_limit_replay_and_confirmation_reset(
    actors, issue_mcp_token, tmp_path, monkeypatch,
):
    from app.api.v1 import asset_attachments

    monkeypatch.setattr(asset_attachments, "STORAGE", tmp_path)
    client = issue_mcp_token().client
    item = create(client, actors)
    preview = actors.owner.post("/api/v1/assets/" + item["id"] + "/confirmation", json={
        "request_id": str(uuid4()), "version": item["version"], "sharing_scope": "company",
    })
    assert preview.status_code == 200, preview.text
    payload = {
        "asset_id": item["id"], "request_id": str(uuid4()), "version": item["version"],
        "file_name": "synthetic.zip", "content_base64": "!not-base64!",
    }
    result(call(client, "upload_asset_attachment", payload), error=422)
    too_large = payload | {
        "request_id": str(uuid4()), "content_base64": base64.b64encode(b"x" * 1_000_001).decode(),
    }
    result(call(client, "upload_asset_attachment", too_large), error=413)
    assert result(call(client, "get_asset", {"asset_id": item["id"]}))["version"] == item["version"]
    assert not list(tmp_path.rglob("*"))
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("SKILL.md", "Synthetic fixture, not a real business outcome.")
    payload |= {
        "request_id": str(uuid4()), "content_base64": base64.b64encode(archive.getvalue()).decode(),
    }
    uploaded = result(call(client, "upload_asset_attachment", payload))
    assert uploaded["attachment"]["size_bytes"] == len(archive.getvalue())
    assert uploaded["version"] == item["version"] + 1
    assert uploaded["status"] == "draft" and uploaded["sharing_scope"] == "private"
    assert result(call(client, "upload_asset_attachment", payload)) == uploaded
    stale = payload | {"request_id": str(uuid4())}
    result(call(client, "upload_asset_attachment", stale), error=409)
    confirmation = preview.json()
    assert actors.owner.post("/api/v1/assets/" + item["id"] + "/confirm", json={
        "confirmation_id": confirmation["id"], "version": confirmation["asset_version"],
        "content_digest": confirmation["content_digest"], "confirmed": True,
    }).status_code == 409


def test_unexpected_tool_failure_is_sanitized_and_rolled_back(issue_mcp_token, monkeypatch):
    from app.api.v1 import agent_mcp

    client = issue_mcp_token().client
    pending_id = uuid4()

    def fail(_name, _arguments, db, access):
        db.add(AgentIncubation(
            id=pending_id, user_id=access.user.id, version=1, title="Uncommitted synthetic row",
            stage="paused", workflow_summary="", opportunity_summary="", blueprint_summary="",
            next_step="",
        ))
        db.flush()
        raise RuntimeError("synthetic-internal-error-must-not-leak")

    monkeypatch.setattr(agent_mcp, "dispatch", fail)
    response = call(client, "get_capabilities")
    result(response, error=503)
    assert "synthetic-internal-error-must-not-leak" not in response.text
    with SessionLocal() as db:
        assert db.get(AgentIncubation, pending_id) is None

