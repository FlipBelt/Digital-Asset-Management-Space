import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select

from app.core.auth import token_hash
from app.core.auth_logging import AuthQueryRedaction
from app.core.config import Settings
from app.db.session import SessionLocal, engine
from app.main import app
from app.models import (
    AuditLog,
    Department,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    DingTalkWebLoginState,
    LegalEntity,
    Person,
    User,
    UserRoleScope,
    UserSession,
)
from app.services.dingtalk import DingTalkClient
from app.services.dingtalk_web_login import (
    consume_login_state,
    new_login_state,
    safe_login_return_path,
)


@pytest.fixture
def web_settings() -> Settings:
    return Settings(
        _env_file=None,
        app_env="local",
        session_cookie_name="web_login_test_session",
        session_secure_cookie=True,
        dingtalk_enabled=True,
        dingtalk_client_id="test-web-app",
        dingtalk_client_secret="test-only-secret",
        dingtalk_corp_id="test-corp",
        dingtalk_web_enabled=True,
        dingtalk_web_redirect_uri="https://asset.example/test-api/api/dingtalk/web/callback",
        dingtalk_web_frontend_url="https://asset.example/test/",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("dingtalk_web_redirect_uri", "https://evil.example/api/dingtalk/web/callback"),
        ("dingtalk_web_redirect_uri", "http://asset.example/api/dingtalk/web/callback"),
        (
            "dingtalk_web_redirect_uri",
            "https://asset.example/api/dingtalk/web/callback?token=secret",
        ),
        (
            "dingtalk_web_redirect_uri",
            "https://name:password@asset.example/api/dingtalk/web/callback",
        ),
        ("dingtalk_web_frontend_url", "https://asset.example/test/../"),
        ("dingtalk_web_frontend_url", "https://asset.example/test/%2e%2e/"),
        ("dingtalk_web_frontend_url", "https://asset.example/test/#fragment"),
        ("dingtalk_web_frontend_url", "https://asset.example/test"),
        ("session_secure_cookie", False),
    ],
)
def test_unsafe_web_configuration_is_rejected(web_settings, field, value):
    values = web_settings.model_dump()
    values[field] = value
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "value",
    [
        "//evil.example",
        "https://evil.example/",
        "/\\evil.example",
        "/../my",
        "/%2e%2e/my",
        "/%252e%252e/my",
        "/%2fevil.example",
        "/my?x=%0d%0aLocation:evil",
        "/login",
        "/api/dingtalk/web/callback",
        "/test/my",
        "not-a-route",
    ],
)
def test_unsafe_return_path_falls_back_to_personal_home(value):
    assert safe_login_return_path(value) == "/my"


def test_configuration_validation_errors_do_not_print_credentials(web_settings):
    values = web_settings.model_dump()
    values["dingtalk_web_frontend_url"] = "https://evil.example/"
    with pytest.raises(ValidationError) as failure:
        Settings(_env_file=None, **values)
    assert web_settings.dingtalk_client_secret not in str(failure.value)
    assert "input_value" not in str(failure.value)


def test_workspace_return_routes_preserved():
    assert safe_login_return_path("/my/bookmarks") == "/my/bookmarks"
    assert safe_login_return_path("/hudu") == "/hudu"
    assert (
        safe_login_return_path("/discover?category=workflows&q=AI")
        == "/discover?category=workflows&q=AI"
    )


def oauth_transport(settings, *, corp_id="test-corp", personal=None, mapping=None, detail=None):
    requests = []
    if personal is None:
        personal = {"unionId": "test-union", "nick": "Personal nickname"}
    if mapping is None:
        mapping = {"errcode": 0, "result": {"userid": "verified-corp-user"}}
    if detail is None:
        detail = {"userid": "verified-corp-user", "unionid": "test-union", "name": "Corporate name"}

    def handler(request):
        requests.append(request)
        path = request.url.path
        if path == "/v1.0/oauth2/userAccessToken":
            assert json.loads(request.content) == {
                "clientId": settings.dingtalk_client_id,
                "clientSecret": settings.dingtalk_client_secret,
                "code": "test-once-code",
                "grantType": "authorization_code",
            }
            return httpx.Response(200, json={"accessToken": "user-token", "corpId": corp_id})
        if path == "/v1.0/contact/users/me":
            assert request.headers["x-acs-dingtalk-access-token"] == "user-token"
            return httpx.Response(200, json=personal)
        if path == "/gettoken":
            return httpx.Response(200, json={"access_token": "organization-token"})
        if path == "/topapi/user/getbyunionid":
            assert request.url.params["access_token"] == "organization-token"
            assert json.loads(request.content) == {"unionid": "test-union"}
            return httpx.Response(200, json=mapping)
        if path == "/topapi/v2/user/get":
            assert request.url.params["access_token"] == "organization-token"
            assert json.loads(request.content)["userid"] == "verified-corp-user"
            return httpx.Response(200, json={"errcode": 0, "result": detail})
        raise AssertionError("Unexpected upstream endpoint")

    return httpx.MockTransport(handler), requests


def test_web_code_resolves_verified_corporate_profile(web_settings):
    transport, requests = oauth_transport(web_settings)
    with httpx.Client(transport=transport) as http:
        profile = DingTalkClient(web_settings, http).user_from_web_auth_code("test-once-code")
    assert profile["name"] == "Corporate name"
    assert profile["userid"] == "verified-corp-user"
    assert len(requests) == 5


@pytest.mark.parametrize("corp_id", ["other-corp", None, ""])
def test_wrong_or_missing_organization_never_queries_directory(web_settings, corp_id):
    transport, requests = oauth_transport(web_settings, corp_id=corp_id)
    with httpx.Client(transport=transport) as http, pytest.raises(HTTPException) as failure:
        DingTalkClient(web_settings, http).user_from_web_auth_code("test-once-code")
    assert failure.value.status_code == 403
    assert len(requests) == 1


@pytest.mark.parametrize(
    "kwargs,status",
    [
        ({"personal": {}}, 401),
        ({"mapping": {"errcode": 60121}}, 403),
        ({"mapping": {"errcode": "60121"}}, 403),
        ({"detail": {"userid": "verified-corp-user", "unionid": "different-union"}}, 403),
        ({"detail": {"userid": "different-user", "unionid": "test-union"}}, 403),
        ({"detail": []}, 502),
    ],
)
def test_incomplete_or_mismatched_identity_is_rejected(web_settings, kwargs, status):
    transport, _ = oauth_transport(web_settings, **kwargs)
    with httpx.Client(transport=transport) as http, pytest.raises(HTTPException) as failure:
        DingTalkClient(web_settings, http).user_from_web_auth_code("test-once-code")
    assert failure.value.status_code == status


def test_upstream_network_errors_do_not_expose_credentials(web_settings):
    def handler(request):
        raise httpx.ConnectError("private upstream details", request=request)

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        pytest.raises(HTTPException) as failure,
    ):
        DingTalkClient(web_settings, http).user_from_web_auth_code("test-once-code")
    assert failure.value.status_code == 502
    assert "private" not in str(failure.value.detail)
    assert web_settings.dingtalk_client_secret not in str(failure.value.detail)


def test_oauth_access_logs_keep_status_without_query_credentials():
    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        0,
        "%s - %s %s HTTP/%s %s",
        (
            "127.0.0.1",
            "GET",
            "/api/dingtalk/web/callback?authCode=private-code&state=private-state",
            "1.1",
            303,
        ),
        None,
    )
    assert AuthQueryRedaction().filter(record)
    assert "private" not in record.getMessage()
    assert "callback" in record.getMessage() and "303" in record.getMessage()
    upstream = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        0,
        "%s %s %s",
        (
            "GET",
            httpx.URL("https://oapi.dingtalk.com/gettoken?appsecret=private-secret&appkey=test"),
            200,
        ),
        None,
    )
    AuthQueryRedaction().filter(upstream)
    assert "private-secret" not in upstream.getMessage()
    assert "appkey=test" in upstream.getMessage()


@pytest.fixture
def browser(web_settings):
    # Integration cases may only use the existing isolated local PostgreSQL rehearsal.
    assert engine.url.host == "127.0.0.1" and engine.url.port == 55433
    with (
        patch("app.api.v1.dingtalk_web.get_settings", return_value=web_settings),
        patch("app.api.v1.sessions.get_settings", return_value=web_settings),
        patch("app.core.auth.get_settings", return_value=web_settings),
    ):
        client = TestClient(app, base_url="https://asset.example")
        states = []
        yield client, states
        with SessionLocal() as db:
            if states:
                db.execute(
                    delete(DingTalkWebLoginState).where(
                        DingTalkWebLoginState.state_hash.in_(
                            [token_hash(state) for state in states]
                        )
                    )
                )
                db.commit()
        client.close()


def begin(browser, next_path="/my/bookmarks"):
    client, states = browser
    response = client.get(
        "/api/dingtalk/web/authorize", params={"next": next_path}, follow_redirects=False
    )
    assert response.status_code == 302
    params = parse_qs(urlsplit(response.headers["location"]).query)
    state = params["state"][0]
    states.append(state)
    return state, response, params


@pytest.fixture
def corporate_profile():
    marker = uuid4().hex[:8]
    ding_user_id = f"web-employee-{marker}"
    department_id = str(950000000 + int(marker[:4], 16))
    with SessionLocal() as db:
        entity = LegalEntity(code=f"WEB{marker}", name="Web login integration fixture")
        db.add(entity)
        db.flush()
        department = Department(
            legal_entity_id=entity.id, code=f"WEB{marker}", name="Web login fixture department"
        )
        db.add(department)
        db.flush()
        db.add(
            DingTalkDepartmentLink(
                department_id=department.id, dingtalk_department_id=department_id
            )
        )
        db.commit()
        entity_id, local_department_id = entity.id, department.id
    profile = {
        "userid": ding_user_id,
        "unionid": f"union-{marker}",
        "name": "Verified fixture employee",
        "dept_id_list": [int(department_id)],
        "job_number": f"WEB-{marker}",
    }
    yield profile
    with SessionLocal() as db:
        local_profile = db.scalar(
            select(DingTalkPersonProfile).where(
                DingTalkPersonProfile.dingtalk_user_id == ding_user_id
            )
        )
        if local_profile is not None:
            user = db.scalar(select(User).where(User.person_id == local_profile.person_id))
            if user is not None:
                db.execute(delete(AuditLog).where(AuditLog.actor_user_id == user.id))
                db.execute(delete(UserSession).where(UserSession.user_id == user.id))
                db.execute(delete(UserRoleScope).where(UserRoleScope.user_id == user.id))
                db.delete(user)
                db.flush()
            person_id = local_profile.person_id
            db.delete(local_profile)
            db.flush()
            db.execute(delete(Person).where(Person.id == person_id))
        db.execute(
            delete(DingTalkDepartmentLink).where(
                DingTalkDepartmentLink.department_id == local_department_id
            )
        )
        db.execute(delete(Department).where(Department.id == local_department_id))
        db.execute(delete(LegalEntity).where(LegalEntity.id == entity_id))
        db.commit()


def test_web_configuration_contract_does_not_expose_secrets(browser):
    client, _ = browser
    response = client.get("/api/dingtalk/web/config")
    assert response.json() == {"enabled": True, "configured": True}
    assert response.headers["Cache-Control"] == "no-store"
    # Keep the old micro-app bootstrap contract unchanged.
    assert set(client.get("/api/dingtalk/config").json()) == {"corpId", "agentId", "configured"}


def test_disabled_web_login_does_not_create_a_challenge(browser, web_settings):
    client, _ = browser
    disabled = Settings(
        _env_file=None, **{**web_settings.model_dump(), "dingtalk_web_enabled": False}
    )
    with patch("app.api.v1.dingtalk_web.get_settings", return_value=disabled):
        assert client.get("/api/dingtalk/web/config").json() == {
            "enabled": False,
            "configured": False,
        }
        response = client.get("/api/dingtalk/web/authorize", follow_redirects=False)
    assert response.status_code == 303
    assert (
        response.headers["location"] == "https://asset.example/test/login?dingtalkError=unavailable"
    )
    assert client.get("/api/v1/sessions/current").status_code == 401


def test_request_host_cannot_replace_the_configured_callback(browser, web_settings):
    client, states = browser
    response = client.get(
        "/api/dingtalk/web/authorize",
        headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"},
        follow_redirects=False,
    )
    params = parse_qs(urlsplit(response.headers["location"]).query)
    states.append(params["state"][0])
    assert params["redirect_uri"] == [web_settings.dingtalk_web_redirect_uri]
    assert "evil.example" not in response.headers["location"]


def test_authorize_uses_trusted_callback_and_browser_bound_hashed_state(browser, web_settings):
    state, response, params = begin(browser, "//evil.example")
    assert params["redirect_uri"] == [web_settings.dingtalk_web_redirect_uri]
    assert params["corpId"] == [web_settings.dingtalk_corp_id]
    assert params["scope"] == ["openid corpid"]
    assert "test-only-secret" not in response.headers["location"]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "secure" in cookie
    assert "max-age=300" in cookie
    with SessionLocal() as db:
        row = db.scalar(
            select(DingTalkWebLoginState).where(
                DingTalkWebLoginState.state_hash == token_hash(state)
            )
        )
        assert row is not None and row.return_path == "/my"
        assert row.state_hash != state
        assert row.browser_hash != browser[0].cookies.get(
            web_settings.session_cookie_name + "_dingtalk_web"
        )


@pytest.mark.parametrize("kind", ["missing", "bad_state", "wrong_browser", "expired", "duplicate"])
def test_invalid_callback_never_exchanges_a_code(browser, web_settings, kind):
    client, _ = browser
    state, _, _ = begin(browser)
    params = {"state": state, "authCode": "private-test-code"}
    if kind == "missing":
        client.cookies.clear()
    elif kind == "bad_state":
        params["state"] = "bad-state"
    elif kind == "wrong_browser":
        client.cookies.set(
            web_settings.session_cookie_name + "_dingtalk_web",
            "x" * 43,
            domain="asset.example",
            path="/",
        )
    elif kind == "expired":
        with SessionLocal() as db:
            row = db.scalar(
                select(DingTalkWebLoginState).where(
                    DingTalkWebLoginState.state_hash == token_hash(state)
                )
            )
            row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
    elif kind == "duplicate":
        params = [("state", state), ("state", "other"), ("authCode", "private-test-code")]
    with patch("app.services.dingtalk.DingTalkClient.user_from_web_auth_code") as exchange:
        response = client.get("/api/dingtalk/web/callback", params=params, follow_redirects=False)
    exchange.assert_not_called()
    assert response.status_code == 303
    assert "dingtalkError=invalid_state" in response.headers["location"]
    assert "private-test-code" not in response.headers["location"]
    assert client.get("/api/v1/sessions/current").status_code == 401


def test_cancelled_oauth_consumes_challenge_without_creating_session(browser):
    client, _ = browser
    state, _, _ = begin(browser)
    with patch("app.services.dingtalk.DingTalkClient.user_from_web_auth_code") as exchange:
        response = client.get(
            "/api/dingtalk/web/callback",
            params={"state": state, "error": "access_denied"},
            follow_redirects=False,
        )
    exchange.assert_not_called()
    assert "dingtalkError=cancelled" in response.headers["location"]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(DingTalkWebLoginState.id).where(
                    DingTalkWebLoginState.state_hash == token_hash(state)
                )
            )
            is None
        )


def test_valid_scan_reuses_employee_mapping_sets_cookie_and_rejects_replay(
    browser, web_settings, corporate_profile
):
    client, _ = browser
    identities = []
    with patch(
        "app.services.dingtalk.DingTalkClient.user_from_web_auth_code",
        return_value=corporate_profile,
    ) as exchange:
        for _ in range(2):
            state, _, _ = begin(browser)
            browser_cookie = client.cookies.get(web_settings.session_cookie_name + "_dingtalk_web")
            response = client.get(
                "/api/dingtalk/web/callback",
                params={"state": state, "authCode": "private-test-code"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"].startswith(
                "https://asset.example/test/login?dingtalk=success"
            )
            assert "redirect=%2Fmy%2Fbookmarks" in response.headers["location"]
            assert response.headers["Referrer-Policy"] == "no-referrer"
            assert "private-test-code" not in response.headers["location"]
            assert "session_token" not in response.headers["location"]
            current = client.get("/api/v1/sessions/current")
            assert current.status_code == 200, current.text
            assert current.json()["display_name"] == corporate_profile["name"]
            assert current.json()["person_id"]
            identities.append(current.json()["id"])
            calls = exchange.call_count
            replay = client.get(
                "/api/dingtalk/web/callback",
                params={"state": state, "authCode": "private-test-code"},
                headers={
                    "Cookie": web_settings.session_cookie_name + "_dingtalk_web=" + browser_cookie
                },
                follow_redirects=False,
            )
            assert "dingtalkError=invalid_state" in replay.headers["location"]
            assert exchange.call_count == calls
    assert identities[0] == identities[1]
    with SessionLocal() as db:
        assert (
            len(
                list(
                    db.scalars(
                        select(DingTalkPersonProfile).where(
                            DingTalkPersonProfile.dingtalk_user_id == corporate_profile["userid"]
                        )
                    )
                )
            )
            == 1
        )
        assert (
            len(
                list(
                    db.scalars(
                        select(AuditLog).where(
                            AuditLog.actor_user_id == identities[0],
                            AuditLog.action == "session.dingtalk_web_login",
                        )
                    )
                )
            )
            == 2
        )
    # Browser cookie writes still require a CSRF token.
    assert client.delete("/api/v1/sessions/current").status_code == 403
    csrf = client.get("/api/v1/sessions/current").json()["csrf_token"]
    assert (
        client.delete("/api/v1/sessions/current", headers={"X-CSRF-Token": csrf}).status_code == 204
    )


def test_unsynchronized_employee_cannot_create_an_account(browser):
    client, _ = browser
    state, _, _ = begin(browser)
    profile = {
        "userid": f"unknown-web-{uuid4().hex}",
        "name": "Unknown employee",
        "dept_id_list": [],
    }
    with patch(
        "app.services.dingtalk.DingTalkClient.user_from_web_auth_code", return_value=profile
    ):
        response = client.get(
            "/api/dingtalk/web/callback",
            params={"state": state, "authCode": "test-code"},
            follow_redirects=False,
        )
    assert "dingtalkError=access_denied" in response.headers["location"]
    with SessionLocal() as db:
        assert (
            db.scalar(select(User.id).where(User.username == "dingtalk:" + profile["userid"]))
            is None
        )


def test_inactive_employee_cannot_get_a_new_session(browser, corporate_profile):
    client, _ = browser
    with patch(
        "app.services.dingtalk.DingTalkClient.user_from_web_auth_code",
        return_value=corporate_profile,
    ):
        state, _, _ = begin(browser)
        first = client.get(
            "/api/dingtalk/web/callback",
            params={"state": state, "authCode": "first-code"},
            follow_redirects=False,
        )
        assert "dingtalk=success" in first.headers["location"]
        user_id = client.get("/api/v1/sessions/current").json()["id"]
        with SessionLocal() as db:
            user = db.get(User, user_id)
            user.is_active = False
            db.execute(delete(UserSession).where(UserSession.user_id == user.id))
            db.commit()
        client.cookies.clear()
        state, _, _ = begin(browser)
        denied = client.get(
            "/api/dingtalk/web/callback",
            params={"state": state, "authCode": "second-code"},
            follow_redirects=False,
        )
        assert "dingtalkError=access_denied" in denied.headers["location"]
        assert client.get("/api/v1/sessions/current").status_code == 401
        with SessionLocal() as db:
            assert db.scalar(select(UserSession.id).where(UserSession.user_id == user_id)) is None


def test_login_state_can_only_be_consumed_once_across_concurrent_connections(browser):
    assert engine.url.host == "127.0.0.1" and engine.url.port == 55433
    with SessionLocal() as db:
        state, nonce = new_login_state(db, "/my/subscriptions")
    browser[1].append(state)

    def consume():
        with SessionLocal() as db:
            return consume_login_state(db, state, nonce)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: consume(), range(2)))
    assert results.count("/my/subscriptions") == 1
    assert results.count(None) == 1
