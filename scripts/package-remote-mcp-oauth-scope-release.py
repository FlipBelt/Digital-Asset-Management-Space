"""Freeze one reviewed OAuth scope runtime change; upload a small, fully bound delta."""
import argparse
import base64
import gzip
import hashlib
import json
import runpy
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIVE = "a160657200a93f05050d5c69d31ff7d0f966a448"
OLD_PACKAGE_SHA = "218bfb22885ea98a5cb6d90987dd054e6f34d3fd513b2ec3b32215e2bd09a97f"
BASELINE_OPERATOR_SHA = "88a31a35ceeaa1bc69756aafd55bc997d003587aa48d92e47d2470851606487b"
TARGET = "app/core/mcp_oauth.py"
OPERATOR = "deploy/remote-mcp-oauth-scope-release.py"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT)


def build(commit, base, output):
    assert len(commit) == 40 and all(char in "0123456789abcdef" for char in commit)
    assert git("rev-parse", "HEAD").decode().strip() == commit
    assert not git("status", "--porcelain", "--untracked-files=no"), "Commit tracked changes before freezing"
    git("merge-base", "--is-ancestor", LIVE, commit)
    changed = git("diff", "--name-only", LIVE, commit, "--", "backend/app", "backend/alembic",
                  "backend/pyproject.toml", "backend/uv.lock", "backend/alembic.ini")
    assert set(changed.decode().splitlines()) == {"backend/" + TARGET}, "Only OAuth runtime may change"
    tree = git("rev-parse", commit + ":frontend").decode().strip()
    assert tree == git("rev-parse", LIVE + ":frontend").decode().strip(), "Frontend source changed"
    old_raw = (base / "release.json.gz").read_bytes()
    assert sha(old_raw) == OLD_PACKAGE_SHA
    old = json.loads(gzip.decompress(old_raw))
    verifier = runpy.run_path(str(ROOT / "scripts/verify-remote-mcp-release.py"))
    baseline = verifier["frozen_manifest"](base)
    assert baseline["sha256"] == OLD_PACKAGE_SHA
    assert baseline["commit"] == LIVE and baseline["operator_sha256"] == BASELINE_OPERATOR_SHA
    for label in ("test", "production"):
        receipt = json.loads((base / (label + "-server-PASS.json")).read_bytes())
        assert receipt["status"] == "PASS" and receipt["commit"] == LIVE
        assert receipt["package_sha256"] == OLD_PACKAGE_SHA and receipt["schema"] == "f13g20261016"
        assert receipt["environment"] == label and receipt["operator_sha256"] == BASELINE_OPERATOR_SHA
        public = json.loads((base / (label + "-public-PASS.json")).read_bytes())
        assert public["status"] == "PASS" and public["environment"] == label
        assert public["commit"] == LIVE and public["package_sha256"] == OLD_PACKAGE_SHA
        assert public["schema"] == "f13g20261016" and public["operator_sha256"] == BASELINE_OPERATOR_SHA
    operator = git("show", commit + ":" + OPERATOR)
    namespace = {"__name__": "frozen_oauth_scope_operator"}
    exec(compile(operator, OPERATOR, "exec"), namespace)
    assert namespace["LIVE"] == LIVE and namespace["OLD_PACKAGE_SHA"] == OLD_PACKAGE_SHA
    assert namespace["BASELINE_OPERATOR_SHA"] == BASELINE_OPERATOR_SHA
    encoded = namespace["encoded"]
    data = git("show", commit + ":backend/" + TARGET)
    assert base64.b64decode(old["backend"][TARGET]["data"], validate=True) == (
        git("show", LIVE + ":backend/" + TARGET)
    )
    assert sha(data) != old["backend"][TARGET]["sha256"], "No runtime change to release"
    compile(data, TARGET, "exec")
    delta = {
        "kind": "remote-mcp-oauth-scope", "commit": commit, "live_base": LIVE,
        "old_package_sha256": OLD_PACKAGE_SHA, "schema": namespace["SCHEMA"],
        "runtime": {"name": TARGET, "data": base64.b64encode(data).decode(),
                    "sha256": sha(data), "old_sha256": old["backend"][TARGET]["sha256"]},
        "operator": {"data": base64.b64encode(operator).decode(), "sha256": sha(operator)},
        "hotfix": {"baseline_commit": LIVE, "baseline_package_sha256": OLD_PACKAGE_SHA,
                   "schema_migration_performed": False, "runtime_changed": TARGET,
                   "frontend_source_tree": tree}, "static": {},
    }
    for label in ("test", "production"):
        entries = old["static"][label]
        metadata = json.loads(base64.b64decode(entries["release-meta.json"]["data"]))
        metadata.update(commit=commit, backend_commit=commit)
        raw = encoded(metadata)
        old_files = {name: entry["sha256"] for name, entry in entries.items()}
        delta["static"][label] = {
            "old_files": old_files, "new_files": {**old_files, "release-meta.json": sha(raw)},
            "metadata": {"data": base64.b64encode(raw).decode(), "sha256": sha(raw)},
        }
    spec = namespace["rebuild"](old, delta)
    full = namespace["portable_gzip"](encoded(spec))
    assert json.loads(gzip.decompress(full)) == spec
    delta["package_sha256"] = sha(full)
    wire = gzip.compress(encoded(delta), compresslevel=9, mtime=0)
    assert len(wire) <= 24000, "Delta exceeds single-file delivery budget"
    anchor = ROOT / ".deploy-artifacts"
    output = output.absolute()
    assert ".." not in output.parts and output.is_relative_to(anchor)
    for parent in (output, *output.parents):
        assert not parent.is_symlink() and not parent.is_junction(), "Linked artifact path refused"
        if parent == anchor:
            break
    assert output.resolve().is_relative_to(anchor) and anchor.resolve() == anchor
    output.mkdir(parents=True, exist_ok=False)
    (output / "release.json.gz").write_bytes(full)
    (output / "release-delta.json.gz").write_bytes(wire)
    # Existing public verifier expects this artifact filename; the old operator is untouched.
    (output / "remote-mcp-release.py").write_bytes(operator)
    manifest = {
        "commit": commit, "kind": spec["kind"], "sha256": sha(full), "bytes": len(full),
        "operator_sha256": sha(operator), "delta_sha256": sha(wire), "delta_bytes": len(wire),
        "source_base": LIVE, "live_base": LIVE, "schema": namespace["SCHEMA"],
        "backend": {name: entry["sha256"] for name, entry in spec["backend"].items()},
        "static": {label: item["new_files"] for label, item in delta["static"].items()},
        "hotfix": delta["hotfix"], "status": "frozen_not_deployed",
    }
    (output / "PACKAGE.json").write_bytes(encoded(manifest))
    for label, entries in spec["static"].items():
        for name, entry in entries.items():
            assert not Path(name).is_absolute() and ".." not in Path(name).parts
            destination = output / ("static-" + label) / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            raw = base64.b64decode(entry["data"], validate=True)
            assert sha(raw) == entry["sha256"]
            destination.write_bytes(raw)
    server = "/opt/account-center/releases/remote-mcp-oauth-scope-" + commit[:12] + "-upload"
    assembly = (
        "set -eu\n/opt/account-center/.venv/bin/python - <<'PY'\n"
        "import base64,gzip,hashlib,json,os\nfrom pathlib import Path\nos.umask(0o077)\n"
        f"root=Path({server!r});root.mkdir(parents=True,exist_ok=True)\n"
        "raw=(root/'release-delta.json.gz').read_bytes()\n"
        f"assert hashlib.sha256(raw).hexdigest()=={sha(wire)!r}\n"
        "delta=json.loads(gzip.decompress(raw))\n"
        "operator=base64.b64decode(delta['operator']['data'],validate=True)\n"
        f"assert hashlib.sha256(operator).hexdigest()=={sha(operator)!r}\n"
        "target=root/'remote-mcp-release.py'\n"
        "if target.exists(): assert target.read_bytes()==operator\n"
        "else:\n temporary=target.with_suffix('.tmp');temporary.write_bytes(operator);os.replace(temporary,target)\n"
        "print('UPLOAD_HASH_PASS')\nPY\n"
    )
    (output / "assembly.sh").write_bytes(assembly.encode())
    for label in ("test", "production"):
        command = (
            "set -eu\n/opt/account-center/.venv/bin/python - <<'PY'\n"
            "import hashlib\nfrom pathlib import Path\n"
            f"assert hashlib.sha256(Path({(server + '/remote-mcp-release.py')!r}).read_bytes()).hexdigest()=={sha(operator)!r}\n"
            "PY\n/opt/account-center/.venv/bin/python " + server + "/remote-mcp-release.py "
            + label + " --delta " + server + "/release-delta.json.gz --delta-sha256 " + sha(wire) + "\n"
        )
        (output / ("cloud-" + label + ".sh")).write_bytes(command.encode())
        assert len(command.encode()) <= 24000
    assert len(assembly.encode()) <= 24000
    # Validate the exact frozen manifest with the existing local-only verification entry point.
    assert verifier["frozen_manifest"](output)["sha256"] == sha(full)
    return {key: value for key, value in manifest.items() if key not in {"backend", "static"}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--commit", required=True)
    parser.add_argument("--base-package", type=Path,
                        default=ROOT / ".deploy-artifacts/remote-mcp-oauth-extension/a160657200a9")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / ".deploy-artifacts/remote-mcp-oauth-scope" / args.commit[:12]
    print(json.dumps(build(args.commit, args.base_package.resolve(), output)), flush=True)
    print("Frozen package: " + str(output.resolve()))


if __name__ == "__main__":
    main()
