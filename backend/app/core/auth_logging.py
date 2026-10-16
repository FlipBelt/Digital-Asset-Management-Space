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
            route = path.split("?", 1)[0]
            if (route.endswith("/api/dingtalk/web/callback")
                    or "/mcp-oauth/" in route or route.endswith("/agent/oauth")):
                record.args = (*args[:2], path.split("?", 1)[0], *args[3:])
        elif record.name == "httpx" and len(args) >= 2:
            value = str(args[1])
            parsed = urlsplit(value)
            if ("/mcp-oauth/" in parsed.path or parsed.path.endswith("/agent/oauth")):
                record.args = (args[0], urlunsplit(parsed._replace(query="")), *args[2:])
            elif parsed.hostname in {"api.dingtalk.com", "oapi.dingtalk.com"}:
                private_keys = {
                    "access_token",
                    "appsecret",
                    "authcode",
                    "code",
                    "clientsecret",
                    "refreshtoken",
                    "client_secret",
                    "refresh_token",
                    "code_verifier",
                    "request_token",
                    "state",
                }
                query = [
                    (key, "REDACTED" if key.lower() in private_keys else item)
                    for key, item in parse_qsl(parsed.query, keep_blank_values=True)
                ]
                safe_url = urlunsplit(parsed._replace(query=urlencode(query)))
                record.args = (args[0], safe_url, *args[2:])
            else:
                private_keys = {"code", "request_token", "access_token", "refresh_token",
                                "client_secret", "code_verifier", "state"}
                query = [(key, "REDACTED" if key.lower() in private_keys else item)
                         for key, item in parse_qsl(parsed.query, keep_blank_values=True)]
                record.args = (args[0], urlunsplit(parsed._replace(query=urlencode(query))), *args[2:])
        return True


def install_auth_log_redaction() -> None:
    for name in ("uvicorn.access", "httpx"):
        logger = logging.getLogger(name)
        if not any(isinstance(item, AuthQueryRedaction) for item in logger.filters):
            logger.addFilter(AuthQueryRedaction())
