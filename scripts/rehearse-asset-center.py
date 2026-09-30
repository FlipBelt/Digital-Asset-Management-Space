"""Rehearse only on a new loopback PostgreSQL cluster; never target a configured application DB."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "b8c4d2e6f901"
HEAD = "f13b20260928"


def run(command: list[str], env: dict[str, str], log: Path, *, expect_failure: bool = False):
    result = subprocess.run(
        command,
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    log.write_text(result.stdout + result.stderr, encoding="utf-8")
    if (result.returncode == 0) == expect_failure:
        raise RuntimeError(f"Unexpected command result; inspect {log}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pg-bin", type=Path, required=True)
    parser.add_argument("--port", type=int, default=55433)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".local" / "replacement" / "rehearsal"
    )
    args = parser.parse_args()
    args.pg_bin = args.pg_bin.resolve()
    if args.port != 55433:
        raise RuntimeError("This rehearsal is restricted to its dedicated loopback port 55433.")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / ".local").resolve()):
        raise RuntimeError(
            "Rehearsal output must stay in this repository's ignored .local directory."
        )
    for program in ["pg_dump.exe", "pg_restore.exe"]:
        if not (args.pg_bin / program).is_file():
            raise RuntimeError(f"Missing runtime: {program}")
    marker = uuid4().hex[:10]
    databases = {
        key: f"dam_v13_{key}_{marker}"
        for key in ("empty", "upgrade", "restore", "tests", "preview")
    }
    output = output / marker
    output.mkdir(parents=True, exist_ok=False)
    connection = dict(host="127.0.0.1", port=args.port, user="preflight")
    with psycopg.connect(dbname="postgres", autocommit=True, **connection) as admin:
        if admin.execute("SELECT host(inet_server_addr()), inet_server_port()").fetchone() != (
            "127.0.0.1",
            55433,
        ):
            raise RuntimeError("The PostgreSQL target is not the dedicated loopback cluster.")
        for key in ("empty", "upgrade", "restore"):
            admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(databases[key])))
    env = os.environ.copy()
    env.update(
        APP_ENV="local",
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONIOENCODING="utf-8",
        DINGTALK_ENABLED="false",
    )

    def migrate(key: str, operation: str, revision: str, *, fail: bool = False):
        task_env = {
            **env,
            "DATABASE_URL": f"postgresql+psycopg://preflight@127.0.0.1:55433/{databases[key]}",
        }
        return run(
            [sys.executable, "-m", "alembic", operation, revision],
            task_env,
            output / f"{key}-{operation}-{revision}.log",
            expect_failure=fail,
        )

    migrate("empty", "upgrade", "head")
    migrate("upgrade", "upgrade", BASELINE)
    ids = {
        key: uuid4()
        for key in (
            "entity",
            "category",
            "type",
            "asset",
            "other",
            "relation",
            "provider",
            "product",
            "instance",
        )
    }
    with psycopg.connect(dbname=databases["upgrade"], **connection) as db:
        db.execute(
            "INSERT INTO legal_entities(id,code,name,status) "
            "VALUES (%s,'REHEARSAL','迁移演练公司','active')",
            [ids["entity"]],
        )
        db.execute(
            "INSERT INTO asset_categories(id,code,name,sort_order) "
            "VALUES (%s,'rehearsal','迁移演练类型',99)",
            [ids["category"]],
        )
        db.execute(
            """INSERT INTO asset_types(id,category_id,code,name,profile_kind,is_system,
                   completeness_rules,code_prefix,ownership_default)
                   VALUES (%s,%s,'legacy_rehearsal','旧类型演练',
                           'generic',false,'{}','PRE','manual')""",
            [ids["type"], ids["category"]],
        )
        for key, name, code in [
            ("asset", "旧订阅演练", "PRE-001"),
            ("other", "旧关联演练", "PRE-002"),
        ]:
            db.execute(
                """INSERT INTO assets(id,asset_code,name,asset_type_id,legal_entity_id,
                       ownership_scope,status,criticality,confidentiality,description,source_type,
                       review_status,version)
                       VALUES (%s,%s,%s,%s,%s,'company','active','normal','internal',
                       '只用于隔离迁移的数据','manual','approved',7)""",
                [ids[key], code, name, ids["type"], ids["entity"]],
            )
        db.execute(
            """INSERT INTO asset_relations(id,source_asset_id,target_asset_id,relation_type,
                   source_type,note) VALUES (%s,%s,%s,'uses','manual','迁移前关系证据')""",
            [ids["relation"], ids["asset"], ids["other"]],
        )
        db.execute(
            "INSERT INTO providers(id,code,name) VALUES (%s,'rehearsal','演练供应商')",
            [ids["provider"]],
        )
        db.execute(
            """INSERT INTO service_products(id,provider_id,code,name,service_category,billing_mode)
                   VALUES (%s,%s,'rehearsal','演练服务','ai','subscription')""",
            [ids["product"], ids["provider"]],
        )
        db.execute(
            """INSERT INTO service_instances
                   (id,asset_id,service_product_id,subscription_name,currency)
                   VALUES (%s,%s,%s,'旧套餐演练','USD')""",
            [ids["instance"], ids["asset"], ids["product"]],
        )

    def legacy_fingerprint(db) -> str:
        rows = [
            db.execute(
                "SELECT id,asset_code,name,description,status,review_status,version,asset_type_id "
                "FROM assets ORDER BY id"
            ).fetchall(),
            db.execute(
                "SELECT id,source_asset_id,target_asset_id,relation_type,note "
                "FROM asset_relations ORDER BY id"
            ).fetchall(),
            db.execute(
                "SELECT id,asset_id,service_product_id,subscription_name,currency "
                "FROM service_instances ORDER BY id"
            ).fetchall(),
        ]
        return hashlib.sha256(
            json.dumps(rows, default=str, ensure_ascii=False).encode()
        ).hexdigest()

    with psycopg.connect(dbname=databases["upgrade"], **connection) as db:
        original = legacy_fingerprint(db)
    migrate("upgrade", "upgrade", "head")
    with psycopg.connect(dbname=databases["upgrade"], **connection) as db:
        assert legacy_fingerprint(db) == original
        assert db.execute(
            "SELECT funding_source,payer_person_id,primary_purpose FROM service_instances"
        ).fetchone() == (None, None, None)
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
        # Populate one new fact to prove a destructive downgrade is refused.
        db.execute("UPDATE assets SET sharing_scope='private' WHERE id=%s", [ids["asset"]])
    migrate("upgrade", "downgrade", BASELINE, fail=True)
    with psycopg.connect(dbname=databases["upgrade"], **connection) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
        assert (
            db.execute("SELECT sharing_scope FROM assets WHERE id=%s", [ids["asset"]]).fetchone()[0]
            == "private"
        )
    dump = output / "synthetic-upgraded.dump"
    run(
        [
            str(args.pg_bin / "pg_dump.exe"),
            "-h",
            "127.0.0.1",
            "-p",
            "55433",
            "-U",
            "preflight",
            "-Fc",
            "-f",
            str(dump),
            databases["upgrade"],
        ],
        env,
        output / "backup.log",
    )
    run(
        [
            str(args.pg_bin / "pg_restore.exe"),
            "-h",
            "127.0.0.1",
            "-p",
            "55433",
            "-U",
            "preflight",
            "--exit-on-error",
            "-d",
            databases["restore"],
            str(dump),
        ],
        env,
        output / "restore.log",
    )
    with psycopg.connect(dbname=databases["restore"], **connection) as db:
        assert legacy_fingerprint(db) == original
        assert (
            db.execute("SELECT sharing_scope FROM assets WHERE id=%s", [ids["asset"]]).fetchone()[0]
            == "private"
        )
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
    with psycopg.connect(dbname="postgres", autocommit=True, **connection) as admin:
        for key in ("tests", "preview"):
            admin.execute(
                sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
                    sql.Identifier(databases[key]), sql.Identifier(databases["empty"])
                )
            )
    with psycopg.connect(dbname=databases["empty"], **connection) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == HEAD
        for table in ("asset_bookmarks", "asset_evidence", "asset_confirmations"):
            assert db.execute("SELECT to_regclass(%s)", [table]).fetchone()[0] == table
    for key in ("tests", "preview"):
        seed_env = {
            **env,
            "DATABASE_URL": f"postgresql+psycopg://preflight@127.0.0.1:55433/{databases[key]}",
        }
        run([sys.executable, "-m", "app.cli.seed"], seed_env, output / f"{key}-seed.log")
    report = (
        "# 本地隔离迁移演练\n\n"
        f"- Baseline: {BASELINE}; head: {HEAD}.\n"
        "- Target: dedicated loopback PostgreSQL 127.0.0.1:55433. Synthetic data only.\n"
        "- Empty DB upgrade: passed.\n"
        "- Baseline schema + assets/relations/subscription -> head: passed; "
        "legacy fingerprint preserved.\n"
        "- Historical funding remains unknown: passed.\n"
        "- Populated downgrade blocked without deleting facts: passed.\n"
        "- Backup restored into a separate DB: passed; "
        "legacy fingerprint, new fact and revision preserved.\n"
        "- No configured existing DB, remote environment or production service was contacted.\n\n"
        + "\n".join(f"- {key}: {name}" for key, name in databases.items())
        + "\n"
    )
    (output / "RESULT.md").write_text(report, encoding="utf-8")
    (output / "databases.json").write_text(json.dumps(databases), encoding="utf-8")
    print("REHEARSAL_RESULT=" + str(output / "RESULT.md"))
    print("TEST_DATABASE=" + databases["tests"])
    print("PREVIEW_DATABASE=" + databases["preview"])


if __name__ == "__main__":
    main()
