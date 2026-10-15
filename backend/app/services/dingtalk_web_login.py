import re
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from urllib.parse import unquote, urlsplit

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.auth import token_hash
from app.models import DingTalkWebLoginState

LOGIN_STATE_TTL_SECONDS = 300
_NONCE = re.compile(r"[A-Za-z0-9_-]{43}")
_PATH = re.compile(r"/[A-Za-z0-9/_-]*")


def safe_login_return_path(value: str | None) -> str:
    """Keep a return route inside this frontend mount, including /test/."""
    if not value or len(value) > 2000:
        return "/my"
    decoded = unquote(value)
    if "\\" in decoded or any(ord(char) < 32 or ord(char) == 127 for char in decoded):
        return "/my"
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "/my"
    path = unquote(parsed.path)
    if (
        parsed.scheme
        or parsed.netloc
        or not _PATH.fullmatch(path)
        or path.startswith("//")
        or path == "/login"
        or path.startswith("/api/")
        or path == "/test"
        or path.startswith("/test/")
    ):
        return "/my"
    return path + ("?" + parsed.query if parsed.query else "")


def new_login_state(db: Session, return_path: str) -> tuple[str, str]:
    state, browser_nonce = token_urlsafe(32), token_urlsafe(32)
    now = datetime.now(UTC)
    # Clean only expired transient challenges; no identity or business data is touched.
    db.execute(delete(DingTalkWebLoginState).where(DingTalkWebLoginState.expires_at <= now))
    db.add(
        DingTalkWebLoginState(
            state_hash=token_hash(state),
            browser_hash=token_hash(browser_nonce),
            return_path=safe_login_return_path(return_path),
            expires_at=now + timedelta(seconds=LOGIN_STATE_TTL_SECONDS),
        )
    )
    db.commit()
    return state, browser_nonce


def consume_login_state(db: Session, state: str | None, browser_nonce: str | None) -> str | None:
    if (
        not state
        or not browser_nonce
        or not _NONCE.fullmatch(state)
        or not _NONCE.fullmatch(browser_nonce)
    ):
        return None
    # Atomic consumption, committed before the external exchange, prevents reuse across workers.
    value = db.execute(
        delete(DingTalkWebLoginState)
        .where(
            DingTalkWebLoginState.state_hash == token_hash(state),
            DingTalkWebLoginState.browser_hash == token_hash(browser_nonce),
            DingTalkWebLoginState.expires_at > datetime.now(UTC),
        )
        .returning(DingTalkWebLoginState.return_path)
    ).scalar_one_or_none()
    db.commit()
    return value
