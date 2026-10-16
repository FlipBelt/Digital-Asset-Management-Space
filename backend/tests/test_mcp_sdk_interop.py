"""Optional real SDK smoke against this app on an isolated loopback HTTP server."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
from test_agent_mcp import RESOURCE, TOOLS, issue_mcp_token, mcp_settings  # noqa: F401

from app.db.session import engine

pytest_plugins = ["test_asset_center_integration"]

SDK_CLIENT = r'''
import importlib.metadata
import json
import os
from urllib.parse import urlsplit

import anyio
import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    url = os.environ["MCP_INTEROP_URL"]
    parsed = urlsplit(url)
    assert parsed.scheme == "http" and parsed.hostname == "127.0.0.1" and parsed.port
    headers = {"Authorization": "Bearer " + os.environ["MCP_INTEROP_TOKEN"]}
    async with httpx.AsyncClient(headers=headers, trust_env=False, timeout=10) as http:
        async with streamable_http_client(url, http_client=http) as (read, write, _):
            async with ClientSession(read, write) as session:
                initialized = await session.initialize()
                tools = await session.list_tools()
                capabilities = await session.call_tool("get_capabilities", {})
                assert capabilities.isError is False
                print(json.dumps({
                    "sdk_version": importlib.metadata.version("mcp"),
                    "protocol": initialized.protocolVersion,
                    "tools": sorted(tool.name for tool in tools.tools),
                    "capabilities": capabilities.structuredContent,
                }))


anyio.run(main)
'''


def test_real_sdk_initializes_lists_and_calls_over_local_http(
    issue_mcp_token, mcp_settings,  # noqa: F811 - imported fixtures register with pytest
):
    configured = os.environ.get("MCP_SDK_PYTHON")
    if not configured:
        pytest.skip("Set MCP_SDK_PYTHON to an existing MCP 1.30.0 interpreter for SDK interop.")
    sdk_python = Path(configured)
    assert sdk_python.is_file(), "MCP_SDK_PYTHON must point to an existing interpreter."
    assert os.environ.get("ASSET_CENTER_ISOLATED_TESTS") == "1"
    assert engine.url.host == "127.0.0.1" and engine.url.port in {55433, 55439}
    assert (engine.url.database or "").startswith("dam_v13_tests_")
    identity = issue_mcp_token()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    environment = {
        **os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8",
        "APP_ENV": "local", "DINGTALK_ENABLED": "false", "DINGTALK_WEB_ENABLED": "false",
        "DATABASE_URL": engine.url.render_as_string(hide_password=False),
        "AGENT_CONNECTOR_ENABLED": "true", "AGENT_MCP_ENABLED": "true",
        "AGENT_FRONTEND_URL": RESOURCE.removesuffix("/mcp"), "AGENT_MCP_PUBLIC_URL": RESOURCE,
        "AGENT_MCP_ALLOWED_REDIRECT_URIS": json.dumps(mcp_settings.agent_mcp_allowed_redirect_uris),
        "AGENT_MCP_ALLOWED_ORIGINS": json.dumps(mcp_settings.agent_mcp_allowed_origins),
    }
    backend = Path(__file__).resolve().parents[1]
    server = subprocess.Popen(
        [sys.executable, "-B", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
         "--port", str(port), "--lifespan", "off", "--no-access-log", "--log-level", "warning"],
        cwd=backend, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            assert server.poll() is None, "The isolated loopback MCP server failed to start."
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                if time.monotonic() >= deadline:
                    pytest.fail("The isolated loopback MCP server did not become ready.")
                time.sleep(0.05)
        child = subprocess.run(
            [str(sdk_python), "-B", "-c", SDK_CLIENT], cwd=backend,
            env=environment | {
                "MCP_INTEROP_URL": f"http://127.0.0.1:{port}/mcp",
                "MCP_INTEROP_TOKEN": identity.access_token,
            },
            capture_output=True, text=True, encoding="utf-8", timeout=30, check=False,
        )
        assert child.returncode == 0, "The real SDK could not complete its local MCP exchange."
        value = json.loads(child.stdout)
        assert value["sdk_version"] == "1.30.0"
        assert value["protocol"] in {"2025-06-18", "2025-11-25"}
        assert set(value["tools"]) == TOOLS
        assert value["capabilities"]["protocol"] == "flipbelt-agent-mcp-v1"
        assert value["capabilities"]["remote_tool_count"] == 13
        assert value["capabilities"]["confirmation"] == "web_only"
    finally:
        server.terminate()
        try:
            server.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.communicate(timeout=5)

