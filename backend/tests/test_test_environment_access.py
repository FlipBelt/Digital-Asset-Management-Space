from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from app.core.access import AccessContext


def _context() -> AccessContext:
    return AccessContext(
        user=None,  # type: ignore[arg-type]
        person_id=None,
        roles=frozenset(),
        permissions=frozenset(),
        department_scopes=frozenset({uuid4()}),
    )


def test_test_environment_grants_authenticated_context_full_scope() -> None:
    context = _context()
    with patch("app.core.access.get_settings", return_value=SimpleNamespace(app_env="test")):
        assert context.is_global_manager
        assert context.is_read_all
        assert context.has_permission("admin.manage")


def test_production_context_keeps_rbac_scope() -> None:
    context = _context()
    with patch(
        "app.core.access.get_settings", return_value=SimpleNamespace(app_env="production")
    ):
        assert not context.is_global_manager
        assert not context.has_permission("admin.manage")
