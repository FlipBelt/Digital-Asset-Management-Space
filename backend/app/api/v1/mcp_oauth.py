"""OAuth endpoints plus first-party, CSRF-protected human consent."""

import asyncio
import json
import re
from urllib.parse import parse_qsl, urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.access import AccessContext, get_access_context
from app.core.agent_auth import digest, employee_access, frontend_url, now, throttle
from app.core.auth import require_csrf
from app.core.mcp_oauth import (
    BUSINESS_SCOPES,
    OAuthError,
    approve,
    audit,
    authenticate_client,
    authorization_error_redirect,
    create_authorization,
    enabled,
    exchange_code,
    issuer_url,
    preview,
    refresh,
    register_client,
    resource_url,
    revoke_family,
)
from app.db.session import get_db
from app.models import McpOAuthClient, McpOAuthGrant, McpOAuthRequest
from app.schemas.mcp_oauth import ApproveInput, ClientRegistration, PreviewInput

router = APIRouter(tags=["remote-mcp-oauth"], dependencies=[Depends(enabled)])
web_router = APIRouter(
    prefix="/api/v1/agent/oauth", tags=["remote-mcp-consent"], dependencies=[Depends(enabled)]
)
PRIVATE = {"Cache-Control": "no-store", "Pragma": "no-cache", "Referrer-Policy": "no-referrer"}
MAX_BODY = 16_384


def failure(error):
    return JSONResponse(
        {"error": error.error, "error_description": error.description},
        status_code=error.status,
        headers=PRIVATE,
    )


def throttle_public(request, operation, maximum):
    host = request.client.host if request.client else "unknown"
    throttle(f"mcp-oauth:{operation}:{digest(host)}", maximum, 60)


async def body(request):
    try:
        length = int(request.headers.get("content-length", "0"))
    except ValueError as exc:
        raise OAuthError("invalid_request", "Invalid request size") from exc
    if length < 0 or length > MAX_BODY:
        raise OAuthError("invalid_request", "Request body is too large", 413)
    parts, total = [], 0
    try:
        async with asyncio.timeout(10):
            async for chunk in request.stream():
                total += len(chunk)
                if total > MAX_BODY:
                    raise OAuthError("invalid_request", "Request body is too large", 413)
                parts.append(chunk)
    except TimeoutError as exc:
        raise OAuthError("invalid_request", "Request body timed out", 408) from exc
    try:
        return b"".join(parts).decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OAuthError("invalid_request", "Request must use UTF-8") from exc


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise OAuthError("invalid_request", "Repeated request parameter")
        result[key] = value
    return result


def encoded_parameters(value):
    if re.search(r"%(?![0-9A-Fa-f]{2})", value):
        raise OAuthError("invalid_request", "Invalid form encoding")
    try:
        return unique_pairs(
            parse_qsl(
                value,
                keep_blank_values=True,
                strict_parsing=True,
                encoding="utf-8",
                errors="strict",
                max_num_fields=30,
            )
        )
    except (ValueError, UnicodeDecodeError) as exc:
        raise OAuthError("invalid_request", "Invalid request parameters") from exc


async def form(request):
    if (
        request.headers.get("content-type", "").split(";")[0].strip().lower()
        != "application/x-www-form-urlencoded"
    ):
        raise OAuthError("invalid_request", "Use application/x-www-form-urlencoded", 415)
    return encoded_parameters(await body(request))


async def json_input(request, model):
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise OAuthError("invalid_request", "Use application/json", 415)
    try:
        data = json.loads(await body(request), object_pairs_hook=unique_pairs)
        return model.model_validate(data)
    except (ValueError, ValidationError) as exc:
        raise OAuthError("invalid_request", "Invalid request fields") from exc


def authorization_metadata():
    issuer = issuer_url()
    return {
        "issuer": issuer,
        "authorization_endpoint": issuer + "/authorize",
        "token_endpoint": issuer + "/token",
        "registration_endpoint": issuer + "/register",
        "revocation_endpoint": issuer + "/revoke",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_post",
            "client_secret_basic",
        ],
        "revocation_endpoint_auth_methods_supported": [
            "none",
            "client_secret_post",
            "client_secret_basic",
        ],
        "scopes_supported": sorted(BUSINESS_SCOPES),
        "authorization_response_iss_parameter_supported": True,
    }


def register_result(db, payload):
    if (
        db.scalar(
            select(func.count())
            .select_from(McpOAuthClient)
            .where(McpOAuthClient.revoked_at.is_(None))
        )
        >= 1000
    ):
        raise OAuthError("temporarily_unavailable", "Registration limit reached", 429)
    return register_client(db, payload)


def token_result(db, params, request):
    client = authenticate_client(db, params, request)
    if params.get("grant_type") == "authorization_code":
        if "refresh_token" in params:
            raise OAuthError("invalid_request", "Unexpected refresh token")
        return exchange_code(db, client, params)
    if params.get("grant_type") == "refresh_token":
        if set(params) & {"code", "code_verifier", "redirect_uri"}:
            raise OAuthError("invalid_request", "Unexpected authorization code parameter")
        return refresh(db, client, params)
    raise OAuthError("unsupported_grant_type", "Unsupported grant type")


def revoke_result(db, params, request):
    client = authenticate_client(db, params, request)
    checksum = digest(params["token"])
    grant = db.scalar(
        select(McpOAuthGrant).where(
            McpOAuthGrant.client_id == client.id,
            (McpOAuthGrant.token_hash == checksum) | (McpOAuthGrant.refresh_hash == checksum),
        )
    )
    if grant:
        revoke_family(db, grant.family_id)
        audit(db, grant.user_id, "revoke", grant.id)
        db.commit()
    return {}


@router.get("/.well-known/oauth-authorization-server")
@router.get("/.well-known/oauth-authorization-server/{path:path}")
@router.get("/mcp-oauth/.well-known/oauth-authorization-server")
def authorization_discovery(path: str = ""):
    if path not in {"", "mcp-oauth", urlsplit(issuer_url()).path.lstrip("/")}:
        raise HTTPException(404, "Unknown authorization server")
    return JSONResponse(authorization_metadata(), headers=PRIVATE)


@router.get("/.well-known/oauth-protected-resource")
@router.get("/.well-known/oauth-protected-resource/{path:path}")
def resource_discovery(path: str = ""):
    if path not in {"", "mcp", urlsplit(resource_url()).path.lstrip("/")}:
        raise HTTPException(404, "Unknown MCP resource")
    return JSONResponse(
        {
            "resource": resource_url(),
            "authorization_servers": [issuer_url()],
            "scopes_supported": sorted(BUSINESS_SCOPES),
            "bearer_methods_supported": ["header"],
            "resource_name": "FlipBelt AI Asset Center",
        },
        headers=PRIVATE,
    )


@router.post("/mcp-oauth/register")
async def register(request: Request, db: Session = Depends(get_db)):
    throttle_public(request, "register", 10)
    try:
        payload = await json_input(request, ClientRegistration)
        result = await run_in_threadpool(register_result, db, payload)
        return JSONResponse(result, status_code=201, headers=PRIVATE)
    except OAuthError as exc:
        return failure(exc)


@router.get("/mcp-oauth/authorize")
def authorize(request: Request, db: Session = Depends(get_db)):
    throttle_public(request, "authorize", 30)
    params = {}
    try:
        if len(request.url.query) > 8192:
            raise OAuthError("invalid_request", "Request query is too large", 414)
        params = encoded_parameters(request.url.query)
        allowed = {
            "client_id",
            "redirect_uri",
            "response_type",
            "state",
            "scope",
            "resource",
            "code_challenge",
            "code_challenge_method",
        }
        # RFC 6749 section 3.1: ignore extensions after strict parsing and deduplication.
        params = {key: value for key, value in params.items() if key in allowed}
        if (
            db.scalar(
                select(func.count())
                .select_from(McpOAuthRequest)
                .where(
                    McpOAuthRequest.expires_at > now(),
                    McpOAuthRequest.approved_at.is_(None),
                    McpOAuthRequest.denied_at.is_(None),
                )
            )
            >= 1000
        ):
            raise OAuthError("temporarily_unavailable", "Authorization limit reached", 429)
        token = create_authorization(db, params)
        return RedirectResponse(
            frontend_url("agent/oauth?request_token=" + token), status_code=302, headers=PRIVATE
        )
    except OAuthError as exc:
        destination = authorization_error_redirect(db, params, exc)
        if destination:
            return RedirectResponse(destination, status_code=302, headers=PRIVATE)
        return failure(exc)


@router.post("/mcp-oauth/token")
async def token(request: Request, db: Session = Depends(get_db)):
    throttle_public(request, "token", 120)
    try:
        params = await form(request)
        allowed = {
            "grant_type",
            "client_id",
            "client_secret",
            "code",
            "redirect_uri",
            "code_verifier",
            "resource",
            "refresh_token",
            "scope",
        }
        # RFC 6749 section 3.2: unsupported extensions never reach token processing.
        params = {key: value for key, value in params.items() if key in allowed}
        result = await run_in_threadpool(token_result, db, params, request)
        return JSONResponse(result, headers=PRIVATE)
    except OAuthError as exc:
        return failure(exc)


@router.post("/mcp-oauth/revoke")
async def revoke(request: Request, db: Session = Depends(get_db)):
    throttle_public(request, "revoke", 120)
    try:
        params = await form(request)
        if (
            set(params) - {"client_id", "client_secret", "token", "token_type_hint"}
            or not params.get("token")
            or len(params["token"]) > 200
            or (
                "token_type_hint" in params
                and params["token_type_hint"] not in {"access_token", "refresh_token"}
            )
        ):
            raise OAuthError("invalid_request", "Invalid revocation request")
        result = await run_in_threadpool(revoke_result, db, params, request)
        return JSONResponse(result, headers=PRIVATE)
    except OAuthError as exc:
        return failure(exc)


@web_router.post("/preview", dependencies=[Depends(require_csrf)])
async def preview_request(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    throttle(f"mcp-consent-preview:{access.user.id}", 30, 60)
    response.headers.update(PRIVATE)
    try:
        payload = await json_input(request, PreviewInput)
        return await run_in_threadpool(preview, db, payload.request_token, access)
    except OAuthError as exc:
        return failure(exc)


@web_router.post("/approve", dependencies=[Depends(require_csrf)])
async def approve_request(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    throttle(f"mcp-consent-approve:{access.user.id}", 30, 60)
    response.headers.update(PRIVATE)
    try:
        payload = await json_input(request, ApproveInput)
        return await run_in_threadpool(approve, db, payload.request_token, payload.approved, access)
    except OAuthError as exc:
        return failure(exc)


@web_router.get("/grants")
def grants(
    response: Response,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    response.headers.update(PRIVATE)
    employee_access(db, access.user)
    rows = db.execute(
        select(McpOAuthGrant, McpOAuthClient.client_name)
        .join(McpOAuthClient, McpOAuthClient.id == McpOAuthGrant.client_id)
        .where(McpOAuthGrant.user_id == access.user.id, McpOAuthGrant.rotated_at.is_(None))
        .order_by(McpOAuthGrant.created_at.desc())
        .limit(100)
    )
    return [
        {
            "id": item.id,
            "client_name": name,
            "scopes": item.scopes,
            "expires_at": item.expires_at,
            "revoked_at": item.revoked_at,
        }
        for item, name in rows
    ]


@web_router.delete("/grants/{grant_id}", dependencies=[Depends(require_csrf)])
def revoke_grant(
    grant_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    employee_access(db, access.user)
    item = db.scalar(
        select(McpOAuthGrant).where(
            McpOAuthGrant.id == grant_id, McpOAuthGrant.user_id == access.user.id
        )
    )
    if item is None:
        raise HTTPException(404, "授权不存在")
    revoke_family(db, item.family_id)
    audit(db, access.user.id, "revoke", item.id)
    db.commit()
    return {"status": "revoked"}
