"""Distribution integrity and isolated stdio checks; never contact the service."""

import asyncio
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

import pytest


PACKAGE = Path(__file__).resolve().parents[1] / "plugin" / "connector"
EXPECTED_TOOLS = {
    "start_connection",
    "complete_connection",
    "get_capabilities",
    "search_assets",
    "get_asset",
    "create_asset_draft",
    "update_asset_draft",
    "get_my_incubations",
    "get_incubation",
    "save_snapshot",
    "operation_status",
    "disconnect",
    "get_asset_details",
    "search_people",
    "save_asset_details",
    "upload_asset_attachment",
}


def test_source_provenance_and_locked_dependencies():
    provenance_path = PACKAGE / "SOURCE-PROVENANCE.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    assert provenance["source_repository"] == (
        "https://github.com/FlipBelt/Digital-Asset-Management-Space"
    )
    assert provenance["source_commit"] == "fa56c38f9f9b37d78ba65971f1f9b810ce8d2ddf"
    assert provenance["tool_count"] == 16
    assert len(provenance["files"]) == 6
    assert {record["path"] for record in provenance["files"]} == {
        "pyproject.toml",
        "uv.lock",
        "src/flipbelt_connector/__init__.py",
        "src/flipbelt_connector/client.py",
        "src/flipbelt_connector/server.py",
        "src/flipbelt_connector/vault.py",
    }
    for record in provenance["files"]:
        path = PACKAGE / record["path"]
        assert path.resolve().is_relative_to(PACKAGE.resolve())
        assert not path.is_symlink()
        content = path.read_bytes()
        assert len(content) == record["bytes"]
        assert hashlib.sha256(content).hexdigest() == record["sha256"]
    assert ":\\" not in provenance_path.read_text(encoding="utf-8")
    assert "C:/Users/" not in provenance_path.read_text(encoding="utf-8")
    project = tomllib.loads((PACKAGE / "pyproject.toml").read_text(encoding="utf-8"))
    locked = tomllib.loads((PACKAGE / "uv.lock").read_text(encoding="utf-8"))
    root = next(
        package
        for package in locked["package"]
        if package["name"] == project["project"]["name"]
    )
    assert root["version"] == project["project"]["version"]
    assert root["source"] == {"editable": "."}
    assert {item["name"] for item in root["dependencies"]} == {"mcp", "httpx"}


def test_packaged_source_has_exact_tool_catalog():
    path = PACKAGE / "src" / "flipbelt_connector" / "server.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = {
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "server"
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        )
    }
    assert names == EXPECTED_TOOLS


def test_stdio_handshake_has_16_tools_and_no_http(tmp_path):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    marker = tmp_path / "network-attempt.txt"
    local = tmp_path / "isolated-localappdata"
    child = "\n".join(
        [
            "import pathlib, sys, httpx",
            f"sys.path.insert(0, {str(PACKAGE / 'src')!r})",
            f"marker = pathlib.Path({str(marker)!r})",
            "def forbid_http(*args, **kwargs):",
            "    marker.write_text('HTTP attempted', encoding='utf-8')",
            "    raise RuntimeError('Offline package verification forbids HTTP')",
            "httpx.Client.request = forbid_http",
            "def audit(event, args):",
            "    if event == 'socket.connect' and isinstance(args[1], tuple) and args[1][0] in {'127.0.0.1', '::1'}:",
            "        return  # Windows asyncio creates an internal loopback socketpair.",
            "    if event in {'socket.connect', 'socket.getaddrinfo'}:",
            "        marker.write_text('Network attempted', encoding='utf-8')",
            "        raise RuntimeError('Offline package verification forbids network')",
            "sys.addaudithook(audit)",
            "from flipbelt_connector.server import main",
            "main()",
        ]
    )

    async def exercise():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", child],
            env={
                "LOCALAPPDATA": str(local),
                "FLIPBELT_API_BASE": "https://jtzhzt.flipbeltchina.com",
                "FLIPBELT_CLIENT_NAME": "OfflinePackageCheck",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        async with (
            stdio_client(params) as (read, write),
            ClientSession(read, write) as session,
        ):
            initialized = await session.initialize()
            assert "request_id" in initialized.instructions
            tools = await session.list_tools()
            assert {tool.name for tool in tools.tools} == EXPECTED_TOOLS
            result = await session.call_tool("get_capabilities", {})
            assert result.isError
            assert "尚未连接" in str(result.content)

    asyncio.run(exercise())
    assert not marker.exists(), "The connector attempted HTTP or another network call"
    assert not local.exists(), "The isolated no-credential check wrote a vault"


def powershell():
    if os.name != "nt":
        pytest.skip("Windows launcher")
    command = shutil.which("powershell") or shutil.which("pwsh")
    if not command:
        pytest.skip("PowerShell is unavailable")
    return command


def run_launcher(tmp_path, path):
    command = powershell()
    script = tmp_path / "run.ps1"
    shutil.copyfile(PACKAGE / "run.ps1", script)
    environment = {**os.environ, "PATH": str(path)}
    return subprocess.run(
        [command, "-NoLogo", "-NoProfile", "-NonInteractive", "-File", str(script)],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )


def test_launcher_missing_uv_fails_without_installing(tmp_path):
    result = run_launcher(tmp_path, tmp_path / "empty-path")
    assert result.returncode == 2
    assert "Missing uv" in result.stderr
    assert not (tmp_path / ".venv").exists()


def test_launcher_missing_environment_fails_before_running_uv(tmp_path):
    powershell()
    tools = tmp_path / "tools"
    tools.mkdir()
    marker = tmp_path / "uv-was-called.txt"
    (tools / "uv.cmd").write_text(
        f'@echo UV should not run>"{marker}"\r\n@exit /b 99\r\n',
        encoding="ascii",
    )
    result = run_launcher(tmp_path, tools)
    assert result.returncode == 3
    assert "Missing local dependencies" in result.stderr
    assert not marker.exists()
    assert not (tmp_path / ".venv").exists()


def test_launcher_incomplete_dependencies_fail_before_running_uv(tmp_path):
    powershell()
    tools = tmp_path / "tools"
    tools.mkdir()
    marker = tmp_path / "uv-was-called.txt"
    (tools / "uv.cmd").write_text(
        f'@echo UV should not run>"{marker}"\r\n@exit /b 99\r\n',
        encoding="ascii",
    )
    subprocess.run(
        [sys.executable, "-m", "venv", "--without-pip", str(tmp_path / ".venv")],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    result = run_launcher(tmp_path, tools)
    assert result.returncode == 4
    assert "Invalid local dependencies" in result.stderr
    assert not marker.exists()
