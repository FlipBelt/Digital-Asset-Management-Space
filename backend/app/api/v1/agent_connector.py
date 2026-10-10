"""The first-party web approval routes and delegated tool routes stay separate."""

import json
import secrets
from datetime import timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.asset_space import (
    AI_ASSISTED_CODES,
    AI_DEVELOPMENT_METHODS,
    DraftInput,
    persist_draft,
)
from app.core.access import AccessContext, asset_visibility_clause, get_access_context
from app.core.agent_auth import (
    SCOPES,
    agent_access,
    digest,
    employee_access,
    enabled,
    frontend_url,
    now,
    random_code,
    throttle,
)
from app.core.auth import require_csrf
from app.db.session import get_db
from app.models import AgentGrant, AgentIncubation, AgentOperation, Asset, AssetType, AuditLog
from app.schemas.agent_connector import (
    AttachmentInput,
    DetailsInput,
    DeviceApprove,
    DeviceCode,
    DevicePoll,
    DeviceStart,
    DraftUpdate,
    IncubationInput,
)

router = APIRouter(prefix="/agent", tags=["agent-connector"], dependencies=[Depends(enabled)])


def no_store(response: Response):
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"


def audit(db, access, action, object_id):
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action=action,
            object_type="agent_connector",
            object_id=object_id,
            after_data={"source": "agent_connector"},
        )
    )


@router.post("/device/start")
def device_start(
    payload: DeviceStart, request: Request, response: Response, db: Session = Depends(get_db)
):
    no_store(response)
    throttle("pair:" + digest(request.client.host if request.client else "unknown"), 5)
    pending = db.scalar(
        select(func.count())
        .select_from(AgentGrant)
        .where(AgentGrant.device_expires_at > now(), AgentGrant.token_hash.is_(None))
    )
    if pending >= 1000:
        raise HTTPException(429, "请求过多，请稍后重试")
    device_code, code = secrets.token_urlsafe(32), random_code()
    db.add(
        AgentGrant(
            device_hash=digest(device_code),
            user_code_hash=digest(code),
            client_name=payload.client_name,
            device_expires_at=now() + timedelta(minutes=10),
        )
    )
    db.commit()
    # Codes are not placed in URLs, access logs, referrers or browser history.
    return {
        "device_code": device_code,
        "user_code": code,
        "expires_in": 600,
        "interval": 5,
        "verification_uri": frontend_url("agent/connect"),
    }


@router.post("/device/poll")
def device_poll(
    payload: DevicePoll, response: Response, request: Request, db: Session = Depends(get_db)
):
    no_store(response)
    throttle("poll:" + digest(request.client.host if request.client else "unknown"), 120, 60)
    item = db.scalar(
        select(AgentGrant)
        .where(AgentGrant.device_hash == digest(payload.device_code))
        .with_for_update()
    )
    if item is None or item.revoked_at is not None or item.device_expires_at <= now():
        raise HTTPException(400, "授权已失效，请重新连接")
    if item.token_hash:
        raise HTTPException(400, "授权已领取；如果结果丢失，请重新连接")
    if item.last_polled_at and item.last_polled_at > now() - timedelta(seconds=5):
        raise HTTPException(429, "请等待五秒再查询", headers={"Retry-After": "5"})
    item.last_polled_at = now()
    if not item.user_id:
        db.commit()
        return {"status": "pending"}
    token = "agt_" + secrets.token_urlsafe(32)
    item.token_hash = digest(token)
    item.token_expires_at = now() + timedelta(hours=__ttl())
    db.commit()
    return {
        "status": "authorized",
        "access_token": token,
        "expires_at": item.token_expires_at,
        "scopes": SCOPES,
    }


def __ttl():
    from app.core.config import get_settings

    return get_settings().agent_token_ttl_hours


@router.post("/device/preview", dependencies=[Depends(require_csrf)])
def device_preview(
    payload: DeviceCode,
    response: Response,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    no_store(response)
    employee_access(db, access.user)
    throttle(f"preview:{access.user.id}", 8, 60)
    item = db.scalar(
        select(AgentGrant).where(AgentGrant.user_code_hash == digest(payload.user_code))
    )
    if (
        item is None
        or item.device_expires_at <= now()
        or item.revoked_at
        or item.user_id
        or item.token_hash
    ):
        raise HTTPException(404, "授权码不存在、已处理或已失效")
    return {"client_name": item.client_name, "scopes": SCOPES, "expires_in_hours": __ttl()}


@router.post("/device/approve", dependencies=[Depends(require_csrf)])
def device_approve(
    payload: DeviceApprove,
    response: Response,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    no_store(response)
    access = employee_access(db, access.user)
    throttle(f"approve:{access.user.id}", 8, 60)
    item = db.scalar(
        select(AgentGrant)
        .where(AgentGrant.user_code_hash == digest(payload.user_code))
        .with_for_update()
    )
    if (
        item is None
        or item.device_expires_at <= now()
        or item.revoked_at
        or item.user_id
        or item.token_hash
    ):
        raise HTTPException(404, "授权码不存在、已处理或已失效")
    if payload.approved:
        item.user_id = access.user.id
    else:
        item.revoked_at = now()
    audit(db, access, "agent.authorize" if payload.approved else "agent.deny", item.id)
    db.commit()
    return {
        "status": "approved" if payload.approved else "denied",
        "client_name": item.client_name,
        "scopes": SCOPES,
    }


@router.get("/grants")
def my_grants(db: Session = Depends(get_db), access: AccessContext = Depends(get_access_context)):
    return [
        {
            "id": r.id,
            "client_name": r.client_name,
            "expires_at": r.token_expires_at,
            "revoked_at": r.revoked_at,
        }
        for r in db.scalars(
            select(AgentGrant)
            .where(AgentGrant.user_id == access.user.id)
            .order_by(AgentGrant.created_at.desc())
            .limit(100)
        )
    ]


@router.delete("/grants/{grant_id}", dependencies=[Depends(require_csrf)])
def revoke(
    grant_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    item = db.scalar(
        select(AgentGrant)
        .where(AgentGrant.id == grant_id, AgentGrant.user_id == access.user.id)
        .with_for_update()
    )
    if item is None:
        raise HTTPException(404, "授权不存在")
    item.revoked_at = item.revoked_at or now()
    audit(db, access, "agent.revoke", item.id)
    db.commit()
    return {"status": "revoked"}


def types(db):
    return list(
        db.scalars(
            select(AssetType)
            .where(
                AssetType.archived_at.is_(None),
                (AssetType.code.startswith("ai_", autoescape=True))
                | AssetType.code.in_(AI_ASSISTED_CODES),
            )
            .order_by(AssetType.code)
        )
    )


@router.get("/capabilities")
def capabilities(
    response: Response, db: Session = Depends(get_db), access: AccessContext = Depends(agent_access)
):
    no_store(response)
    return {
        "protocol": "flipbelt-agent-v1",
        "scopes": SCOPES,
        "user": {"id": access.user.id, "person_id": access.person_id},
        "asset_types": [
            {
                "id": t.id,
                "code": t.code,
                "name": t.name,
                "requires_ai_development": t.code in AI_ASSISTED_CODES,
            }
            for t in types(db)
        ],
        "confirmation": "web_only",
        "attachments": True,
        "attachment_formats": ["png", "jpg", "jpeg", "webp", "zip"],
        "structured_details": True,
        "responsibility": "proposal_web_governance",
        "relations": False,
        "incubation": "private_structured_summary",
    }


def visible_query(access):
    return (
        select(Asset)
        .join(AssetType, AssetType.id == Asset.asset_type_id)
        .where(
            Asset.archived_at.is_(None),
            asset_visibility_clause(access),
            or_(
                AssetType.code.startswith("ai_", autoescape=True),
                and_(
                    AssetType.code.in_(AI_ASSISTED_CODES),
                    Asset.development_method.in_(AI_DEVELOPMENT_METHODS),
                ),
            ),
            # Other people's private drafts never become discoverable through delegation.
            (Asset.status != "draft") | (Asset.created_by_person_id == access.person_id),
        )
    )


def asset_card(item):
    return {
        "id": str(item.id),
        "name": item.name,
        "description": item.description,
        "asset_type_id": str(item.asset_type_id),
        "version": item.version,
        "outcome_version": item.outcome_version,
        "created_by_person_id": (
            str(item.created_by_person_id) if item.created_by_person_id else None
        ),
        "status": item.status,
        "review_status": item.review_status,
        "sharing_scope": item.sharing_scope,
        "confirmation_url": frontend_url(f"discover/{item.id}"),
    }


@router.get("/assets")
def search_assets(
    q: str = Query(default="", max_length=200),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    query = visible_query(access)
    if q:
        query = query.where(Asset.name.icontains(q, autoescape=True))
    rows = db.scalars(query.order_by(Asset.updated_at.desc(), Asset.id).limit(50))
    return {"scope": "current_user_visible_ai_assets", "items": [asset_card(r) for r in rows]}


@router.get("/assets/{asset_id}")
def get_asset(
    asset_id: UUID, db: Session = Depends(get_db), access: AccessContext = Depends(agent_access)
):
    item = db.scalar(visible_query(access).where(Asset.id == asset_id))
    if item is None:
        raise HTTPException(404, "成果不存在")
    return asset_card(item)


def operation_id(user_id, operation, request_id):
    return uuid5(NAMESPACE_URL, f"agent:{user_id}:{operation}:{request_id}")


def begin_operation(db, access, operation, payload, *, target=None):
    identity = operation_id(access.user.id, operation, payload.request_id)
    checksum = digest(
        json.dumps(
            {
                "payload": payload.model_dump(
                    mode="json", exclude_unset=operation == "details.save"
                ),
                "target": target,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    previous = db.get(AgentOperation, identity)
    if previous:
        if previous.request_digest != checksum:
            raise HTTPException(409, "同一请求编号不能用于不同内容")
        return previous, True
    item = AgentOperation(
        id=identity, user_id=access.user.id, operation=operation, request_digest=checksum, result={}
    )
    db.add(item)
    try:
        db.flush()  # The unique key serializes simultaneous retries before any business write.
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "请求处理中，请使用原请求编号查询或重试") from exc
    return item, False


def finish(db, operation, result, access, object_id):
    operation.result = jsonable_encoder(result)
    audit(db, access, "agent." + operation.operation, object_id)
    db.commit()
    return operation.result


@router.get("/operations/{operation}/{request_id}")
def operation_status(
    operation: str,
    request_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    item = db.get(AgentOperation, operation_id(access.user.id, operation, request_id))
    if item is None or item.user_id != access.user.id:
        raise HTTPException(404, "请求不存在")
    return {"status": "completed", "result": item.result}


@router.post("/drafts")
def create_asset_draft(
    payload: DraftInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    if payload.source_type != "connector":
        raise HTTPException(422, "连接器草稿的 source_type 必须为 connector")
    op, replay = begin_operation(db, access, "draft.create", payload)
    if replay:
        return op.result
    item = persist_draft(payload, db, access, commit=False)
    return finish(db, op, asset_card(item), access, item.id)


@router.patch("/drafts/{asset_id}")
def update_asset_draft(
    asset_id: UUID,
    payload: DraftUpdate,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    # Bind the target into the operation namespace so a replay cannot cross objects.
    op, replay = begin_operation(db, access, "draft.update", payload, target=str(asset_id))
    if replay:
        return op.result
    item = db.scalar(visible_query(access).where(Asset.id == asset_id).with_for_update(of=Asset))
    if (
        item is None
        or item.archived_at
        or item.status != "draft"
        or item.created_by_person_id != access.person_id
    ):
        raise HTTPException(404, "草稿不存在")
    if item.version != payload.version:
        raise HTTPException(409, "草稿已更新，请读取当前版本")
    if (item.name, item.description) != (payload.name, payload.description):
        item.name, item.description = payload.name, payload.description
        item.version += 1
    db.flush()
    return finish(db, op, asset_card(item), access, item.id)


def incubation_card(item):
    return jsonable_encoder(
        {
            k: getattr(item, k)
            for k in (
                "id",
                "version",
                "title",
                "stage",
                "workflow_summary",
                "opportunity_summary",
                "blueprint_summary",
                "next_step",
                "asset_id",
                "updated_at",
            )
        }
    )


@router.get("/incubations")
def my_incubations(db: Session = Depends(get_db), access: AccessContext = Depends(agent_access)):
    return {
        "items": [
            incubation_card(r)
            for r in db.scalars(
                select(AgentIncubation)
                .where(AgentIncubation.user_id == access.user.id)
                .order_by(AgentIncubation.updated_at.desc(), AgentIncubation.id)
                .limit(50)
            )
        ]
    }


@router.get("/incubations/{incubation_id}")
def get_incubation(
    incubation_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    item = db.scalar(
        select(AgentIncubation).where(
            AgentIncubation.id == incubation_id, AgentIncubation.user_id == access.user.id
        )
    )
    if item is None:
        raise HTTPException(404, "孵化记录不存在")
    return incubation_card(item)


@router.post("/incubations")
def save_incubation(
    payload: IncubationInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    op, replay = begin_operation(db, access, "incubation.save", payload)
    if replay:
        return op.result
    if payload.id:
        item = db.scalar(
            select(AgentIncubation)
            .where(AgentIncubation.id == payload.id, AgentIncubation.user_id == access.user.id)
            .with_for_update()
        )
        if item is None:
            raise HTTPException(404, "孵化记录不存在")
        if item.version != payload.version:
            raise HTTPException(409, "孵化记录已更新，请读取当前版本")
        item.version += 1
    else:
        if payload.version != 0:
            raise HTTPException(422, "新孵化记录版本必须为 0")
        item = AgentIncubation(user_id=access.user.id, version=1)
        db.add(item)
    if payload.asset_id:
        asset = db.scalar(
            visible_query(access).where(
                Asset.id == payload.asset_id, Asset.created_by_person_id == access.person_id
            )
        )
        if asset is None:
            raise HTTPException(404, "成果不存在")
    for key, value in payload.model_dump(exclude={"request_id", "id", "version"}).items():
        setattr(item, key, value)
    db.flush()
    return finish(db, op, incubation_card(item), access, item.id)


@router.post("/disconnect")
def disconnect(
    request: Request, db: Session = Depends(get_db), access: AccessContext = Depends(agent_access)
):
    item = db.get(AgentGrant, request.state.agent_grant_id)
    item.revoked_at = now()
    audit(db, access, "agent.revoke", item.id)
    db.commit()
    return {"status": "disconnected"}


@router.get("/people")
def search_people(
    q: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    from app.models import Department, Person

    owner = db.get(Person, access.person_id)
    rows = db.execute(
        select(Person, Department.name)
        .outerjoin(Department, Person.department_id == Department.id)
        .where(
            Person.legal_entity_id == owner.legal_entity_id,
            Person.archived_at.is_(None),
            Person.employment_status == "active",
            Person.display_name.icontains(q, autoescape=True),
        )
        .order_by(Person.display_name, Person.id)
        .limit(20)
    )
    return {
        "items": [
            {
                "id": str(person.id),
                "display_name": person.display_name,
                "department_name": department,
            }
            for person, department in rows
        ]
    }


def own_outcome(db, access, asset_id, version=None):
    item = db.scalar(
        visible_query(access)
        .where(Asset.id == asset_id, Asset.created_by_person_id == access.person_id)
        .with_for_update(of=Asset)
    )
    if item is None or item.status not in {"draft", "active"}:
        raise HTTPException(404, "本人成果不存在")
    if version is not None and item.version != version:
        raise HTTPException(409, "成果已更新，请读取当前版本")
    return item


@router.get("/assets/{asset_id}/details")
def read_details(
    asset_id: UUID, db: Session = Depends(get_db), access: AccessContext = Depends(agent_access)
):
    from app.services.registrar_details import details

    item = own_outcome(db, access, asset_id)
    return {**asset_card(item), **details(db, item)}


@router.put("/assets/{asset_id}/details")
def write_details(
    asset_id: UUID,
    payload: DetailsInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    from app.services.registrar_details import details, save_details

    op, replay = begin_operation(db, access, "details.save", payload, target=str(asset_id))
    if replay:
        return op.result
    item = own_outcome(db, access, asset_id, payload.version)
    save_details(db, item, payload)
    return finish(db, op, {**asset_card(item), **details(db, item)}, access, item.id)


@router.post("/assets/{asset_id}/attachments")
def upload_outcome(
    asset_id: UUID,
    payload: AttachmentInput,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(agent_access),
):
    import base64
    import binascii

    from app.api.v1.asset_attachments import STORAGE
    from app.services.outcome_attachments import store_outcome
    from app.services.registrar_details import invalidate

    op, replay = begin_operation(db, access, "attachment.upload", payload, target=str(asset_id))
    if replay:
        return op.result
    item = own_outcome(db, access, asset_id, payload.version)
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise HTTPException(422, "附件编码无效") from exc
    attachment, created = store_outcome(db, item, content, payload.file_name, STORAGE)
    if created:
        invalidate(item)
        db.flush()
    return finish(
        db,
        op,
        {
            **asset_card(item),
            "attachment": {
                "id": str(attachment.id),
                "file_name": attachment.file_name,
                "content_type": attachment.content_type,
                "size_bytes": attachment.size_bytes,
            },
        },
        access,
        item.id,
    )
