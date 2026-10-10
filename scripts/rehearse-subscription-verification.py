"""Run registration and authorization checks in a fresh disposable loopback database."""

import argparse
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
    parser.add_argument("--tests", nargs="+", default=[
        "tests/test_subscription_verification.py", "tests/test_asset_space.py",
        "tests/test_service_catalog.py", "tests/test_asset_center_integration.py",
    ])
    args = parser.parse_args()
    marker = uuid4().hex[:10]
    output = ROOT / ".local" / "subscription-verification" / marker
    output.mkdir(parents=True)
    cluster = output / "cluster"
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 55439)) == 0:
            raise RuntimeError("Port 55439 is occupied; never reuse an existing cluster")
    pg_bin = args.pg_bin.resolve()
    database = "dam_v13_tests_subscription_" + marker
    env = {**os.environ, "APP_ENV": "local", "DINGTALK_ENABLED": "false",
           "DINGTALK_WEB_ENABLED": "false", "PYTHONIOENCODING": "utf-8",
           "PYTHONDONTWRITEBYTECODE": "1", "ASSET_CENTER_ISOLATED_TESTS": "1",
           "ASSET_CENTER_TEST_PORT": "55439",
           "DATABASE_URL": f"postgresql+psycopg://preflight@127.0.0.1:55439/{database}"}

    def run(command, name):
        log = output / (name + ".log")
        with log.open("w", encoding="utf-8") as stream:
            result = subprocess.run(command, cwd=ROOT / "backend", env=env,
                                    stdout=stream, stderr=subprocess.STDOUT, check=False)
        if result.returncode:
            print(log.read_text(encoding="utf-8", errors="replace")[-22000:])
            raise RuntimeError(name + " failed; retained local evidence: " + str(output))
        print(name + ": passed", flush=True)
        if name == "pytest":
            print(log.read_text(encoding="utf-8", errors="replace").strip(), flush=True)

    run([str(pg_bin / "initdb.exe"), "-D", str(cluster), "-U", "preflight", "--auth=trust",
         "--no-locale", "--encoding=UTF8"], "initdb")
    run([str(pg_bin / "pg_ctl.exe"), "-D", str(cluster), "-l", str(output / "postgres.log"),
         "-o", "-h 127.0.0.1 -p 55439", "-w", "start"], "start")
    try:
        with psycopg.connect(dbname="postgres", host="127.0.0.1", port=55439,
                             user="preflight", autocommit=True) as db:
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
        run([sys.executable, "-m", "alembic", "upgrade", "head"], "isolated-upgrade")
        run([sys.executable, "-m", "app.cli.seed"], "seed")
        run([sys.executable, "-m", "pytest", *args.tests, "-q",
             "-o", "faulthandler_timeout=20"], "pytest")
        print("evidence: " + str(output), flush=True)
    finally:
        run([str(pg_bin / "pg_ctl.exe"), "-D", str(cluster), "-w", "stop"], "stop")


if __name__ == "__main__":
    main()
