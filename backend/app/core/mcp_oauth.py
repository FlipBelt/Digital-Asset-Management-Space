"""Persistent, resource-bound OAuth for remote MCP; no browser credential fallback."""

import base64
import binascii
import hashlib
import hmac
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode, urlsplit
from uuid import uuid4

from fastapi import HTTPException, Request
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.core.access import AccessContext
from app.core.agent_auth import SCOPES, digest, employee_access, now, throttle
from app.core.config import get_settings
from app.models import AuditLog, McpOAuthClient, McpOAuthGrant, McpOAuthRequest, User
from app.schemas.mcp_oauth import ClientRegistration

QWEN_REDIRECT = "qwenwork-cn://mcp-oauth"
BUSINESS_SCOPES = frozenset(SCOPES)
CLIENT_IDENTITY_NOTE = "客户端名称由申请方自行填写，未经企业身份认证；只允许你本人发起的连接。"


class OAuthError(Exception):
    def __init__(self, error: str, description: str, status: int = 400):
        self.error, self.description, self.status = error, description, status
        super().__init__(description)


def enabled():
    settings = get_settings()
    if not (
        settings.agent_mcp_enabled
        and settings.agent_connector_enabled
        and settings.agent_mcp_public_url
        and settings.agent_frontend_url
    ):
        raise HTTPException(404, "远程 MCP 尚未启用")


def resource_url() -> str:
    enabled()
    return get_settings().agent_mcp_public_url


def issuer_url() -> str:
    return resource_url().removesuffix("/mcp") + "/mcp-oauth"


def resource_metadata_url() -> str:
    parsed = urlsplit(resource_url())
    return f"{parsed.scheme}://{parsed.netloc}/.well-known/oauth-protected-resource{parsed.path}"


def audit(db, user_id, action, object_id):
    db.add(
        AuditLog(
            actor_user_id=user_id,
            action="mcp_oauth." + action,
            object_type="mcp_oauth",
            object_id=object_id,
            after_data={"source": "remote_mcp"},
        )
    )


def scopes(value: str, allowed=BUSINESS_SCOPES) -> list[str]:
    if not isinstance(value, str) or len(value) > 200 or not value.strip():
        raise OAuthError("invalid_scope", "A nonempty business scope is required")
    items = value.split(" ")
    if (
        any(not item for item in items)
        or len(set(items)) != len(items)
        or not set(items) <= set(allowed)
    ):
        raise OAuthError("invalid_scope", "Unsupported or repeated scope")
    return items


def qwen_compatibility(client, redirect_uri):
    return (
        client.client_name in {"QwenWork", "QoderWork"}
        and redirect_uri == QWEN_REDIRECT
        and client.redirect_uris == [QWEN_REDIRECT]
        and client.auth_method == "none"
        and client.application_type in {None, "native"}
        and set(client.grant_types) == {"authorization_code", "refresh_token"}
    )


def valid_redirect(uri: str, client_name: str) -> bool:
    if not isinstance(uri, str) or len(uri) > 2000:
        return False
    if any(ord(c) < 33 or ord(c) == 127 for c in uri) or "\\" in uri or "%" in uri:
        return False
    if uri == QWEN_REDIRECT:
        return client_name in {"QwenWork", "QoderWork"}
    try:
        parsed = urlsplit(uri)
        if (
            not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(part in {".", ".."} for part in parsed.path.split("/"))
        ):
            return False
        port = parsed.port
        if parsed.scheme == "http":
            return (
                parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                and port is not None
                and 1 <= port <= 65535
                and parsed.path == "/callback"
            )
        if parsed.scheme != "https":
            return False
        if parsed.hostname == "chatgpt.com" and port in {None, 443}:
            return parsed.path == "/connector_platform_oauth_redirect"
        return uri in get_settings().agent_mcp_allowed_redirect_uris
    except ValueError:
        return False


def load_client(db: Session, identity: str) -> McpOAuthClient:
    if not isinstance(identity, str) or not re.fullmatch(r"mcl_[A-Za-z0-9_-]{43}", identity):
        raise OAuthError("invalid_client", "Invalid client", 401)
    client = db.scalar(select(McpOAuthClient).where(McpOAuthClient.client_id == identity))
    if client is None or client.revoked_at:
        raise OAuthError("invalid_client", "Invalid client", 401)
    return client


def register_client(db: Session, payload: ClientRegistration):
    if (
        not payload.client_name.strip()
        or any(ord(c) < 32 or ord(c) == 127 for c in payload.client_name)
        or len(set(payload.redirect_uris)) != len(payload.redirect_uris)
        or not all(valid_redirect(uri, payload.client_name) for uri in payload.redirect_uris)
        or payload.response_types != ["code"]
        or "authorization_code" not in payload.grant_types
        or len(set(payload.grant_types)) != len(payload.grant_types)
        or not set(payload.grant_types) <= {"authorization_code", "refresh_token"}
    ):
        raise OAuthError("invalid_client_metadata", "Unsupported client metadata or callback")
    if QWEN_REDIRECT in payload.redirect_uris and not (
        payload.client_name in {"QwenWork", "QoderWork"}
        and payload.redirect_uris == [QWEN_REDIRECT]
        and payload.token_endpoint_auth_method == "none"
        and payload.application_type in {None, "native"}
        and set(payload.grant_types) == {"authorization_code", "refresh_token"}
    ):
        raise OAuthError("invalid_client_metadata", "Unsupported native client registration")
    allowed_scopes = list(SCOPES) if payload.scope is None else scopes(payload.scope)
    secret = secrets.token_urlsafe(32) if payload.token_endpoint_auth_method != "none" else None
    client = McpOAuthClient(
        client_id="mcl_" + secrets.token_urlsafe(32),
        client_name=payload.client_name,
        redirect_uris=payload.redirect_uris,
        scopes=allowed_scopes,
        grant_types=payload.grant_types,
        auth_method=payload.token_endpoint_auth_method,
        application_type=payload.application_type,
        secret_hash=digest(secret) if secret else None,
    )
    db.add(client)
    db.commit()
    result = {
        "client_id": client.client_id,
        "client_name": client.client_name,
        "redirect_uris": client.redirect_uris,
        "scope": " ".join(client.scopes),
        "grant_types": client.grant_types,
        "response_types": ["code"],
        "token_endpoint_auth_method": client.auth_method,
        "client_id_issued_at": int(client.created_at.timestamp()),
    }
    if secret:
        result.update(client_secret=secret, client_secret_expires_at=0)
    return result


def redirect_for(client, params):
    redirect = params.get("redirect_uri")
    if redirect not in client.redirect_uris or not valid_redirect(redirect, client.client_name):
        raise OAuthError("invalid_request", "Callback is not registered")
    return redirect


def checked_state(params):
    value = params.get("state", "")
    if not value or len(value) > 1024 or any(ord(c) < 33 or ord(c) == 127 for c in value):
        raise OAuthError("invalid_request", "A nonempty state is required")
    return value


def bound_resource(params, client, redirect):
    if "resource" not in params:
        if qwen_compatibility(client, redirect) and "scope" not in params:
            return resource_url()
        raise OAuthError("invalid_target", "The MCP resource is required")
    if params["resource"] != resource_url():
        raise OAuthError("invalid_target", "Invalid MCP resource")
    return params["resource"]


def create_authorization(db: Session, params: dict[str, str]):
    client = load_client(db, params.get("client_id"))
    redirect = redirect_for(client, params)
    state = checked_state(params)
    if params.get("response_type") != "code":
        raise OAuthError("unsupported_response_type", "Only authorization code is supported")
    if params.get("code_challenge_method") != "S256" or not re.fullmatch(
        r"[A-Za-z0-9_-]{43}", params.get("code_challenge", "")
    ):
        raise OAuthError("invalid_request", "PKCE S256 is required")
    resource = bound_resource(params, client, redirect)
    if "scope" not in params:
        if not qwen_compatibility(client, redirect) or "resource" in params:
            raise OAuthError("invalid_scope", "Business scopes are required")
        selected_scopes = list(SCOPES)
        if not set(selected_scopes) <= set(client.scopes):
            raise OAuthError("invalid_scope", "Client is not registered for these scopes")
    else:
        selected_scopes = scopes(params["scope"], client.scopes)
    token = "mrq_" + secrets.token_urlsafe(32)
    db.add(
        McpOAuthRequest(
            request_hash=digest(token),
            client_id=client.id,
            redirect_uri=redirect,
            state=state,
            code_challenge=params["code_challenge"],
            scopes=selected_scopes,
            resource=resource,
            issuer=issuer_url(),
            expires_at=now() + timedelta(minutes=10),
        )
    )
    db.commit()
    return token


def callback(uri: str, state: str, **values):
    # Callback URLs are exact registered URLs with no preexisting query/fragment.
    return uri + "?" + urlencode({**values, "state": state, "iss": issuer_url()})


def authorization_error_redirect(db, params, error: OAuthError):
    try:
        client = load_client(db, params.get("client_id"))
        redirect = redirect_for(client, params)
        state = checked_state(params)
    except OAuthError:
        return None
    return callback(redirect, state, error=error.error, error_description=error.description)


def pending_request(db, token, user_id, *, require_preview=False):
    item = db.scalar(
        select(McpOAuthRequest)
        .where(McpOAuthRequest.request_hash == digest(token))
        .with_for_update()
    )
    if (
        item is None
        or item.expires_at <= now()
        or item.approved_at
        or item.denied_at
        or item.issuer != issuer_url()
        or item.resource != resource_url()
    ):
        raise HTTPException(404, "授权请求不存在、已处理或已失效")
    if item.user_id is not None and item.user_id != user_id:
        raise HTTPException(403, "请使用预览此次请求的同一账号")
    if require_preview and item.user_id is None:
        raise HTTPException(409, "请先预览授权请求")
    return item


def preview(db, token, access):
    employee_access(db, access.user)
    item = pending_request(db, token, access.user.id)
    client = db.get(McpOAuthClient, item.client_id)
    if client is None or client.revoked_at:
        raise HTTPException(404, "客户端请求已失效")
    item.user_id = access.user.id
    db.commit()
    return {
        "client_name": client.client_name,
        "client_identity_note": CLIENT_IDENTITY_NOTE,
        "scopes": item.scopes,
        "resource": item.resource,
        "expires_at": item.expires_at,
        "expires_in_seconds": max(0, int((item.expires_at - now()).total_seconds())),
    }


def approve(db, token, approved, access):
    employee_access(db, access.user)
    item = pending_request(db, token, access.user.id, require_preview=True)
    client = db.get(McpOAuthClient, item.client_id)
    if (
        client is None
        or client.revoked_at
        or not valid_redirect(item.redirect_uri, client.client_name)
    ):
        raise HTTPException(404, "客户端请求已失效")
    if approved:
        code = "mcd_" + secrets.token_urlsafe(32)
        item.code_hash, item.approved_at = digest(code), now()
        item.code_expires_at = now() + timedelta(seconds=120)
        destination = callback(item.redirect_uri, item.state, code=code)
    else:
        item.denied_at = now()
        destination = callback(item.redirect_uri, item.state, error="access_denied")
    audit(db, access.user.id, "authorize" if approved else "deny", item.id)
    db.commit()
    return {"redirect_url": destination}


def authenticate_client(db, params, request):
    identity, secret = params.get("client_id"), params.get("client_secret")
    headers = request.headers.getlist("authorization")
    if len(headers) > 1:
        raise OAuthError("invalid_client", "Invalid client authentication", 401)
    basic = False
    if headers:
        try:
            scheme, encoded = headers[0].split(" ", 1)
            if scheme.lower() != "basic" or "client_secret" in params:
                raise ValueError
            from urllib.parse import unquote

            header_identity, secret = (
                base64.b64decode(encoded, validate=True).decode("utf-8").split(":", 1)
            )
            header_identity, secret = unquote(header_identity), unquote(secret)
            if identity is not None and identity != header_identity:
                raise ValueError
            identity, basic = header_identity, True
        except (ValueError, UnicodeDecodeError, binascii.Error) as exc:
            raise OAuthError("invalid_client", "Invalid client authentication", 401) from exc
    client = load_client(db, identity)
    if client.auth_method == "none":
        valid = not basic and "client_secret" not in params
    else:
        expected_basic = client.auth_method == "client_secret_basic"
        valid = (
            basic == expected_basic
            and isinstance(secret, str)
            and bool(secret)
            and hmac.compare_digest(digest(secret), client.secret_hash or "")
        )
    if not valid:
        raise OAuthError("invalid_client", "Invalid client authentication", 401)
    return client


def live_employee(db, user_id):
    user = db.get(User, user_id)
    if user is None:
        raise OAuthError("invalid_grant", "Authorization is no longer valid")
    try:
        return employee_access(db, user)
    except HTTPException as exc:
        raise OAuthError("invalid_grant", "Authorization is no longer valid") from exc


def issue(
    db, client, user_id, selected_scopes, resource, redirect, *, family=None, refresh_expires=None
):
    access_token = "mcp_" + secrets.token_urlsafe(48)
    refresh_token = (
        "mrf_" + secrets.token_urlsafe(48) if "refresh_token" in client.grant_types else None
    )
    settings = get_settings()
    expiry = now() + timedelta(seconds=settings.agent_mcp_access_token_ttl_seconds)
    refresh_expiry = (
        (refresh_expires or now() + timedelta(days=settings.agent_mcp_refresh_token_ttl_days))
        if refresh_token
        else None
    )
    grant = McpOAuthGrant(
        client_id=client.id,
        user_id=user_id,
        family_id=family or uuid4(),
        token_hash=digest(access_token),
        refresh_hash=digest(refresh_token) if refresh_token else None,
        scopes=selected_scopes,
        resource=resource,
        issuer=issuer_url(),
        redirect_uri=redirect,
        expires_at=expiry,
        refresh_expires_at=refresh_expiry,
    )
    db.add(grant)
    db.flush()
    audit(db, user_id, "token", grant.id)
    result = {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": settings.agent_mcp_access_token_ttl_seconds,
        "scope": " ".join(selected_scopes),
    }
    if refresh_token:
        result["refresh_token"] = refresh_token
    return result


def exchange_code(db, client, params):
    if "authorization_code" not in client.grant_types:
        raise OAuthError("unauthorized_client", "Grant type is not registered")
    code, verifier = params.get("code", ""), params.get("code_verifier", "")
    if not re.fullmatch(r"mcd_[A-Za-z0-9_-]{43}", code) or not re.fullmatch(
        r"[A-Za-z0-9._~-]{43,128}", verifier
    ):
        raise OAuthError("invalid_grant", "Invalid authorization code or verifier")
    item = db.scalar(
        select(McpOAuthRequest).where(McpOAuthRequest.code_hash == digest(code)).with_for_update()
    )
    if (
        item is None
        or item.client_id != client.id
        or not item.approved_at
        or item.consumed_at
        or item.denied_at
        or not item.code_expires_at
        or item.code_expires_at <= now()
        or item.issuer != issuer_url()
        or item.resource != resource_url()
        or params.get("redirect_uri") != item.redirect_uri
    ):
        raise OAuthError("invalid_grant", "Authorization code is invalid or expired")
    requested = bound_resource(params, client, item.redirect_uri)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    )
    if not hmac.compare_digest(challenge, item.code_challenge):
        raise OAuthError("invalid_grant", "Invalid authorization code or verifier")
    if "scope" in params and set(scopes(params["scope"], item.scopes)) != set(item.scopes):
        raise OAuthError("invalid_scope", "Authorization code scopes cannot change")
    live_employee(db, item.user_id)
    item.consumed_at = now()
    result = issue(db, client, item.user_id, item.scopes, requested, item.redirect_uri)
    db.commit()
    return result


def lock_family(db, family):
    # All family mutations take this lock before any grant row lock. The following
    # statement gets a fresh READ COMMITTED snapshot including completed rotations.
    key = int.from_bytes(hashlib.sha256(b"mcp-oauth:" + family.bytes).digest()[:8], signed=True)
    db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": key})


def revoke_family(db, family):
    lock_family(db, family)
    db.execute(
        update(McpOAuthGrant)
        .where(McpOAuthGrant.family_id == family, McpOAuthGrant.revoked_at.is_(None))
        .values(revoked_at=now())
    )


def refresh(db, client, params):
    raw = params.get("refresh_token", "")
    if "refresh_token" not in client.grant_types or not re.fullmatch(r"mrf_[A-Za-z0-9_-]{64}", raw):
        raise OAuthError("invalid_grant", "Invalid refresh token")
    family = db.scalar(
        select(McpOAuthGrant.family_id).where(
            McpOAuthGrant.refresh_hash == digest(raw), McpOAuthGrant.client_id == client.id
        )
    )
    if family is None:
        raise OAuthError("invalid_grant", "Invalid refresh token")
    lock_family(db, family)
    grant = db.scalar(
        select(McpOAuthGrant)
        .where(McpOAuthGrant.refresh_hash == digest(raw), McpOAuthGrant.client_id == client.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if grant is None:
        raise OAuthError("invalid_grant", "Invalid refresh token")
    if grant.rotated_at:
        revoke_family(db, grant.family_id)
        audit(db, grant.user_id, "refresh_reuse", grant.id)
        db.commit()
        raise OAuthError("invalid_grant", "Refresh token was already used; reconnect")
    if (
        grant.revoked_at
        or not grant.refresh_expires_at
        or grant.refresh_expires_at <= now()
        or grant.issuer != issuer_url()
        or grant.resource != resource_url()
    ):
        raise OAuthError("invalid_grant", "Refresh authorization is no longer valid")
    requested = bound_resource(params, client, grant.redirect_uri)
    selected_scopes = (
        grant.scopes if "scope" not in params else scopes(params["scope"], grant.scopes)
    )
    live_employee(db, grant.user_id)
    grant.rotated_at = grant.revoked_at = now()
    result = issue(
        db,
        client,
        grant.user_id,
        selected_scopes,
        requested,
        grant.redirect_uri,
        family=grant.family_id,
        refresh_expires=grant.refresh_expires_at,
    )
    db.commit()
    return result


def mcp_access(request: Request, db: Session, required_scopes: set[str]) -> AccessContext:
    enabled()
    challenge = f'Bearer resource_metadata="{resource_metadata_url()}"'
    headers = request.headers.getlist("authorization")
    raw = headers[0] if len(headers) == 1 else ""
    if not raw.startswith("Bearer mcp_") or len(raw) > 200:
        raise HTTPException(
            401, "请通过 OAuth 连接远程 MCP", headers={"WWW-Authenticate": challenge}
        )
    grant = db.scalar(select(McpOAuthGrant).where(McpOAuthGrant.token_hash == digest(raw[7:])))
    if (
        grant is None
        or grant.revoked_at
        or grant.expires_at <= now()
        or grant.issuer != issuer_url()
        or grant.resource != resource_url()
    ):
        raise HTTPException(401, "远程授权已失效", headers={"WWW-Authenticate": challenge})
    client = db.get(McpOAuthClient, grant.client_id)
    user = db.get(User, grant.user_id)
    if client is None or client.revoked_at or user is None:
        raise HTTPException(401, "远程授权已失效", headers={"WWW-Authenticate": challenge})
    if (
        not set(grant.scopes) <= BUSINESS_SCOPES
        or not set(grant.scopes) <= set(client.scopes)
        or not required_scopes <= set(grant.scopes)
    ):
        raise HTTPException(
            403,
            "授权范围不足",
            headers={"WWW-Authenticate": challenge + ', error="insufficient_scope"'},
        )
    access = employee_access(db, user)
    throttle(f"mcp:{grant.id}", 120, 60)
    request.state.mcp_scopes = frozenset(grant.scopes)
    request.state.mcp_grant_id = grant.id
    request.state.mcp_client_id = client.client_id
    return access
