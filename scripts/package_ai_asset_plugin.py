"""Build three downstream packages from the project skills; never install or publish."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ("flipbelt-ai-asset-registrar", "flipbelt-ai-workflow-incubator")
CONNECTOR_FILES = {
    "README.md", "SOURCE-PROVENANCE.json", "pyproject.toml", "uv.lock", "run.ps1",
    "src/flipbelt_connector/__init__.py", "src/flipbelt_connector/client.py",
    "src/flipbelt_connector/server.py", "src/flipbelt_connector/vault.py",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def tree_digest(files: dict[str, str]) -> str:
    return digest("".join(f"{name}\0{sha}\n" for name, sha in sorted(files.items())).encode())


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def remote_url(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        parsed = urlsplit(value)
        if (len(value) > 2000 or parsed.scheme != "https" or not parsed.hostname
                or parsed.username is not None or parsed.password is not None
                or "?" in value or "#" in value or "\\" in value or "%" in value
                or not parsed.path.endswith("/mcp")
                or any(part in {".", ".."} for part in parsed.path.split("/"))
                or any(ord(char) < 33 or ord(char) == 127 for char in value)
                or parsed.port is not None and not 1 <= parsed.port <= 65535):
            raise ValueError
    except (ValueError, TypeError) as exc:
        raise ValueError("Remote MCP URL must be an exact HTTPS URL ending in /mcp, without credentials, query or fragment") from exc
    return value


def normalize_team_app_id(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) > 200 or not re.fullmatch(
            r"(?:plugin_)?asdk_app_[A-Za-z0-9][A-Za-z0-9_-]*", value):
        raise ValueError("Team App ID must be an exact asdk_app_ ID or its plugin_asdk_app_ technical ID")
    # Workspace manifests use the App ID, not the plugin ID shown in the browser URL.
    return value.removeprefix("plugin_")


def reject_links(path: Path) -> None:
    for candidate in (path, *path.parents):
        try:
            info = candidate.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise ValueError(f"Linked or reparse path rejected: {candidate}")


def safe_absolute(path: Path) -> Path:
    absolute = path.absolute()
    reject_links(absolute)
    return absolute.resolve()


def file_paths(directory: Path) -> dict[str, Path]:
    reject_links(directory.absolute())
    paths = {}
    pending = [directory]
    while pending:
        for path in sorted(pending.pop().iterdir()):
            reject_links(path)
            if path.is_dir():
                pending.append(path)
            elif path.is_file():
                paths[path.relative_to(directory).as_posix()] = path
    return paths


def checked_files(directory: Path, expected: set[str] | None = None) -> dict[str, bytes]:
    paths = file_paths(directory)
    if expected is not None:
        paths = {name: path for name, path in paths.items()
                 if not ("__pycache__" in Path(name).parts and path.suffix == ".pyc")}
    if expected is not None and set(paths) != expected:
        raise ValueError(f"Unexpected source file set: {directory}: {sorted(set(paths) ^ expected)}")
    return {name: path.read_bytes() for name, path in paths.items()}


def public_files(files: dict[str, bytes]) -> None:
    for name, data in files.items():
        if "\\" in name or name.startswith("/") or ".." in Path(name).parts:
            raise ValueError(f"Unsafe package entry: {name}")
        text = data.decode("utf-8")
        if re.search(r"[A-Za-z]:[/\\](?:Users|FILPBELT|flipbelt-ai-asset-center)[/\\]", text):
            raise ValueError(f"Machine path in public file: {name}")
        if re.search(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|\b(?:agt|mcp|mrf|mcd|mrq)_[A-Za-z0-9_-]{24,}", text):
            raise ValueError(f"Credential-like material in public file: {name}")


def check_links(files: dict[str, bytes]) -> None:
    from posixpath import dirname, join, normpath

    for name, data in files.items():
        if not name.endswith(".md"):
            continue
        for target in re.findall(r"\]\(([^)]+)\)", data.decode("utf-8")):
            if re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target) or target.startswith("#"):
                continue
            link = normpath(join(dirname(name), target.split("#", 1)[0]))
            if link not in files:
                raise ValueError(f"Broken reference: {name} -> {target}")


def collect_source(root: Path) -> tuple[dict, dict[str, bytes], dict[str, str]]:
    reject_links(root / "plugin/metadata.json")
    metadata = json.loads((root / "plugin/metadata.json").read_text(encoding="utf-8"))
    if metadata["skills"] != list(SKILLS) or not re.fullmatch(r"\d+\.\d+\.\d+", metadata["version"]):
        raise ValueError("Unexpected plugin identity, version or skill set")
    files: dict[str, bytes] = {}
    source_files = {"plugin/metadata.json": digest((root / "plugin/metadata.json").read_bytes())}
    for skill in SKILLS:
        source = checked_files(root / ".agents/skills" / skill,
                               {"SKILL.md", "references/PILOT.md", "references/CONNECTOR.md"})
        for name, data in source.items():
            if b"\r" in data:
                raise ValueError(f"Skill source must use LF for Git byte parity: {skill}/{name}")
            files[f"skills/{skill}/{name}"] = data
            source_files[f".agents/skills/{skill}/{name}"] = digest(data)
    for reference in ("PILOT.md", "CONNECTOR.md"):
        if files[f"skills/{SKILLS[0]}/references/{reference}"] != files[f"skills/{SKILLS[1]}/references/{reference}"]:
            raise ValueError(f"Shared protocol drift: {reference}")
    for name in ("README.md", "CONNECTORS.md"):
        reject_links(root / "plugin" / name)
        data = (root / "plugin" / name).read_bytes()
        files[name] = data
        source_files[f"plugin/{name}"] = digest(data)
    return metadata, files, source_files


def git_evidence(root: Path) -> tuple[str, bool]:
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root, text=True).strip())
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid source commit")
    return commit, dirty


def build_package(root: Path, target: str, remote_mcp_url: str | None = None,
                  team_app_id: str | None = None) -> dict[str, bytes]:
    remote_mcp_url = remote_url(remote_mcp_url)
    team_app_id = normalize_team_app_id(team_app_id)
    if team_app_id is not None and (target != "team" or remote_mcp_url is None):
        raise ValueError("Team App binding requires the team target and an explicit remote MCP URL")
    meta, files, source_files = collect_source(root)
    name = meta["name"] + ("-personal" if target == "personal" else "")
    base = {
        "name": name, "version": meta["version"], "description": meta["description"],
        "author": {"name": meta["author"]},
    }
    if target == "qwenwork":
        base.update({
            "displayName": meta["display_name"], "descriptionZh": meta["description_zh"],
            "category": "productivity", "tags": ["flipbelt", "ai-assets", "incubation", "registration"],
            "skills": [f"./skills/{skill}" for skill in SKILLS],
        })
        if remote_mcp_url is not None:
            base["mcpServers"] = "./.mcp.json"
        files[".qoder-plugin/plugin.json"] = encoded(base)
        if remote_mcp_url is None:
            connector = checked_files(root / "plugin/connector", CONNECTOR_FILES)
            for path, data in connector.items():
                files[f"connector/{path}"] = data
                source_files[f"plugin/connector/{path}"] = digest(data)
    elif target in {"team", "personal"}:
        repository = "flipbelt-plugin-marketplace" if target == "team" else "flipbelt-personal-marketplace"
        base.update({
            "repository": f"https://github.com/J21NIANYI/{repository}",
            "license": "Proprietary", "skills": "./skills/",
            "keywords": ["flipbelt", "ai-assets", "incubation", "registration"],
            "interface": {
                "displayName": meta["display_name"] + ("（个人）" if target == "personal" else ""),
                "shortDescription": "工作机会孵化与已有成果登记，连接器独立授权。",
                "longDescription": meta["description_zh"], "developerName": meta["author"],
                "category": "Productivity",
                "capabilities": ["workflow-incubation", "asset-registration"],
                "defaultPrompt": ["帮我梳理这项重复工作，给出可试方案。", "整理当前项目成果卡，先保留本地草稿。"],
            },
        })
        if team_app_id is not None:
            base["apps"] = "./.app.json"
            files[".app.json"] = encoded({"apps": {"flipbelt-ai-assets": {
                "id": team_app_id, "required": True,
            }}})
        elif remote_mcp_url is not None:
            base["mcpServers"] = "./.mcp.json"
        files[".codex-plugin/plugin.json"] = encoded(base)
        if target == "personal":
            files["plugin.json"] = encoded({key: base[key] for key in ("name", "version", "description", "author", "repository", "license", "keywords")})
    else:
        raise ValueError(f"Unknown target: {target}")
    profile = "workspace-app-candidate" if team_app_id is not None else (
        "remote-oauth-candidate" if remote_mcp_url is not None else "local-legacy")
    if team_app_id is not None:
        notice = ("> 分发配置：团队已注册 App 引用候选。仅声明必需 App，不携带直接 MCP 配置；"
                  "App 标识格式与映射不证明服务可用、组织开放或本人授权，仍需分别验证。\n\n")
    elif remote_mcp_url is not None:
        files[".mcp.json"] = encoded({"mcpServers": {"flipbelt-ai-assets": {
            "type": "http", "url": remote_mcp_url,
        }}})
        notice = (f"> 分发配置：远程 OAuth 候选。MCP 入口 `{remote_mcp_url}` 的部署与宿主状态须另行核对；"
                  "配置存在不代表连接可用。宿主完成本人 OAuth 后才可访问获授权工具。\n\n")
    else:
        notice = ("> 分发配置：本机兼容模式。未生成自动 MCP 配置；"
                  "仅千问包携带可选 Windows 连接器源码，需独立配置和本人授权。\n\n")
    files["README.md"] = notice.encode("utf-8") + files["README.md"]
    commit, dirty = git_evidence(root)
    hashes = {path: digest(data) for path, data in files.items()}
    copied = {path: sha for path, sha in hashes.items() if path.startswith("skills/")}
    files["SOURCE-PROVENANCE.json"] = encoded({
        "schema_version": "1.0", "role": "downstream-distribution",
        "canonical_repository": "https://github.com/FlipBelt/Digital-Asset-Management-Space",
        "canonical_project": "flipbelt-ai-asset-center", "canonical_commit": commit,
        "canonical_worktree_dirty": dirty, "canonical_version": meta["version"],
        "target_plugin": name, "target_host": target, "synced_paths": ["skills"],
        "connection_profile": profile, "remote_mcp_url": remote_mcp_url,
        "workspace_app_id": team_app_id, "workspace_app_binding_verified": False,
        "remote_deployment_verified": False, "host_runtime_verified": False,
        "source_files": source_files, "source_tree_sha256": tree_digest(source_files),
        "copied_files": copied, "distribution_files": hashes,
        "distribution_tree_sha256": tree_digest(hashes),
        "adaptations": ["host manifest", "profile notice", profile],
        "exclusions": ["credentials", "virtual environments", "business data", "raw conversations", "unrequested App IDs", "automatic user authorization"],
    })
    public_files(files)
    check_links(files)
    return files


def preflight(directory: Path, files: dict[str, bytes], check: bool) -> None:
    reject_links(directory.absolute())
    paths = file_paths(directory) if directory.exists() else {}
    extras = set(paths) - set(files)
    if extras:
        raise ValueError(f"Unexpected downstream files; no deletion performed: {directory}: {sorted(extras)}")
    if check and {name: path.read_bytes() for name, path in paths.items()} != files:
        raise ValueError(f"Downstream drift: {directory}")


def write_tree(directory: Path, files: dict[str, bytes]) -> None:
    for name, data in files.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != data:
            path.write_bytes(data)


def zip_bytes(files: dict[str, bytes]) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name, (2026, 10, 15, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, data)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--team-root", type=Path)
    parser.add_argument("--personal-root", type=Path)
    parser.add_argument("--remote-mcp-url", help="Explicit HTTPS MCP endpoint for an unverified remote OAuth candidate")
    parser.add_argument("--team-app-id", help="Existing asdk_app_ App ID or plugin_asdk_app_ technical ID, for the team package only")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    app_id = normalize_team_app_id(args.team_app_id)
    if args.team_root and args.remote_mcp_url is not None and app_id is None:
        raise ValueError("Remote team marketplace distribution requires --team-app-id; direct MCP is a local candidate only")
    packages = {target: build_package(ROOT, target, args.remote_mcp_url, app_id if target == "team" else None)
                for target in ("team", "personal", "qwenwork")}
    version = json.loads((ROOT / "plugin/metadata.json").read_text(encoding="utf-8"))["version"]
    output = safe_absolute(args.output_dir)
    destinations = {output / target: files for target, files in packages.items()}
    for target, market in (("team", args.team_root), ("personal", args.personal_root)):
        if market:
            market = safe_absolute(market)
            reject_links(market / ".agents/plugins/marketplace.json")
            manifest = json.loads((market / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
            expected = "flipbelt-team" if target == "team" else "flipbelt-personal"
            if manifest["name"] != expected:
                raise ValueError(f"Unexpected market identity: {market}")
            name = "flipbelt-ai-asset-center" + ("-personal" if target == "personal" else "")
            destinations[market / "plugins" / name] = packages[target]
    paths = list(destinations)
    protected = [ROOT / ".agents", ROOT / "plugin", ROOT / "scripts", ROOT / "tests"]
    for index, directory in enumerate(paths):
        for other in paths[index + 1:] + protected:
            if directory == other or directory in other.parents or other in directory.parents:
                raise ValueError(f"Overlapping source/output paths: {directory}, {other}")
    # Check every destination before any write; unknown downstream files are never removed.
    for directory, files in destinations.items():
        preflight(directory, files, args.check)
    artifact = output / f"flipbelt-ai-asset-center-{version}-qwenwork.zip"
    zip_data = zip_bytes(packages["qwenwork"])
    reject_links(artifact)
    if args.check:
        if not artifact.is_file() or artifact.read_bytes() != zip_data:
            raise ValueError(f"ZIP drift: {artifact}")
    else:
        for directory, files in destinations.items():
            write_tree(directory, files)
        artifact.write_bytes(zip_data)
    with zipfile.ZipFile(artifact) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(packages["qwenwork"]):
            raise ValueError("ZIP integrity failure")
        if any(archive.read(name) != data for name, data in packages["qwenwork"].items()):
            raise ValueError("ZIP content mismatch")
    print(json.dumps({"mode": "check" if args.check else "build", "version": version,
                      "connection_profile": "remote-oauth-candidate" if args.remote_mcp_url is not None else "local-legacy",
                      "team_connection_profile": "workspace-app-candidate" if app_id is not None else (
                          "remote-oauth-candidate" if args.remote_mcp_url is not None else "local-legacy"),
                      "files": {key: len(value) for key, value in packages.items()},
                      "zip": str(artifact), "sha256": digest(zip_data)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
