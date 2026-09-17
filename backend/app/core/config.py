from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
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
        return self

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
