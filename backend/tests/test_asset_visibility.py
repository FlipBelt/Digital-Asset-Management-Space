from types import SimpleNamespace

from app.core.access import asset_visibility_clause
from app.models import Asset


def test_authenticated_asset_library_uses_company_wide_read_scope() -> None:
    clause = asset_visibility_clause(SimpleNamespace())

    assert clause.compare(Asset.id.is_not(None))
