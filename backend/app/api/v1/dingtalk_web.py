from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.api.v1.dingtalk import create_verified_dingtalk_session
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.services.dingtalk import DingTalkClient
from app.services.dingtalk_web_login import (
    LOGIN_STATE_TTL_SECONDS,
    consume_login_state,
    new_login_state,
    safe_login_return_path,
)

public_router = APIRouter(prefix="/api/dingtalk/web", tags=["dingtalk"])


def web_login_configured(settings: Settings) -> bool:
    return (
        settings.dingtalk_enabled
        and settings.dingtalk_web_enabled
        and not settings.dingtalk_web_missing_settings()
    )


def _cookie_name(settings: Settings) -> str:
    return settings.session_cookie_name + "_dingtalk_web"


def _private_response(response: Response) -> Response:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


def _login_result(
    settings: Settings, error: str | None = None, return_path: str = "/my"
) -> Response:
    if not settings.dingtalk_web_frontend_url:
        raise HTTPException(status_code=409, detail="DingTalk web login is not configured")
    query = (
        {"dingtalkError": error}
        if error
        else {
            "dingtalk": "success",
            "redirect": safe_login_return_path(return_path),
        }
    )
    response = RedirectResponse(
        settings.dingtalk_web_frontend_url + "login?" + urlencode(query), status_code=303
    )
    response.delete_cookie(_cookie_name(settings), path="/")
    return _private_response(response)


@public_router.get("/config")
def config(response: Response) -> dict[str, bool]:
    settings = get_settings()
    _private_response(response)
    return {
        "enabled": settings.dingtalk_web_enabled,
        "configured": web_login_configured(settings),
    }


@public_router.get("/authorize")
def authorize(request: Request, next: str = "/my", db: Session = Depends(get_db)) -> Response:
    settings = get_settings()
    if not web_login_configured(settings):
        return _login_result(settings, "unavailable")
    state, browser_nonce = new_login_state(db, next)
    params = {
        "client_id": settings.dingtalk_client_id,
        "redirect_uri": settings.dingtalk_web_redirect_uri,
        "response_type": "code",
        "scope": "openid corpid",
        "prompt": "consent",
        "corpId": settings.dingtalk_corp_id,
        "state": state,
    }
    response = RedirectResponse(
        "https://login.dingtalk.com/oauth2/auth?" + urlencode(params), status_code=302
    )
    response.set_cookie(
        _cookie_name(settings),
        browser_nonce,
        max_age=LOGIN_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.session_secure_cookie
        or settings.dingtalk_web_redirect_uri.startswith("https:"),
        samesite="lax",
        path="/",
    )
    return _private_response(response)


@public_router.get("/callback")
def callback(request: Request, db: Session = Depends(get_db)) -> Response:
    settings = get_settings()
    if not web_login_configured(settings):
        return _login_result(settings, "unavailable")
    params = request.query_params
    if any(len(params.getlist(key)) > 1 for key in ("state", "authCode", "error")):
        return _login_result(settings, "invalid_state")
    return_path = consume_login_state(
        db,
        params.get("state"),
        request.cookies.get(_cookie_name(settings)),
    )
    if return_path is None:
        return _login_result(settings, "invalid_state")
    if params.get("error"):
        return _login_result(settings, "cancelled")
    auth_code = params.get("authCode")
    if not auth_code or len(auth_code) > 2000:
        return _login_result(settings, "exchange_failed")
    response = _login_result(settings, return_path=return_path)
    try:
        client = DingTalkClient(settings=settings)
        try:
            profile_data = client.user_from_web_auth_code(auth_code)
        finally:
            client.client.close()
        create_verified_dingtalk_session(
            profile_data, request, response, db, audit_action="session.dingtalk_web_login"
        )
    except HTTPException as exc:
        db.rollback()
        return _login_result(
            settings, "access_denied" if exc.status_code == 403 else "exchange_failed"
        )
    return response
