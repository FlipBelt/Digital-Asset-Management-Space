"""Supplementary registration and explicit review, using synthetic isolated data."""

import base64
import io
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from test_agent_connector import create
from test_asset_center_integration import confirm, prepare

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models import (
    Asset,
    AssetFieldDefinition,
    AssetType,
    AuditLog,
    Person,
    Role,
    User,
    UserRoleScope,
)
from app.services.outcome_attachments import MAX_BYTES, validate_outcome

pytest_plugins = ["test_agent_connector"]


def internal(client, actors):
    with SessionLocal() as db:
        type_id = db.scalar(select(AssetType.id).where(AssetType.code == "internal_system"))
    return create(client, actors, asset_type_id=str(type_id), development_method="vibe_coding")


def save(client, item, **values):
    return client.put(
        "/api/v1/agent/assets/" + item["id"] + "/details",
        json={"request_id": str(uuid4()), "version": item["version"], **values},
    )


def active(actors, client):
    item = internal(client, actors)
    response = confirm(actors.owner, item, prepare(actors.owner, item, "company"))
    assert response.status_code == 200, response.text
    return response.json()


def image_bytes(kind="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", (12, 10), (10, 20, 30)).save(stream, format=kind)
    return stream.getvalue()


@pytest.fixture
def storage(tmp_path, monkeypatch):
    import app.api.v1.asset_attachments as files

    monkeypatch.setattr(files, "STORAGE", tmp_path)
    return tmp_path


def test_details_roundtrip_snapshot_and_proposal_is_not_permission(actors, agent_clients):
    client = agent_clients["owner"]
    item = internal(client, actors)
    with SessionLocal() as db:
        definition = AssetFieldDefinition(
            asset_type_id=UUID(item["asset_type_id"]),
            field_key=uuid4().hex,
            label="实际用途",
            data_type="text",
        )
        db.add(definition)
        db.commit()
        field_id = str(definition.id)
    payload = {
        "request_id": str(uuid4()),
        "version": item["version"],
        "profile": {
            "repository_url": "https://github.com/example/synthetic",
            "tech_stack": "Vue / FastAPI",
        },
        "fields": [{"field_definition_id": field_id, "value": "合成用途"}],
        "identifiers": [
            {
                "namespace": "GitHub",
                "identifier_type": "repository",
                "identifier_value": uuid4().hex,
            }
        ],
        "proposed_responsible_person_id": str(actors.person["other"]),
    }
    old = prepare(actors.owner, item)
    path = "/api/v1/agent/assets/" + item["id"] + "/details"
    response = client.put(path, json=payload)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["version"] == 2
    assert result["profile"]["tech_stack"] == "Vue / FastAPI"
    assert result["fields"][0]["value"] == "合成用途"
    assert any(f["id"] == field_id for f in result["field_definitions"])
    assert result["proposed_responsibilities"][0]["display_name"] == "测试身份 other"
    assert client.put(path, json=payload).json() == result
    assert (
        client.put(path, json=payload | {"profile": {"tech_stack": "different"}}).status_code == 409
    )
    assert client.put(path, json=payload | {"request_id": str(uuid4())}).status_code == 409
    assert (
        client.get("/api/v1/agent/operations/details.save/" + payload["request_id"]).json()[
            "result"
        ]
        == result
    )
    assert confirm(actors.owner, item, old).status_code == 409
    assert agent_clients["other"].get(path).status_code == 404
    assert actors.other.get("/api/v1/assets/" + item["id"]).status_code == 404
    receipt = prepare(actors.owner, result)
    assert receipt["preview"]["profile"]["tech_stack"] == "Vue / FastAPI"
    assert receipt["preview"]["fields"][0][2] == "实际用途"
    proposed = [r for r in receipt["preview"]["responsibilities"] if r[3] == "proposed_responsible"]
    assert proposed[0][6] == "测试身份 other"


def test_active_supplement_returns_private_draft_and_invalidates_approval(actors, agent_clients):
    item = active(actors, agent_clients["owner"])
    with SessionLocal() as db:
        db.get(Asset, UUID(item["id"])).review_status = "approved"
        db.commit()
    response = save(agent_clients["owner"], item, profile={"backup_description": "隔离合成说明"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert (result["status"], result["sharing_scope"], result["review_status"]) == (
        "draft",
        "private",
        "pending_review",
    )
    current = actors.owner.get("/api/v1/assets/" + item["id"]).json()
    assert current["confirmed_at"] is None and current["confirmed_by_person_id"] is None
    assert actors.other.get("/api/v1/assets/" + item["id"]).status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"profile": {"repository_url": "https://user:password@example.invalid"}},
        {"profile": {"repository_url": "https://example.invalid/?token=synthetic"}},
        {"fields": [{"field_definition_id": str(uuid4()), "value": "unknown"}]},
        {
            "identifiers": [
                {"namespace": "internal", "identifier_type": "id", "identifier_value": "fake"}
            ]
        },
        {"proposed_responsible_person_id": str(uuid4())},
        {"confirmed": True},
        {},
    ],
)
def test_invalid_supplements_do_not_mutate(actors, agent_clients, changes):
    item = internal(agent_clients["owner"], actors)
    response = save(agent_clients["owner"], item, **changes)
    assert response.status_code == 422, response.text
    assert agent_clients["owner"].get("/api/v1/agent/assets/" + item["id"]).json()["version"] == 1


def test_wrong_type_profile_and_owner(actors, agent_clients):
    item = create(agent_clients["owner"], actors)
    assert (
        save(agent_clients["owner"], item, profile={"tech_stack": "unsupported"}).status_code == 422
    )
    assert (
        save(
            agent_clients["other"], item, proposed_responsible_person_id=str(actors.person["other"])
        ).status_code
        == 404
    )
    assert (
        save(
            agent_clients["admin"], item, proposed_responsible_person_id=str(actors.person["admin"])
        ).status_code
        == 404
    )


def test_proposal_partial_update_preserves_omitted_roles_and_explicit_null_digest(
    actors, agent_clients
):
    client = agent_clients["owner"]
    item = internal(client, actors)
    r = save(
        client,
        item,
        proposed_responsible_person_id=str(actors.person["other"]),
        proposed_user_person_ids=[str(actors.person["stranger"])],
    )
    assert r.status_code == 200, r.text
    r = save(client, r.json(), proposed_responsible_person_id=str(actors.person["owner"]))
    assert r.status_code == 200, r.text
    roles = {p["role_type"]: p["person_id"] for p in r.json()["proposed_responsibilities"]}
    assert roles == {
        "proposed_responsible": str(actors.person["owner"]),
        "proposed_user": str(actors.person["stranger"]),
    }
    payload = {
        "request_id": str(uuid4()),
        "version": r.json()["version"],
        "profile": {"tech_stack": "synthetic"},
    }
    path = "/api/v1/agent/assets/" + item["id"] + "/details"
    assert client.put(path, json=payload).status_code == 200
    assert (
        client.put(path, json=payload | {"proposed_responsible_person_id": None}).status_code == 409
    )


def test_person_search_uses_live_company_and_minimal_fields(actors, agent_clients):
    path = "/api/v1/agent/people?q=测试身份%20other"
    response = agent_clients["owner"].get(path)
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [
        {
            "id": str(actors.person["other"]),
            "display_name": "测试身份 other",
            "department_name": "测试部门 1",
        }
    ]
    with SessionLocal() as db:
        db.get(Person, actors.person["other"]).employment_status = "inactive"
        db.commit()
    assert agent_clients["owner"].get(path).json()["items"] == []
    item = internal(agent_clients["owner"], actors)
    assert (
        save(
            agent_clients["owner"], item, proposed_responsible_person_id=str(actors.person["other"])
        ).status_code
        == 422
    )


@pytest.mark.parametrize(("kind", "extension"), [("PNG", "png"), ("JPEG", "jpg"), ("WEBP", "webp")])
@pytest.mark.parametrize("via_agent", [True, False])
def test_image_upload_preview_download_and_duplicate(
    actors, agent_clients, storage, kind, extension, via_agent
):
    item = internal(agent_clients["owner"], actors)
    content = image_bytes(kind)
    path = "/api/v1/agent/assets/" + item["id"] + "/attachments"
    payload = {
        "request_id": str(uuid4()),
        "version": 1,
        "file_name": "outcome." + extension,
        "content_base64": base64.b64encode(content).decode(),
    }
    if via_agent:
        response = agent_clients["owner"].post(path, json=payload)
        assert response.status_code == 200, response.text
        assert agent_clients["owner"].post(path, json=payload).json() == response.json()
        attachment = response.json()["attachment"]
        assert (
            agent_clients["owner"]
            .get("/api/v1/agent/operations/attachment.upload/" + payload["request_id"])
            .status_code
            == 200
        )
    else:
        response = actors.owner.post(
            "/api/v1/assets/" + item["id"] + "/attachments",
            files={"file": ("outcome." + extension, content)},
        )
        assert response.status_code == 200, response.text
        attachment = response.json()
    download = "/api/v1/assets/" + item["id"] + "/attachments/" + attachment["id"] + "/download"
    result = actors.owner.get(download)
    assert result.content == content and result.headers["content-type"].startswith("image/")
    assert (
        result.headers["x-content-type-options"] == "nosniff"
        and "no-store" in result.headers["cache-control"]
    )
    assert actors.other.get(download).status_code == 404
    assert len(list(storage.iterdir())) == 1
    assert (
        actors.owner.post(
            "/api/v1/assets/" + item["id"] + "/attachments",
            files={"file": ("outcome." + extension, content)},
        ).json()["id"]
        == attachment["id"]
    )
    assert actors.owner.get("/api/v1/assets/" + item["id"]).json()["version"] == 2


@pytest.mark.parametrize(
    ("content", "filename"),
    [
        (b"not-an-image", "fake.png"),
        (image_bytes(), "fake.jpg"),
        (b"<svg></svg>", "outcome.svg"),
        (b"", "empty.png"),
        (b"x" * (MAX_BYTES + 1), "large.png"),
    ],
    ids=["invalid", "extension", "svg", "empty", "overlimit"],
)
def test_malformed_or_oversized_outcomes_rejected(content, filename):
    with pytest.raises(HTTPException) as exc:
        validate_outcome(content, filename)
    assert exc.value.status_code == 422


def test_assignment_cannot_complete_registration_or_approve_outcome(actors, agent_clients):
    item = internal(agent_clients["owner"], actors)
    payload = {
        "version": item["version"],
        "ownership_scope": "company",
        "owner_department_id": None,
        "responsible_person_id": str(actors.person["other"]),
        "user_person_ids": [],
    }
    path = "/api/v1/assets/" + item["id"] + "/assignment"
    assert actors.owner.put(path, json=payload).status_code == 403
    r = actors.admin.put(path, json=payload)
    assert r.status_code == 200, r.text
    current = actors.owner.get("/api/v1/assets/" + item["id"]).json()
    assert (
        current["status"] == "draft"
        and current["review_status"] == "pending_review"
        and current["confirmed_at"] is None
    )
    response = confirm(actors.owner, current, prepare(actors.owner, current))
    assert response.status_code == 200, response.text
    active_item = response.json()
    payload["version"] = active_item["version"]
    assert actors.admin.put(path, json=payload).status_code == 200
    current = actors.owner.get("/api/v1/assets/" + item["id"]).json()
    assert current["status"] == "active" and current["review_status"] == "pending_review"
    assert current["confirmed_by_person_id"] == str(actors.person["owner"])


@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_explicit_review_exact_version_audit_and_no_machine_access(actors, agent_clients, decision):
    item = active(actors, agent_clients["owner"])
    path = "/api/v1/asset-reviews/" + item["id"]
    payload = {"version": item["version"], "decision": decision, "reason": "合成审核说明"}
    assert actors.owner.get("/api/v1/asset-reviews").status_code == 403
    assert actors.owner.post(path, json=payload).status_code == 403
    assert agent_clients["admin"].post(path, json=payload).status_code == 401
    assert item["id"] in {a["id"] for a in actors.admin.get("/api/v1/asset-reviews").json()["data"]}
    assert (
        actors.admin.post(path, json=payload | {"version": item["version"] - 1}).status_code == 409
    )
    if decision == "rejected":
        assert actors.admin.post(path, json=payload | {"reason": ""}).status_code == 422
    result = actors.admin.post(path, json=payload)
    assert result.status_code == 200, result.text
    assert (
        result.json()["review_status"] == decision
        and result.json()["version"] == item["version"] + 1
    )
    assert actors.admin.post(path, json=payload).status_code == 409
    with SessionLocal() as db:
        audit = db.scalar(
            select(AuditLog).where(
                AuditLog.object_id == UUID(item["id"]), AuditLog.action == "asset.review"
            )
        )
        assert audit.after_data["reason"] == "合成审核说明"


def test_review_csrf_department_scope_and_draft_exclusion(actors, agent_clients):
    item = active(actors, agent_clients["owner"])
    new = internal(agent_clients["owner"], actors)
    assert new["id"] not in {
        a["id"] for a in actors.admin.get("/api/v1/asset-reviews").json()["data"]
    }
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.person_id == actors.person["other"]))
        role = db.scalar(select(Role.id).where(Role.code == "department_manager"))
        db.add(
            UserRoleScope(
                user_id=user.id, role_id=role, scope_type="department", scope_id=actors.teams[1]
            )
        )
        db.commit()
    assert actors.other.get("/api/v1/asset-reviews").status_code == 200
    assert item["id"] not in {
        a["id"] for a in actors.other.get("/api/v1/asset-reviews").json()["data"]
    }
    payload = {"version": item["version"], "decision": "approved"}
    assert actors.other.post("/api/v1/asset-reviews/" + item["id"], json=payload).status_code == 404
    cookie = TestClient(app)
    cookie.cookies.set(get_settings().session_cookie_name, actors.admin.headers["X-PM-Session"])
    assert cookie.post("/api/v1/asset-reviews/" + item["id"], json=payload).status_code == 403
    csrf = cookie.get("/api/v1/sessions/current").json()["csrf_token"]
    assert (
        cookie.post(
            "/api/v1/asset-reviews/" + item["id"], json=payload, headers={"X-CSRF-Token": csrf}
        ).status_code
        == 200
    )
    cookie.close()


def test_web_profile_change_invalidates_review_version(actors, agent_clients):
    item = active(actors, agent_clients["owner"])
    path = "/api/v1/assets/" + item["id"]
    response = actors.admin.put(
        path + "/internal-system-profile", json={"tech_stack": "new synthetic stack"}
    )
    assert response.status_code == 200, response.text
    assert (
        actors.admin.post(
            "/api/v1/asset-reviews/" + item["id"],
            json={"version": item["version"], "decision": "approved"},
        ).status_code
        == 409
    )
    assert actors.admin.get(path).json()["version"] == item["version"] + 1


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        ("number", True),
        ("number", "5"),
        ("boolean", "false"),
        ("date", "not-a-date"),
        ("select", "outside-options"),
    ],
)
def test_type_field_validation(actors, agent_clients, kind, value):
    item = internal(agent_clients["owner"], actors)
    with SessionLocal() as db:
        field = AssetFieldDefinition(
            asset_type_id=UUID(item["asset_type_id"]),
            field_key=uuid4().hex,
            label="合成字段",
            data_type=kind,
            options=["allowed"] if kind == "select" else None,
        )
        db.add(field)
        db.commit()
        field_id = str(field.id)
    response = save(
        agent_clients["owner"], item, fields=[{"field_definition_id": field_id, "value": value}]
    )
    assert response.status_code == 422, response.text


def test_reserved_namespace_prefix_and_cross_company_candidates(actors, agent_clients):
    item = internal(agent_clients["owner"], actors)
    r = save(
        agent_clients["owner"],
        item,
        identifiers=[
            {
                "namespace": "internal:" + actors.entity,
                "identifier_type": "asset_code",
                "identifier_value": "fake",
            }
        ],
    )
    assert r.status_code == 422, r.text
    with SessionLocal() as db:
        from app.models import LegalEntity

        entity = LegalEntity(code=uuid4().hex, name="合成外部公司")
        db.add(entity)
        db.flush()
        person = Person(
            legal_entity_id=entity.id, employee_no="synthetic", display_name="测试身份 other"
        )
        db.add(person)
        db.commit()
        foreign_id = str(person.id)
    r = save(agent_clients["owner"], item, proposed_responsible_person_id=foreign_id)
    assert r.status_code == 422, r.text
    assert foreign_id not in {
        p["id"]
        for p in agent_clients["owner"].get("/api/v1/agent/people?q=测试身份").json()["items"]
    }
