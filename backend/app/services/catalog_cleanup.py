"""Transactional, exact-alias cleanup. Historical rows remain archived and auditable."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AssetPlatformLink,
    AuditLog,
    ImportProposedObject,
    Platform,
    PlatformTenant,
    Provider,
    ServiceInstance,
    ServiceProduct,
)
from app.services.catalog_reference import REFERENCES
from app.services.service_catalog import directory_record, provider_record


def normalized(name):
    return name.strip().casefold()


def cleanup_catalog(db: Session, *, actor_id, review=False):
    changes = []
    reviews = []
    review_candidates = []
    now = datetime.now(UTC)

    def change(item, **values):
        before = {key: getattr(item, key) for key in values}
        if all(before[key] == value for key, value in values.items()):
            return
        for key, value in values.items():
            setattr(item, key, value)
        changes.append(
            dict(
                object_type=item.__tablename__,
                id=str(item.id),
                name=getattr(item, "name", None),
                before=jsonable_encoder(before),
                after=jsonable_encoder(values),
            )
        )

    def note_created(item):
        db.add(item)
        db.flush()
        changes.append(
            dict(
                object_type=item.__tablename__,
                id=str(item.id),
                name=item.name,
                created=True,
                after=jsonable_encoder(
                    {
                        column.name: getattr(item, column.name)
                        for column in item.__table__.columns
                        if column.name not in {"created_at", "updated_at"}
                    }
                ),
            )
        )

    for platform in db.scalars(
        select(Platform).where(Platform.archived_at.is_(None), Platform.review_status == "approved")
    ):
        latest = db.scalar(
            select(AuditLog)
            .where(AuditLog.object_id == platform.id, AuditLog.action == "directory.review")
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(1)
        )
        evidence = latest.after_data or {} if latest else {}
        if evidence.get("decision") != "approved" or not evidence.get("source_url"):
            change(platform, review_status="pending_review")
    db.flush()
    for reference in REFERENCES:
        aliases = {normalized(name) for name in reference["aliases"]}
        providers = [
            item
            for item in db.scalars(select(Provider).where(Provider.archived_at.is_(None)))
            if normalized(item.name) in aliases
        ]
        provider_ids = {item.id for item in providers}
        platforms = [
            item
            for item in db.scalars(select(Platform).where(Platform.archived_at.is_(None)))
            if normalized(item.name) in aliases
            and (item.provider_id is None or item.provider_id in provider_ids)
        ]
        products = [
            item
            for item in db.scalars(
                select(ServiceProduct).where(ServiceProduct.archived_at.is_(None))
            )
            if item.provider_id in provider_ids
            and any(
                normalized(item.name) in {normalized(name) for name in service["aliases"]}
                for service in reference["services"]
            )
        ]
        if not providers and not platforms and not products:
            continue
        provider = next(
            (item for item in providers if normalized(item.name) == normalized(reference["name"])),
            None,
        )
        if provider is None:
            provider = Provider(
                id=uuid5(NAMESPACE_URL, "service-catalog-provider:" + reference["code"]),
                code="catalog-" + reference["code"],
                name=reference["name"],
                website=reference["website"],
            )
            note_created(provider)
        platform = next(
            (item for item in platforms if normalized(item.name) == normalized(reference["name"])),
            None,
        )
        if platform is None:
            platform = Platform(
                id=uuid5(NAMESPACE_URL, "service-catalog-platform:" + reference["code"]),
                code="catalog-" + reference["code"],
                name=reference["name"],
                provider_id=provider.id,
                category=reference["category"],
                website=reference["website"],
                review_status="pending_review",
            )
            note_created(platform)
        start = len(changes)
        change(provider, name=reference["name"], website=reference["website"])
        change(
            platform,
            provider_id=provider.id,
            name=reference["name"],
            category=reference["category"],
            website=reference["website"],
        )
        for legacy in platforms:
            if legacy.id == platform.id:
                continue
            for tenant in db.scalars(
                select(PlatformTenant).where(PlatformTenant.platform_id == legacy.id)
            ):
                collision = db.scalar(
                    select(PlatformTenant.id).where(
                        PlatformTenant.platform_id == platform.id,
                        PlatformTenant.legal_entity_id == tenant.legal_entity_id,
                        PlatformTenant.tenant_identifier == tenant.tenant_identifier,
                    )
                )
                if collision:
                    raise ValueError(f"{reference['name']} 存在重名公司账号，须人工核对后归并")
                change(tenant, platform_id=platform.id)
            for link in db.scalars(
                select(AssetPlatformLink).where(AssetPlatformLink.platform_id == legacy.id)
            ):
                collision = db.scalar(
                    select(AssetPlatformLink.id).where(
                        AssetPlatformLink.platform_id == platform.id,
                        AssetPlatformLink.asset_id == link.asset_id,
                        AssetPlatformLink.relation_type == link.relation_type,
                        AssetPlatformLink.archived_at.is_(None),
                    )
                )
                if collision and link.archived_at is None:
                    change(link, archived_at=now)
                change(link, platform_id=platform.id)
            for model, field in (
                (ServiceInstance, "purchase_platform_id"),
                (ImportProposedObject, "matched_platform_id"),
                (ServiceProduct, "platform_id"),
            ):
                for row in db.scalars(select(model).where(getattr(model, field) == legacy.id)):
                    change(row, **{field: platform.id})
            change(legacy, archived_at=now)
            db.flush()
        for spec in reference["services"]:
            product_aliases = {
                normalized(alias): default for alias, default in spec["aliases"].items()
            }
            matches = [item for item in products if normalized(item.name) in product_aliases]
            canonical = next(
                (
                    item
                    for item in matches
                    if item.provider_id == provider.id and item.name == spec["name"]
                ),
                None,
            )
            if canonical is None:
                canonical = ServiceProduct(
                    id=uuid5(
                        NAMESPACE_URL,
                        "service-catalog-product:" + reference["code"] + ":" + spec["code"],
                    ),
                    provider_id=provider.id,
                    platform_id=platform.id,
                    code="catalog-" + spec["code"],
                    name=spec["name"],
                    service_category=reference["category"],
                    billing_mode=spec["billing"],
                    plan_options=list(spec["plans"]),
                )
                note_created(canonical)
            change(
                canonical,
                platform_id=platform.id,
                service_category=reference["category"],
                billing_mode=spec["billing"],
                plan_options=list(spec["plans"]),
            )
            for legacy in matches:
                if legacy.id == canonical.id:
                    continue
                default = product_aliases[normalized(legacy.name)]
                for instance in db.scalars(
                    select(ServiceInstance).where(ServiceInstance.service_product_id == legacy.id)
                ):
                    values = {"service_product_id": canonical.id}
                    if default and (
                        not instance.subscription_name
                        or normalized(instance.subscription_name) == normalized(legacy.name)
                    ):
                        values["subscription_name"] = default
                    change(instance, **values)
                change(legacy, archived_at=now)
            db.flush()
        # Other service products remain distinct; only their provider ownership is corrected.
        for legacy in providers:
            if legacy.id == provider.id:
                continue
            for model in (Platform, ServiceProduct):
                for row in db.scalars(
                    select(model).where(model.provider_id == legacy.id, model.archived_at.is_(None))
                ):
                    if model is ServiceProduct and db.scalar(
                        select(ServiceProduct.id).where(
                            ServiceProduct.provider_id == provider.id,
                            ServiceProduct.code == row.code,
                            ServiceProduct.id != row.id,
                        )
                    ):
                        raise ValueError(f"{reference['name']} 存在服务编码冲突，须人工核对")
                    change(row, provider_id=provider.id)
            change(legacy, archived_at=now)
        if len(changes) != start:
            change(platform, review_status="pending_review")
        db.flush()
        review_candidates.append((platform, reference))
    db.flush()
    # Bring historical supplier-only records into the same directory without guessing
    # their website, package or approval. Multiple services/platforms remain distinct.
    platforms = list(db.scalars(select(Platform).where(Platform.archived_at.is_(None))))
    providers = list(db.scalars(select(Provider).where(Provider.archived_at.is_(None))))
    for platform in platforms:
        if platform.provider_id or "待确认" in platform.name or "未知" in platform.name:
            continue
        provider = next(
            (item for item in providers if normalized(item.name) == normalized(platform.name)), None
        )
        if provider is None:
            provider = Provider(
                id=uuid5(platform.id, "directory-provider"),
                code="DIR-" + platform.id.hex[:16],
                name=platform.name,
                website=platform.website,
            )
            note_created(provider)
            providers.append(provider)
        change(platform, provider_id=provider.id, review_status="pending_review")
    db.flush()
    for provider in providers:
        associated = [item for item in platforms if item.provider_id == provider.id]
        if not associated:
            platform = next(
                (item for item in platforms if normalized(item.name) == normalized(provider.name)),
                None,
            )
            if platform is not None:
                # Two distinct historical owners with the same name require manual review.
                continue
            platform = Platform(
                id=uuid5(provider.id, "directory-platform"),
                provider_id=provider.id,
                code="DIR-" + provider.id.hex[:16],
                name=provider.name,
                website=provider.website,
                category="other",
                review_status="pending_review",
            )
            note_created(platform)
            platforms.append(platform)
            associated = [platform]
        if len(associated) == 1:
            for product in db.scalars(
                select(ServiceProduct).where(
                    ServiceProduct.provider_id == provider.id,
                    ServiceProduct.platform_id.is_(None),
                    ServiceProduct.archived_at.is_(None),
                )
            ):
                change(product, platform_id=associated[0].id)
                change(associated[0], review_status="pending_review")
    db.flush()
    if review:
        for platform, reference in review_candidates:
            if platform.review_status == "approved":
                continue
            snapshot = directory_record(db, platform).model_dump(mode="json")
            expected = {
                spec["name"]: (spec["billing"], list(spec["plans"]))
                for spec in reference["services"]
            }
            actual = snapshot["services"]
            # Official sources cover only the listed services. Other historical
            # services require their own evidence before this directory is approved.
            if len(actual) != len(expected) or any(
                expected.get(item["name"]) != (item["billing_mode"], item["plan_options"])
                or item["provider_id"] != str(platform.provider_id)
                for item in actual
            ):
                continue
            change(platform, review_status="approved")
            facts = dict(
                decision="approved",
                note="按2026-10-10官方资料核对目录名称及套餐；历史Team保留，不推定采购、账号权利或付款事实。",
                source_url=reference["source"],
                source_urls=[reference["source"], *reference.get("extra_sources", ())],
            )
            reviews.append(
                dict(
                    id=str(platform.id), name=platform.name, revision=snapshot["revision"], **facts
                )
            )
            db.add(
                AuditLog(
                    actor_user_id=actor_id,
                    action="directory.review",
                    object_type="platform",
                    object_id=platform.id,
                    request_id="catalog-reference-20261010:" + reference["code"],
                    before_data=snapshot,
                    after_data=facts,
                )
            )
        db.flush()
    remaining = [
        directory_record(db, item)
        for item in db.scalars(select(Platform).where(Platform.archived_at.is_(None)))
        if item.review_status != "approved"
    ]
    linked = {item.provider_id for item in platforms}
    remaining += [provider_record(item) for item in providers if item.id not in linked]
    changes.sort(
        key=lambda item: (
            item["object_type"],
            item["id"],
            str(sorted(item.get("after", {}).keys())),
        )
    )
    if changes:
        db.add(
            AuditLog(
                actor_user_id=actor_id,
                action="directory.cleanup",
                object_type="service_catalog",
                request_id="catalog-reference-20261010",
                after_data={"changes": changes},
            )
        )
    return {
        "changes": changes,
        "reviews": sorted(reviews, key=lambda item: item["id"]),
        "pending": [
            dict(id=str(item.id), name=item.name, reason="需要真实官网、提供方和套餐来源后审核")
            for item in sorted(remaining, key=lambda item: (item.name, str(item.id)))
        ],
        "unlinked_services": [
            dict(id=str(item.id), name=item.name)
            for item in db.scalars(
                select(ServiceProduct)
                .where(ServiceProduct.platform_id.is_(None), ServiceProduct.archived_at.is_(None))
                .order_by(ServiceProduct.id)
            )
        ],
    }
