from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import Boolean, Column, Date, MetaData, String, Table, Uuid, create_engine, select

from app.api.v1.asset_space import DraftInput, create_draft, draft_id, personal_scope
from app.models import Asset, AssetType
from app.schemas.inventory import ServiceInstanceCreate
from app.services.assets import AssetService


def test_draft_rejects_client_status_and_identity():
    base = dict(request_id=uuid4(), name="Skill", description="Description", asset_type_id=uuid4())
    for field in ["status", "created_by_person_id", "review_status"]:
        with pytest.raises(ValidationError):
            DraftInput(**base, **{field: "active"})
    with pytest.raises(ValidationError):
        DraftInput(**{**base, "name": "   "})


def test_request_ids_are_scoped_to_operator():
    request = uuid4()
    user = uuid4()
    assert draft_id(user, request) == draft_id(user, request)
    assert draft_id(user, request) != draft_id(uuid4(), request)


def test_draft_retry_returns_existing_without_write():
    payload = DraftInput(
        request_id=uuid4(), name="Skill", description="Test", asset_type_id=uuid4()
    )
    existing = SimpleNamespace(**payload.model_dump(exclude={"request_id"}), archived_at=None)
    db = Mock()
    db.get.side_effect = lambda model, identity: (
        SimpleNamespace(code="ai_skill", archived_at=None) if model is AssetType else existing
    )
    access = SimpleNamespace(person_id=uuid4(), user=SimpleNamespace(id=uuid4()))
    assert create_draft(payload, db, access) is existing
    db.add.assert_not_called()
    existing.name = "changed"
    with pytest.raises(HTTPException) as exc:
        create_draft(payload, db, access)
    assert exc.value.status_code == 409


def test_draft_requires_employee_and_system_development_type():
    payload = DraftInput(
        request_id=uuid4(),
        name="Skill",
        description="Test",
        asset_type_id=uuid4(),
        development_method="vibe_coding",
    )
    db = Mock()
    db.get.side_effect = lambda model, identity: (
        SimpleNamespace(code="ai_skill", archived_at=None) if model is AssetType else None
    )
    with pytest.raises(HTTPException) as exc:
        create_draft(payload, db, SimpleNamespace(person_id=None))
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        create_draft(
            payload, db, SimpleNamespace(person_id=uuid4(), user=SimpleNamespace(id=uuid4()))
        )
    assert exc.value.status_code == 422


def test_funding_requires_personal_payer_and_valid_dates():
    base = dict(asset_id=uuid4(), service_product_id=uuid4())
    with pytest.raises(ValidationError):
        ServiceInstanceCreate(**base, funding_source="personal")
    with pytest.raises(ValidationError):
        ServiceInstanceCreate(**base, funding_source="company", payer_person_id=uuid4())
    with pytest.raises(ValidationError):
        ServiceInstanceCreate(
            **base, starts_at=date.today(), expires_at=date.today() - timedelta(days=1)
        )
    assert ServiceInstanceCreate(**base).funding_source is None


def test_core_audit_uses_verified_actor():
    actor = uuid4()
    db = Mock()
    db.info = {"audit_actor_user_id": actor}
    AssetService._audit(db, "asset.update", uuid4(), None, {})
    assert db.add.call_args.args[0].actor_user_id == actor


def test_personal_projection_excludes_expired_and_other_people():
    # Real SQL execution over just the tables used by the projection predicate.
    engine = create_engine("sqlite://")
    metadata = MetaData()
    assets = Table(
        "assets",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("created_by_person_id", Uuid),
    )
    responsibilities = Table(
        "asset_responsibilities",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("asset_id", Uuid),
        Column("person_id", Uuid),
        Column("role_type", String),
        Column("archived_at", Date),
        Column("starts_at", Date),
        Column("ends_at", Date),
    )
    grants = Table(
        "access_grants",
        metadata,
        Column("id", Uuid, primary_key=True),
        Column("asset_id", Uuid),
        Column("account_id", Uuid),
        Column("person_id", Uuid),
        Column("department_id", Uuid),
        Column("archived_at", Date),
        Column("status", String),
        Column("starts_at", Date),
        Column("ends_at", Date),
    )
    Table(
        "accounts",
        metadata,
        Column("id", Uuid),
        Column("asset_id", Uuid),
        Column("archived_at", Date),
    )
    Table(
        "people",
        metadata,
        Column("id", Uuid),
        Column("department_id", Uuid),
        Column("archived_at", Date),
        Column("employment_status", String),
    )
    Table("departments", metadata, Column("id", Uuid), Column("archived_at", Date))
    Table(
        "department_memberships",
        metadata,
        Column("person_id", Uuid),
        Column("department_id", Uuid),
        Column("is_active", Boolean),
    )
    metadata.create_all(engine)
    person, other = uuid4(), uuid4()
    created, used, expired, foreign = [uuid4() for _ in range(4)]
    with engine.begin() as db:
        db.execute(
            assets.insert(),
            [
                {"id": x, "created_by_person_id": person if x == created else other}
                for x in [created, used, expired, foreign]
            ],
        )
        db.execute(
            responsibilities.insert(),
            [dict(id=uuid4(), asset_id=used, person_id=person, role_type="user")],
        )
        db.execute(
            grants.insert(),
            [
                dict(
                    id=uuid4(),
                    asset_id=expired,
                    person_id=person,
                    status="active",
                    ends_at=date.today() - timedelta(days=1),
                ),
                dict(id=uuid4(), asset_id=foreign, person_id=other, status="active", ends_at=None),
            ],
        )
        rows = set(db.scalars(select(Asset.id).where(personal_scope(person, None, "all"))))
        assert rows == {created, used}
        assert set(db.scalars(select(Asset.id).where(personal_scope(person, None, "created")))) == {
            created
        }


def test_zip_rejects_traversal_and_accepts_skill():
    import io
    import zipfile

    from app.api.v1.asset_attachments import validate_zip

    def archive(name):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as target:
            target.writestr(name, "# Skill")
        return data.getvalue()

    validate_zip(archive("skill/SKILL.md"))
    for name in ["../outside.txt", "/root.txt", "C:/outside.txt"]:
        with pytest.raises(HTTPException):
            validate_zip(archive(name))
    with pytest.raises(HTTPException):
        validate_zip(b"not a zip")


def test_draft_creation_forces_review_and_trusted_actor(monkeypatch):
    import app.api.v1.asset_space as module
    from app.models import AuditLog, Person

    payload = DraftInput(
        request_id=uuid4(),
        name="Skill",
        description="Test",
        asset_type_id=uuid4(),
        source_type="agent",
        source_system="codex",
    )
    person = SimpleNamespace(
        id=uuid4(), legal_entity_id=uuid4(), department_id=uuid4(), archived_at=None
    )
    access = SimpleNamespace(person_id=person.id, user=SimpleNamespace(id=uuid4()))
    db = Mock()
    db.get.side_effect = lambda model, identity: (
        person
        if model is Person
        else SimpleNamespace(code="ai_skill", archived_at=None)
        if model is AssetType
        else None
    )
    monkeypatch.setattr(module, "allocate_asset_code", lambda *args: "AI-001")
    monkeypatch.setattr(module, "ensure_internal_identifier", lambda *args: None)
    result = create_draft(payload, db, access)
    assert result.created_by_person_id == person.id
    assert result.status == "draft" and result.review_status == "pending_review"
    audits = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], AuditLog)]
    assert audits[0].actor_user_id == access.user.id
    db.commit.assert_called_once()


def test_membership_uses_unified_asset_and_private_visibility(monkeypatch):
    import app.api.v1.asset_space as module
    from app.models import Person, ServiceInstance, ServiceProduct

    payload = module.MembershipInput(
        request_id=uuid4(),
        service_product_id=uuid4(),
        plan="Pro",
        funding_source="personal",
        starts_at=date.today(),
        usage_frequency="weekly",
        primary_purpose="Design",
    )
    person = SimpleNamespace(
        id=uuid4(), legal_entity_id=uuid4(), department_id=uuid4(), archived_at=None
    )
    product = SimpleNamespace(id=payload.service_product_id, name="Tool", archived_at=None)
    access = SimpleNamespace(person_id=person.id, user=SimpleNamespace(id=uuid4()))
    db = Mock()
    db.scalar.return_value = SimpleNamespace(id=uuid4())
    db.get.side_effect = lambda model, identity: (
        person if model is Person else product if model is ServiceProduct else None
    )
    monkeypatch.setattr(module, "allocate_asset_code", lambda *args: "SUB-001")
    monkeypatch.setattr(module, "ensure_internal_identifier", lambda *args: None)
    result = module.create_membership(payload, db, access)
    assert result.confidentiality == "personal" and result.status == "draft"
    subscriptions = [
        c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ServiceInstance)
    ]
    assert len(subscriptions) == 1
    assert subscriptions[0].asset_id == result.id
    assert subscriptions[0].payer_person_id == person.id


def test_attachment_upload_requires_write_and_versions_draft(monkeypatch, tmp_path):
    import asyncio
    import io
    import zipfile

    from starlette.datastructures import UploadFile

    import app.api.v1.asset_attachments as module
    from app.models import AssetAttachment

    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("SKILL.md", "# Test")
    person_id = uuid4()
    asset_id = uuid4()
    asset = SimpleNamespace(
        id=asset_id, created_by_person_id=person_id, status="draft", version=1, archived_at=None
    )
    monkeypatch.setattr(module, "visible_asset", lambda *args: asset)
    monkeypatch.setattr(module, "lock_asset", lambda *args: asset)
    monkeypatch.setattr(module, "STORAGE", tmp_path)
    access = SimpleNamespace(
        person_id=person_id, user=SimpleNamespace(id=uuid4()), has_permission=lambda p: False
    )
    db = Mock()
    db.get.return_value = None
    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            module.upload_attachment(
                asset_id,
                UploadFile(io.BytesIO(content.getvalue()), filename="test.zip"),
                db,
                access,
            )
        )
    assert exc.value.status_code == 403
    db.add.assert_not_called()
    access.has_permission = lambda p: True
    item = asyncio.run(
        module.upload_attachment(
            asset_id, UploadFile(io.BytesIO(content.getvalue()), filename="test.zip"), db, access
        )
    )
    assert isinstance(item, AssetAttachment)
    assert asset.version == 2 and asset.review_status == "pending_review"
    assert (tmp_path / item.file_path).is_file()
    db.get.return_value = item
    again = asyncio.run(
        module.upload_attachment(
            asset_id, UploadFile(io.BytesIO(content.getvalue()), filename="test.zip"), db, access
        )
    )
    assert again is item and asset.version == 2
