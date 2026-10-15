"""Company service views exclude personal registrations without changing history or access."""

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Asset, MetricDefinition, MetricSample, ServiceInstance
from tests.test_asset_center_integration import draft, membership

pytest_plugins = ["tests.test_asset_center_integration"]


def company_service(actors, *, source_system=None, funding_source=None):
    asset = draft(actors.owner, actors, name="隔离公司服务", source_system=source_system)
    with SessionLocal() as db:
        instance = ServiceInstance(
            asset_id=UUID(asset["id"]),
            service_product_id=UUID(actors.product),
            subscription_name="隔离公司套餐",
            funding_source=funding_source,
            payer_person_id=actors.person["owner"] if funding_source == "personal" else None,
        )
        db.add(instance)
        db.commit()
        return asset, str(instance.id)


def instance_ids(client, scope=None):
    response = client.get("/api/v1/service-instances", params={"scope": scope} if scope else {})
    assert response.status_code == 200, response.text
    return {row["id"] for row in response.json()}


@pytest.mark.parametrize("funding", ["personal", "company", "department", "free", "trial"])
def test_company_scope_excludes_all_personal_registrations_and_preserves_default(actors, funding):
    personal_asset, personal = membership(actors.owner, actors, funding)
    _, company_id = company_service(actors, funding_source=funding)
    before = actors.owner.get("/api/v1/space/memberships").json()
    for client in (actors.owner, actors.admin):
        default = instance_ids(client)
        assert default == instance_ids(client, "all")
        assert personal["id"] in default and company_id in default
        company = instance_ids(client, "company")
        assert company_id in company and personal["id"] not in company
    assert actors.owner.get("/api/v1/space/memberships").json() == before
    current = actors.owner.get(f"/api/v1/assets/{personal_asset['id']}")
    assert current.status_code == 200 and current.json()["is_personal_subscription"]
    stored = next(row for row in before if row["id"] == personal["id"])
    assert stored["funding_source"] == funding
    assert stored["starts_at"] == personal["starts_at"]
    assert stored["subscription_name"] == personal["subscription_name"]


def test_company_scope_preserves_visibility_and_does_not_expose_other_people(actors):
    _, personal = membership(actors.owner, actors)
    _, company_id = company_service(actors)
    for scope in (None, "all", "company"):
        assert company_id not in instance_ids(actors.other, scope)
        assert personal["id"] not in instance_ids(actors.other, scope)
    assert company_id in instance_ids(actors.admin, "company")


@pytest.mark.parametrize("archived", ["asset", "instance"])
def test_company_scope_keeps_archive_filter(actors, archived):
    asset, instance_id = company_service(actors)
    with SessionLocal() as db:
        item = db.get(Asset, UUID(asset["id"])) if archived == "asset" else db.get(ServiceInstance, UUID(instance_id))
        item.archived_at = datetime.now(UTC)
        db.commit()
    for scope in (None, "company"):
        assert instance_id not in instance_ids(actors.admin, scope)


def test_company_scope_uses_subscription_type_as_well_as_registration_source(actors):
    asset, instance_id = company_service(actors, source_system="membership-registration")
    assert not asset["is_personal_subscription"]
    assert instance_id in instance_ids(actors.owner, "company")


def test_company_scope_does_not_change_company_metrics_or_delete_personal_history(actors):
    _, personal = membership(actors.owner, actors)
    _, company_id = company_service(actors)
    with SessionLocal() as db:
        definition = db.scalar(select(MetricDefinition).where(MetricDefinition.archived_at.is_(None)))
        assert definition is not None
        definition_id = str(definition.id)
        historical = MetricSample(
            service_instance_id=UUID(personal["id"]),
            metric_definition_id=definition.id,
            value=12,
            currency="CNY",
            collected_at=datetime.now(UTC),
            source_type="manual",
        )
        db.add(historical)
        db.commit()
        history_id = str(historical.id)
    body = {"metric_definition_id": definition_id, "value": "25.50", "currency": "CNY"}
    saved = actors.owner.post(f"/api/v1/service-instances/{company_id}/metrics", json=body)
    assert saved.status_code == 201, saved.text
    assert company_id in instance_ids(actors.owner, "company")
    company_metrics = actors.owner.get(f"/api/v1/service-instances/{company_id}/metrics")
    assert company_metrics.status_code == 200
    assert saved.json()["id"] in {row["id"] for row in company_metrics.json()}
    history = actors.owner.get(f"/api/v1/service-instances/{personal['id']}/metrics")
    assert history.status_code == 200
    assert history_id in {row["id"] for row in history.json()}
    assert actors.other.get(f"/api/v1/service-instances/{personal['id']}/metrics").status_code == 404


def test_service_instance_scope_rejects_unknown_values(actors):
    response = actors.admin.get("/api/v1/service-instances", params={"scope": "unsupported"})
    assert response.status_code == 422
