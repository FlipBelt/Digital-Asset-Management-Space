import asyncio
import os
import sys
from uuid import uuid4

import httpx
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from flipbelt_connector.client import Connector, ConnectorError
from flipbelt_connector.vault import Vault, crypt

BASE = "https://jtzhzt.flipbeltchina.com"


class MemoryVault:
    def __init__(self):
        self.value = None

    def load(self):
        return self.value

    def save(self, token):
        self.value = {"token": token}

    def clear(self):
        self.value = None


def test_pairing_keeps_credentials_out_of_tool_result():
    secret, token = uuid4().hex, "agt_" + uuid4().hex

    def handler(request):
        assert "Authorization" not in request.headers
        if request.url.path.endswith("/start"):
            return httpx.Response(
                200,
                json={
                    "device_code": secret,
                    "user_code": "ABCD2345",
                    "verification_uri": BASE + "/agent/connect",
                    "expires_in": 600,
                    "interval": 5,
                },
            )
        assert secret in request.content.decode()
        return httpx.Response(
            200,
            json={
                "status": "authorized",
                "access_token": token,
                "expires_at": "synthetic",
                "scopes": ["asset:read", "asset:draft"],
            },
        )

    vault = MemoryVault()
    client = Connector(BASE, vault, httpx.MockTransport(handler))
    started = client.start("Codex")
    assert secret not in str(started) and token not in str(started)
    finished = client.finish()
    assert secret not in str(finished) and token not in str(finished)
    assert vault.load()["token"] == token


def test_unknown_network_write_does_not_retry():
    attempts = []

    def handler(request):
        attempts.append(request)
        raise httpx.ReadTimeout("synthetic timeout with secret-request-body")

    vault = MemoryVault()
    vault.save("agt_synthetic")
    client = Connector(BASE, vault, httpx.MockTransport(handler))
    with pytest.raises(ConnectorError, match="原 request_id") as error:
        client.call("POST", "/drafts", {"request_id": str(uuid4())})
    assert len(attempts) == 1
    assert "secret-request-body" not in str(error.value)


def test_no_redirect_or_untrusted_error_echo():
    vault = MemoryVault()
    vault.save("agt_synthetic")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            302, headers={"Location": "https://evil.invalid"}, text="upstream secret"
        )

    client = Connector(BASE, vault, httpx.MockTransport(handler))
    with pytest.raises(ConnectorError) as error:
        client.call("GET", "/capabilities")
    assert len(requests) == 1 and "secret" not in str(error.value)


@pytest.mark.parametrize(
    "base",
    [
        "http://localhost",
        "https://user:secret@example.com",
        "https://example.com?code=secret",
        "https://example.com/../api",
        "https://example.com/%2fapi",
        "https://example.com/#secret",
    ],
)
def test_untrusted_configuration_rejected(base):
    with pytest.raises(ValueError):
        Connector(base, MemoryVault())


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI")
def test_dpapi_roundtrip_origin_binding_and_no_plaintext(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    vault = Vault(BASE)
    token = "agt_synthetic_" + uuid4().hex
    vault.save(token)
    assert token.encode() not in vault.path.read_bytes()
    assert vault.load()["token"] == token
    with pytest.raises(RuntimeError):
        crypt(vault.path.read_bytes(), b"https://other.invalid", decrypt=True)
    assert not Vault("https://other.invalid").path.exists()
    vault.clear()
    assert not vault.path.exists()


def test_official_stdio_initialize_and_tools(tmp_path):
    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "flipbelt_connector.server"],
            env={**os.environ, "LOCALAPPDATA": str(tmp_path)},
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            initialized = await session.initialize()
            assert "request_id" in initialized.instructions
            listed = await session.list_tools()
            names = {t.name for t in listed.tools}
            assert {
                "get_capabilities",
                "create_asset_draft",
                "save_snapshot",
                "get_my_incubations",
                "operation_status",
            } <= names
            assert not any("confirm" in name for name in names)
            assert {
                "get_asset_details",
                "search_people",
                "save_asset_details",
                "upload_asset_attachment",
            } <= names
            assert len(names) == 16
            result = await session.call_tool("get_capabilities", {})
            assert result.isError  # No local credential: no network request.
            assert "尚未连接" in str(result.content)

    asyncio.run(exercise())


def test_supplement_tools_are_bounded_and_metadata_only(tmp_path, monkeypatch):
    from flipbelt_connector import server as api

    calls = []

    def safe(method, path, payload=None):
        calls.append((method, path, payload))
        return {"attachment": {"id": "synthetic", "file_name": "outcome.png"}}

    monkeypatch.setattr(api, "safe", safe)
    asset, request = uuid4(), uuid4()
    path = tmp_path / "outcome.png"
    path.write_bytes(b"synthetic-image")
    result = api.upload_asset_attachment(asset, request, 2, str(path))
    assert "content_base64" not in str(result) and str(path) not in str(result)
    assert calls[-1][2]["file_name"] == "outcome.png"
    assert calls[-1][2]["request_id"] == str(request)
    api.save_asset_details(asset, request, 2, {"profile": {"tech_stack": "synthetic"}})
    assert calls[-1][0] == "PUT" and calls[-1][2]["version"] == 2
    api.operation_status("attachment.upload", request)
    api.operation_status("details.save", request)
    for value in ({"confirmed": True}, {"actor_user_id": str(uuid4())}, {}):
        with pytest.raises(ValueError):
            api.save_asset_details(asset, request, 2, value)
    for value in ("relative.png", str(tmp_path / "config.env")):
        with pytest.raises(ValueError):
            api.upload_asset_attachment(asset, request, 2, value)
    with pytest.raises(ValueError):
        api.search_people(" ")


def test_upload_reads_no_more_than_limit_and_never_sends_oversize(
    tmp_path, monkeypatch
):
    from flipbelt_connector import server as api

    path = tmp_path / "large.png"
    with path.open("wb") as stream:
        stream.truncate(20 * 1024 * 1024 + 1)
    monkeypatch.setattr(
        api, "safe", lambda *args: pytest.fail("oversized content sent")
    )
    with pytest.raises(ValueError, match="20MB"):
        api.upload_asset_attachment(uuid4(), uuid4(), 1, str(path))
