from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_env: str = "local"
    app_name: str = "集团账号管理中台 API"
    app_host: str = "127.0.0.1"
    app_port: int = 8100
    app_debug: bool = False
    database_url: str = (
        "postgresql+psycopg://account_center:account_center_local@127.0.0.1:55432/account_center"
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:5173", "http://localhost:5173"]
    )
    session_cookie_name: str = "account_center_session"
    # Seven days is the standard first-party DingTalk session lifetime.  The
    # server stores only a hash of the generated token.
    session_ttl_hours: int = Field(default=168, ge=1, le=168)
    session_secure_cookie: bool = False
    dingtalk_enabled: bool = False
    dingtalk_client_id: str | None = None
    dingtalk_client_secret: str | None = None
    dingtalk_corp_id: str | None = None
    dingtalk_agent_id: str | None = None
    dingtalk_web_enabled: bool = False
    dingtalk_web_redirect_uri: str | None = None
    dingtalk_web_frontend_url: str | None = None
    agent_connector_enabled: bool = False
    agent_frontend_url: str | None = None
    agent_token_ttl_hours: int = Field(default=24, ge=1, le=168)
    ai_import_enabled: bool = False
    ai_import_base_url: str | None = None
    ai_import_api_key: str | None = None
    ai_import_model: str | None = None
    ai_import_timeout_seconds: int = Field(default=30, ge=5, le=120)
    ai_import_max_rows_per_request: int = Field(default=50, ge=1, le=200)
    ai_import_max_retries: int = Field(default=1, ge=0, le=2)
    # A developer control plane is intentionally separate from normal business
    # roles. Access requires this server-managed username and a dedicated role.
    developer_supervisor_username: str | None = None

    @model_validator(mode="after")
    def validate_production_session_security(self) -> "Settings":
        if self.app_env == "production" and not self.session_secure_cookie:
            raise ValueError("SESSION_SECURE_COOKIE must be true in production")
        web_urls = [
            self.dingtalk_web_redirect_uri,
            self.dingtalk_web_frontend_url,
            self.agent_frontend_url,
        ]
        for value in (url for url in web_urls if url):
            parsed = urlsplit(value)
            local_http = (
                self.app_env == "local"
                and parsed.scheme == "http"
                and parsed.hostname in {"127.0.0.1", "localhost"}
            )
            if (
                (parsed.scheme != "https" and not local_http)
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or parsed.query
                or parsed.fragment
                or "\\" in value
                or any(ord(char) < 33 or ord(char) == 127 for char in value)
                or "/../" in parsed.path
                or "%" in parsed.path
            ):
                raise ValueError("DingTalk web URLs must be trusted HTTPS URLs without queries")
            _ = parsed.port  # Reject malformed ports while loading configuration.
        if self.dingtalk_web_redirect_uri and self.dingtalk_web_frontend_url:
            callback = urlsplit(self.dingtalk_web_redirect_uri)
            frontend = urlsplit(self.dingtalk_web_frontend_url)
            if (
                self.dingtalk_web_enabled
                and callback.scheme == "https"
                and not self.session_secure_cookie
            ):
                raise ValueError("SESSION_SECURE_COOKIE must be true for HTTPS web login")
            if (callback.scheme, callback.netloc) != (frontend.scheme, frontend.netloc):
                raise ValueError("DingTalk web callback and frontend must share the same origin")
            if not callback.path.endswith("/api/dingtalk/web/callback"):
                raise ValueError("DINGTALK_WEB_REDIRECT_URI must point to the web callback")
            if not frontend.path.endswith("/"):
                raise ValueError("DINGTALK_WEB_FRONTEND_URL must end with a slash")
        if self.agent_connector_enabled and not self.agent_frontend_url:
            raise ValueError("AGENT_FRONTEND_URL is required when the connector is enabled")
        return self

    def dingtalk_web_missing_settings(self) -> list[str]:
        missing = self.dingtalk_missing_settings()
        if not self.dingtalk_web_redirect_uri:
            missing.append("DINGTALK_WEB_REDIRECT_URI")
        if not self.dingtalk_web_frontend_url:
            missing.append("DINGTALK_WEB_FRONTEND_URL")
        return missing

    def dingtalk_missing_settings(self, *, require_corp_id: bool = True) -> list[str]:
        required = {
            "DINGTALK_CLIENT_ID": self.dingtalk_client_id,
            "DINGTALK_CLIENT_SECRET": self.dingtalk_client_secret,
        }
        if require_corp_id:
            required["DINGTALK_CORP_ID"] = self.dingtalk_corp_id
        return [key for key, value in required.items() if not value]

    def ai_import_missing_settings(self) -> list[str]:
        required = {
            "AI_IMPORT_BASE_URL": self.ai_import_base_url,
            "AI_IMPORT_API_KEY": self.ai_import_api_key,
            "AI_IMPORT_MODEL": self.ai_import_model,
        }
        return [key for key, value in required.items() if not value]


@lru_cache
def get_settings() -> Settings:
    return Settings()
