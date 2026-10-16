"""Freeze reviewed Git bytes and fresh live preflight into an uploadable release."""
import argparse
import ast
import base64
import gzip
import hashlib
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_BASE = "fa56c38f9f9b37d78ba65971f1f9b810ce8d2ddf"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def blob(commit, name, *, missing=False):
    result = subprocess.run(["git", "show", commit + ":" + name], cwd=ROOT,
                            capture_output=True, check=False)
    if result.returncode and missing:
        return None
    assert result.returncode == 0, "Git object unavailable: " + name
    return result.stdout


def matched_old_sha(original, observed):
    actual = set(observed)
    assert len(actual) == 1, "Test and production runtime bytes differ"
    selected = actual.pop()
    if original is None:
        assert selected is None, "New runtime file unexpectedly exists on the server"
        return None
    lf = original.replace(b"\r\n", b"\n")
    variants = {sha(original), sha(lf), sha(lf.replace(b"\n", b"\r\n"))}
    assert selected in variants, "Live runtime bytes differ beyond LF/CRLF conversion"
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--preflight", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    commit = git("rev-parse", args.commit + "^{commit}").decode().strip()
    assert commit == args.commit and len(commit) == 40
    assert git("rev-parse", "HEAD").decode().strip() == commit
    git("merge-base", "--is-ancestor", SOURCE_BASE, commit)
    operator = blob(commit, "deploy/remote-mcp-release.py")
    constants = {}
    for node in ast.parse(operator).body:
        if (isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in {"RUNTIME", "LIVE", "SCHEMA", "OLD_SCHEMA", "KIND"}):
            constants[node.targets[0].id] = ast.literal_eval(node.value)
    live, runtime = constants["LIVE"], constants["RUNTIME"]
    preflight_raw = args.preflight.read_bytes()
    preflight = json.loads(preflight_raw)
    assert preflight["status"] == "PREFLIGHT_PASS"
    age = datetime.now(UTC) - datetime.fromisoformat(preflight["created_at"])
    assert 0 <= age.total_seconds() < 3600, "Fresh server preflight required"
    changed = git("diff", "--name-only", SOURCE_BASE, commit, "--", "backend/app", "backend/alembic")
    changed = {name.removeprefix("backend/") for name in changed.decode().splitlines()}
    assert changed and changed <= runtime, "Review runtime allowlist before packaging"
    for label in ("test", "production"):
        observed = preflight["environments"][label]
        assert observed["metadata"]["commit"] == observed["metadata"]["backend_commit"] == live
        assert observed["metadata"]["schema"] == constants["OLD_SCHEMA"]
        assert observed["database"]["revision"] == constants["OLD_SCHEMA"]
        assert len(observed["database"]["rows"]) == 75
    git("diff", "--exit-code", commit, "--", "frontend")
    assert not git("ls-files", "--others", "--exclude-standard", "--", "frontend").strip()
    output = (args.output or ROOT / ".deploy-artifacts" / "remote-mcp" / commit[:12]).resolve()
    assert output.is_relative_to((ROOT / ".deploy-artifacts").resolve())
    output.mkdir(parents=True, exist_ok=False)
    backend = {}
    for name in sorted(changed):
        old = blob(live, "backend/" + name, missing=True)
        assert old == blob(SOURCE_BASE, "backend/" + name, missing=True)
        old_sha = matched_old_sha(old, [preflight["environments"][label]["backend"][name]
                                       for label in ("test", "production")])
        data = blob(commit, "backend/" + name)
        backend[name] = {"old_sha256": old_sha, "sha256": sha(data),
                         "data": base64.b64encode(data).decode()}
    static = {}
    for label in ("test", "production"):
        destination = output / ("static-" + label)
        environment = {**os.environ, "VITE_BASE_PATH": "/test/" if label == "test" else "/",
                       "VITE_API_BASE": "/test-api" if label == "test" else ""}
        npm = shutil.which("npm.cmd") or shutil.which("npm")
        assert npm is not None
        subprocess.run([npm, "run", "build", "--", "--emptyOutDir", "--outDir", str(destination)],
                       cwd=ROOT / "frontend", env=environment, check=True, timeout=240)
        metadata = {"commit": commit, "backend_commit": commit, "schema": constants["SCHEMA"],
                    "environment": label, "release_kind": constants["KIND"]}
        (destination / "release-meta.json").write_bytes(json.dumps(metadata, sort_keys=True).encode())
        static[label] = {path.relative_to(destination).as_posix(): {
            "data": base64.b64encode(path.read_bytes()).decode(), "sha256": sha(path.read_bytes()),
        } for path in destination.rglob("*") if path.is_file()}
    specification = {"commit": commit, "source_base": SOURCE_BASE, "live_base": live,
                     "operator_sha256": sha(operator),
                     "kind": constants["KIND"], "preflight": preflight,
                     "backend": backend, "static": static}
    raw = gzip.compress(json.dumps(specification, sort_keys=True, separators=(",", ":")).encode(),
                        compresslevel=9, mtime=0)
    (output / "release.json.gz").write_bytes(raw)
    (output / "remote-mcp-release.py").write_bytes(operator)
    (output / "preflight.json").write_bytes(preflight_raw)
    manifest = {"commit": commit, "kind": constants["KIND"], "sha256": sha(raw),
                "operator_sha256": sha(operator), "bytes": len(raw), "source_base": SOURCE_BASE,
                "live_base": live, "schema": constants["SCHEMA"],
                "static": {label: {name: entry["sha256"] for name, entry in entries.items()}
                           for label, entries in static.items()},
                "backend": {name: entry["sha256"] for name, entry in backend.items()},
                "preflight_sha256": sha(preflight_raw), "status": "frozen_not_deployed"}
    (output / "PACKAGE.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    server = "/opt/account-center/releases/remote-mcp-" + commit[:12] + "-upload"
    commands = output / "upload-commands"
    commands.mkdir()
    parts = []
    for name, data in (("payload", raw), ("operator", operator)):
        names = []
        for index, offset in enumerate(range(0, len(data), 12000)):
            part = f"{name}.part{index:03}"
            content = data[offset:offset + 12000]
            names.append(part)
            parts.append((part, sha(content)))
            command = (
                "set -eu\n/opt/account-center/.venv/bin/python - <<'PY'\n"
                "import base64,hashlib,os\nfrom pathlib import Path\nos.umask(0o077)\n"
                f"root=Path({server!r});root.mkdir(parents=True,exist_ok=True)\n"
                f"p=root/{part!r};raw=base64.b64decode({base64.b64encode(content).decode()!r})\n"
                f"assert hashlib.sha256(raw).hexdigest()=={sha(content)!r}\n"
                "if p.exists(): assert p.read_bytes()==raw\n"
                "else:\n t=p.with_suffix(p.suffix+'.tmp');t.write_bytes(raw);os.replace(t,p)\nPY\n"
            )
            assert len(command.encode()) <= 24000
            (commands / (part + ".sh")).write_bytes(command.encode())
        assert all(len(data[index:index + 12000]) <= 24000 for index in range(0, len(data), 12000))
    assembly = (
        "set -eu\n/opt/account-center/.venv/bin/python - <<'PY'\n"
        "import hashlib,os\nfrom pathlib import Path\nos.umask(0o077)\n"
        f"root=Path({server!r})\n"
        f"for name,digest in {parts!r}:\n assert hashlib.sha256((root/name).read_bytes()).hexdigest()==digest\n"
    )
    for prefix, name, data in (("payload", "release.json.gz", raw),
                               ("operator", "remote-mcp-release.py", operator)):
        assembly += (
            f"raw=b''.join(p.read_bytes() for p in sorted(root.glob({(prefix + '.part*')!r})))\n"
            f"assert hashlib.sha256(raw).hexdigest()=={sha(data)!r}\n"
            f"target=root/{name!r}\n"
            "if target.exists(): assert target.read_bytes()==raw\n"
            "else:\n t=target.with_suffix('.tmp');t.write_bytes(raw);os.replace(t,target)\n"
        )
    assembly += "print('UPLOAD_HASH_PASS')\nPY\n"
    assert len(assembly.encode()) <= 24000
    (commands / "assemble.sh").write_bytes(assembly.encode())
    for label in ("test", "production"):
        command = (
            "set -eu\n/opt/account-center/.venv/bin/python - <<'PY'\n"
            "import hashlib\nfrom pathlib import Path\n"
            f"assert hashlib.sha256(Path({(server + '/remote-mcp-release.py')!r}).read_bytes()).hexdigest()=={sha(operator)!r}\n"
            "PY\n/opt/account-center/.venv/bin/python " + server
                   + "/remote-mcp-release.py " + label + " --package " + server
                   + " --package-sha256 " + sha(raw) + "\n")
        (output / ("cloud-" + label + ".sh")).write_bytes(command.encode())
    print(json.dumps({key: value for key, value in manifest.items() if key not in {"backend", "static"}}))
    print("Frozen package: " + str(output))


if __name__ == "__main__":
    main()
