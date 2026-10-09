"""Run migration and safe downgrade against an isolated transaction/schema."""

import importlib.util
import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import text

from app.db.session import engine


def test_historical_backfill_preserves_revisions_and_downgrade_guards():
    if os.environ.get("ASSET_CENTER_ISOLATED_TESTS") != "1":
        pytest.skip("Disposable database only")
    assert engine.url.host == "127.0.0.1" and engine.url.port == 55433
    assert (engine.url.database or "").startswith("dam_v13_tests_")
    path = Path(__file__).parents[1] / "alembic/versions/f13e20261009_outcome_versions.py"
    spec = importlib.util.spec_from_file_location("outcome_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = "outcome_test_" + uuid4().hex
    with engine.connect() as db:
        transaction = db.begin()
        try:
            db.execute(text(f'CREATE SCHEMA "{schema}"'))
            db.execute(text(f'SET LOCAL search_path TO "{schema}"'))
            db.execute(
                text("""CREATE TABLE assets (
                id integer PRIMARY KEY, version integer, sharing_scope text,
                confirmed_at timestamptz
            )""")
            )
            db.execute(
                text("""CREATE TABLE asset_confirmations (
                asset_id integer, consumed_at timestamptz, cancelled_at timestamptz
            )""")
            )
            db.execute(
                text("""INSERT INTO assets VALUES
                (1, 5, 'private', now()), (2, 9, 'private', NULL),
                (3, 4, 'private', NULL), (4, 12, NULL, now())""")
            )
            db.execute(text("INSERT INTO asset_confirmations VALUES (2, now(), NULL)"))
            with Operations.context(MigrationContext.configure(db)):
                module.upgrade()
                assert db.execute(
                    text("SELECT version, outcome_version FROM assets ORDER BY id")
                ).all() == [(5, 1), (9, 1), (4, 0), (12, 0)]
                assert db.scalar(text("SELECT outcome_version FROM asset_confirmations")) == 1
                # Old code's column projection still works with the additive schema.
                assert db.scalar(text("SELECT count(version) FROM assets")) == 4
                db.execute(text("UPDATE assets SET outcome_version = 2 WHERE id = 1"))
                with pytest.raises(RuntimeError, match="Published outcome"):
                    module.downgrade()
                db.execute(text("UPDATE assets SET outcome_version = 1 WHERE id = 1"))
                db.execute(text("INSERT INTO asset_confirmations VALUES (1, NULL, NULL, 2)"))
                with pytest.raises(RuntimeError, match="confirmation previews"):
                    module.downgrade()
                db.execute(
                    text(
                        "UPDATE asset_confirmations SET cancelled_at = now() "
                        "WHERE consumed_at IS NULL"
                    )
                )
                module.downgrade()
                assert db.execute(
                    text("SELECT version FROM assets ORDER BY id")
                ).scalars().all() == [5, 9, 4, 12]
                assert db.scalar(text("SELECT count(*) FROM asset_confirmations")) == 2
        finally:
            transaction.rollback()
