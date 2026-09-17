from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.api.v1.workspace import list_my_assets


def test_my_assets_uses_one_filtered_query_and_returns_assets() -> None:
    person_id = uuid4()
    asset = SimpleNamespace(
        id=uuid4(),
        asset_code="ASSET-001",
        name="测试资产",
        asset_type_id=uuid4(),
        legal_entity_id=uuid4(),
        owner_department_id=None,
        ownership_scope="company",
        created_by_person_id=None,
        confirmed_by_person_id=None,
        confirmed_at=None,
        review_status="approved",
        status="active",
        criticality="normal",
        confidentiality="internal",
        source_type="manual",
        started_at=date.today(),
        expires_at=None,
        last_verified_at=None,
        description=None,
        version=1,
        created_at=datetime.now(),
        updated_at=datetime.now(),
        archived_at=None,
    )
    db = Mock()
    db.scalars.return_value = [asset]

    result = list_my_assets(db, SimpleNamespace(person_id=person_id))

    assert [item.id for item in result] == [asset.id]
    db.scalars.assert_called_once()


def test_my_assets_skips_database_for_anonymous_identity() -> None:
    db = Mock()

    assert list_my_assets(db, SimpleNamespace(person_id=None)) == []

    db.scalars.assert_not_called()
