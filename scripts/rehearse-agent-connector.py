"""Fresh disposable DBs only; production configuration is never loaded."""

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
BASELINE = "f13c20260928"
HEAD = "f13d20261008"


def run(args, env, *, expect_failure=False):
    result = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT / "backend",
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if (result.returncode == 0) == expect_failure:
        print(result.stdout[-18000:] + result.stderr[-6000:])
        raise RuntimeError("隔离验证失败")
    print(result.stdout[-4000:])
    return result


def fingerprint(db):
    names = [
        r[0]
        for r in db.execute("""
        SELECT tablename FROM pg_tables WHERE schemaname='public'
        AND tablename <> 'alembic_version' AND tablename NOT LIKE 'agent_%'
        ORDER BY tablename
    """)
    ]
    rows = {}
    for name in names:
        values = db.execute(
            sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY 1").format(
                sql.Identifier(name)
            )
        ).fetchall()
        rows[name] = hashlib.sha256(json.dumps(values).encode()).hexdigest()
    return rows


def main():
    marker = uuid4().hex[:10]
    names = {
        "tests": "dam_v13_tests_agent_" + marker,
        "upgrade": "dam_v13_upgrade_agent_" + marker,
    }
    connection = {"host": "127.0.0.1", "port": 55433, "user": "preflight"}
    with psycopg.connect(
        dbname="postgres", autocommit=True, connect_timeout=3, **connection
    ) as db:
        assert db.execute(
            "SELECT host(inet_server_addr()), inet_server_port()"
        ).fetchone() == ("127.0.0.1", 55433)
        for name in names.values():
            db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    env = {
        **os.environ,
        "APP_ENV": "local",
        "DINGTALK_ENABLED": "false",
        "DINGTALK_WEB_ENABLED": "false",
        "AGENT_CONNECTOR_ENABLED": "false",
        "ASSET_CENTER_ISOLATED_TESTS": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    def config(key):
        return {
            **env,
            "DATABASE_URL": f"postgresql+psycopg://preflight@127.0.0.1:55433/{names[key]}",
        }

    run(["-m", "alembic", "upgrade", BASELINE], config("upgrade"))
    with psycopg.connect(dbname=names["upgrade"], **connection) as db:
        # A durable preexisting business object tests upgrade and downgrade preservation.
        entity, asset = uuid4(), uuid4()
        type_id = db.execute(
            "SELECT id FROM asset_types WHERE code='ai_skill'"
        ).fetchone()[0]
        db.execute(
            "INSERT INTO legal_entities(id,code,name,status) VALUES(%s,%s,%s,'active')",
            (entity, "AGENT-UPGRADE-" + marker, "迁移保留验证"),
        )
        db.execute(
            """INSERT INTO assets(id,asset_code,name,asset_type_id,legal_entity_id,
                   ownership_scope,status,criticality,confidentiality,source_type,version)
                   VALUES(%s,'AGENT-OLD','旧版本成果',%s,%s,'company','draft','normal',
                   'internal','manual',1)""",
            (asset, type_id, entity),
        )
        db.commit()
        before = fingerprint(db)
    for command, revision in (
        ("upgrade", HEAD),
        ("downgrade", BASELINE),
        ("upgrade", HEAD),
    ):
        run(["-m", "alembic", command, revision], config("upgrade"))
        with psycopg.connect(dbname=names["upgrade"], **connection) as db:
            assert fingerprint(db) == before, "原有业务表发生变化"
    run(["-m", "alembic", "upgrade", HEAD], config("tests"))
    run(["-m", "app.cli.seed"], config("tests"))
    (ROOT / ".local").mkdir(exist_ok=True)
    result = run(
        [
            "-m",
            "pytest",
            "tests/test_agent_connector.py",
            "tests/test_asset_space.py",
            "tests/test_asset_visibility.py",
            "tests/test_pm_session_security.py",
            "tests/test_asset_center_integration.py",
            "-q",
            "--tb=short",
            "--basetemp",
            str(ROOT / ".local" / ("pytest-agent-" + marker)),
        ],
        config("tests"),
    )
    rejected = run(
        ["-m", "alembic", "downgrade", BASELINE], config("tests"), expect_failure=True
    )
    assert "Connector tables contain data" in rejected.stderr
    output = ROOT / ".local" / "agent-connector"
    output.mkdir(parents=True, exist_ok=True)
    (output / "REHEARSAL.md").write_text(
        "# 连接器隔离验证\n\n"
        f"- 环境：127.0.0.1:55433，新建 {names['tests']} / {names['upgrade']}。\n"
        f"- 空库升级至 {HEAD} 完成。\n"
        f"- {BASELINE} → {HEAD} → {BASELINE} → {HEAD} 完成。\n"
        "- 每轮所有原有业务表内容摘要一致，旧成果保留；已有连接器数据的降级已被拒绝。\n"
        f"- 目标测试：\n\n{text_block(result.stdout)}\n"
        "- 合成测试，不代表真实授权或业务验收；生产未修改。\n",
        encoding="utf-8",
    )
    print("Evidence: .local/agent-connector/REHEARSAL.md")


def text_block(value):
    return "```text\n" + value.strip()[-5000:] + "\n```"


if __name__ == "__main__":
    main()
