"""Rehearse remote MCP migrations only in a new, retained loopback test cluster."""

import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Json

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "f13f20261010"
TARGET = "f13g20261016"
PORT = 55439
OAUTH_TABLES = ("mcp_oauth_clients", "mcp_oauth_requests", "mcp_oauth_grants")
REFUSAL = "Remote MCP OAuth tables contain data"


def checksum(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def rows_fingerprint(db, names):
    result = {}
    for name in names:
        rows = db.execute(sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY 1").format(
            sql.Identifier("public", name)
        )).fetchall()
        result[name] = {"count": len(rows), "sha256": checksum(rows)}
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    args = parser.parse_args()
    pg_bin = args.pg_bin.resolve()
    for name in ("initdb.exe", "pg_ctl.exe", "pg_dump.exe"):
        if not (pg_bin / name).is_file():
            raise RuntimeError("Missing PostgreSQL runtime program: " + name)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            raise RuntimeError("Port 55439 is occupied; never reuse an existing cluster")
    marker = uuid4().hex[:10]
    output = (ROOT / ".local" / "remote-mcp-rehearsal" / marker).resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        raise RuntimeError("Rehearsal evidence must remain under this checkout's .local")
    output.mkdir(parents=True, exist_ok=False)
    cluster = output / "cluster"
    database = "dam_v13_tests_remote_mcp_" + marker
    connection = {"host": "127.0.0.1", "port": PORT, "user": "preflight", "connect_timeout": 3}
    environment = {
        key: value for key, value in os.environ.items()
        if key.upper() not in {"PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD", "PGSERVICE"}
    } | {
        "APP_ENV": "local", "DINGTALK_ENABLED": "false", "DINGTALK_WEB_ENABLED": "false",
        "AGENT_CONNECTOR_ENABLED": "false", "AGENT_MCP_ENABLED": "false",
        "AI_IMPORT_ENABLED": "false", "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1", "ASSET_CENTER_ISOLATED_TESTS": "1",
        "ASSET_CENTER_TEST_PORT": str(PORT),
        "DATABASE_URL": f"postgresql+psycopg://preflight@127.0.0.1:{PORT}/{database}",
    }

    def run(command, name, *, refused=False, timeout=120):
        log_path = output / (name + ".log")
        # Windows postgres inherits pg_ctl's handles; a PIPE can keep communicate waiting.
        with log_path.open("w", encoding="utf-8") as stream:
            try:
                completed = subprocess.run(
                    command, cwd=ROOT / "backend", env=environment,
                    stdout=stream, stderr=subprocess.STDOUT, check=False, timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(name + " timed out; inspect " + str(output)) from exc
        log = log_path.read_text(encoding="utf-8", errors="replace")
        if refused:
            if completed.returncode == 0 or REFUSAL not in log:
                raise RuntimeError(name + " did not refuse safely; inspect " + str(output))
        elif completed.returncode:
            raise RuntimeError(name + " failed; inspect " + str(output))
        print(name + ": passed", flush=True)
        return log

    def connect(*, administrative=False):
        db = psycopg.connect(
            dbname="postgres" if administrative else database,
            autocommit=administrative, **connection,
        )
        try:
            assert db.execute("SELECT host(inet_server_addr()), inet_server_port()").fetchone() == (
                "127.0.0.1", PORT,
            )
            assert Path(db.execute("SHOW data_directory").fetchone()[0]).resolve() == cluster
        except BaseException:
            db.close()
            raise
        return db

    def revision(db):
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [(TARGET,)]

    def schema_fingerprint(names):
        dump = subprocess.run(
            [str(pg_bin / "pg_dump.exe"), "--host=127.0.0.1", f"--port={PORT}",
             "--username=preflight", "--schema-only", "--no-owner", "--no-privileges",
             "--no-comments", *["--table=public." + name for name in names], database],
            cwd=ROOT / "backend", env=environment, capture_output=True, check=False, timeout=30,
        )
        if dump.returncode:
            raise RuntimeError("Cannot fingerprint the isolated business schema")
        stable = b"\n".join(
            line for line in dump.stdout.splitlines()
            if not line.startswith((b"--", b"\\restrict ", b"\\unrestrict "))
        )
        return hashlib.sha256(stable).hexdigest()

    def verify_business(names, before):
        with connect() as db:
            assert rows_fingerprint(db, names) == before["rows"], "Existing business data changed"
            actual = {row[0] for row in db.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )}
            assert set(names) <= actual, "Existing business tables disappeared"
        assert schema_fingerprint(names) == before["schema"], "Existing business schema changed"

    def refuse_populated_downgrade(label, names, before):
        with connect() as db:
            revision(db)
            populated = rows_fingerprint(db, OAUTH_TABLES)
        run([sys.executable, "-B", "-m", "alembic", "downgrade", BASELINE], label, refused=True)
        with connect() as db:
            revision(db)
            assert rows_fingerprint(db, OAUTH_TABLES) == populated, "OAuth rows changed on refusal"
        verify_business(names, before)

    run([str(pg_bin / "initdb.exe"), "-D", str(cluster), "-U", "preflight", "--auth=trust",
         "--no-locale", "--encoding=UTF8"], "initdb")
    try:
        run([str(pg_bin / "pg_ctl.exe"), "-D", str(cluster), "-l", str(output / "postgres.log"),
             "-o", f"-h 127.0.0.1 -p {PORT}", "-w", "start"], "start")
        with connect(administrative=True) as db:
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        run([sys.executable, "-B", "-m", "alembic", "upgrade", BASELINE], "baseline-upgrade")
        run([sys.executable, "-B", "-m", "app.cli.seed"], "baseline-seed")
        user_id, client_id = uuid4(), uuid4()
        with connect() as db:
            db.execute(
                "INSERT INTO users(id,username,password_hash,is_active) VALUES(%s,%s,%s,false)",
                (user_id, "synthetic-mcp-migration-" + marker, "!disabled-synthetic-user!"),
            )
            names = [row[0] for row in db.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename <> 'alembic_version' ORDER BY tablename"
            )]
            assert not set(names) & set(OAUTH_TABLES)
            before = {"rows": rows_fingerprint(db, names)}
        before["schema"] = schema_fingerprint(names)
        run([sys.executable, "-B", "-m", "alembic", "upgrade", TARGET], "remote-upgrade")
        verify_business(names, before)
        with connect() as db:
            revision(db)
            assert all(item["count"] == 0 for item in rows_fingerprint(db, OAUTH_TABLES).values())
        run([sys.executable, "-B", "-m", "alembic", "downgrade", BASELINE], "empty-downgrade")
        verify_business(names, before)
        with connect() as db:
            assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [(BASELINE,)]
            assert not set(OAUTH_TABLES) & {row[0] for row in db.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public'"
            )}
        run([sys.executable, "-B", "-m", "alembic", "upgrade", TARGET], "remote-reupgrade")
        verify_business(names, before)
        run([sys.executable, "-B", "-c", (
            "from fastapi.testclient import TestClient; from app.main import app; "
            "c=TestClient(app); "
            "assert c.post('/mcp',json={'jsonrpc':'2.0','id':1,'method':'initialize'}).status_code==404; "
            "assert c.get('/mcp').status_code==404; c.close(); print('MCP disabled: 404')"
        )], "disabled-mcp")
        scopes = Json(["asset:read"])
        callback, resource = "http://127.0.0.1:12345/callback", "https://mcp.example.invalid/mcp"
        with connect() as db:
            db.execute(
                "INSERT INTO mcp_oauth_clients "
                "(id,client_id,client_name,redirect_uris,scopes,grant_types,auth_method) "
                "VALUES(%s,%s,%s,%s,%s,%s,'none')",
                (client_id, "mcl_" + "x" * 43, "Synthetic migration client", Json([callback]),
                 scopes, Json(["authorization_code", "refresh_token"])),
            )
        # Progressive insertion reaches each guard first: clients, requests, then grants.
        refuse_populated_downgrade("refuse-client-data", names, before)
        with connect() as db:
            db.execute(
                "INSERT INTO mcp_oauth_requests "
                "(id,request_hash,client_id,redirect_uri,state,code_challenge,scopes,resource,"
                "issuer,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (uuid4(), "2" * 64, client_id, callback, "synthetic-state", "c" * 43, scopes,
                 resource, resource.removesuffix("/mcp") + "/mcp-oauth",
                 datetime.now(UTC) + timedelta(minutes=5)),
            )
        refuse_populated_downgrade("refuse-request-data", names, before)
        with connect() as db:
            db.execute(
                "INSERT INTO mcp_oauth_grants "
                "(id,client_id,user_id,family_id,token_hash,scopes,redirect_uri,resource,"
                "issuer,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (uuid4(), client_id, user_id, uuid4(), "3" * 64, scopes, callback, resource,
                 resource.removesuffix("/mcp") + "/mcp-oauth",
                 datetime.now(UTC) + timedelta(minutes=5)),
            )
        refuse_populated_downgrade("refuse-grant-data", names, before)
    finally:
        if (cluster / "postmaster.pid").is_file():
            run([str(pg_bin / "pg_ctl.exe"), "-D", str(cluster), "-w", "stop"], "stop")
    (output / "REHEARSAL.md").write_text(
        "# Remote MCP 隔离迁移演练\n\n"
        f"- 数据库：127.0.0.1:{PORT}/{database}；全新集群，已停止，目录与日志保留。\n"
        f"- 迁移：{BASELINE} → {TARGET} → {BASELINE} → {TARGET}，空表回退通过。\n"
        f"- 原有业务表：{len(names)} 张，表结构和种子数据逐表摘要保持一致。\n"
        f"- 结构 SHA-256：{before['schema']}\n"
        f"- 数据摘要 SHA-256：{checksum(before['rows'])}\n"
        "- 客户端、请求、令牌表依次加入合成记录；每次降级均拒绝，版本与全部记录保持。\n"
        "- 关闭开关后 POST/GET /mcp 均为 404。\n"
        "- 未运行生产连接、部署或真人业务验收；本演练不重复业务回归测试。\n",
        encoding="utf-8",
    )
    print("evidence: " + str(output / "REHEARSAL.md"), flush=True)


if __name__ == "__main__":
    main()
