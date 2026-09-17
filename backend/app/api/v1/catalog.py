from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, require_permission
from app.db.session import get_db
from app.models import AssetCategory, AssetFieldDefinition, AssetType, RelationDefinition
from app.schemas.catalog import (
    AssetCategoryCreate,
    AssetCategoryRead,
    AssetFieldDefinitionCreate,
    AssetFieldDefinitionRead,
    AssetTypeCreate,
    AssetTypeRead,
    RelationDefinitionCreate,
    RelationDefinitionRead,
)

router = APIRouter(tags=["catalog"])
require_catalog_admin = Depends(require_permission("admin.manage"))


@router.get("/asset-categories", response_model=list[AssetCategoryRead])
def list_categories(db: Session = Depends(get_db)) -> list[AssetCategory]:
    return list(
        db.scalars(
            select(AssetCategory)
            .where(AssetCategory.archived_at.is_(None))
            .order_by(AssetCategory.sort_order, AssetCategory.name)
        )
    )


@router.post(
    "/asset-categories", response_model=AssetCategoryRead, status_code=status.HTTP_201_CREATED
)
def create_category(
    payload: AssetCategoryCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_catalog_admin,
) -> AssetCategory:
    item = AssetCategory(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/asset-types", response_model=list[AssetTypeRead])
def list_asset_types(db: Session = Depends(get_db)) -> list[AssetType]:
    return list(
        db.scalars(
            select(AssetType).where(AssetType.archived_at.is_(None)).order_by(AssetType.name)
        )
    )


@router.post("/asset-types", response_model=AssetTypeRead, status_code=status.HTTP_201_CREATED)
def create_asset_type(
    payload: AssetTypeCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_catalog_admin,
) -> AssetType:
    item = AssetType(**payload.model_dump(), is_system=False)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.get("/asset-types/{asset_type_id}/fields", response_model=list[AssetFieldDefinitionRead])
def list_asset_fields(
    asset_type_id: str, db: Session = Depends(get_db)
) -> list[AssetFieldDefinition]:
    return list(
        db.scalars(
            select(AssetFieldDefinition)
            .where(
                AssetFieldDefinition.asset_type_id == asset_type_id,
                AssetFieldDefinition.archived_at.is_(None),
            )
            .order_by(AssetFieldDefinition.sort_order, AssetFieldDefinition.label)
        )
    )


@router.post(
    "/asset-types/{asset_type_id}/fields",
    response_model=AssetFieldDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_asset_field(
    asset_type_id: str,
    payload: AssetFieldDefinitionCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_catalog_admin,
) -> AssetFieldDefinition:
    values = payload.model_dump()
    # Keep the legacy flag coherent for existing clients while the new stage
    # explicitly describes when the requirement applies.
    values["is_required"] = values["requirement_stage"] == "create"
    item = AssetFieldDefinition(asset_type_id=asset_type_id, **values)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/asset-types/{asset_type_id}/fields/{field_id}/archive",
    status_code=status.HTTP_204_NO_CONTENT,
)
def archive_asset_field(
    asset_type_id: str,
    field_id: str,
    db: Session = Depends(get_db),
    _: AccessContext = require_catalog_admin,
) -> None:
    item = db.get(AssetFieldDefinition, field_id)
    if item is None or str(item.asset_type_id) != asset_type_id:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="字段不存在")
    from datetime import UTC, datetime

    item.archived_at = datetime.now(UTC)
    db.commit()


@router.get("/relation-definitions", response_model=list[RelationDefinitionRead])
def list_relation_definitions(db: Session = Depends(get_db)) -> list[RelationDefinition]:
    return list(
        db.scalars(
            select(RelationDefinition)
            .where(RelationDefinition.archived_at.is_(None))
            .order_by(RelationDefinition.category, RelationDefinition.relation_type)
        )
    )


@router.post(
    "/relation-definitions",
    response_model=RelationDefinitionRead,
    status_code=status.HTTP_201_CREATED,
)
def create_relation_definition(
    payload: RelationDefinitionCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_catalog_admin,
) -> RelationDefinition:
    item = RelationDefinition(**payload.model_dump(), is_system=False)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
