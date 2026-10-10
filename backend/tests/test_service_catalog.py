"""Unified catalog, exact-plan selection and legacy cleanup on disposable PostgreSQL."""

from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import (
    Asset,
    AssetPlatformLink,
    AuditLog,
    Platform,
    PlatformTenant,
    Provider,
    ServiceInstance,
    ServiceProduct,
)
from app.services.catalog_cleanup import cleanup_catalog

pytest_plugins = ["test_asset_center_integration"]


def register(actors, **values):
    payload = dict(
        request_id=str(uuid4()),
        name="Synthetic provider " + uuid4().hex,
        website="https://example.com",
        category="ai",
    )
    payload.update(values)
    response = actors.admin.post("/api/v1/platform-directory", json=payload)
    assert response.status_code == 200, response.text
    return response.json(), payload


def service(actors, item, **values):
    payload = dict(
        request_id=str(uuid4()),
        expected_revision=item["revision"],
        name="Synthetic chat",
        plan_options=["Plus", "Pro", "Team"],
    )
    payload.update(values)
    response = actors.admin.post(f"/api/v1/platform-directory/{item['id']}/services", json=payload)
    assert response.status_code == 200, response.text
    return response.json(), payload


def approve(actors, item, **values):
    payload = dict(
        request_id=str(uuid4()),
        expected_revision=item["revision"],
        decision="approved",
        note="Synthetic directory verification",
        source_url="https://example.com/plans",
    )
    payload.update(values)
    response = actors.admin.post(f"/api/v1/platform-directory/{item['id']}/review", json=payload)
    return response, payload


def subscription(actors, item, **values):
    body = dict(
        request_id=str(uuid4()),
        service_product_id=item["services"][0]["id"],
        plan="Plus",
        catalog_plan="Plus",
        funding_source="personal",
        starts_at="2026-10-10",
        usage_frequency="weekly",
        primary_purpose="Synthetic core path",
    )
    body.update(values)
    return actors.owner.post("/api/v1/space/memberships", json=body), body


def test_registration_is_single_entry_idempotent_and_rejects_changed_request(actors):
    item, payload = register(actors)
    assert item["review_status"] == "pending_review" and item["provider_id"]
    replay = actors.admin.post("/api/v1/platform-directory", json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == item["id"]
    payload["name"] += " changed"
    assert actors.admin.post("/api/v1/platform-directory", json=payload).status_code == 409
    assert actors.owner.post("/api/v1/platform-directory", json=payload).status_code == 403
    with SessionLocal() as db:
        assert (
            len(list(db.scalars(select(Provider).where(Provider.id == UUID(item["provider_id"])))))
            == 1
        )


@pytest.mark.parametrize(
    "name", ["ChatGPT Plus", "ChatGPT Team", "ChatGPT Pro", "Claude Pro", "Plus", "Team", "Pro"]
)
def test_plan_cannot_be_registered_as_platform(actors, name):
    assert (
        actors.admin.post(
            "/api/v1/platform-directory", json=dict(request_id=str(uuid4()), name=name)
        ).status_code
        == 422
    )
    body = dict(code="bad-" + uuid4().hex, name=name)
    assert actors.admin.post("/api/v1/providers", json=body).status_code == 422
    assert actors.admin.post("/api/v1/platforms", json=body).status_code == 422
    with SessionLocal() as db:
        provider_id = str(db.get(ServiceProduct, UUID(actors.product)).provider_id)
    assert (
        actors.admin.post(
            "/api/v1/service-products", json={**body, "provider_id": provider_id}
        ).status_code
        == 422
    )


def test_review_selectable_plans_owner_privacy_and_replay(actors):
    item, _ = register(actors)
    item, _ = service(actors, item)
    response, payload = subscription(actors, item)
    assert response.status_code == 422
    review, review_payload = approve(actors, item)
    assert review.status_code == 200, review.text
    item = review.json()
    options = actors.owner.get("/api/v1/subscription-options").json()
    assert next(row for row in options if row["id"] == item["services"][0]["id"])[
        "plan_options"
    ] == ["Plus", "Pro", "Team"]
    response = actors.owner.post("/api/v1/space/memberships", json=payload)
    assert response.status_code == 200, response.text
    asset = response.json()
    assert asset["sharing_scope"] == "private" and asset["created_by_person_id"] == str(
        actors.person["owner"]
    )
    assert actors.owner.post("/api/v1/space/memberships", json=payload).json()["id"] == asset["id"]
    assert (
        actors.admin.post(
            f"/api/v1/platform-directory/{item['id']}/review", json=review_payload
        ).status_code
        == 200
    )
    with SessionLocal() as db:
        event = db.scalar(
            select(AuditLog).where(
                AuditLog.object_id == UUID(item["id"]), AuditLog.action == "directory.review"
            )
        )
        assert event.actor_user_id == UUID(
            actors.admin.get("/api/v1/sessions/current").json()["id"]
        )
        assert event.after_data["source_url"] == "https://example.com/plans"
        instance = db.scalar(
            select(ServiceInstance).where(ServiceInstance.asset_id == UUID(asset["id"]))
        )
        assert (
            instance.subscription_name == "Plus"
            and instance.payer_person_id == actors.person["owner"]
        )


def test_review_permissions_sources_and_stale_revision(actors):
    item, _ = register(actors)
    route = f"/api/v1/platform-directory/{item['id']}/review"
    review, payload = approve(actors, item, source_url=None)
    assert review.status_code == 422
    payload["source_url"] = "https://example.com"
    assert actors.owner.post(route, json=payload).status_code == 403
    item2, _ = service(actors, item)
    assert actors.admin.post(route, json=payload).status_code == 409
    review, _ = approve(actors, item2, decision="rejected", source_url=None)
    assert review.status_code == 200 and review.json()["review_status"] == "rejected"
    assert approve(actors, review.json(), note=" ")[0].status_code == 422


def test_service_edits_invalidate_approval_and_wrong_plan_is_rejected(actors):
    item, _ = register(actors)
    item, payload = service(actors, item)
    assert (
        actors.admin.post(
            f"/api/v1/platform-directory/{item['id']}/services",
            json=dict(
                request_id=str(uuid4()),
                expected_revision=item["revision"],
                name="Synthetic chat",
                plan_options=["Plus"],
            ),
        ).status_code
        == 409
    )
    assert (
        actors.admin.post(
            f"/api/v1/platform-directory/{item['id']}/services", json=payload
        ).status_code
        == 200
    )
    payload["plan_options"] = ["Plus", "Plus"]
    assert (
        actors.admin.post(
            f"/api/v1/platform-directory/{item['id']}/services", json=payload
        ).status_code
        == 422
    )
    item = approve(actors, item)[0].json()
    assert subscription(actors, item, plan="Unknown", catalog_plan="Unknown")[0].status_code == 422
    assert (
        subscription(actors, item, plan="Actual custom plan", catalog_plan=None)[0].status_code
        == 200
    )
    assert subscription(actors, item, plan="Pro", catalog_plan="Plus")[0].status_code == 422
    updated, _ = service(actors, item, product_id=item["services"][0]["id"], plan_options=["Pro"])
    assert updated["review_status"] == "pending_review"
    assert not any(
        row["id"] == item["services"][0]["id"]
        for row in actors.owner.get("/api/v1/subscription-options").json()
    )
    assert subscription(actors, updated)[0].status_code == 422


def test_orphan_provider_completion_keeps_identity_and_hides_separate_row(actors):
    with SessionLocal() as db:
        provider = Provider(code="orphan-" + uuid4().hex, name="Synthetic historical provider")
        db.add(provider)
        db.flush()
        product = ServiceProduct(
            provider_id=provider.id,
            code="historical",
            name="Historical service",
            service_category="other",
            billing_mode="other",
        )
        db.add(product)
        db.commit()
        identity = str(provider.id)
        product_id = str(product.id)
    rows = actors.admin.get("/api/v1/platform-directory").json()
    assert next(item for item in rows if item["id"] == identity)["kind"] == "provider"
    item, _ = register(
        actors, provider_id=identity, name="Synthetic historical provider " + uuid4().hex
    )
    rows = actors.admin.get("/api/v1/platform-directory").json()
    assert not any(item["id"] == identity for item in rows)
    assert item["provider_id"] == identity
    assert item["services"][0]["id"] == product_id
    with SessionLocal() as db:
        assert db.get(Provider, UUID(identity)).name == item["name"]
    updated = actors.admin.patch(
        f"/api/v1/platform-directory/{item['id']}",
        json=dict(
            request_id=str(uuid4()),
            expected_revision=item["revision"],
            provider_id=identity,
            name=item["name"] + " updated",
            website="https://example.com/updated",
            category="other",
        ),
    )
    assert updated.status_code == 200, updated.text
    with SessionLocal() as db:
        provider = db.get(Provider, UUID(identity))
        assert provider.name == updated.json()["name"]
        assert provider.website == updated.json()["website"]


def test_cleanup_dry_run_preserves_history_apply_is_idempotent_and_no_guess_for_unknown(actors):
    actor_id = UUID(actors.admin.get("/api/v1/sessions/current").json()["id"])
    with SessionLocal() as db:
        provider = Provider(code="legacy-" + uuid4().hex, name="ChatGPT Plus")
        unknown = Platform(
            code="unknown-" + uuid4().hex,
            name="VPN服务（供应商待确认）",
            review_status="approved",
        )
        db.add_all([provider, unknown])
        db.flush()
        legacy_platform = Platform(
            provider_id=provider.id,
            code="plus",
            name="ChatGPT Plus",
            review_status="pending_review",
        )
        db.add(legacy_platform)
        db.flush()
        product = ServiceProduct(
            provider_id=provider.id,
            code="plus",
            name="ChatGPT Plus",
            service_category="ai",
            billing_mode="subscription",
        )
        db.add(product)
        db.flush()
        asset = Asset(
            asset_code="CAT-" + uuid4().hex,
            name="Historical actual subscription",
            asset_type_id=UUID(actors.skill),
            legal_entity_id=UUID(actors.entity),
            created_by_person_id=actors.person["owner"],
            status="active",
            sharing_scope="private",
        )
        db.add(asset)
        db.flush()
        tenant = PlatformTenant(
            asset_id=asset.id,
            platform_id=legacy_platform.id,
            legal_entity_id=UUID(actors.entity),
            tenant_identifier="historical-" + uuid4().hex,
        )
        link = AssetPlatformLink(
            asset_id=asset.id,
            platform_id=legacy_platform.id,
            review_status="approved",
            note="Keep this historical relationship",
        )
        db.add_all([tenant, link])
        instance = ServiceInstance(
            asset_id=asset.id,
            service_product_id=product.id,
            subscription_name=None,
            payer_person_id=actors.person["owner"],
            funding_source="personal",
            starts_at=date(2026, 10, 10),
            purchase_platform_id=legacy_platform.id,
        )
        db.add(instance)
        db.commit()
        old_id, instance_id, asset_id, unknown_id = product.id, instance.id, asset.id, unknown.id
        tenant_id, link_id = tenant.id, link.id
        report = cleanup_catalog(db, actor_id=actor_id, review=True)
        assert report["changes"]
        db.rollback()
        assert db.get(ServiceInstance, instance_id).service_product_id == old_id
        assert db.get(Platform, unknown_id).review_status == "approved"
        report = cleanup_catalog(db, actor_id=actor_id, review=True)
        db.commit()
        db.expire_all()
        current = db.get(ServiceInstance, instance_id)
        assert current.subscription_name == "Plus" and current.asset_id == asset_id
        assert current.service_product_id != old_id
        assert db.get(ServiceProduct, old_id).archived_at is not None
        assert db.get(Platform, unknown_id).review_status == "pending_review"
        assert db.get(Asset, asset_id).name == "Historical actual subscription"
        canonical_platform = db.get(ServiceProduct, current.service_product_id).platform_id
        assert current.purchase_platform_id == canonical_platform
        assert current.payer_person_id == actors.person["owner"]
        assert current.funding_source == "personal" and current.starts_at == date(2026, 10, 10)
        assert db.get(PlatformTenant, tenant_id).platform_id == canonical_platform
        assert db.get(AssetPlatformLink, link_id).platform_id == canonical_platform
        assert db.get(AssetPlatformLink, link_id).note == "Keep this historical relationship"
        assert db.get(Platform, canonical_platform).review_status == "approved"
        second = cleanup_catalog(db, actor_id=actor_id, review=True)
        assert second["changes"] == []
        db.rollback()


def test_cleanup_does_not_assume_third_party_ownership_or_review_unknown_services(actors):
    actor_id = UUID(actors.admin.get("/api/v1/sessions/current").json()["id"])
    with SessionLocal() as db:
        reseller = Provider(code="reseller-" + uuid4().hex, name="Synthetic third-party reseller")
        official = Provider(code="minimax-" + uuid4().hex, name="MiniMax")
        db.add_all([reseller, official])
        db.flush()
        product = ServiceProduct(
            provider_id=reseller.id,
            code="resold-chat",
            name="ChatGPT",
            service_category="ai",
            billing_mode="subscription",
        )
        unknown = ServiceProduct(
            provider_id=official.id,
            code="unknown-" + uuid4().hex,
            name="Unverified MiniMax package",
            service_category="ai",
            billing_mode="subscription",
        )
        third_party_platform = Platform(
            provider_id=reseller.id,
            code="resold-platform",
            name="ChatGPT Plus",
            review_status="pending_review",
        )
        db.add_all([product, unknown, third_party_platform])
        db.commit()
        reseller_id, product_id, unknown_id, third_party_id = (
            reseller.id,
            product.id,
            unknown.id,
            third_party_platform.id,
        )
        report = cleanup_catalog(db, actor_id=actor_id, review=True)
        db.commit()
        db.expire_all()
        assert db.get(ServiceProduct, product_id).provider_id == reseller_id
        assert db.get(ServiceProduct, product_id).archived_at is None
        assert db.get(Platform, third_party_id).provider_id == reseller_id
        assert db.get(Platform, third_party_id).archived_at is None
        unknown_platform = db.get(ServiceProduct, unknown_id).platform_id
        assert db.get(Platform, unknown_platform).review_status == "pending_review"
        assert any(item["id"] == str(unknown_platform) for item in report["pending"])
        cleanup_catalog(db, actor_id=actor_id, review=True)
        assert db.get(Platform, unknown_platform).review_status == "pending_review"
        db.rollback()


def test_membership_replay_survives_catalog_changes(actors):
    item, _ = register(actors)
    item, _ = service(actors, item)
    item = approve(actors, item)[0].json()
    created, payload = subscription(actors, item)
    assert created.status_code == 200
    service(actors, item, product_id=item["services"][0]["id"], plan_options=["Enterprise"])
    replay = actors.owner.post("/api/v1/space/memberships", json=payload)
    assert replay.status_code == 200 and replay.json()["id"] == created.json()["id"]


def test_existing_inventory_writes_follow_review_and_plan_rules(actors):
    item, _ = register(actors)
    item, _ = service(actors, item)
    item = approve(actors, item)[0].json()
    draft = actors.owner.post(
        "/api/v1/assets/draft",
        json=dict(
            request_id=str(uuid4()),
            name="Synthetic company service",
            description="Local test only",
            asset_type_id=actors.skill,
        ),
    ).json()
    body = dict(
        asset_id=draft["id"],
        service_product_id=item["services"][0]["id"],
        subscription_name="Incorrect",
        catalog_plan="Incorrect",
    )
    assert actors.owner.post("/api/v1/service-instances", json=body).status_code == 422
    body.update(subscription_name="Plus", catalog_plan="Plus")
    assert actors.owner.post("/api/v1/service-instances", json=body).status_code == 201
    invalid = actors.admin.post(
        "/api/v1/service-products",
        json=dict(
            provider_id=str(uuid4()), platform_id=item["id"], code="wrong", name="Wrong provider"
        ),
    )
    assert invalid.status_code == 422
    updated = actors.admin.patch(
        f"/api/v1/platforms/{item['id']}", json=dict(description="Changed registration evidence")
    )
    assert updated.status_code == 200 and updated.json()["review_status"] == "pending_review"
    assert not any(
        row["id"] == item["services"][0]["id"]
        for row in actors.owner.get("/api/v1/subscription-options").json()
    )


def test_cli_preview_digest_authorization_and_bound_apply(actors, monkeypatch, capsys):
    import json

    from app.cli.normalize_service_catalog import main

    admin_id = actors.admin.get("/api/v1/sessions/current").json()["id"]
    owner_id = actors.owner.get("/api/v1/sessions/current").json()["id"]
    with SessionLocal() as db:
        provider = Provider(code="cli-" + uuid4().hex, name="Synthetic CLI supplier " + uuid4().hex)
        db.add(provider)
        db.commit()
        provider_id = provider.id
    monkeypatch.setattr("sys.argv", ["catalog", "--actor-id", owner_id])
    with pytest.raises(RuntimeError, match="管理员"):
        main()
    monkeypatch.setattr("sys.argv", ["catalog", "--actor-id", admin_id, "--review-known"])
    main()
    preview = json.loads(capsys.readouterr().out)
    assert preview["applied"] is False and preview["changes"]
    with SessionLocal() as db:
        assert db.scalar(select(Platform.id).where(Platform.provider_id == provider_id)) is None
    monkeypatch.setattr(
        "sys.argv",
        [
            "catalog",
            "--actor-id",
            admin_id,
            "--review-known",
            "--apply",
            "--expected-digest",
            "wrong",
        ],
    )
    with pytest.raises(RuntimeError, match="摘要"):
        main()
    monkeypatch.setattr(
        "sys.argv",
        [
            "catalog",
            "--actor-id",
            admin_id,
            "--review-known",
            "--apply",
            "--expected-digest",
            preview["digest"],
        ],
    )
    main()
    applied = json.loads(capsys.readouterr().out)
    assert applied["applied"] is True and applied["digest"] == preview["digest"]
    with SessionLocal() as db:
        assert db.scalar(select(Platform.id).where(Platform.provider_id == provider_id)) is not None
