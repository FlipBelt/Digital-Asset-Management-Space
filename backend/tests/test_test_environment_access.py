from app.core.access import AccessContext


def test_employee_context_keeps_rbac_including_isolated_test_environment() -> None:
    context = AccessContext(
        user=None,
        person_id=None,
        roles=frozenset({"employee"}),
        permissions=frozenset({"asset.read"}),
        department_scopes=frozenset(),
    )
    assert not context.is_global_manager
    assert not context.is_read_all
    assert not context.has_permission("admin.manage")
    assert context.has_permission("asset.read")


def test_system_admin_keeps_explicit_full_scope() -> None:
    context = AccessContext(
        user=None,
        person_id=None,
        roles=frozenset({"system_admin"}),
        permissions=frozenset(),
        department_scopes=frozenset(),
    )
    assert context.is_global_manager
    assert context.is_read_all
    assert context.has_permission("admin.manage")
