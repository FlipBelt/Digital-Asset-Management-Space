import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog, Platform, Provider, ServiceProduct
from app.schemas.inventory import ServiceProductRead
from app.schemas.service_catalog import DirectoryRead


def digest(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def validate_subscription(db: Session, product: ServiceProduct, plan, catalog_plan):
    if product.platform_id:
        platform = db.scalar(
            select(Platform).where(Platform.id == product.platform_id).with_for_update()
        )
        db.refresh(product)
        provider = db.get(Provider, product.provider_id)
        if (
            platform is None
            or platform.id != product.platform_id
            or platform.archived_at is not None
            or platform.review_status != "approved"
            or platform.provider_id != product.provider_id
            or provider is None
            or provider.archived_at is not None
            or product.archived_at is not None
        ):
            raise HTTPException(422, "平台/供应商尚未通过目录审核")
    if catalog_plan is not None and (
        catalog_plan != plan or catalog_plan not in product.plan_options
    ):
        raise HTTPException(422, "套餐已改变，请重新选择或补充实际套餐")


def directory_record(db: Session, platform: Platform) -> DirectoryRead:
    provider = db.get(Provider, platform.provider_id) if platform.provider_id else None
    services = list(
        db.scalars(
            select(ServiceProduct)
            .where(ServiceProduct.platform_id == platform.id, ServiceProduct.archived_at.is_(None))
            .order_by(ServiceProduct.name)
        )
    )
    values = dict(
        id=str(platform.id),
        kind="platform",
        provider_id=str(platform.provider_id) if platform.provider_id else None,
        provider_name=provider.name if provider else None,
        name=platform.name,
        category=platform.category,
        website=platform.website,
        description=platform.description,
        review_status=platform.review_status,
        services=[
            ServiceProductRead.model_validate(item).model_dump(mode="json") for item in services
        ],
    )
    revision = digest(values)
    review = db.scalar(
        select(AuditLog)
        .where(AuditLog.object_id == platform.id, AuditLog.action == "directory.review")
        .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .limit(1)
    )
    evidence = review.after_data or {} if review else {}
    return DirectoryRead(
        **values,
        revision=revision,
        review_note=evidence.get("note"),
        source_url=evidence.get("source_url"),
    )


def provider_record(provider: Provider) -> DirectoryRead:
    return DirectoryRead(
        id=provider.id,
        kind="provider",
        provider_id=provider.id,
        provider_name=provider.name,
        name=provider.name,
        category="other",
        website=provider.website,
        description=None,
        review_status="incomplete",
        revision="",
        services=[],
    )
