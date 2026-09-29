from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.access import can_manage_asset, get_access_context
from app.core.auth import (
    get_permission_codes,
    get_role_codes,
    require_developer_supervisor,
    require_system_admin,
)
from app.db.session import engine
from app.models import (
    AppSetting,
    Asset,
    Department,
    DepartmentMembership,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
    LegalEntity,
    Permission,
    Person,
    Role,
    RolePermission,
    User,
    UserRoleScope,
)
from app.services.dingtalk import DingTalkClient, DingTalkDirectorySync


@pytest.fixture
def db():
    with engine.connect() as connection:
        outer = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            session.execute(delete(DingTalkDepartmentLink))
            for key in (
                "organization_bootstrap",
                "dingtalk_leadership_policy",
                "dingtalk_directory_snapshot",
            ):
                row = session.scalar(select(AppSetting).where(AppSetting.key == key))
                if row is None:
                    row = AppSetting(key=key, value={})
                    session.add(row)
                row.value = {}
            group = session.scalar(select(Role).where(Role.code == "group_leader"))
            if not group:
                group = Role(code="group_leader", name="合成组长")
                session.add(group)
                session.flush()
            for code in ("asset.read", "asset.write", "organization.read", "governance.read"):
                permission = session.scalar(select(Permission).where(Permission.code == code))
                assert permission
                if not session.get(RolePermission, (group.id, permission.id)):
                    session.add(RolePermission(role_id=group.id, permission_id=permission.id))
            session.flush()
            yield session
        outer.rollback()


def setup_actor(db):
    entity = LegalEntity(code=f"LEAD-{uuid4().hex}", name="合成组织")
    db.add(entity)
    db.flush()
    units = {}
    for index, (name, parent) in enumerate(
        (
            ("中心", None),
            ("职能部门", "中心"),
            ("一组", "职能部门"),
            ("子组", "一组"),
            ("其他部门", None),
        )
    ):
        item = Department(
            legal_entity_id=entity.id,
            code=f"DT-{6000 + index}",
            name=name,
            parent_id=units[parent].id if parent else None,
        )
        db.add(item)
        db.flush()
        units[name] = item
        db.add(
            DingTalkDepartmentLink(department_id=item.id, dingtalk_department_id=str(6000 + index))
        )
    person = Person(
        legal_entity_id=entity.id,
        department_id=units["一组"].id,
        employee_no=uuid4().hex,
        display_name="合成负责人",
    )
    db.add(person)
    db.flush()
    profile = DingTalkPersonProfile(
        person_id=person.id,
        dingtalk_user_id=uuid4().hex,
        profile_data={"directory_status": "current"},
    )
    user = User(person_id=person.id, username=uuid4().hex, password_hash="!synthetic!")
    membership = DepartmentMembership(
        person_id=person.id,
        department_id=units["一组"].id,
        is_manager=True,
        is_primary=True,
        is_active=True,
    )
    db.add_all([profile, user, membership])
    db.flush()
    for code, scope in (("employee", entity.id), ("department_manager", units["一组"].id)):
        role = db.scalar(select(Role).where(Role.code == code))
        assert role
        db.add(
            UserRoleScope(
                user_id=user.id,
                role_id=role.id,
                scope_type="company" if code == "employee" else "department",
                scope_id=scope,
            )
        )
    policy = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_leadership_policy"))
    policy.value = {
        "legal_entity_id": str(entity.id),
        "department_kinds": {
            item.code: ("group" if name in ("一组", "子组") else "department")
            for name, item in units.items()
        },
    }
    db.flush()
    return entity, units, person, profile, user, membership


def test_group_leader_has_only_own_group_scope_and_no_admin_or_governance_write(db):
    _, units, person, _, user, _ = setup_actor(db)
    context = get_access_context(user, db)
    assert context.roles == frozenset({"employee", "group_leader"})
    assert context.department_scopes == frozenset({units["一组"].id})
    assert not context.is_global_manager
    assert not context.has_permission("admin.manage")
    assert not context.has_permission("governance.write")
    for name in ("中心", "职能部门", "子组", "其他部门"):
        assert not can_manage_asset(
            db, context, Asset(owner_department_id=units[name].id, sharing_scope="team")
        )
    assert can_manage_asset(
        db, context, Asset(owner_department_id=units["一组"].id, sharing_scope="team")
    )
    assert not can_manage_asset(
        db,
        context,
        Asset(
            owner_department_id=units["一组"].id,
            sharing_scope="private",
            created_by_person_id=uuid4(),
        ),
    )


def test_functional_department_manager_inherits_descendants_but_not_sibling(db):
    _, units, person, _, user, group_membership = setup_actor(db)
    group_membership.is_manager = False
    db.add(
        DepartmentMembership(
            person_id=person.id, department_id=units["职能部门"].id, is_manager=True, is_active=True
        )
    )
    db.flush()
    context = get_access_context(user, db)
    assert "department_manager" in context.roles and "group_leader" not in context.roles
    assert context.department_scopes == frozenset(
        units[name].id for name in ("职能部门", "一组", "子组")
    )
    assert context.has_permission("governance.write")
    assert not context.has_permission("admin.manage")


def test_unknown_unit_cannot_promote_a_dingtalk_leader(db):
    entity, units, _, _, user, _ = setup_actor(db)
    policy = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_leadership_policy"))
    policy.value = {
        "legal_entity_id": str(entity.id),
        "department_kinds": {units["中心"].code: "department"},
    }
    db.flush()
    assert get_role_codes(db, user.id) == ["employee"]
    assert not get_access_context(user, db).department_scopes


def test_stored_admin_and_unlinked_manual_scopes_survive_source_mapping(db):
    entity, _, _, _, user, _ = setup_actor(db)
    manual = Department(legal_entity_id=entity.id, code=uuid4().hex, name="人工部门")
    db.add(manual)
    db.flush()
    for code, scope in (("system_admin", entity.id), ("department_manager", manual.id)):
        role = db.scalar(select(Role).where(Role.code == code))
        assert role
        db.add(
            UserRoleScope(
                user_id=user.id,
                role_id=role.id,
                scope_type="company" if code == "system_admin" else "department",
                scope_id=scope,
            )
        )
    db.flush()
    context = get_access_context(user, db)
    assert context.is_global_manager and "department_manager" in context.roles
    assert manual.id in context.department_scopes


def test_test_environment_does_not_bypass_admin_or_developer_roles(db):
    user = User(username=uuid4().hex, password_hash="!synthetic!")
    db.add(user)
    db.flush()
    with patch(
        "app.core.auth.get_settings",
        return_value=SimpleNamespace(app_env="test", developer_supervisor_username="someone-else"),
    ):
        assert get_permission_codes(db, user.id) == []
        with pytest.raises(HTTPException) as denied:
            require_system_admin(user, db)
        assert denied.value.status_code == 403
        with pytest.raises(HTTPException) as denied:
            require_developer_supervisor(user, db)
        assert denied.value.status_code == 403


@pytest.mark.parametrize(
    "bad",
    [
        None,
        {"list": "broken", "has_more": False},
        {"list": [{}], "has_more": False},
        {"list": [], "has_more": "maybe"},
    ],
)
def test_invalid_directory_page_fails_closed(bad):
    client = DingTalkClient()
    client._request = MagicMock(return_value={"result": bad})
    with pytest.raises(HTTPException):
        list(client.users("synthetic", "6000"))


def test_string_false_pagination_stops_and_true_cursor_must_progress():
    client = DingTalkClient()
    client._request = MagicMock(
        return_value={"result": {"list": [{"userid": "synthetic"}], "has_more": "false"}}
    )
    assert len(list(client.users("synthetic", "6000"))) == 1
    assert client._request.call_count == 1
    client._request = MagicMock(
        return_value={
            "result": {"list": [{"userid": "synthetic"}], "has_more": True, "next_cursor": 0}
        }
    )
    with pytest.raises(HTTPException):
        list(client.users("synthetic", "6000"))
    assert client._request.call_count == 1


def sync_fixture(db):
    entity, units, person, profile, user, membership = setup_actor(db)
    bootstrap = db.scalar(select(AppSetting).where(AppSetting.key == "organization_bootstrap"))
    bootstrap.value = {"legal_entity_code": entity.code}
    client = MagicMock(spec=DingTalkClient)
    client.departments.return_value = [{"dept_id": 6000, "parent_id": 1, "name": "中心"}]
    client.users.return_value = [{"userid": "synthetic-current", "name": "合成当前成员"}]
    client.user_detail.return_value = {
        "userid": "synthetic-current",
        "name": "合成当前成员",
        "dept_id_list": [6000],
    }
    db.flush()
    return entity, person, profile, user, membership, client


def test_full_sync_adds_current_member_and_preserves_history_placements_and_grants(db):
    entity, person, profile, user, membership, client = sync_fixture(db)
    grants = [
        tuple(row)
        for row in db.execute(
            select(UserRoleScope.role_id, UserRoleScope.scope_id).where(
                UserRoleScope.user_id == user.id
            )
        )
    ]
    sync = DingTalkDirectorySync(db, client)
    result = sync.run(str(entity.id))
    assert (
        result.people_current == 1 and result.people_historical == 1 and result.people_created == 1
    )
    assert profile.profile_data["directory_status"] == "not_in_current_directory"
    assert membership.is_active and membership.is_manager and membership.is_primary
    assert person.employment_status == "active" and user.is_active
    assert [
        tuple(row)
        for row in db.execute(
            select(UserRoleScope.role_id, UserRoleScope.scope_id).where(
                UserRoleScope.user_id == user.id
            )
        )
    ] == grants
    assert "department_manager" in get_role_codes(db, user.id)
    snapshot = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot"))
    assert snapshot.value["historical_person_ids"] == [str(person.id)]
    again = sync.run(str(entity.id))
    assert again.people_created == 0 and again.people_updated == 1 and again.people_current == 1


def test_detail_failure_leaves_previous_snapshot_and_database_untouched(db):
    entity, _, _, _, _, client = sync_fixture(db)
    snapshot = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot"))
    snapshot.value = {"sentinel": "unchanged"}
    db.flush()
    client.user_detail.side_effect = HTTPException(
        status_code=502, detail="synthetic upstream failure"
    )
    with pytest.raises(HTTPException):
        DingTalkDirectorySync(db, client).run(str(entity.id))
    assert snapshot.value == {"sentinel": "unchanged"}
    assert not db.new and not db.dirty


def test_invalid_hierarchy_and_identity_fail_before_writes(db):
    entity, _, _, _, _, client = sync_fixture(db)
    client.departments.return_value = [{"dept_id": 6000, "parent_id": 6000, "name": "中心"}]
    with pytest.raises(HTTPException):
        DingTalkDirectorySync(db, client).run(str(entity.id))
    assert not db.new and not db.dirty
    client.departments.return_value = [{"dept_id": 6000, "parent_id": 1, "name": "中心"}]
    client.user_detail.return_value = {"userid": "different", "dept_id_list": [6000]}
    with pytest.raises(HTTPException):
        DingTalkDirectorySync(db, client).run(str(entity.id))
    assert not db.new and not db.dirty


def test_department_scope_does_not_follow_a_cross_company_parent_link(db):
    _, units, person, _, user, group_membership = setup_actor(db)
    group_membership.is_manager = False
    db.add(
        DepartmentMembership(
            person_id=person.id, department_id=units["职能部门"].id, is_manager=True, is_active=True
        )
    )
    other = LegalEntity(code=uuid4().hex, name="合成其他组织")
    db.add(other)
    db.flush()
    cross = Department(
        legal_entity_id=other.id,
        parent_id=units["职能部门"].id,
        code=uuid4().hex,
        name="错误跨组织子节点",
    )
    db.add(cross)
    db.flush()
    assert cross.id not in get_access_context(user, db).department_scopes
