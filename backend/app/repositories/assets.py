from __future__ import annotations

from uuid import UUID

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy.orm import Session

from app.models import Asset, AssetIdentifier, AssetRelation, AssetResponsibility


class AssetRepository:
    def get(self, db: Session, asset_id: UUID, *, include_archived: bool = False) -> Asset | None:
        stmt = select(Asset).where(Asset.id == asset_id)
        if not include_archived:
            stmt = stmt.where(Asset.archived_at.is_(None))
        return db.scalar(stmt)

    def list(
        self,
        db: Session,
        *,
        page: int,
        page_size: int,
        legal_entity_id: UUID | None = None,
        department_id: UUID | None = None,
        asset_type_id: UUID | None = None,
        status: str | None = None,
        criticality: str | None = None,
        include_archived: bool = False,
        keyword: str | None = None,
        visibility_filter: ColumnElement[bool] | None = None,
    ) -> tuple[list[Asset], int]:
        filters = [] if include_archived else [Asset.archived_at.is_(None)]
        if visibility_filter is not None:
            filters.append(visibility_filter)
        if legal_entity_id:
            filters.append(Asset.legal_entity_id == legal_entity_id)
        if department_id:
            filters.append(Asset.owner_department_id == department_id)
        if asset_type_id:
            filters.append(Asset.asset_type_id == asset_type_id)
        if status:
            filters.append(Asset.status == status)
        if criticality:
            filters.append(Asset.criticality == criticality)
        if keyword:
            term = f"%{keyword.strip()}%"
            identifier_match = exists(
                select(AssetIdentifier.id).where(
                    AssetIdentifier.asset_id == Asset.id,
                    AssetIdentifier.archived_at.is_(None),
                    AssetIdentifier.identifier_value.ilike(term),
                )
            )
            filters.append(
                or_(Asset.name.ilike(term), Asset.asset_code.ilike(term), identifier_match)
            )

        total = db.scalar(select(func.count()).select_from(Asset).where(*filters)) or 0
        stmt = (
            select(Asset)
            .where(*filters)
            .order_by(Asset.updated_at.desc(), Asset.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return list(db.scalars(stmt)), total

    def add_responsibility(
        self, db: Session, responsibility: AssetResponsibility
    ) -> AssetResponsibility:
        db.add(responsibility)
        db.flush()
        return responsibility

    def list_responsibilities(self, db: Session, asset_id: UUID) -> list[AssetResponsibility]:
        stmt = (
            select(AssetResponsibility)
            .where(
                AssetResponsibility.asset_id == asset_id,
                AssetResponsibility.archived_at.is_(None),
            )
            .order_by(AssetResponsibility.is_primary.desc(), AssetResponsibility.created_at)
        )
        return list(db.scalars(stmt))

    def add_relation(self, db: Session, relation: AssetRelation) -> AssetRelation:
        db.add(relation)
        db.flush()
        return relation

    def list_relations(self, db: Session, asset_id: UUID) -> list[AssetRelation]:
        stmt = (
            select(AssetRelation)
            .where(
                AssetRelation.source_asset_id == asset_id,
                AssetRelation.archived_at.is_(None),
            )
            .order_by(AssetRelation.created_at)
        )
        return list(db.scalars(stmt))

    def list_relation_neighborhood(self, db: Session, asset_id: UUID) -> list[AssetRelation]:
        """Return every active edge touching an asset, irrespective of direction."""
        stmt = (
            select(AssetRelation)
            .where(
                AssetRelation.archived_at.is_(None),
                or_(
                    AssetRelation.source_asset_id == asset_id,
                    AssetRelation.target_asset_id == asset_id,
                ),
            )
            .order_by(AssetRelation.created_at)
        )
        return list(db.scalars(stmt))


asset_repository = AssetRepository()
