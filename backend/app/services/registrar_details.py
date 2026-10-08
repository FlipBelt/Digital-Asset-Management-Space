"""Supplementary facts and proposed responsibility never grant management rights."""

from datetime import UTC, datetime
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select

from app.models import (
    AssetFieldDefinition,
    AssetFieldValue,
    AssetIdentifier,
    AssetResponsibility,
    AssetType,
    InternalSystemProfile,
    Person,
)

PROFILE_KEYS = (
    "repository_url",
    "production_url",
    "tech_stack",
    "deployment_guide_url",
    "recovery_guide_url",
    "backup_description",
)


def details(db, asset):
    profile = db.scalar(
        select(InternalSystemProfile).where(InternalSystemProfile.asset_id == asset.id)
    )
    definitions = list(
        db.scalars(
            select(AssetFieldDefinition).where(
                AssetFieldDefinition.asset_type_id == asset.asset_type_id,
                AssetFieldDefinition.archived_at.is_(None),
            )
        )
    )
    from app.models import AssetAttachment

    return {
        "profile": {key: getattr(profile, key) for key in PROFILE_KEYS} if profile else None,
        "field_definitions": [
            {
                "id": str(f.id),
                "field_key": f.field_key,
                "label": f.label,
                "data_type": f.data_type,
                "is_required": f.is_required,
                "options": f.options,
            }
            for f in definitions
        ],
        "fields": [
            {"field_definition_id": str(f.field_definition_id), "value": f.value.get("value")}
            for f in db.scalars(select(AssetFieldValue).where(AssetFieldValue.asset_id == asset.id))
        ],
        "identifiers": [
            {
                "namespace": i.namespace,
                "identifier_type": i.identifier_type,
                "identifier_value": i.identifier_value,
            }
            for i in db.scalars(
                select(AssetIdentifier).where(
                    AssetIdentifier.asset_id == asset.id, AssetIdentifier.archived_at.is_(None)
                )
            )
        ],
        "proposed_responsibilities": [
            {
                "person_id": str(r.person_id),
                "role_type": r.role_type,
                "display_name": db.get(Person, r.person_id).display_name,
            }
            for r in db.scalars(
                select(AssetResponsibility).where(
                    AssetResponsibility.asset_id == asset.id,
                    AssetResponsibility.archived_at.is_(None),
                    AssetResponsibility.role_type.in_(["proposed_responsible", "proposed_user"]),
                )
            )
        ],
        "attachments": [
            {
                "id": str(a.id),
                "file_name": a.file_name,
                "content_type": a.content_type,
                "size_bytes": a.size_bytes,
            }
            for a in db.scalars(
                select(AssetAttachment).where(
                    AssetAttachment.asset_id == asset.id, AssetAttachment.archived_at.is_(None)
                )
            )
        ],
    }


def invalidate(asset):
    # Supplementing an already registered outcome requires a fresh private draft preview.
    asset.status = "draft"
    asset.sharing_scope = "private"
    asset.review_status = "pending_review"
    asset.confirmed_at = None
    asset.confirmed_by_person_id = None
    asset.version += 1


def save_details(db, asset, payload):
    if not (
        payload.fields
        or payload.identifiers
        or payload.profile
        and payload.profile.model_fields_set
        or {"proposed_responsible_person_id", "proposed_user_person_ids"} & payload.model_fields_set
    ):
        raise HTTPException(422, "请提供需要补充的资料")
    if payload.profile is not None:
        kind = db.get(AssetType, asset.asset_type_id)
        if kind.profile_kind != "internal_system":
            raise HTTPException(422, "该类型不支持自研系统接管资料")
        values = payload.profile.model_dump(exclude_unset=True)
        for key, value in values.items():
            if key.endswith("_url") and value:
                try:
                    url = urlsplit(value)
                except ValueError as exc:
                    raise HTTPException(422, "地址格式无效") from exc
                if (
                    url.scheme not in {"https", "http"}
                    or not url.hostname
                    or url.username
                    or url.password
                    or url.query
                ):
                    raise HTTPException(422, "地址须为不含凭据或临时查询参数的HTTP(S)链接")
        profile = db.scalar(
            select(InternalSystemProfile).where(InternalSystemProfile.asset_id == asset.id)
        )
        if profile is None:
            profile = InternalSystemProfile(asset_id=asset.id)
            db.add(profile)
        for key, value in values.items():
            setattr(profile, key, value)
    definitions = {
        f.id: f
        for f in db.scalars(
            select(AssetFieldDefinition).where(
                AssetFieldDefinition.asset_type_id == asset.asset_type_id,
                AssetFieldDefinition.archived_at.is_(None),
            )
        )
    }
    if len({f.field_definition_id for f in payload.fields}) != len(payload.fields):
        raise HTTPException(422, "类型字段不能重复")
    for field in payload.fields:
        definition = definitions.get(field.field_definition_id)
        if not definition:
            raise HTTPException(422, "包含未定义的类型字段")
        value = field.value
        if value is not None:
            import math
            from datetime import date

            if definition.data_type == "number":
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                ):
                    raise HTTPException(422, "数值字段格式无效")
            elif definition.data_type == "boolean":
                if not isinstance(value, bool):
                    raise HTTPException(422, "布尔字段格式无效")
            else:
                if not isinstance(value, str) or len(value) > 4000:
                    raise HTTPException(422, "文本字段格式无效或超长")
                if definition.data_type == "date":
                    try:
                        date.fromisoformat(value)
                    except ValueError as exc:
                        raise HTTPException(422, "日期须为YYYY-MM-DD") from exc
        if definition.options and field.value is not None and field.value not in definition.options:
            raise HTTPException(422, "类型字段选项无效")
        if definition.is_required and (field.value is None or field.value == ""):
            raise HTTPException(422, "必填类型字段不能为空")
        row = db.scalar(
            select(AssetFieldValue).where(
                AssetFieldValue.asset_id == asset.id,
                AssetFieldValue.field_definition_id == field.field_definition_id,
            )
        )
        if row is None:
            row = AssetFieldValue(
                asset_id=asset.id,
                field_definition_id=field.field_definition_id,
                value={"value": field.value},
            )
            db.add(row)
        else:
            row.value = {"value": field.value}
    for identifier in payload.identifiers:
        if identifier.namespace.strip().lower().split(":")[0] in {
            "internal",
            "asset_center",
            "asset-center",
        }:
            raise HTTPException(422, "内部资产编号由服务端维护")
        existing = db.scalar(
            select(AssetIdentifier).where(
                AssetIdentifier.asset_id == asset.id,
                AssetIdentifier.namespace == identifier.namespace,
                AssetIdentifier.identifier_type == identifier.identifier_type,
                AssetIdentifier.identifier_value == identifier.identifier_value,
                AssetIdentifier.archived_at.is_(None),
            )
        )
        if not existing:
            duplicate = db.scalar(
                select(AssetIdentifier.id).where(
                    AssetIdentifier.namespace == identifier.namespace,
                    AssetIdentifier.identifier_type == identifier.identifier_type,
                    AssetIdentifier.identifier_value == identifier.identifier_value,
                    AssetIdentifier.archived_at.is_(None),
                )
            )
            if duplicate:
                raise HTTPException(409, "该外部标识已被使用，请核对")
            db.add(
                AssetIdentifier(
                    asset_id=asset.id,
                    **identifier.model_dump(),
                    is_primary=False,
                    verification_status="unverified",
                    confidentiality="internal",
                )
            )
    if (
        "proposed_responsible_person_id" in payload.model_fields_set
        or "proposed_user_person_ids" in payload.model_fields_set
    ):
        existing_proposals = list(
            db.scalars(
                select(AssetResponsibility).where(
                    AssetResponsibility.asset_id == asset.id,
                    AssetResponsibility.role_type.in_(["proposed_responsible", "proposed_user"]),
                    AssetResponsibility.archived_at.is_(None),
                )
            )
        )
        if "proposed_responsible_person_id" not in payload.model_fields_set:
            payload.proposed_responsible_person_id = next(
                (r.person_id for r in existing_proposals if r.role_type == "proposed_responsible"),
                None,
            )
        if "proposed_user_person_ids" not in payload.model_fields_set:
            payload.proposed_user_person_ids = [
                r.person_id for r in existing_proposals if r.role_type == "proposed_user"
            ]
        ids = set(payload.proposed_user_person_ids)
        if payload.proposed_responsible_person_id:
            ids.add(payload.proposed_responsible_person_id)
        people = list(
            db.scalars(
                select(Person).where(
                    Person.id.in_(ids),
                    Person.legal_entity_id == asset.legal_entity_id,
                    Person.archived_at.is_(None),
                    Person.employment_status == "active",
                )
            )
        )
        if len(people) != len(ids):
            raise HTTPException(422, "候选人员必须是当前公司在职成员")
        for row in db.scalars(
            select(AssetResponsibility).where(
                AssetResponsibility.asset_id == asset.id,
                AssetResponsibility.role_type.in_(["proposed_responsible", "proposed_user"]),
                AssetResponsibility.archived_at.is_(None),
            )
        ):
            row.archived_at = datetime.now(UTC)
        for person_id in ids:
            db.add(
                AssetResponsibility(
                    asset_id=asset.id,
                    person_id=person_id,
                    role_type="proposed_responsible"
                    if person_id == payload.proposed_responsible_person_id
                    else "proposed_user",
                )
            )
    invalidate(asset)
    db.flush()


def touch_web_details(asset, access):
    if asset.sharing_scope is None:
        return
    if asset.created_by_person_id == access.person_id:
        invalidate(asset)
    else:
        asset.version += 1
        asset.review_status = "pending_review"
        asset.confirmed_at = None
        asset.confirmed_by_person_id = None
