from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.access import AccessContext, require_global_manager
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import AuditLog, Platform, Provider, ServiceProduct
from app.schemas.inventory import ServiceProductRead
from app.schemas.service_catalog import (
    DirectoryCreate,
    DirectoryRead,
    DirectoryReview,
    DirectoryService,
    DirectoryUpdate,
    SubscriptionOption,
)
from app.services.service_catalog import digest, directory_record, provider_record

router = APIRouter(tags=["service-catalog"])


def locked_platform(db: Session, identity: UUID) -> Platform:
    item = db.scalar(
        select(Platform)
        .where(Platform.id == identity, Platform.archived_at.is_(None))
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "平台/供应商不存在")
    return item


def retry(db: Session, access: AccessContext, action: str, payload, object_id=None):
    if db.bind.dialect.name == "postgresql":
        lock = int(
            digest({"actor": str(access.user.id), "request": str(payload.request_id)})[:15], 16
        )
        db.execute(select(func.pg_advisory_xact_lock(lock)))
    operation = db.scalar(
        select(AuditLog).where(
            AuditLog.actor_user_id == access.user.id,
            AuditLog.action == action,
            AuditLog.request_id == str(payload.request_id),
        )
    )
    fingerprint = digest({**payload.model_dump(mode="json"), "target": str(object_id)})
    if operation and (operation.after_data or {}).get("request_digest") != fingerprint:
        raise HTTPException(409, "请求编号对应的内容已改变")
    return operation, fingerprint


def record(db, access, action, item, payload, fingerprint, before=None, **facts):
    try:
        db.flush()
        snapshot = directory_record(db, item).model_dump(
            mode="json", exclude={"review_note", "source_url"}
        )
        db.add(
            AuditLog(
                actor_user_id=access.user.id,
                action=action,
                object_type="platform",
                object_id=item.id,
                request_id=str(payload.request_id),
                before_data=before,
                after_data={"request_digest": fingerprint, "snapshot": snapshot, **facts},
            )
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "目录记录重复，请重新读取后重试") from exc


def check_revision(db, item, expected):
    current = directory_record(db, item)
    if current.revision != expected:
        raise HTTPException(409, "目录或套餐已改变，请重新读取后审核或保存")
    return current.model_dump(mode="json")


@router.get("/platform-directory", response_model=list[DirectoryRead])
def list_directory(db: Session = Depends(get_db)):
    platforms = list(db.scalars(select(Platform).where(Platform.archived_at.is_(None))))
    linked = {item.provider_id for item in platforms if item.provider_id}
    providers = list(db.scalars(select(Provider).where(Provider.archived_at.is_(None))))
    rows = [directory_record(db, item) for item in platforms]
    rows += [provider_record(item) for item in providers if item.id not in linked]
    return sorted(rows, key=lambda item: item.name.casefold())


@router.post(
    "/platform-directory", response_model=DirectoryRead, dependencies=[Depends(require_csrf)]
)
def create_directory(
    payload: DirectoryCreate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_global_manager),
):
    operation, fingerprint = retry(db, access, "directory.create", payload)
    if db.bind.dialect.name == "postgresql":
        name_lock = int(digest({"directory_name": payload.name.casefold()})[:15], 16)
        db.execute(select(func.pg_advisory_xact_lock(name_lock)))
    identity = uuid5(NAMESPACE_URL, f"directory:{access.user.id}:{payload.request_id}")
    if operation:
        return directory_record(db, locked_platform(db, identity))
    duplicate = db.scalar(
        select(Platform.id).where(
            func.lower(Platform.name) == payload.name.lower(), Platform.archived_at.is_(None)
        )
    )
    if duplicate:
        raise HTTPException(409, "平台/供应商已在目录中，请维护已有记录")
    provider = db.get(Provider, payload.provider_id) if payload.provider_id else None
    if payload.provider_id and (provider is None or provider.archived_at is not None):
        raise HTTPException(422, "原服务提供方不存在")
    if provider is None:
        provider = db.scalar(
            select(Provider).where(
                func.lower(Provider.name) == payload.name.lower(), Provider.archived_at.is_(None)
            )
        )
    if provider is None:
        provider = Provider(
            id=uuid5(identity, "provider"),
            code=f"DIR-{identity.hex[:16]}",
            name=payload.name,
            website=str(payload.website) if payload.website else None,
        )
        db.add(provider)
        db.flush()
    item = Platform(
        id=identity,
        provider_id=provider.id,
        code=f"DIR-{identity.hex[:16]}",
        name=payload.name,
        category=payload.category,
        website=str(payload.website) if payload.website else None,
        description=payload.description,
        review_status="pending_review",
        submitted_by_person_id=access.person_id,
    )
    db.add(item)
    if not db.scalar(
        select(Platform.id).where(
            Platform.provider_id == provider.id,
            Platform.id != item.id,
            Platform.archived_at.is_(None),
        )
    ):
        provider.name = payload.name
        provider.website = str(payload.website) if payload.website else None
        for product in db.scalars(
            select(ServiceProduct).where(
                ServiceProduct.provider_id == provider.id,
                ServiceProduct.platform_id.is_(None),
                ServiceProduct.archived_at.is_(None),
            )
        ):
            product.platform_id = item.id
    record(db, access, "directory.create", item, payload, fingerprint, name=item.name)
    return directory_record(db, item)


@router.patch(
    "/platform-directory/{identity}",
    response_model=DirectoryRead,
    dependencies=[Depends(require_csrf)],
)
def update_directory(
    identity: UUID,
    payload: DirectoryUpdate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_global_manager),
):
    item = locked_platform(db, identity)
    operation, fingerprint = retry(db, access, "directory.update", payload, identity)
    if operation:
        return directory_record(db, item)
    before = check_revision(db, item, payload.expected_revision)
    if payload.provider_id != item.provider_id:
        raise HTTPException(422, "服务提供方归并请使用经过核对的目录整理操作")
    duplicate = db.scalar(
        select(Platform.id).where(
            Platform.id != identity,
            func.lower(Platform.name) == payload.name.lower(),
            Platform.archived_at.is_(None),
        )
    )
    if duplicate:
        raise HTTPException(409, "目录名称已存在")
    item.name = payload.name
    item.category = payload.category
    item.website = str(payload.website) if payload.website else None
    item.description = payload.description
    item.review_status = "pending_review"
    associated = list(
        db.scalars(
            select(Platform.id).where(
                Platform.provider_id == item.provider_id, Platform.archived_at.is_(None)
            )
        )
    )
    if item.provider_id and associated == [item.id]:
        provider = db.get(Provider, item.provider_id)
        if provider and provider.archived_at is None:
            provider.name = item.name
            provider.website = item.website
    record(db, access, "directory.update", item, payload, fingerprint, before, name=item.name)
    return directory_record(db, item)


@router.post(
    "/platform-directory/{identity}/services",
    response_model=DirectoryRead,
    dependencies=[Depends(require_csrf)],
)
def save_directory_service(
    identity: UUID,
    payload: DirectoryService,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_global_manager),
):
    item = locked_platform(db, identity)
    operation, fingerprint = retry(db, access, "directory.service.save", payload, identity)
    if operation:
        return directory_record(db, item)
    before = check_revision(db, item, payload.expected_revision)
    if not item.provider_id:
        raise HTTPException(422, "请先补齐平台/供应商登记")
    product = db.get(ServiceProduct, payload.product_id) if payload.product_id else None
    if payload.product_id and (
        product is None or product.archived_at is not None or product.platform_id != identity
    ):
        raise HTTPException(422, "服务不属于当前平台/供应商")
    if db.scalar(
        select(ServiceProduct.id).where(
            ServiceProduct.platform_id == identity,
            ServiceProduct.archived_at.is_(None),
            func.lower(ServiceProduct.name) == payload.name.lower(),
            ServiceProduct.id != payload.product_id,
        )
    ):
        raise HTTPException(409, "服务已存在，请维护其可选套餐")
    if not product:
        product_id = uuid5(
            NAMESPACE_URL, f"directory-service:{access.user.id}:{payload.request_id}"
        )
        product = ServiceProduct(
            id=product_id,
            provider_id=item.provider_id,
            platform_id=item.id,
            code=f"DIR-{product_id.hex[:16]}",
            service_category=item.category,
            name=payload.name,
            billing_mode=payload.billing_mode,
            plan_options=payload.plan_options,
        )
        db.add(product)
    else:
        product.name = payload.name
        product.billing_mode = payload.billing_mode
        product.plan_options = payload.plan_options
    item.review_status = "pending_review"
    record(
        db,
        access,
        "directory.service.save",
        item,
        payload,
        fingerprint,
        before,
        product_id=str(product.id),
        plans=payload.plan_options,
    )
    return directory_record(db, item)


@router.post(
    "/platform-directory/{identity}/review",
    response_model=DirectoryRead,
    dependencies=[Depends(require_csrf)],
)
def review_directory(
    identity: UUID,
    payload: DirectoryReview,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(require_global_manager),
):
    item = locked_platform(db, identity)
    operation, fingerprint = retry(db, access, "directory.review", payload, identity)
    if operation:
        return directory_record(db, item)
    before = check_revision(db, item, payload.expected_revision)
    if payload.decision == "approved" and (
        not item.provider_id or not item.website or not payload.source_url
    ):
        raise HTTPException(422, "审核通过须补齐服务提供方、官网和核验来源")
    if payload.decision == "approved" and any(
        row["provider_id"] != str(item.provider_id) for row in before["services"]
    ):
        raise HTTPException(422, "服务提供方与目录不一致，请核对后审核")
    item.review_status = payload.decision
    record(
        db,
        access,
        "directory.review",
        item,
        payload,
        fingerprint,
        before,
        decision=payload.decision,
        note=payload.note,
        source_url=str(payload.source_url) if payload.source_url else None,
    )
    return directory_record(db, item)


@router.get("/subscription-options", response_model=list[SubscriptionOption])
def list_subscription_options(db: Session = Depends(get_db)):
    rows = db.execute(
        select(ServiceProduct, Platform.name)
        .join(Platform, ServiceProduct.platform_id == Platform.id)
        .join(Provider, ServiceProduct.provider_id == Provider.id)
        .where(
            ServiceProduct.archived_at.is_(None),
            Platform.archived_at.is_(None),
            Platform.review_status == "approved",
            Provider.archived_at.is_(None),
            Platform.provider_id == ServiceProduct.provider_id,
        )
        .order_by(Platform.name, ServiceProduct.name)
    ).all()
    return [
        SubscriptionOption(
            **ServiceProductRead.model_validate(product).model_dump(), platform_name=name
        )
        for product, name in rows
    ]
