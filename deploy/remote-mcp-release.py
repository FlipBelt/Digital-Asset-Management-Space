"""Frozen remote MCP operator. Run only after review and environment authorization."""
import argparse
import base64
import gzip
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from dotenv import dotenv_values
from sqlalchemy import create_engine, text

LIVE = "1b216a847cee4f5d73d344510c9a09f069c32a92"
SCHEMA = "f13g20261016"
OLD_SCHEMA = "f13f20261010"
KIND = "digital-center-remote-mcp"
HOST = "https://jtzhzt.flipbeltchina.com"
NEW_TABLES = {"mcp_oauth_clients", "mcp_oauth_requests", "mcp_oauth_grants"}
RUNTIME = {
    "app/core/auth_logging.py", "app/core/config.py", "app/main.py", "app/models/__init__.py",
    "app/schemas/agent_connector.py", "app/api/v1/agent_mcp.py", "app/api/v1/mcp_oauth.py",
    "app/core/mcp_oauth.py", "app/models/mcp_oauth.py", "app/schemas/mcp_oauth.py",
    "alembic/versions/f13g20261016_mcp_oauth.py",
}
LOG = None


def sha(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def run(args, **kwargs):
    with open(os.devnull, "ab") as null:
        subprocess.run(args, stdout=LOG or null, stderr=LOG or null, check=True,
                       timeout=120, **kwargs)


def state(unit):
    return subprocess.check_output(
        ["systemctl", "show", unit, "-p", "MainPID", "-p", "ActiveState", "-p", "User",
         "-p", "WorkingDirectory"], text=True, timeout=15,
    ).strip()


def layout(label):
    root = Path("/opt/account-center-test" if label == "test" else "/opt/account-center")
    return root, Path("/var/www/test" if label == "test" else "/var/www/account-center"), (
        8200 if label == "test" else 8100
    ), Path("/etc") / root.name / "app.env"


def engine_for(label):
    root, _, _, config = layout(label)
    cfg = {key: value for key, value in dotenv_values(config).items() if value is not None}
    engine = create_engine(cfg["DATABASE_URL"])
    assert engine.url.database == ("account_center_test" if label == "test" else "account_center")
    current = state(root.name + ".service")
    assert "User=accountcenter" in current and "WorkingDirectory=" + str(root / "backend") in current
    return engine, cfg


def fingerprint(engine, names=None):
    with engine.connect() as db:
        db.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY"))
        tables = list(db.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public' "
                                     "AND tablename <> 'alembic_version' ORDER BY tablename")).scalars())
        names = sorted(names or [name for name in tables if name not in NEW_TABLES])
        assert len(names) == 75 and set(names) <= set(tables)
        rows, definitions = {}, {}
        for name in names:
            quoted = engine.dialect.identifier_preparer.quote(name)
            data = sorted(db.execute(text("SELECT to_jsonb(t)::text FROM " + quoted + " t")).scalars())
            rows[name] = {"rows": len(data), "sha256": sha(encoded(data))}
            columns = db.execute(text(
                "SELECT a.attnum,a.attname,format_type(a.atttypid,a.atttypmod),a.attnotnull,"
                "pg_get_expr(d.adbin,d.adrelid),a.attidentity,a.attgenerated FROM pg_attribute a "
                "LEFT JOIN pg_attrdef d ON d.adrelid=a.attrelid AND d.adnum=a.attnum "
                "WHERE a.attrelid=to_regclass(:name) AND a.attnum>0 AND NOT a.attisdropped "
                "ORDER BY a.attnum"), {"name": "public." + name}).all()
            constraints = db.execute(text(
                "SELECT conname,pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conrelid=to_regclass(:name) ORDER BY conname"), {"name": "public." + name}).all()
            indexes = db.execute(text("SELECT indexname,indexdef FROM pg_indexes "
                                      "WHERE schemaname='public' AND tablename=:name ORDER BY indexname"),
                                 {"name": name}).all()
            triggers = db.execute(text("SELECT tgname,pg_get_triggerdef(oid) FROM pg_trigger "
                                       "WHERE tgrelid=to_regclass(:name) AND NOT tgisinternal "
                                       "ORDER BY tgname"), {"name": "public." + name}).all()
            options = db.execute(text("SELECT relrowsecurity,relforcerowsecurity,reloptions "
                                      "FROM pg_class WHERE oid=to_regclass(:name)"),
                                 {"name": "public." + name}).all()
            definitions[name] = sha(encoded([list(map(list, part)) for part in (
                columns, constraints, indexes, triggers, options,
            )]))
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    return {"rows": rows, "schema": definitions, "revision": revision, "tables": tables}


def files(root):
    return {path.relative_to(root).as_posix(): sha(path.read_bytes())
            for path in root.rglob("*") if path.is_file()}


def public_local(port, path, method="GET"):
    request = urllib.request.Request("http://127.0.0.1:" + str(port) + path, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.read(), {k.lower(): v for k, v in response.headers.items()}
    except urllib.error.HTTPError as error:
        return error.code, error.read(), {k.lower(): v for k, v in error.headers.items()}


def ready(port, *, candidate=False, label=None):
    for _ in range(40):
        try:
            status, body, _ = public_local(port, "/api/v1/health/ready")
            if status == 200 and json.loads(body).get("database") == "ok":
                break
        except (OSError, ValueError):
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Readiness timeout")
    assert public_local(port, "/api/v1/agent/capabilities")[0] in ((401,) if candidate else (401, 404))
    if candidate:
        expected = settings(label)
        status, _, headers = public_local(port, "/mcp", "POST")
        assert status == 401 and "resource_metadata" in headers.get("www-authenticate", "")
        status, body, _ = public_local(port, "/.well-known/oauth-protected-resource/mcp")
        assert status == 200 and json.loads(body)["resource"] == expected["AGENT_MCP_PUBLIC_URL"]


def settings(label):
    prefix = "/test-api" if label == "test" else ""
    return {
        "AGENT_CONNECTOR_ENABLED": "true", "AGENT_MCP_ENABLED": "true",
        "AGENT_FRONTEND_URL": HOST + ("/test/" if label == "test" else "/"),
        "AGENT_MCP_PUBLIC_URL": HOST + prefix + "/mcp",
        "AGENT_MCP_ALLOWED_ORIGINS": '["https://chatgpt.com"]',
        "AGENT_MCP_ALLOWED_REDIRECT_URIS": "[]", "AGENT_MCP_ACCESS_TOKEN_TTL_SECONDS": "3600",
        "AGENT_MCP_REFRESH_TOKEN_TTL_DAYS": "30",
    }


def upsert(raw, values):
    result = raw.decode("utf-8")
    for key, value in values.items():
        pattern = r"(?m)^(?:export[ \t]+)?" + re.escape(key) + r"=.*(?:\n|$)"
        assert len(re.findall(pattern, result)) <= 1, "Duplicate managed config key"
        replacement = key + "=" + value + "\n"
        if re.search(pattern, result):
            result = re.sub(pattern, lambda _, replacement=replacement: replacement, result)
        else:
            result += ("" if result.endswith("\n") else "\n") + replacement
    return result.encode()


def proxy_block(label, commit):
    prefix, port = ("/test-api", 8200) if label == "test" else ("", 8100)
    locations = [("= " + prefix + "/mcp", "/mcp"),
                 ("^~ " + prefix + "/mcp-oauth/", "/mcp-oauth/"),
                 ("= /.well-known/oauth-protected-resource" + prefix + "/mcp",
                  "/.well-known/oauth-protected-resource/mcp"),
                 ("= /.well-known/oauth-authorization-server" + prefix + "/mcp-oauth",
                  "/.well-known/oauth-authorization-server/mcp-oauth")]
    if label == "production":
        locations += [("= /.well-known/" + name, "/.well-known/" + name)
                      for name in ("oauth-protected-resource", "oauth-authorization-server")]
    lines = ["    # BEGIN REMOTE_MCP " + label + " " + commit]
    for location, target in locations:
        lines += ["    location " + location + " {", "        access_log off;",
                  f"        proxy_pass http://127.0.0.1:{port}{target};",
                  "        proxy_http_version 1.1;", "        proxy_buffering off;",
                  "        proxy_set_header Host $host;",
                  "        proxy_set_header X-Real-IP $remote_addr;",
                  "        proxy_set_header X-Forwarded-For $remote_addr;",
                  "        proxy_set_header X-Forwarded-Proto $scheme;",
                  "        proxy_hide_header Referrer-Policy;",
                  "        add_header Referrer-Policy no-referrer always;", "    }"]
    route = "/test/agent/oauth" if label == "test" else "/agent/oauth"
    lines += ["    location ^~ " + route + " {", "        access_log off;",
              "        add_header Cache-Control no-store always;",
              "        add_header Referrer-Policy no-referrer always;",
              "        add_header X-Frame-Options DENY always;",
              '        add_header Content-Security-Policy "frame-ancestors \'none\'" always;',
              "        add_header X-Content-Type-Options nosniff always;"]
    if label == "test":
        lines += ["        root /var/www;", "        try_files /test/index.html =404;"]
    else:
        lines += ["        try_files /index.html =404;"]
    return "\n".join(lines + ["    }", "    # END REMOTE_MCP " + label + " " + commit, ""])


def patch_proxy(raw, label, commit):
    content = raw.decode()
    block = proxy_block(label, commit)
    assert "# BEGIN REMOTE_MCP " + label not in content
    prefix = "/test-api" if label == "test" else ""
    for route in (prefix + "/mcp", prefix + "/mcp-oauth/",
                  "/test/agent/oauth" if label == "test" else "/agent/oauth"):
        assert not re.search(r"location\s+(?:=\s+|\^~\s+)?" + re.escape(route) + r"\s*\{", content)
    anchor = re.compile(r"(?m)^[ \t]*root /var/www/account-center;[ \t]*$")
    assert len(anchor.findall(content)) == 1 and "listen 443" in content
    return anchor.sub(lambda match: match.group() + "\n" + block, content, count=1).encode()


def replace(path, expected, data):
    assert sha(path.read_bytes()) == sha(expected), "Live file changed; refusing overwrite"
    metadata = path.stat()
    temporary = path.with_name(path.name + ".remote-mcp-next")
    assert not temporary.exists()
    temporary.write_bytes(data)
    os.chmod(temporary, stat.S_IMODE(metadata.st_mode))
    os.chown(temporary, metadata.st_uid, metadata.st_gid)
    os.replace(temporary, path)


def preflight(nginx):
    assert nginx.is_file() and nginx.is_relative_to(Path("/etc/nginx"))
    run(["nginx", "-t"])
    result = {"created_at": datetime.now(UTC).isoformat(), "status": "PREFLIGHT_PASS",
              "nginx": {"path": str(nginx), "sha256": sha(nginx.read_bytes())}, "environments": {}}
    for label in ("test", "production"):
        root, static, port, config = layout(label)
        assert (root / "backend").is_dir() and not (root / "backend").is_symlink()
        assert config.is_file() and not config.is_symlink()
        assert static.is_symlink() and "ActiveState=active" in state(root.name + ".service")
        metadata = json.loads((static / "release-meta.json").read_bytes())
        assert metadata["commit"] == LIVE and metadata["backend_commit"] == LIVE
        assert metadata["schema"] == OLD_SCHEMA and metadata["environment"] == label
        engine, _ = engine_for(label)
        try:
            snapshot = fingerprint(engine)
            assert snapshot["revision"] == OLD_SCHEMA and not NEW_TABLES & set(snapshot["tables"])
        finally:
            engine.dispose()
        result["environments"][label] = {
            "metadata": metadata, "static_files": files(static.resolve()),
            "static_target": str(static.resolve()), "service": state(root.name + ".service"),
            "backend": {name: sha((root / "backend" / name).read_bytes())
                        if (root / "backend" / name).is_file() else None for name in sorted(RUNTIME)},
            "database": snapshot, "config_sha256": sha(config.read_bytes()),
            "free_bytes": shutil.disk_usage(root).free,
        }
        ready(port)
    return result


def preserve(source, target):
    if not source.exists():
        return
    shutil.copytree(source, target, symlinks=True, dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for path in [source, *source.rglob("*")]:
        destination = target / path.relative_to(source)
        if not path.is_symlink() and destination.exists():
            metadata = path.stat()
            os.chown(destination, metadata.st_uid, metadata.st_gid)
            os.chmod(destination, stat.S_IMODE(metadata.st_mode))


def deploy(label, package, expected):
    global LOG
    raw = (package / "release.json.gz").read_bytes()
    assert sha(raw) == expected
    spec = json.loads(gzip.decompress(raw))
    assert sha(Path(__file__).read_bytes()) == spec["operator_sha256"]
    commit, initial = spec["commit"], spec["preflight"]
    assert re.fullmatch(r"[0-9a-f]{40}", commit) and spec["live_base"] == LIVE
    assert spec["kind"] == KIND and set(spec["backend"]) <= RUNTIME
    assert initial["status"] == "PREFLIGHT_PASS"
    age = datetime.now(UTC) - datetime.fromisoformat(initial["created_at"])
    assert 0 <= age.total_seconds() < 3600, "Fresh preflight required"
    nginx = Path(initial["nginx"]["path"])
    root, static, port, config = layout(label)
    release = commit[:12] + "-remote-mcp-" + label
    backup, stage = root / "backups" / release, root / ("backend-next-" + commit[:12])
    target = Path("/var/www/account-center-test-releases" if label == "test"
                  else "/var/www/account-center-prod-releases") / release
    assert not any(path.exists() for path in (backup, stage, target)), "Inspect prior attempt first"
    baseline = initial["environments"][label]
    assert json.loads((static / "release-meta.json").read_bytes()) == baseline["metadata"]
    assert files(static.resolve()) == baseline["static_files"]
    assert sha(config.read_bytes()) == baseline["config_sha256"]
    if label == "production":
        gate = json.loads((package / "test-PASS.json").read_bytes())
        public = json.loads((package / "test-public-PASS.json").read_bytes())
        assert gate["status"] == public["status"] == "PASS"
        assert gate["commit"] == public["commit"] == commit
        assert gate["package_sha256"] == public["package_sha256"] == expected
        assert gate["operator_sha256"] == public["operator_sha256"] == spec["operator_sha256"]
        assert gate["kind"] == public["kind"] == KIND and gate["schema"] == public["schema"] == SCHEMA
        assert gate["rollback_rehearsed_retaining_schema"] and gate["production_untouched_during_test"]
        assert public["environment"] == "test" and public["business_writes_performed"] is False
        assert set(public["public_checks"]) >= {
            "frozen_static_bytes", "ready", "resource_and_issuer", "oauth_metadata",
            "anonymous_mcp_challenge", "consent_page_headers",
        }
        assert sha(nginx.read_bytes()) == gate["nginx_sha256"]
    else:
        assert sha(nginx.read_bytes()) == initial["nginx"]["sha256"]
    old_proxy, old_config, old_static = nginx.read_bytes(), config.read_bytes(), static.resolve()
    new_proxy, new_config = patch_proxy(old_proxy, label, commit), upsert(old_config, settings(label))
    engine, cfg = engine_for(label)
    for name, entry in spec["backend"].items():
        path = root / "backend" / name
        assert (sha(path.read_bytes()) if path.is_file() else None) == entry["old_sha256"]
    assert shutil.disk_usage(root).free > 600 * 1024 ** 2
    backup.mkdir(parents=True, mode=0o700)
    LOG = (backup / "operations.log").open("ab")
    for path, name in ((config, "app.env"), (nginx, "nginx.conf")):
        shutil.copy2(path, backup / name)
        os.chmod(backup / name, 0o600)
    preserve(root / "backend", stage)
    for name, entry in spec["backend"].items():
        destination = stage / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(entry["data"], validate=True)
        assert sha(data) == entry["sha256"]
        destination.write_bytes(data)
        os.chown(destination, (root / "backend").stat().st_uid, (root / "backend").stat().st_gid)
        os.chmod(destination, 0o644)
    target.mkdir(parents=True)
    for name, entry in spec["static"][label].items():
        assert not Path(name).is_absolute() and ".." not in Path(name).parts
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = base64.b64decode(entry["data"], validate=True)
        assert sha(data) == entry["sha256"]
        path.write_bytes(data)
    for path in [target, *target.rglob("*")]:
        os.chmod(path, 0o755 if path.is_dir() else 0o644)
    environment = {**os.environ, **cfg, **settings(label), "PYTHONDONTWRITEBYTECODE": "1",
                   "PGOPTIONS": "-c lock_timeout=10000 -c statement_timeout=60000"}
    python = str(root / ".venv/bin/python")
    run([python, "-m", "compileall", "-q", str(stage / "app"), str(stage / "alembic")])
    run(["runuser", "-u", "accountcenter", "--", python, "-c",
         ("import PIL; from app.api.v1.agent_mcp import TOOLS; assert len(TOOLS)==13; "
          "from app.main import app")],
        cwd=stage, env=environment)
    unit = root.name + ".service"
    old_moved = new_moved = stopped = False

    def switch(candidate):
        nonlocal old_moved, new_moved
        if candidate:
            preserve(root / "backend" / ".local", stage / ".local")
            os.rename(root / "backend", backup / "backend-old")
            old_moved = True
            os.rename(stage, root / "backend")
            new_moved = True
        else:
            preserve(root / "backend" / ".local", backup / "backend-old" / ".local")
            os.rename(root / "backend", stage)
            new_moved = False
            os.rename(backup / "backend-old", root / "backend")
            old_moved = False
        expected_static = old_static if candidate else target
        assert static.resolve() == expected_static
        temporary = static.with_name(static.name + "-remote-mcp-switch")
        assert not temporary.exists() and not temporary.is_symlink()
        temporary.symlink_to(target if candidate else old_static, target_is_directory=True)
        os.replace(temporary, static)
        replace(config, old_config if candidate else new_config, new_config if candidate else old_config)
        replace(nginx, old_proxy if candidate else new_proxy, new_proxy if candidate else old_proxy)
        run(["nginx", "-t"])
        run(["systemctl", "reload", "nginx"])

    before = None
    production_guard = None
    try:
        if label == "test":
            production_engine, _ = engine_for("production")
            try:
                production_guard = {"database": fingerprint(production_engine),
                                    "service": state("account-center.service"),
                                    "static": files(Path("/var/www/account-center").resolve())}
            finally:
                production_engine.dispose()
        stopped = True
        run(["systemctl", "stop", unit])
        before = fingerprint(engine)
        assert before["revision"] == OLD_SCHEMA
        (backup / "tables-before.json").write_bytes(encoded(before))
        (backup / "ROLLBACK.json").write_bytes(encoded({
            "commit": commit, "environment": label, "old_static": str(old_static),
            "old_backend": str(backup / "backend-old"), "config_backup": str(backup / "app.env"),
            "nginx_backup": str(backup / "nginx.conf"), "nginx_path": str(nginx),
            "database_backup": str(backup / "database.dump"), "retain_schema": SCHEMA,
        }))
        pg_env = {**os.environ, "PGHOST": engine.url.host or "127.0.0.1",
                  "PGPORT": str(engine.url.port or 5432), "PGUSER": engine.url.username,
                  "PGPASSWORD": engine.url.password or "", "PGDATABASE": engine.url.database}
        run(["pg_dump", "-Fc", "-f", str(backup / "database.dump")], env=pg_env)
        run(["pg_restore", "--list", str(backup / "database.dump")])
        run(["runuser", "-u", "accountcenter", "--", python, "-m", "alembic", "upgrade", SCHEMA],
            cwd=stage, env=environment)

        def unchanged():
            current = fingerprint(engine, before["rows"])
            assert current["revision"] == SCHEMA
            assert current["rows"] == before["rows"] and current["schema"] == before["schema"]
            assert set(current["tables"]) == set(before["tables"]) | NEW_TABLES

        unchanged()
        switch(True)
        run(["systemctl", "start", unit])
        ready(port, candidate=True, label=label)
        unchanged()
        if label == "test":
            run(["systemctl", "stop", unit])
            switch(False)
            run(["systemctl", "start", unit])
            ready(port)
            unchanged()
            run(["systemctl", "stop", unit])
            switch(True)
            run(["systemctl", "start", unit])
            ready(port, candidate=True, label=label)
            unchanged()
            production_engine, _ = engine_for("production")
            try:
                assert production_guard == {"database": fingerprint(production_engine),
                                            "service": state("account-center.service"),
                                            "static": files(Path("/var/www/account-center").resolve())}
            finally:
                production_engine.dispose()
        assert files(target) == {name: entry["sha256"] for name, entry in spec["static"][label].items()}
        assert all(sha((root / "backend" / name).read_bytes()) == entry["sha256"]
                   for name, entry in spec["backend"].items())
        receipt = {"status": "PASS", "kind": KIND, "commit": commit, "environment": label,
                   "operator_sha256": spec["operator_sha256"],
                   "package_sha256": expected, "schema": SCHEMA, "old_business_tables_preserved": 75,
                   "business_snapshot_sha256": sha(encoded(before)), "nginx_sha256": sha(new_proxy),
                   "database_backup_sha256": sha((backup / "database.dump").read_bytes()),
                   "backup": str(backup), "rollback_rehearsed_retaining_schema": label == "test",
                   "production_untouched_during_test": label == "test",
                   "human_oauth_or_business_uat_performed": False,
                   "completed_at": datetime.now(UTC).isoformat()}
        (backup / "tables-before.json").write_bytes(encoded(before))
        (backup / "tables-after.json").write_bytes(encoded(fingerprint(engine, before["rows"])))
        (package / (label + "-PASS.json")).write_bytes(encoded(receipt))
        return receipt
    except BaseException:
        if stopped:
            run(["systemctl", "stop", unit])
            if new_moved:
                preserve(root / "backend" / ".local", backup / "backend-old" / ".local")
                os.rename(root / "backend", backup / "backend-failed")
            if old_moved:
                os.rename(backup / "backend-old", root / "backend")
            if static.resolve() == target:
                temporary = static.with_name(static.name + "-remote-mcp-rollback")
                assert not temporary.exists() and not temporary.is_symlink()
                temporary.symlink_to(old_static, target_is_directory=True)
                os.replace(temporary, static)
            if config.read_bytes() != old_config:
                replace(config, new_config, old_config)
            if nginx.read_bytes() != old_proxy:
                replace(nginx, new_proxy, old_proxy)
            run(["nginx", "-t"])
            run(["systemctl", "reload", "nginx"])
            run(["systemctl", "start", unit])
            ready(port)
        raise
    finally:
        engine.dispose()
        LOG.close()
        LOG = None


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["preflight", "test", "production"])
    parser.add_argument("--nginx-config", type=Path)
    parser.add_argument("--package", type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument("--package-sha256")
    args = parser.parse_args()
    if args.mode == "preflight":
        assert args.nginx_config is not None
        value = preflight(args.nginx_config.resolve())
    else:
        assert re.fullmatch(r"[0-9a-f]{64}", args.package_sha256 or "")
        import fcntl
        with Path("/var/lock/account-center-remote-mcp.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            value = deploy(args.mode, args.package.resolve(), args.package_sha256)
    print(json.dumps(value, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
