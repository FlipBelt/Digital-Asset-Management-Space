import json
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
    AuditLog,
    Department,
    DepartmentMembership,
    DingTalkDepartmentLink,
    DingTalkPersonProfile,
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
from app.services.dingtalk_company import (
    COMPANY_SOURCE_FIELD,
    company_affiliation_from_detail,
    stored_company_affiliation,
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
    client.user_detail.return_value = {"userid": user_id, "dept_id_list": [external_id]}
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
        "directory_snapshot": None,
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


# Company grouping uses a different source from the department directory.
@pytest.mark.parametrize("shape", ["extension_dict", "extension_json", "attribute_text", "both"])
def test_company_field_shapes_and_whitelist(shape):
    name = "合成创作有限公司"
    detail = {"mobile": "never-store-this", "dept_id_list": [123]}
    if shape in ("extension_dict", "both"):
        detail["extension"] = {COMPANY_SOURCE_FIELD: name, "其他资料": "never-store-this"}
    if shape == "extension_json":
        detail["extension"] = json.dumps({COMPANY_SOURCE_FIELD: name})
    if shape in ("attribute_text", "both"):
        detail["ext_attrs"] = [{"name": COMPANY_SOURCE_FIELD, "value": {"text": name}}]
    result = company_affiliation_from_detail(detail)
    assert result["name"] == name and result["status"] == "available"
    assert set(result) == {"name", "status", "source_field", "checked_at"}
    assert "never-store-this" not in json.dumps(result)


@pytest.mark.parametrize(
    "detail,state",
    [
        ({"dept_id_list": [123], "name": "合成成员"}, "missing"),
        ({"extension": "{malformed", "ext_attrs": []}, "missing"),
        ({"extension": {COMPANY_SOURCE_FIELD: ["合成公司"]}}, "invalid"),
        ({"extension": {COMPANY_SOURCE_FIELD: "无"}}, "invalid"),
        ({"extension": {COMPANY_SOURCE_FIELD: "a" * 201 + "公司"}}, "invalid"),
        (
            {
                "extension": {COMPANY_SOURCE_FIELD: "合成甲有限公司"},
                "ext_attrs": [{"name": COMPANY_SOURCE_FIELD, "value": {"text": "合成乙有限公司"}}],
            },
            "conflict",
        ),
    ],
)
def test_company_field_missing_invalid_and_conflicting_fail_closed(detail, state):
    result = company_affiliation_from_detail(detail)
    assert result["name"] is None and result["status"] == state


def company_subject(db, target, department):
    marker = uuid4().hex
    person = Person(
        legal_entity_id=target.id,
        department_id=department.id,
        employee_no=f"COMP-{marker[:12]}",
        display_name="合成公司成员",
    )
    db.add(person)
    db.flush()
    profile = DingTalkPersonProfile(
        person_id=person.id,
        dingtalk_user_id=f"synthetic-company-{marker}",
        job_title="合成岗位",
        profile_data={"avatar": "synthetic-avatar", "department_ids": ["old"]},
    )
    db.add(profile)
    db.flush()
    return person, profile


def company_client(details):
    client = MagicMock(spec=DingTalkClient)
    client.access_token.return_value = "synthetic-token"
    client.departments.return_value = [{"dept_id": "123", "name": "合成职能部门"}]
    client.user_detail.side_effect = lambda token, uid: details[uid]
    return client


def test_company_refresh_does_not_move_department_tenant_or_roles(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    department = link(db, target)
    person, profile = company_subject(db, target, department)
    db.add(
        DepartmentMembership(
            person_id=person.id,
            department_id=department.id,
            is_primary=True,
            is_active=True,
            is_manager=True,
        )
    )
    db.flush()
    before_roles = set(db.scalars(select(UserRoleScope.id)))
    before_memberships = [
        (m.id, m.department_id, m.is_primary, m.is_manager, m.is_active)
        for m in db.scalars(select(DepartmentMembership))
    ]
    client = company_client(
        {
            profile.dingtalk_user_id: {
                "userid": profile.dingtalk_user_id,
                "extension": {COMPANY_SOURCE_FIELD: "合成创作有限公司"},
                "mobile": "never-store-this",
            }
        }
    )
    counts = DingTalkDirectorySync(db, client).refresh_company_affiliations(str(target.id))
    assert counts["available"] == 1 and counts["checked"] == 1
    assert person.legal_entity_id == target.id and person.department_id == department.id
    assert set(db.scalars(select(UserRoleScope.id))) == before_roles
    assert [
        (m.id, m.department_id, m.is_primary, m.is_manager, m.is_active)
        for m in db.scalars(select(DepartmentMembership))
    ] == before_memberships
    assert profile.profile_data["avatar"] == "synthetic-avatar"
    assert profile.profile_data["department_ids"] == ["old"]
    assert profile.profile_data["company_affiliation"]["name"] == "合成创作有限公司"
    assert "never-store-this" not in json.dumps(profile.profile_data)
    snapshot = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot"))
    assert snapshot.value["legal_entity_id"] == str(target.id)
    assert snapshot.value["department_codes"] == ["DT-123"]
    audit = db.scalar(
        select(AuditLog).where(
            AuditLog.action == "organization.company_affiliations_refresh",
            AuditLog.object_id == target.id,
        )
    )
    assert audit.after_data == counts


def test_company_refresh_excludes_other_tenants_and_archived_people(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    person, profile = company_subject(db, target, link(db, target))
    other_target = entity(db)
    other_department = Department(
        legal_entity_id=other_target.id,
        code="other",
        name="合成其他部门",
    )
    db.add(other_department)
    db.flush()
    _, other_profile = company_subject(db, other_target, other_department)
    archived, archived_profile = company_subject(
        db, target, db.get(Department, person.department_id)
    )
    archived.archived_at = datetime.now(UTC)
    db.flush()
    client = company_client(
        {
            profile.dingtalk_user_id: {
                "userid": profile.dingtalk_user_id,
                "extension": {COMPANY_SOURCE_FIELD: "合成创作有限公司"},
            }
        }
    )
    counts = DingTalkDirectorySync(db, client).refresh_company_affiliations(str(target.id))
    assert counts["checked"] == 1
    assert "company_affiliation" not in other_profile.profile_data
    assert "company_affiliation" not in archived_profile.profile_data


@pytest.mark.parametrize("code", [60121, "60121"])
def test_unavailable_source_is_pending_and_keeps_person_and_roles(db, code):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    person, profile = company_subject(db, target, link(db, target))
    client = company_client({})
    client.user_detail.side_effect = HTTPException(502, detail={"code": code})
    counts = DingTalkDirectorySync(db, client).refresh_company_affiliations(str(target.id))
    assert counts["unavailable"] == 1
    assert profile.profile_data["company_affiliation"]["name"] is None
    assert person.archived_at is None and person.employment_status == "active"


def test_transient_company_query_failure_preserves_entire_old_snapshot(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    _, first = company_subject(db, target, link(db, target))
    _, second = company_subject(
        db, target, db.get(Department, db.get(Person, first.person_id).department_id)
    )
    before = {p.id: dict(p.profile_data) for p in (first, second)}
    client = company_client({})
    calls = []

    def upstream_detail(token, uid):
        calls.append(uid)
        if len(calls) == 2:
            raise HTTPException(502, detail={"code": 88})
        return {"userid": uid, "extension": {COMPANY_SOURCE_FIELD: "合成创作有限公司"}}

    client.user_detail.side_effect = upstream_detail
    with pytest.raises(HTTPException) as failure:
        DingTalkDirectorySync(db, client).refresh_company_affiliations(str(target.id))
    assert failure.value.detail == {"code": 88}
    assert len(calls) == 2
    assert {p.id: p.profile_data for p in (first, second)} == before
    assert not db.new and not db.dirty


def test_company_refresh_rejects_empty_directory_before_writes(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    link(db, target)
    client = company_client({})
    client.departments.return_value = []
    with pytest.raises(HTTPException) as failure:
        DingTalkDirectorySync(db, client).refresh_company_affiliations(str(target.id))
    assert failure.value.status_code == 502
    client.user_detail.assert_not_called()
    assert not db.new and not db.dirty


def test_company_refresh_api_keeps_auth_manager_and_binding_guards(db, monkeypatch):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    link(db, target)
    wrong = entity(db)
    upstream = company_client({})
    monkeypatch.setattr("app.api.v1.dingtalk.DingTalkClient", lambda: upstream)
    client = TestClient(app)
    endpoint = "/api/v1/dingtalk/organization/companies/refresh"
    assert client.post(endpoint, json={"legal_entity_id": str(target.id)}).status_code == 401
    assert (
        client.post(
            endpoint,
            json={"legal_entity_id": str(target.id)},
            headers=session_headers(db, admin=False),
        ).status_code
        == 403
    )
    assert (
        client.post(
            endpoint, json={"legal_entity_id": str(wrong.id)}, headers=session_headers(db)
        ).status_code
        == 409
    )
    upstream.access_token.assert_not_called()


def test_company_profile_api_exposes_only_the_typed_company_snapshot(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    _, profile = company_subject(db, target, link(db, target))
    profile.profile_data = {
        "private_unrelated_field": "never-expose-this",
        "company_affiliation": company_affiliation_from_detail(
            {
                "extension": {COMPANY_SOURCE_FIELD: "合成创作有限公司"},
            }
        ),
    }
    db.flush()
    client = TestClient(app)
    assert (
        client.get(
            "/api/v1/dingtalk/profiles", headers=session_headers(db, admin=False)
        ).status_code
        == 403
    )
    response = client.get("/api/v1/dingtalk/profiles", headers=session_headers(db))
    assert response.status_code == 200
    row = next(item for item in response.json() if item["person_id"] == str(profile.person_id))
    assert row["company_affiliation"]["name"] == "合成创作有限公司"
    assert "never-expose-this" not in response.text


def test_stored_company_snapshot_rejects_invalid_source_and_status():
    assert (
        stored_company_affiliation(
            {
                "company_affiliation": {
                    "name": "合成创作有限公司",
                    "source_field": "client-claim",
                    "status": "available",
                }
            }
        )["status"]
        == "unknown"
    )
    assert (
        stored_company_affiliation(
            {
                "company_affiliation": {
                    "name": "合成创作有限公司",
                    "source_field": COMPANY_SOURCE_FIELD,
                    "status": {},
                }
            }
        )["status"]
        == "unknown"
    )


def test_company_refresh_rejects_cross_user_detail_before_writes(db):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    _, profile = company_subject(db, target, link(db, target))
    client = company_client(
        {
            profile.dingtalk_user_id: {
                "userid": "different-synthetic-user",
                "extension": {COMPANY_SOURCE_FIELD: "合成创作有限公司"},
            }
        }
    )
    with pytest.raises(HTTPException) as failure:
        DingTalkDirectorySync(db, client).refresh_company_affiliations(str(target.id))
    assert failure.value.status_code == 502
    assert "company_affiliation" not in profile.profile_data
    assert not db.new and not db.dirty


@pytest.mark.parametrize("case", ["valid", "wrong_entity", "invalid_time", "empty"])
def test_directory_snapshot_is_typed_and_bound_to_the_same_organization(db, case):
    target = entity(db)
    configure(db, {"legal_entity_code": target.code})
    snapshot = {
        "legal_entity_id": str(target.id),
        "department_codes": ["DT-123"],
        "checked_at": datetime.now(UTC).isoformat(),
    }
    if case == "wrong_entity":
        snapshot["legal_entity_id"] = str(uuid4())
    if case == "invalid_time":
        snapshot["checked_at"] = "not-a-time"
    if case == "empty":
        snapshot["department_codes"] = []
    setting = db.scalar(select(AppSetting).where(AppSetting.key == "dingtalk_directory_snapshot"))
    if setting is None:
        db.add(AppSetting(key="dingtalk_directory_snapshot", value=snapshot))
    else:
        setting.value = snapshot
    db.flush()
    response = TestClient(app).get("/api/v1/dingtalk/organization", headers=session_headers(db))
    assert response.status_code == 200
    returned = response.json()["directory_snapshot"]
    if case == "valid":
        assert returned["department_codes"] == ["DT-123"]
    else:
        assert returned is None
