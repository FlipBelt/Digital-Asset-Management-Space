"""Run catalog migration and API checks only on a newly created loopback cluster."""

import argparse
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    args = parser.parse_args()
    marker = uuid4().hex[:10]
    output = ROOT / ".local" / "service-catalog" / marker
    output.mkdir(parents=True)
    cluster = output / "cluster"
    pg_bin = args.pg_bin.resolve()
    for executable in ("initdb.exe", "pg_ctl.exe", "pg_dump.exe", "pg_restore.exe"):
        if not (pg_bin / executable).is_file():
            raise RuntimeError("Missing PostgreSQL executable " + executable)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 55439)) == 0:
            raise RuntimeError(
                "Dedicated port 55439 is already occupied; do not reuse that cluster"
            )
    env = {
        **os.environ,
        "APP_ENV": "local",
        "DINGTALK_ENABLED": "false",
        "DINGTALK_WEB_ENABLED": "false",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "ASSET_CENTER_ISOLATED_TESTS": "1",
        "ASSET_CENTER_TEST_PORT": "55439",
    }

    def run(command, name, task_env=None, failure=False):
        log = output / (name + ".log")
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(
                command,
                cwd=ROOT / "backend",
                env=task_env or env,
                stdout=stream,
                stderr=subprocess.STDOUT,
                check=False,
            )
        result.stdout = log.read_text(encoding="utf-8", errors="replace")
        result.stderr = ""
        if (result.returncode == 0) == failure:
            print(result.stdout + result.stderr)
            raise RuntimeError("Unexpected result for " + name)
        print(name + (": expected protection" if failure else ": passed"), flush=True)
        return result

    connection = {"host": "127.0.0.1", "port": 55439, "user": "preflight"}
    tests, upgrade, restore = [
        "dam_v13_" + kind + "_" + marker for kind in ("tests", "upgrade", "restore")
    ]
    run(
        [
            str(pg_bin / "initdb.exe"),
            "-D",
            str(cluster),
            "-U",
            "preflight",
            "--auth=trust",
            "--no-locale",
            "--encoding=UTF8",
        ],
        "initdb",
    )
    run(
        [
            str(pg_bin / "pg_ctl.exe"),
            "-D",
            str(cluster),
            "-l",
            str(output / "postgres.log"),
            "-o",
            "-h 127.0.0.1 -p 55439",
            "-w",
            "start",
        ],
        "start",
    )
    try:
        with psycopg.connect(dbname="postgres", autocommit=True, **connection) as db:
            for name in (tests, upgrade, restore):
                db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))

        def task(name):
            return {
                **env,
                "DATABASE_URL": f"postgresql+psycopg://preflight@127.0.0.1:55439/{name}",
            }

        def migrate(name, operation, revision, label, failure=False):
            return run(
                [sys.executable, "-m", "alembic", operation, revision],
                label,
                task(name),
                failure,
            )

        migrate(tests, "upgrade", "head", "empty-upgrade")
        run([sys.executable, "-m", "app.cli.seed"], "seed", task(tests))
        migrate(upgrade, "upgrade", "f13e20261009", "old-baseline")
        provider_id, product_id = uuid4(), uuid4()
        with psycopg.connect(dbname=upgrade, **connection) as db:
            db.execute(
                "INSERT INTO providers(id,code,name) VALUES(%s,'synthetic-legacy','ChatGPT Plus')",
                (provider_id,),
            )
            db.execute(
                "INSERT INTO service_products"
                "(id,provider_id,code,name,service_category,billing_mode) "
                "VALUES(%s,%s,'synthetic-plus','ChatGPT Plus','ai','subscription')",
                (product_id, provider_id),
            )
            before = db.execute(
                "SELECT to_jsonb(p) FROM service_products p WHERE id=%s", (product_id,)
            ).fetchone()[0]
        migrate(upgrade, "upgrade", "head", "legacy-upgrade")
        with psycopg.connect(dbname=upgrade, **connection) as db:
            current = db.execute(
                "SELECT to_jsonb(p)-'platform_id'-'plan_options',platform_id,plan_options "
                "FROM service_products p WHERE id=%s",
                (product_id,),
            ).fetchone()
            assert current == (before, None, [])
        migrate(upgrade, "downgrade", "f13e20261009", "blank-additive-downgrade")
        migrate(upgrade, "upgrade", "head", "additive-reupgrade")
        with psycopg.connect(dbname=upgrade, **connection) as db:
            db.execute(
                "UPDATE service_products SET plan_options='[\"Plus\"]'::jsonb WHERE id=%s",
                (product_id,),
            )
        migrate(
            upgrade,
            "downgrade",
            "f13e20261009",
            "facts-downgrade-protection",
            failure=True,
        )
        backup = output / "catalog.dump"
        run(
            [
                str(pg_bin / "pg_dump.exe"),
                "-h",
                "127.0.0.1",
                "-p",
                "55439",
                "-U",
                "preflight",
                "-Fc",
                "-f",
                str(backup),
                upgrade,
            ],
            "backup",
        )
        run(
            [
                str(pg_bin / "pg_restore.exe"),
                "-h",
                "127.0.0.1",
                "-p",
                "55439",
                "-U",
                "preflight",
                "-d",
                restore,
                str(backup),
            ],
            "restore",
        )
        with psycopg.connect(dbname=restore, **connection) as db:
            assert db.execute(
                "SELECT plan_options FROM service_products WHERE id=%s", (product_id,)
            ).fetchone()[0] == ["Plus"]
        result = run(
            [
                sys.executable,
                "-m",
                "pytest",
                "tests/test_service_catalog.py",
                "tests/test_asset_center_integration.py",
                "tests/test_asset_space.py",
                "-q",
                "--disable-warnings",
            ],
            "targeted-tests",
            task(tests),
        )
        print(result.stdout[-1500:], flush=True)
        (output / "RESULT.md").write_text(
            "# 服务目录隔离验证\n\n"
            "增量升级、旧服务字段保留、空事实降级、新事实降级保护与备份恢复通过。\n\n"
            + result.stdout,
            encoding="utf-8",
        )
        print(
            json.dumps(
                {
                    "output": str(output),
                    "database": tests,
                    "schema": "f13f20261010",
                    "production_access": False,
                }
            ),
            flush=True,
        )
    finally:
        run(
            [
                str(pg_bin / "pg_ctl.exe"),
                "-D",
                str(cluster),
                "-m",
                "fast",
                "-w",
                "stop",
            ],
            "stop",
        )


if __name__ == "__main__":
    main()
