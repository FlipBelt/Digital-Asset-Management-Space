"""Real OAuth exchanges on the explicitly disposable PostgreSQL harness only."""

import base64
import hashlib
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from starlette.requests import Request

from app.core import mcp_oauth as oauth_core
from app.core.agent_auth import _buckets, digest, now
from app.core.auth_logging import AuthQueryRedaction
from app.core.config import Settings, get_settings
from app.core.mcp_oauth import SCOPES, mcp_access
from app.db.session import SessionLocal
from app.main import app
from app.models import McpOAuthClient, McpOAuthGrant, McpOAuthRequest, Person, User

pytest_plugins = ["test_asset_center_integration"]
CALLBACK = "http://127.0.0.1:47321/callback"
RESOURCE = "https://jtzhzt.flipbeltchina.com/mcp"
ISSUER = "https://jtzhzt.flipbeltchina.com/mcp-oauth"
VERIFIER = "v" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).decode().rstrip("=")
)


@pytest.fixture
def oauth(actors, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_connector_enabled", True)
    monkeypatch.setattr(settings, "agent_mcp_enabled", True)
    monkeypatch.setattr(settings, "agent_frontend_url", "https://jtzhzt.flipbeltchina.com/")
    monkeypatch.setattr(settings, "agent_mcp_public_url", RESOURCE)
    monkeypatch.setattr(settings, "agent_mcp_allowed_redirect_uris", [])
    _buckets.clear()
    client = TestClient(app, follow_redirects=False)
    try:
        yield client
    finally:
        client.close()


def register(client, **changes):
    payload = {
        "client_name": "Synthetic test client",
        "redirect_uris": [CALLBACK],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
    } | changes
    response = client.post("/mcp-oauth/register", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def authorize(client, registered, **changes):
    params = {
        "client_id": registered["client_id"],
        "redirect_uri": registered["redirect_uris"][0],
        "response_type": "code",
        "state": "synthetic-state",
        "scope": " ".join(SCOPES),
        "resource": RESOURCE,
        "code_challenge": CHALLENGE,
        "code_challenge_method": "S256",
    }
    for key, value in changes.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return client.get("/mcp-oauth/authorize", params=params)


def consent(client, actors, registered, **changes):
    response = authorize(client, registered, **changes)
    assert response.status_code == 302, response.text
    location = response.headers["location"]
    assert "/agent/oauth?" in location
    token = parse_qs(urlsplit(location).query)["request_token"][0]
    payload = {"request_token": token}
    preview = actors.owner.post("/api/v1/agent/oauth/preview", json=payload)
    assert preview.status_code == 200, preview.text
    assert preview.json()["client_identity_note"]
    approved = actors.owner.post("/api/v1/agent/oauth/approve", json=payload | {"approved": True})
    assert approved.status_code == 200, approved.text
    query = parse_qs(urlsplit(approved.json()["redirect_url"]).query)
    assert query["state"] == ["synthetic-state"]
    assert query["iss"] == [get_settings().agent_mcp_public_url.removesuffix("/mcp") + "/mcp-oauth"]
    return query["code"][0], token


def exchange(client, registered, code, **changes):
    payload = {
        "grant_type": "authorization_code",
        "client_id": registered["client_id"],
        "code": code,
        "redirect_uri": registered["redirect_uris"][0],
        "code_verifier": VERIFIER,
        "resource": get_settings().agent_mcp_public_url,
    }
    if "client_secret" in registered:
        payload["client_secret"] = registered["client_secret"]
    for key, value in changes.items():
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    return client.post("/mcp-oauth/token", data=payload)


def tokens(client, actors, **changes):
    registered = register(client, **changes)
    code, _ = consent(client, actors, registered)
    response = exchange(client, registered, code)
    assert response.status_code == 200, response.text
    return registered, response.json()


def machine_access(raw, required=None):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/mcp",
            "headers": [(b"authorization", ("Bearer " + raw).encode())],
        }
    )
    with SessionLocal() as db:
        access = mcp_access(request, db, set() if required is None else required)
        return access.user.id, request.state.mcp_scopes


def error_code(response):
    if response.status_code == 302:
        query = parse_qs(urlsplit(response.headers["location"]).query)
        assert query["iss"] == [ISSUER]
        assert query["state"] == ["synthetic-state"]
        return query["error"][0]
    return response.json()["error"]


def test_complete_public_flow_and_hash_only_storage(actors, oauth):
    registered, result = tokens(oauth, actors)
    assert result["token_type"] == "Bearer" and result["expires_in"] == 3600
    user_id, allowed = machine_access(result["access_token"], {"asset:read"})
    assert allowed == set(SCOPES)
    with SessionLocal() as db:
        client = db.scalar(
            select(McpOAuthClient).where(McpOAuthClient.client_id == registered["client_id"])
        )
        grant = db.scalar(
            select(McpOAuthGrant).where(McpOAuthGrant.token_hash == digest(result["access_token"]))
        )
        request = db.scalar(select(McpOAuthRequest).where(McpOAuthRequest.client_id == client.id))
        assert grant.user_id == user_id and grant.issuer == ISSUER and grant.resource == RESOURCE
        assert grant.refresh_hash == digest(result["refresh_token"])
        assert request.consumed_at and request.user_id == user_id
        assert request.code_hash.startswith("mcd_") is False
        assert request.request_hash.startswith("mrq_") is False
        assert client.secret_hash is None and client.revoked_at is None
    assert oauth.get("/.well-known/oauth-authorization-server/mcp-oauth").json()["issuer"] == ISSUER
    metadata = oauth.get("/.well-known/oauth-protected-resource/mcp").json()
    assert metadata["resource"] == RESOURCE and metadata["authorization_servers"] == [ISSUER]


def test_registration_ignores_unsupported_metadata_without_storing_it(actors, oauth):
    metadata = {
        "contacts": ["synthetic-dcr-contact@example.invalid"],
        "jwks_uri": "https://synthetic-dcr-keys.example.invalid/jwks.json",
        "vendor_extension": {"synthetic_extension_marker": True},
    }
    registered = register(
        oauth,
        redirect_uris=["https://chatgpt.com/connector_platform_oauth_redirect"],
        **metadata,
    )
    assert not metadata.keys() & registered.keys()
    with SessionLocal() as db:
        client = db.scalar(
            select(McpOAuthClient).where(McpOAuthClient.client_id == registered["client_id"])
        )
        stored = json.dumps(
            {column.key: getattr(client, column.key) for column in client.__table__.columns},
            default=str,
        )
        for value in (
            metadata["contacts"][0],
            metadata["jwks_uri"],
            "synthetic_extension_marker",
        ):
            assert value not in stored


@pytest.mark.parametrize(
    "changes",
    [
        {"client_name": 123},
        {"redirect_uris": CALLBACK},
        {"token_endpoint_auth_method": "private_key_jwt"},
        {"grant_types": ["client_credentials"]},
        {"response_types": ["token"]},
        {"scope": "openid"},
    ],
)
def test_ignored_registration_metadata_does_not_relax_known_fields(actors, oauth, changes):
    payload = {
        "redirect_uris": [CALLBACK],
        "contacts": ["synthetic-dcr-contact@example.invalid"],
    } | changes
    assert oauth.post("/mcp-oauth/register", json=payload).status_code == 400


def test_registration_duplicate_json_fields_are_rejected(actors, oauth):
    payload = f'{{"client_name":"one","client_name":"two","redirect_uris":["{CALLBACK}"]}}'
    response = oauth.post(
        "/mcp-oauth/register",
        content=payload,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 400


@pytest.mark.parametrize("endpoint", ["preview", "approve"])
def test_consent_endpoints_still_forbid_unknown_fields(actors, oauth, endpoint):
    payload = {"request_token": "mrq_" + "a" * 43, "vendor_extension": "ignored-in-dcr-only"}
    if endpoint == "approve":
        payload["approved"] = True
    assert actors.owner.post("/api/v1/agent/oauth/" + endpoint, json=payload).status_code == 400


def test_consent_binds_preview_user_and_denial_has_iss(actors, oauth):
    registered = register(oauth)
    response = authorize(oauth, registered)
    token = parse_qs(urlsplit(response.headers["location"]).query)["request_token"][0]
    payload = {"request_token": token}
    assert (
        actors.owner.post(
            "/api/v1/agent/oauth/approve", json=payload | {"approved": True}
        ).status_code
        == 409
    )
    assert actors.owner.post("/api/v1/agent/oauth/preview", json=payload).status_code == 200
    assert actors.other.post("/api/v1/agent/oauth/preview", json=payload).status_code == 403
    assert (
        actors.other.post(
            "/api/v1/agent/oauth/approve", json=payload | {"approved": True}
        ).status_code
        == 403
    )
    denied = actors.owner.post("/api/v1/agent/oauth/approve", json=payload | {"approved": False})
    query = parse_qs(urlsplit(denied.json()["redirect_url"]).query)
    assert query == {"error": ["access_denied"], "state": ["synthetic-state"], "iss": [ISSUER]}
    assert actors.owner.post("/api/v1/agent/oauth/preview", json=payload).status_code == 404


def test_consent_cookie_requires_csrf(actors, oauth):
    registered = register(oauth)
    location = authorize(oauth, registered).headers["location"]
    token = parse_qs(urlsplit(location).query)["request_token"][0]
    cookie = TestClient(
        app, cookies={get_settings().session_cookie_name: actors.owner.headers["X-PM-Session"]}
    )
    try:
        assert (
            cookie.post("/api/v1/agent/oauth/preview", json={"request_token": token}).status_code
            == 403
        )
    finally:
        cookie.close()
    assert (
        oauth.post("/api/v1/agent/oauth/preview", json={"request_token": token}).status_code == 401
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"state": None},
        {"state": ""},
        {"code_challenge": None},
        {"code_challenge_method": "plain"},
        {"scope": ""},
        {"scope": "openid"},
        {"scope": "asset:read asset:read"},
        {"resource": ""},
        {"resource": "https://other.invalid/mcp"},
        {"resource": None},
        {"scope": None},
    ],
)
def test_authorization_requires_state_pkce_resource_scope(actors, oauth, changes):
    registered = register(oauth)
    response = authorize(oauth, registered, **changes)
    assert error_code(response) in {"invalid_request", "invalid_scope", "invalid_target"}


def test_duplicate_authorization_parameter_does_not_redirect(actors, oauth):
    registered = register(oauth)
    response = authorize(oauth, registered)
    # A repeated scope is rejected before any safe callback can be selected.
    url = str(response.request.url) + "&scope=asset%3Aread"
    assert oauth.get(url).status_code == 400


@pytest.mark.parametrize(
    "uri",
    [
        "https://evil.invalid/callback",
        "http://127.0.0.1/callback",
        "http://127.0.0.1:0/callback",
        "http://127.0.0.1:5555/other",
        "http://localhost.evil.invalid:5555/callback",
        "https://chatgpt.com.evil.invalid/connector_platform_oauth_redirect",
        "https://chatgpt.com/other",
        "qwenwork-cn://mcp-oauth/",
        "file:///callback",
    ],
)
def test_untrusted_redirect_registration_is_rejected(actors, oauth, uri):
    response = oauth.post(
        "/mcp-oauth/register", json={"client_name": "QwenWork", "redirect_uris": [uri]}
    )
    assert response.status_code == 400


def test_extra_callback_requires_exact_configured_allowlist(actors, oauth, monkeypatch):
    uri = "https://approved.example.invalid/oauth/callback"
    monkeypatch.setattr(get_settings(), "agent_mcp_allowed_redirect_uris", [uri])
    assert register(oauth, redirect_uris=[uri])["redirect_uris"] == [uri]
    assert register(oauth, redirect_uris=["https://chatgpt.com/connector_platform_oauth_redirect"])
    assert oauth.post("/mcp-oauth/register", json={"redirect_uris": [uri + "/"]}).status_code == 400


@pytest.mark.parametrize("name", ["QwenWork", "QoderWork"])
def test_exact_public_qwen_defaults_only_when_both_parameters_absent(actors, oauth, name):
    registered = register(
        oauth,
        client_name=name,
        redirect_uris=["qwenwork-cn://mcp-oauth"],
        application_type="native",
    )
    code, _ = consent(oauth, actors, registered, resource=None, scope=None)
    response = exchange(oauth, registered, code, resource=None)
    assert response.status_code == 200, response.text
    assert set(response.json()["scope"].split()) == set(SCOPES)
    for changes in (
        {"resource": "", "scope": None},
        {"resource": None, "scope": ""},
        {"resource": RESOURCE, "scope": None},
        {"resource": None, "scope": "asset:read"},
    ):
        assert error_code(authorize(oauth, registered, **changes)) in {
            "invalid_target",
            "invalid_scope",
        }


@pytest.mark.parametrize(
    "changes",
    [
        {"client_name": "qwenwork"},
        {"application_type": "web"},
        {"token_endpoint_auth_method": "client_secret_post"},
        {"redirect_uris": ["qwenwork-cn://mcp-oauth", CALLBACK]},
        {"grant_types": ["authorization_code"]},
    ],
)
def test_qwen_compatibility_rejects_near_matches_at_registration(actors, oauth, changes):
    payload = {
        "client_name": "QwenWork",
        "redirect_uris": ["qwenwork-cn://mcp-oauth"],
        "token_endpoint_auth_method": "none",
        "grant_types": ["authorization_code", "refresh_token"],
    } | changes
    assert oauth.post("/mcp-oauth/register", json=payload).status_code == 400


def test_bad_pkce_wrong_client_resource_and_code_replay(actors, oauth):
    registered = register(oauth)
    other = register(oauth)
    code, _ = consent(oauth, actors, registered)
    assert exchange(oauth, registered, code, code_verifier="x" * 64).status_code == 400
    assert exchange(oauth, other, code).status_code == 400
    assert (
        exchange(oauth, registered, code, resource="https://other.invalid/mcp").status_code == 400
    )
    assert (
        exchange(
            oauth, registered, code, redirect_uri="http://127.0.0.1:47322/callback"
        ).status_code
        == 400
    )
    assert exchange(oauth, registered, code).status_code == 200
    assert exchange(oauth, registered, code).status_code == 400


@pytest.mark.parametrize("method", ["client_secret_post", "client_secret_basic"])
def test_confidential_client_secret_is_hashed_and_does_not_expire(actors, oauth, method):
    registered = register(oauth, token_endpoint_auth_method=method)
    assert registered["client_secret_expires_at"] == 0
    with SessionLocal() as db:
        client = db.scalar(
            select(McpOAuthClient).where(McpOAuthClient.client_id == registered["client_id"])
        )
        assert client.secret_hash == digest(registered["client_secret"])
    code, _ = consent(oauth, actors, registered)
    assert exchange(oauth, registered, code, client_secret="wrong").status_code == 401
    if method == "client_secret_post":
        result = exchange(oauth, registered, code)
    else:
        result = oauth.post(
            "/mcp-oauth/token",
            auth=(registered["client_id"], registered["client_secret"]),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": CALLBACK,
                "code_verifier": VERIFIER,
                "resource": RESOURCE,
            },
        )
    assert result.status_code == 200, result.text


def test_refresh_rotates_replay_revokes_family_and_scope_cannot_grow(actors, oauth):
    registered, original = tokens(oauth, actors)
    payload = {
        "grant_type": "refresh_token",
        "client_id": registered["client_id"],
        "refresh_token": original["refresh_token"],
        "resource": RESOURCE,
    }
    bad = oauth.post("/mcp-oauth/token", data=payload | {"scope": "openid"})
    assert bad.status_code == 400
    rotated = oauth.post("/mcp-oauth/token", data=payload | {"scope": "asset:read"})
    assert rotated.status_code == 200, rotated.text
    current = rotated.json()
    assert current["refresh_token"] != original["refresh_token"]
    assert machine_access(current["access_token"], {"asset:read"})[1] == {"asset:read"}
    with pytest.raises(HTTPException) as denied:
        machine_access(current["access_token"], {"asset:draft"})
    assert denied.value.status_code == 403
    assert oauth.post("/mcp-oauth/token", data=payload).status_code == 400
    with pytest.raises(HTTPException) as invalid:
        machine_access(current["access_token"])
    assert invalid.value.status_code == 401


def test_revoke_and_web_grant_management_are_owner_only(actors, oauth):
    registered, result = tokens(oauth, actors)
    rows = actors.owner.get("/api/v1/agent/oauth/grants").json()
    grant = next(item for item in rows if item["client_name"] == registered["client_name"])
    assert actors.other.delete("/api/v1/agent/oauth/grants/" + grant["id"]).status_code == 404
    assert actors.owner.delete("/api/v1/agent/oauth/grants/" + grant["id"]).status_code == 200
    with pytest.raises(HTTPException):
        machine_access(result["access_token"])
    assert (
        oauth.post(
            "/mcp-oauth/revoke",
            data={"client_id": registered["client_id"], "token": result["refresh_token"]},
        ).status_code
        == 200
    )
    assert (
        oauth.post(
            "/mcp-oauth/revoke", data={"client_id": registered["client_id"], "token": "unknown"}
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    "state", ["expired", "revoked", "departed", "inactive", "wrong_resource", "wrong_issuer"]
)
def test_live_access_and_issuer_resource_isolation(actors, oauth, state):
    _, result = tokens(oauth, actors)
    with SessionLocal() as db:
        grant = db.scalar(
            select(McpOAuthGrant).where(McpOAuthGrant.token_hash == digest(result["access_token"]))
        )
        if state == "expired":
            grant.expires_at = now() - timedelta(seconds=1)
        elif state == "revoked":
            grant.revoked_at = now()
        elif state == "wrong_resource":
            grant.resource = "https://jtzhzt.flipbeltchina.com/test-api/mcp"
        elif state == "wrong_issuer":
            grant.issuer = "https://jtzhzt.flipbeltchina.com/test-api/mcp-oauth"
        elif state == "inactive":
            db.get(User, grant.user_id).is_active = False
        else:
            db.get(Person, actors.person["owner"]).employment_status = "departed"
        db.commit()
    with pytest.raises(HTTPException) as denied:
        machine_access(result["access_token"])
    assert denied.value.status_code in {401, 403}
    with pytest.raises(HTTPException):
        machine_access("agt_legacy-token")


def test_prefix_metadata_and_web_return_match_public_urls(actors, oauth, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "agent_frontend_url", "https://jtzhzt.flipbeltchina.com/test/")
    monkeypatch.setattr(
        settings, "agent_mcp_public_url", "https://jtzhzt.flipbeltchina.com/test-api/mcp"
    )
    metadata = oauth.get("/.well-known/oauth-authorization-server/test-api/mcp-oauth").json()
    assert metadata["issuer"] == "https://jtzhzt.flipbeltchina.com/test-api/mcp-oauth"
    registered = register(oauth)
    response = authorize(oauth, registered, resource=settings.agent_mcp_public_url)
    assert response.headers["location"].startswith(
        "https://jtzhzt.flipbeltchina.com/test/agent/oauth?"
    )


def test_bounded_requests_repeated_form_parameters_and_rate_limit(actors, oauth):
    response = oauth.post(
        "/mcp-oauth/register", content=b"x" * 16385, headers={"content-type": "application/json"}
    )
    assert response.status_code == 413
    response = oauth.post(
        "/mcp-oauth/token",
        content="client_id=one&client_id=two",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 400
    _buckets.clear()
    for _ in range(10):
        assert (
            oauth.post("/mcp-oauth/register", json={"redirect_uris": [CALLBACK]}).status_code == 201
        )
    assert oauth.post("/mcp-oauth/register", json={"redirect_uris": [CALLBACK]}).status_code == 429


def test_feature_flag_and_secure_configuration(actors, oauth, monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_mcp_enabled", False)
    assert oauth.get("/.well-known/oauth-authorization-server").status_code == 404
    with pytest.raises(ValueError):
        Settings(_env_file=None, agent_mcp_enabled=True)
    with pytest.raises(ValueError):
        Settings(_env_file=None, agent_mcp_public_url="https://user:password@example.invalid/mcp")


def test_oauth_query_log_redaction():
    guard = AuthQueryRedaction()
    for name, args in [
        (
            "uvicorn.access",
            ("127.0.0.1", "GET", "/mcp-oauth/authorize?state=PRIVATE&code=SECRET", "1.1", 302),
        ),
        ("uvicorn.access", ("127.0.0.1", "GET", "/agent/oauth?request_token=SECRET", "1.1", 200)),
        (
            "httpx",
            ("GET", "http://127.0.0.1:123/callback?code=SECRET&state=PRIVATE", "1.1", 302, "Found"),
        ),
    ]:
        record = logging.LogRecord(name, logging.INFO, __file__, 0, "", args, None)
        assert guard.filter(record)
        assert "SECRET" not in str(record.args) and "PRIVATE" not in str(record.args)


@pytest.mark.parametrize("revocation", ["refresh_reuse", "manual"])
def test_family_revocation_serializes_with_inflight_rotation(
    actors, oauth, monkeypatch, revocation
):
    """G1->G2 must not escape a concurrent old-G0 replay or human revocation."""
    registered, original = tokens(oauth, actors)
    base = {
        "grant_type": "refresh_token",
        "client_id": registered["client_id"],
        "resource": RESOURCE,
    }
    rotated = oauth.post(
        "/mcp-oauth/token", data=base | {"refresh_token": original["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    current = rotated.json()
    with SessionLocal() as db:
        family = db.scalar(
            select(McpOAuthGrant.family_id).where(
                McpOAuthGrant.token_hash == digest(current["access_token"])
            )
        )
    inserted, release, revoker_started = threading.Event(), threading.Event(), threading.Event()
    state = {}
    real_issue = oauth_core.issue

    def pause_after_insert(*args, **kwargs):
        result = real_issue(*args, **kwargs)
        inserted.set()
        assert release.wait(8), "Test did not release the rotating transaction"
        return result

    monkeypatch.setattr(oauth_core, "issue", pause_after_insert)

    def rotation():
        with SessionLocal() as db:
            client = oauth_core.load_client(db, registered["client_id"])
            return oauth_core.refresh(
                db, client, base | {"refresh_token": current["refresh_token"]}
            )

    def revoker():
        with SessionLocal() as db:
            client = oauth_core.load_client(db, registered["client_id"])
            state["pid"] = db.scalar(text("SELECT pg_backend_pid()"))
            revoker_started.set()
            if revocation == "manual":
                oauth_core.revoke_family(db, family)
                db.commit()
                return "revoked"
            try:
                oauth_core.refresh(db, client, base | {"refresh_token": original["refresh_token"]})
            except oauth_core.OAuthError as exc:
                return exc.error
            raise AssertionError("A replayed refresh token unexpectedly succeeded")

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(rotation)
        second = None
        try:
            assert inserted.wait(5), "Rotation did not create its uncommitted G2"
            second = executor.submit(revoker)
            assert revoker_started.wait(5)
            # Two real mutating connections; a read-only observer proves the
            # revoker reaches the advisory lock before G2 becomes visible.
            deadline, waiting = time.monotonic() + 5, False
            with SessionLocal() as observer:
                while time.monotonic() < deadline:
                    row = observer.execute(
                        text(
                            "SELECT wait_event_type, wait_event "
                            "FROM pg_stat_activity WHERE pid=:pid"
                        ),
                        {"pid": state["pid"]},
                    ).first()
                    if row and row[0] == "Lock" and (row[1] or "").lower() == "advisory":
                        waiting = True
                        break
                    # Refresh PostgreSQL's transaction-local statistics snapshot.
                    observer.rollback()
                    time.sleep(0.01)
            assert waiting, "Revocation did not serialize on the stable family lock"
        finally:
            release.set()
        new_tokens = first.result(timeout=5)
        assert second is not None
        assert second.result(timeout=5) == (
            "revoked" if revocation == "manual" else "invalid_grant"
        )
    with SessionLocal() as db:
        rows = list(db.scalars(select(McpOAuthGrant).where(McpOAuthGrant.family_id == family)))
        assert len(rows) == 3 and all(row.revoked_at for row in rows)
    with pytest.raises(HTTPException) as invalid:
        machine_access(new_tokens["access_token"])
    assert invalid.value.status_code == 401
