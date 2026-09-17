from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Asset,
    AssetCodeSequence,
    AssetIdentifier,
    AssetRelation,
    AssetResponsibility,
    AssetType,
    AuditLog,
)
from app.repositories.assets import asset_repository
from app.schemas.assets import (
    AssetCreate,
    AssetPatch,
    AssetRelationCreate,
    AssetResponsibilityCreate,
)


class AssetService:
    def create(
        self, db: Session, payload: AssetCreate, *, created_by_person_id: UUID | None = None
    ) -> Asset:
        asset = Asset(
            **payload.model_dump(exclude={"asset_code"}),
            asset_code=payload.asset_code
            or allocate_asset_code(db, payload.legal_entity_id, payload.asset_type_id),
            source_type="manual",
            created_by_person_id=created_by_person_id,
            review_status="draft",
        )
        db.add(asset)
        try:
            db.flush()
            ensure_internal_identifier(db, asset)
            self._audit(db, "asset.create", asset.id, None, self._snapshot(asset))
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="资产编号或关联数据冲突"
            ) from exc
        db.refresh(asset)
        return asset

    def update(self, db: Session, asset_id: UUID, payload: AssetPatch) -> Asset:
        asset = self.require(db, asset_id)
        if asset.version != payload.version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="记录已被其他用户修改")
        before = self._snapshot(asset)
        for field, value in payload.model_dump(exclude={"version"}, exclude_unset=True).items():
            setattr(asset, field, value)
        asset.version += 1
        db.flush()
        self._audit(db, "asset.update", asset.id, before, self._snapshot(asset))
        db.commit()
        db.refresh(asset)
        return asset

    def archive(self, db: Session, asset_id: UUID, version: int) -> Asset:
        asset = self.require(db, asset_id)
        if asset.version != version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="记录已被其他用户修改")
        before = self._snapshot(asset)
        asset.archived_at = datetime.now(UTC)
        asset.status = "archived"
        asset.version += 1
        db.flush()
        self._audit(db, "asset.archive", asset.id, before, self._snapshot(asset))
        db.commit()
        db.refresh(asset)
        return asset

    def restore(self, db: Session, asset_id: UUID, version: int) -> Asset:
        asset = asset_repository.get(db, asset_id, include_archived=True)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
        if asset.version != version:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="记录已被其他用户修改")
        before = self._snapshot(asset)
        asset.archived_at = None
        asset.status = "active"
        asset.version += 1
        db.flush()
        self._audit(db, "asset.restore", asset.id, before, self._snapshot(asset))
        db.commit()
        db.refresh(asset)
        return asset

    def archive_responsibility(self, db: Session, asset_id: UUID, responsibility_id: UUID) -> None:
        self.require(db, asset_id)
        item = db.get(AssetResponsibility, responsibility_id)
        if item is None or item.asset_id != asset_id:
            raise HTTPException(status_code=404, detail="责任记录不存在")
        item.archived_at = datetime.now(UTC)
        self._audit(db, "asset.responsibility.archive", asset_id, None, {"id": str(item.id)})
        db.commit()

    def archive_relation(self, db: Session, asset_id: UUID, relation_id: UUID) -> None:
        self.require(db, asset_id)
        item = db.get(AssetRelation, relation_id)
        if item is None or asset_id not in {item.source_asset_id, item.target_asset_id}:
            raise HTTPException(status_code=404, detail="关系记录不存在")
        item.archived_at = datetime.now(UTC)
        self._audit(db, "asset.relation.archive", asset_id, None, {"id": str(item.id)})
        db.commit()

    def add_responsibility(
        self, db: Session, asset_id: UUID, payload: AssetResponsibilityCreate
    ) -> AssetResponsibility:
        self.require(db, asset_id)
        item = AssetResponsibility(asset_id=asset_id, **payload.model_dump())
        asset_repository.add_responsibility(db, item)
        self._audit(db, "asset.responsibility.create", asset_id, None, {"id": str(item.id)})
        db.commit()
        db.refresh(item)
        return item

    def add_relation(
        self, db: Session, asset_id: UUID, payload: AssetRelationCreate
    ) -> AssetRelation:
        self.require(db, asset_id)
        self.require(db, payload.target_asset_id)
        item = AssetRelation(source_asset_id=asset_id, source_type="manual", **payload.model_dump())
        try:
            asset_repository.add_relation(db, item)
            self._audit(db, "asset.relation.create", asset_id, None, {"id": str(item.id)})
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="资产关系已存在或不合法"
            ) from exc
        db.refresh(item)
        return item

    def require(self, db: Session, asset_id: UUID) -> Asset:
        asset = asset_repository.get(db, asset_id)
        if asset is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="资产不存在")
        return asset

    @staticmethod
    def _snapshot(asset: Asset) -> dict[str, object]:
        return {
            "asset_code": asset.asset_code,
            "name": asset.name,
            "status": asset.status,
            "criticality": asset.criticality,
            "owner_department_id": str(asset.owner_department_id)
            if asset.owner_department_id
            else None,
            "ownership_scope": asset.ownership_scope,
            "version": asset.version,
            "archived_at": asset.archived_at.isoformat() if asset.archived_at else None,
        }

    @staticmethod
    def _audit(
        db: Session,
        action: str,
        object_id: UUID,
        before: dict | None,
        after: dict | None,
    ) -> None:
        db.add(
            AuditLog(
                actor_user_id=None,
                action=action,
                object_type="asset",
                object_id=object_id,
                before_data=before,
                after_data=after,
                request_id="local-development",
            )
        )


asset_service = AssetService()


def allocate_asset_code(db: Session, legal_entity_id: UUID | None, asset_type_id: UUID) -> str:
    """Allocate a short, business-readable type code without mutable ownership data."""
    asset_type = db.get(AssetType, asset_type_id)
    if asset_type is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="资产类型不存在"
        )
    # Unassigned assets are valid instances.  They cannot use the ownership
    # scoped sequence because that table intentionally requires an L1. Keep a
    # readable, collision-free namespace until a user explicitly assigns L1.
    if legal_entity_id is None:
        number = 1
        while True:
            candidate = f"{asset_type.code_prefix}-U-{number:03d}"
            if db.scalar(select(Asset.id).where(Asset.asset_code == candidate)) is None:
                return candidate
            number += 1

    sequence = db.scalar(
        select(AssetCodeSequence)
        .where(
            AssetCodeSequence.legal_entity_id == legal_entity_id,
            AssetCodeSequence.asset_type_id == asset_type_id,
        )
        .with_for_update()
    )
    if sequence is None:
        sequence = AssetCodeSequence(
            legal_entity_id=legal_entity_id, asset_type_id=asset_type_id, last_value=1
        )
        db.add(sequence)
        db.flush()
    else:
        sequence.last_value += 1
        db.flush()
    # Earlier records can predate the sequence table. Skip any occupied code
    # instead of failing a new registration after the migration is introduced.
    while True:
        candidate = f"{asset_type.code_prefix}-{sequence.last_value:03d}"
        if db.scalar(select(Asset.id).where(Asset.asset_code == candidate)) is None:
            return candidate
        sequence.last_value += 1
        db.flush()


def ensure_internal_identifier(db: Session, asset: Asset) -> AssetIdentifier:
    namespace = f"internal:{asset.legal_entity_id or 'unassigned'}"
    existing = db.scalar(
        select(AssetIdentifier).where(
            AssetIdentifier.asset_id == asset.id,
            AssetIdentifier.namespace == namespace,
            AssetIdentifier.identifier_type == "asset_code",
            AssetIdentifier.archived_at.is_(None),
        )
    )
    if existing is not None:
        return existing
    identifier = AssetIdentifier(
        asset_id=asset.id,
        namespace=namespace,
        identifier_type="asset_code",
        identifier_value=asset.asset_code,
        is_primary=True,
        verification_status="verified",
        confidentiality="internal",
    )
    db.add(identifier)
    db.flush()
    return identifier
