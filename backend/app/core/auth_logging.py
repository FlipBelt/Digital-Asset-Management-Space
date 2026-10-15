import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class AuthQueryRedaction(logging.Filter):
    """Keep access status logs without persisting OAuth codes or upstream tokens."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple):
            return True
        if record.name == "uvicorn.access" and len(args) >= 3:
            path = str(args[2])
            if path.split("?", 1)[0].endswith("/api/dingtalk/web/callback"):
                record.args = (*args[:2], path.split("?", 1)[0], *args[3:])
        elif record.name == "httpx" and len(args) >= 2:
            value = str(args[1])
            parsed = urlsplit(value)
            if parsed.hostname in {"api.dingtalk.com", "oapi.dingtalk.com"}:
                private_keys = {
                    "access_token",
                    "appsecret",
                    "authcode",
                    "code",
                    "clientsecret",
                    "refreshtoken",
                }
                query = [
                    (key, "REDACTED" if key.lower() in private_keys else item)
                    for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                ]
                safe_url = urlunsplit(parsed._replace(query=urlencode(query)))
                record.args = (args[0], safe_url, *args[2:])
        return True


def install_auth_log_redaction() -> None:
    for name in ("uvicorn.access", "httpx"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, AuthQueryRedaction) for item in logger.filters):
            logger.addFilter(AuthQueryRedaction())
