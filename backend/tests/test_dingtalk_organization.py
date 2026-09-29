from datetime import UTC, datetime
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.auth import create_session
from app.db.session import engine, get_db
from app.main import app
from app.models import (
    AppSetting,
    Department,
    DingTalkDepartmentLink,
    LegalEntity,
    Person,
    Role,
    User,
    UserRoleScope,
)
from app.services.dingtalk import (
    DingTalkClient,
    DingTalkDirectorySync,
    resolve_dingtalk_organization,
)


@pytest.fixture
def db():
    # Commits in authentication/sync release a savepoint, never the outer transaction.
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as session:
            session.execute(delete(DingTalkDepartmentLink))
            setting = session.scalar(
                select(AppSetting).where(AppSetting.key == "organization_bootstrap")
            )
            if setting is None:
                setting = AppSetting(key="organization_bootstrap", value={})
                session.add(setting)
            setting.value = {}
            session.flush()
            app.dependency_overrides[get_db] = lambda: session
            try:
                yield session
            finally:
                app.dependency_overrides.pop(get_db, None)
        transaction.rollback()


def entity(db, name="绑定主体"):
    item = LegalEntity(code=f"ORG-{uuid4().hex[:12]}", name=name)
    db.add(item)
    db.flush()
    return item


def configure(db, value):
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "organization_bootstrap"))
    setting.value = value
    db.flush()


def link(db, target):
    department = Department(
        legal_entity_id=target.id, code=f"TEST-{uuid4().hex[:12]}", name="合成部门"
    )
    db.add(department)
    db.flush()
    db.add(
        DingTalkDepartmentLink(
            department_id=department.id, dingtalk_department_id=f"synthetic-{uuid4().hex}"
        )
    )
    db.flush()
    return department


def test_code_binding_does_not_depend_on_sorted_names(db):
    entity(db, name="A 排在前面的其他公司")
    target = entity(db, name="Z 确认的组织")
    configure(db, {"legal_entity_code": target.code, "legal_entity_name": "旧名称"})
    link(db, target)
    binding = resolve_dingtalk_organization(db)
    assert binding.status == "bound"
    assert binding.entity.id == target.id
    assert binding.entity.name == "Z 确认的组织"


def test_legacy_exact_name_binding(db):
    target = entity(db)
    configure(db, {"legal_entity_name": target.name})
    assert resolve_dingtalk_organization(db).entity.id == target.id


def test_unique_link_is_legacy_binding_fallback(db):
    target = entity(db)
    link(db, target)
    assert resolve_dingtalk_organization(db).entity.id == target.id


def test_absent_binding_does_not_choose_first_company(db):
    entity(db)
    result = resolve_dingtalk_organization(db)
    assert result.status == "unbound"
    assert result.entity is None


@pytest.mark.parametrize(
    "config", [{"legal_entity_code": "missing"}, {"legal_entity_name": "missing"}]
)
def test_missing_explicit_binding_does_not_fall_back_to_link(db, config):
    link(db, entity(db))
    configure(db, config)
    result = resolve_dingtalk_organization(db)
    assert result.status == "invalid"
    assert result.entity is None


@pytest.mark.parametrize("disabled", ["archived", "inactive"])
def test_disabled_bound_entity_is_rejected(db, disabled):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    if disabled == "archived":
        target.archived_at = datetime.now(UTC)
    else:
        target.status = "inactive"
    db.flush()
    assert resolve_dingtalk_organization(db).status == "invalid"


def test_ambiguous_name_binding_is_rejected(db):
    entity(db)
    entity(db)
    configure(db, {"legal_entity_name": "绑定主体"})
    assert resolve_dingtalk_organization(db).status == "ambiguous"


@pytest.mark.parametrize("configured", [False, True])
def test_cross_company_directory_links_fail_closed(db, configured):
    target = entity(db)
    link(db, target)
    link(db, entity(db))
    if configured:
        configure(db, {"legal_entity_code": target.code})
    result = resolve_dingtalk_organization(db)
    assert result.status == "ambiguous"
    assert result.entity is None


def test_archived_department_link_does_not_change_binding(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    other = link(db, entity(db))
    other.archived_at = datetime.now(UTC)
    db.flush()
    assert resolve_dingtalk_organization(db).entity.id == target.id


@pytest.mark.parametrize("binding", ["unbound", "different", "conflicting", "invalid"])
def test_unsafe_sync_stops_before_upstream_or_writes(db, binding):
    target = entity(db)
    if binding == "different":
        configure(db, {"legal_entity_code": entity(db).code})
    elif binding == "conflicting":
        configure(db, {"legal_entity_code": target.code})
        link(db, entity(db))
    elif binding == "invalid":
        configure(db, {"legal_entity_code": "missing"})
    client = MagicMock(spec=DingTalkClient)
    with pytest.raises(HTTPException) as failure:
        DingTalkDirectorySync(db, client).run(str(target.id))
    assert failure.value.status_code == 409
    client.access_token.assert_not_called()
    client.departments.assert_not_called()
    assert not db.new and not db.dirty


def test_missing_sync_target_keeps_404(db):
    client = MagicMock(spec=DingTalkClient)
    with pytest.raises(HTTPException) as failure:
        DingTalkDirectorySync(db, client).run(str(uuid4()))
    assert failure.value.status_code == 404
    client.access_token.assert_not_called()


def test_bound_sync_creates_records_in_correct_entity(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    external_id = str(800000000 + int(uuid4().hex[:5], 16))
    user_id = f"synthetic-{uuid4().hex}"
    client = MagicMock(spec=DingTalkClient)
    client.access_token.return_value = "synthetic-token"
    client.departments.return_value = [{"dept_id": external_id, "parent_id": 1, "name": "合成部门"}]
    client.users.return_value = [{"userid": user_id, "name": "合成成员"}]
    client.user_detail.return_value = {"dept_id_list": [external_id]}
    result = DingTalkDirectorySync(db, client).run(str(target.id))
    assert result.departments_created == 1
    assert result.people_created == 1
    assert (
        db.scalar(select(Department).where(Department.code == f"DT-{external_id}")).legal_entity_id
        == target.id
    )
    assert (
        db.scalar(select(Person).where(Person.employee_no == f"DT-{user_id}")).legal_entity_id
        == target.id
    )


def session_headers(db, *, admin=True):
    user = User(username=f"org-binding-{uuid4().hex}", password_hash="not-a-login-credential")
    db.add(user)
    db.flush()
    if admin:
        role = db.scalar(select(Role).where(Role.code == "system_admin"))
        assert role is not None
        db.add(UserRoleScope(user_id=user.id, role_id=role.id, scope_type="company"))
    token, _ = create_session(db, user, "synthetic-organization-test")
    return {"X-PM-Session": token}


def test_binding_endpoint_requires_verified_session(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    client = TestClient(app)
    assert client.get("/api/v1/dingtalk/organization").status_code == 401
    response = client.get("/api/v1/dingtalk/organization", headers=session_headers(db))
    assert response.status_code == 200
    assert response.json() == {
        "status": "bound",
        "legal_entity_id": str(target.id),
        "legal_entity_name": target.name,
        "legal_entity_code": target.code,
        "message": None,
    }


def test_api_sync_keeps_manager_gate_and_rejects_wrong_target(db, monkeypatch):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    wrong = entity(db)
    upstream = MagicMock(spec=DingTalkClient)
    monkeypatch.setattr("app.api.v1.dingtalk.DingTalkClient", lambda: upstream)
    client = TestClient(app)
    body = {"legal_entity_id": str(wrong.id)}
    assert client.post("/api/v1/dingtalk/sync", json=body).status_code == 401
    assert (
        client.post(
            "/api/v1/dingtalk/sync", json=body, headers=session_headers(db, admin=False)
        ).status_code
        == 403
    )
    assert (
        client.post("/api/v1/dingtalk/sync", json=body, headers=session_headers(db)).status_code
        == 409
    )
    upstream.access_token.assert_not_called()
