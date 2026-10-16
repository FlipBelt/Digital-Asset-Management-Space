"""Bounded OAuth input; client metadata is a claim, never a verified identity."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, strict=True)


class ClientRegistration(StrictInput):
    # RFC 7591 requires ignoring unsupported registration metadata only.
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True, strict=True)

    client_name: str = Field(default="MCP client", min_length=1, max_length=80)
    redirect_uris: list[str] = Field(min_length=1, max_length=10)
    token_endpoint_auth_method: Literal["none", "client_secret_post", "client_secret_basic"] = (
        "none"
    )
    grant_types: list[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"], max_length=2
    )
    response_types: list[str] = Field(default_factory=lambda: ["code"], max_length=1)
    application_type: Literal["native", "web"] | None = None
    scope: str | None = Field(default=None, max_length=200)
    # Accepted for interoperability, but never fetched or displayed as trusted links.
    client_uri: str | None = Field(default=None, max_length=2000)
    logo_uri: str | None = Field(default=None, max_length=2000)
    tos_uri: str | None = Field(default=None, max_length=2000)
    policy_uri: str | None = Field(default=None, max_length=2000)
    software_id: str | None = Field(default=None, max_length=200)
    software_version: str | None = Field(default=None, max_length=100)


class PreviewInput(StrictInput):
    request_token: str = Field(pattern=r"^mrq_[A-Za-z0-9_-]{43}$")


class ApproveInput(PreviewInput):
    approved: bool
