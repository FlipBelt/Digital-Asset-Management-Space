"""One-file OAuth scope hotfix; fixed deployed baseline, no schema/config/proxy edits."""
import argparse
import base64
import copy
import gzip
import hashlib
import importlib.util
import json
import os
import shutil
import struct
import zlib
from datetime import UTC, datetime
from pathlib import Path

LIVE = "a160657200a93f05050d5c69d31ff7d0f966a448"
OLD_PACKAGE_SHA = "218bfb22885ea98a5cb6d90987dd054e6f34d3fd513b2ec3b32215e2bd09a97f"
BASELINE_OPERATOR_SHA = "88a31a35ceeaa1bc69756aafd55bc997d003587aa48d92e47d2470851606487b"
HELPER_OPERATOR_SHA = "7c314c7634c74f6d3dab4165778f15f50545871ab79f85cf8f945215123d3683"
BASELINE_ROOT = Path("/opt/account-center/releases/remote-mcp-oauth-extension-a160657200a9-upload")
HELPER_ROOT = Path("/opt/account-center/releases/remote-mcp-210b85f7f947-upload")
TARGET = "app/core/mcp_oauth.py"
SCHEMA = "f13g20261016"
KIND = "digital-center-remote-mcp"
NGINX = Path("/etc/nginx/conf.d/account-center.conf")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def portable_gzip(raw):
    # Stored DEFLATE blocks guarantee identical bytes across Python/zlib platforms.
    parts = [b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x00\xff"]
    for offset in range(0, len(raw), 65535):
        block = raw[offset:offset + 65535]
        parts += [b"\x01" if offset + len(block) == len(raw) else b"\x00",
                  struct.pack("<HH", len(block), len(block) ^ 65535), block]
    return b"".join(parts) + struct.pack("<II", zlib.crc32(raw) & 0xffffffff, len(raw) & 0xffffffff)


def rebuild(old, delta):
    assert delta["kind"] == "remote-mcp-oauth-scope"
    assert len(delta["commit"]) == 40 and all(char in "0123456789abcdef" for char in delta["commit"])
    assert delta["commit"] != LIVE
    assert delta["live_base"] == LIVE and delta["old_package_sha256"] == OLD_PACKAGE_SHA
    assert delta["runtime"]["name"] == TARGET and delta["schema"] == SCHEMA
    assert set(delta["static"]) == {"test", "production"}
    assert old["commit"] == LIVE and old["kind"] == KIND
    assert old["operator_sha256"] == BASELINE_OPERATOR_SHA
    new = copy.deepcopy(old)
    new.update(commit=delta["commit"], source_base=LIVE, live_base=LIVE,
               operator_sha256=delta["operator"]["sha256"], hotfix=delta["hotfix"])
    runtime = delta["runtime"]
    previous = old["backend"][TARGET]
    assert runtime["old_sha256"] == previous["sha256"]
    assert sha(base64.b64decode(runtime["data"], validate=True)) == runtime["sha256"]
    new["backend"][TARGET] = {key: runtime[key] for key in ("data", "sha256")}
    new["backend"][TARGET]["old_sha256"] = runtime["old_sha256"]
    for label in ("test", "production"):
        current = delta["static"][label]
        assert len(old["static"][label]) == 26
        assert current["old_files"] == {name: entry["sha256"] for name, entry in old["static"][label].items()}
        metadata = json.loads(base64.b64decode(old["static"][label]["release-meta.json"]["data"]))
        assert metadata["commit"] == metadata["backend_commit"] == LIVE
        metadata.update(commit=delta["commit"], backend_commit=delta["commit"])
        raw = base64.b64decode(current["metadata"]["data"], validate=True)
        assert json.loads(raw) == metadata and sha(raw) == current["metadata"]["sha256"]
        new["static"][label]["release-meta.json"] = current["metadata"]
        assert current["new_files"] == {name: entry["sha256"] for name, entry in new["static"][label].items()}
    return new


def stable_helpers():
    path = HELPER_ROOT / "remote-mcp-release.py"
    assert sha(path.read_bytes()) == HELPER_OPERATOR_SHA
    spec = importlib.util.spec_from_file_location("frozen_remote_mcp_helpers", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def execute(label, delta_path, expected):
    assert label in {"test", "production"}
    raw_delta = delta_path.read_bytes()
    assert sha(raw_delta) == expected
    delta = json.loads(gzip.decompress(raw_delta))
    assert sha(Path(__file__).read_bytes()) == delta["operator"]["sha256"]
    assert sha(base64.b64decode(delta["operator"]["data"], validate=True)) == delta["operator"]["sha256"]
    assert sha((BASELINE_ROOT / "remote-mcp-release.py").read_bytes()) == BASELINE_OPERATOR_SHA
    old_raw = (BASELINE_ROOT / "release.json.gz").read_bytes()
    assert sha(old_raw) == OLD_PACKAGE_SHA
    old = json.loads(gzip.decompress(old_raw))
    new = rebuild(old, delta)
    full = portable_gzip(encoded(new))
    assert sha(full) == delta["package_sha256"]
    package = delta_path.parent
    full_path = package / "release.json.gz"
    if full_path.exists():
        assert full_path.read_bytes() == full
    else:
        full_path.write_bytes(full)
    h = stable_helpers()
    root, static, port, config = h.layout(label)
    code = root / "backend" / TARGET
    assert code.is_file() and not code.is_symlink() and static.is_symlink()
    assert h.files(static.resolve()) == delta["static"][label]["old_files"]
    for name, entry in old["backend"].items():
        assert sha((root / "backend" / name).read_bytes()) == entry["sha256"]
    old_code, new_code = code.read_bytes(), base64.b64decode(delta["runtime"]["data"], validate=True)
    assert sha(old_code) == delta["runtime"]["old_sha256"]
    compile(new_code, TARGET, "exec")
    if label == "production":
        gate = json.loads((package / "test-PASS.json").read_bytes())
        public = json.loads((package / "test-public-PASS.json").read_bytes())
        assert gate["status"] == public["status"] == "PASS"
        assert gate["environment"] == "test" and gate["kind"] == public["kind"] == KIND
        assert gate["commit"] == public["commit"] == delta["commit"]
        assert gate["package_sha256"] == public["package_sha256"] == delta["package_sha256"]
        assert gate["operator_sha256"] == public["operator_sha256"] == delta["operator"]["sha256"]
        assert gate["delta_sha256"] == expected and gate["schema"] == public["schema"] == SCHEMA
        assert gate["rollback_rehearsed_retaining_schema"] and gate["production_untouched_during_test"]
        assert gate["old_business_tables_preserved"] == 75 and gate["schema_migration_performed"] is False
        assert gate["configuration_or_proxy_changed"] is False
        assert public["environment"] == "test" and public["static_files_verified"] == 26
        assert public["business_writes_performed"] is False and set(public["public_checks"]) >= {
            "frozen_static_bytes", "ready", "resource_and_issuer", "oauth_metadata",
            "anonymous_mcp_challenge", "consent_page_headers",
        }
    name = delta["commit"][:12] + "-oauth-scope-" + label
    backup = root / "backups" / name
    target = Path("/var/www/account-center-test-releases" if label == "test"
                  else "/var/www/account-center-prod-releases") / name
    assert not backup.exists() and not target.exists(), "Inspect any prior attempt first"
    old_static = static.resolve()
    backup.mkdir(parents=True, mode=0o700)
    shutil.copy2(code, backup / "mcp_oauth.py.old")
    os.chmod(backup / "mcp_oauth.py.old", 0o600)
    config_sha, nginx_sha = sha(config.read_bytes()), sha(NGINX.read_bytes())
    (backup / "ROLLBACK.json").write_bytes(encoded({
        "old_static": str(old_static), "new_static": str(target), "runtime": str(code),
        "old_runtime_sha256": sha(old_code), "new_runtime_sha256": sha(new_code),
        "config_sha256": config_sha, "nginx_sha256": nginx_sha, "retain_schema": SCHEMA,
    }))
    shutil.copytree(old_static, target, copy_function=shutil.copy2)
    metadata = target / "release-meta.json"
    h.replace(metadata, metadata.read_bytes(), base64.b64decode(delta["static"][label]["metadata"]["data"]))
    for path in [target, *target.rglob("*")]:
        os.chmod(path, 0o755 if path.is_dir() else 0o644)
    assert h.files(target) == delta["static"][label]["new_files"]
    engine, _ = h.engine_for(label)
    log = (backup / "operations.log").open("ab")
    h.LOG = log
    unit = root.name + ".service"
    stopped = False

    def untouched_config():
        assert sha(config.read_bytes()) == config_sha and sha(NGINX.read_bytes()) == nginx_sha

    def link(destination, expected_target):
        assert static.resolve() == expected_target
        temporary = static.with_name(static.name + "-oauth-scope-switch")
        assert not temporary.exists() and not temporary.is_symlink()
        temporary.symlink_to(destination, target_is_directory=True)
        os.replace(temporary, static)

    def switch(candidate):
        h.replace(code, old_code if candidate else new_code, new_code if candidate else old_code)
        link(target if candidate else old_static, old_static if candidate else target)
        untouched_config()

    def production_snapshot():
        production_engine, _ = h.engine_for("production")
        try:
            return {"database": h.fingerprint(production_engine), "service": h.state("account-center.service"),
                    "static": h.files(Path("/var/www/account-center").resolve())}
        finally:
            production_engine.dispose()

    try:
        guard = production_snapshot() if label == "test" else None
        stopped = True
        h.run(["systemctl", "stop", unit])
        before = h.fingerprint(engine)
        assert before["revision"] == SCHEMA
        (backup / "tables-before.json").write_bytes(encoded(before))
        pg_env = {**os.environ, "PGHOST": engine.url.host or "127.0.0.1",
                  "PGPORT": str(engine.url.port or 5432), "PGUSER": engine.url.username,
                  "PGPASSWORD": engine.url.password or "", "PGDATABASE": engine.url.database}
        h.run(["pg_dump", "-Fc", "-f", str(backup / "database.dump")], env=pg_env)
        h.run(["pg_restore", "--list", str(backup / "database.dump")])

        def unchanged():
            assert h.fingerprint(engine) == before
            untouched_config()

        switch(True)
        h.run(["systemctl", "start", unit])
        h.ready(port, candidate=True, label=label)
        unchanged()
        if label == "test":
            h.run(["systemctl", "stop", unit])
            switch(False)
            h.run(["systemctl", "start", unit])
            h.ready(port, candidate=True, label=label)
            unchanged()
            h.run(["systemctl", "stop", unit])
            switch(True)
            h.run(["systemctl", "start", unit])
            h.ready(port, candidate=True, label=label)
            unchanged()
            assert production_snapshot() == guard
        assert sha(code.read_bytes()) == delta["runtime"]["sha256"]
        assert h.files(static.resolve()) == delta["static"][label]["new_files"]
        receipt = {"status": "PASS", "kind": KIND, "commit": delta["commit"], "environment": label,
                   "schema": SCHEMA, "package_sha256": delta["package_sha256"], "delta_sha256": expected,
                   "operator_sha256": delta["operator"]["sha256"], "old_business_tables_preserved": 75,
                   "schema_migration_performed": False, "configuration_or_proxy_changed": False,
                   "backup": str(backup), "database_backup_sha256": sha((backup / "database.dump").read_bytes()),
                   "rollback_rehearsed_retaining_schema": label == "test",
                   "production_untouched_during_test": label == "test",
                   "human_oauth_or_business_uat_performed": False, "completed_at": datetime.now(UTC).isoformat()}
        (backup / "tables-after.json").write_bytes(encoded(h.fingerprint(engine)))
        (package / (label + "-PASS.json")).write_bytes(encoded(receipt))
        return receipt
    except BaseException:
        if stopped:
            h.run(["systemctl", "stop", unit])
            if sha(code.read_bytes()) == sha(new_code):
                h.replace(code, new_code, old_code)
            else:
                assert code.read_bytes() == old_code, "Unknown runtime drift; manual review required"
            if static.resolve() == target:
                link(old_static, target)
            else:
                assert static.resolve() == old_static, "Unknown static drift; manual review required"
            h.run(["systemctl", "start", unit])
            h.ready(port, candidate=True, label=label)
        raise
    finally:
        engine.dispose()
        h.LOG = None
        log.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("environment", choices=("test", "production"))
    parser.add_argument("--delta", type=Path, required=True)
    parser.add_argument("--delta-sha256", required=True)
    args = parser.parse_args()
    import fcntl
    with Path("/var/lock/account-center-remote-mcp.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        print(json.dumps(execute(args.environment, args.delta.resolve(), args.delta_sha256)), flush=True)


if __name__ == "__main__":
    main()
