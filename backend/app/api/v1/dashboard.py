from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, asset_visibility_clause, get_access_context
from app.db.session import get_db
from app.models import Asset, AssetCategory, AssetType, Department, Person, RiskFinding

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard")
def dashboard(
    scope: str = "company",
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> dict:
    active = [Asset.archived_at.is_(None), asset_visibility_clause(access)]
    now = datetime.now(UTC)
    soon = now.date() + timedelta(days=30)
    total = db.scalar(select(func.count()).select_from(Asset).where(*active)) or 0
    critical = (
        db.scalar(
            select(func.count()).select_from(Asset).where(*active, Asset.criticality == "critical")
        )
        or 0
    )
    expiring = (
        db.scalar(
            select(func.count())
            .select_from(Asset)
            .where(*active, Asset.expires_at.is_not(None), Asset.expires_at <= soon)
        )
        or 0
    )
    missing_owner = (
        db.scalar(
            select(func.count())
            .select_from(Asset)
            .where(*active, Asset.owner_department_id.is_(None))
        )
        or 0
    )
    open_risks = (
        db.scalar(
            select(func.count())
            .select_from(RiskFinding)
            .where(RiskFinding.archived_at.is_(None), RiskFinding.status == "open")
        )
        or 0
    )

    status_rows = db.execute(
        select(Asset.status, func.count()).where(*active).group_by(Asset.status)
    ).all()
    type_rows = db.execute(
        select(AssetType.name, func.count(Asset.id))
        .join(Asset, Asset.asset_type_id == AssetType.id)
        .where(*active)
        .group_by(AssetType.name)
        .order_by(func.count(Asset.id).desc())
        .limit(8)
    ).all()
    recent = list(
        db.execute(
            select(Asset.id, Asset.asset_code, Asset.name, Asset.status, Asset.updated_at)
            .where(*active)
            .order_by(Asset.updated_at.desc())
            .limit(8)
        ).mappings()
    )
    return {
        "scope": scope,
        "metrics": {
            "assets": total,
            "critical_assets": critical,
            "expiring_soon": expiring,
            "missing_department": missing_owner,
            "open_risks": open_risks,
        },
        "by_status": [{"label": key, "value": value} for key, value in status_rows],
        "by_type": [{"label": key, "value": value} for key, value in type_rows],
        "recent_assets": [dict(row) for row in recent],
    }


@router.get("/analytics/summary")
def analytics_summary(db: Session = Depends(get_db)) -> dict:
    category_rows = db.execute(
        select(AssetCategory.name, func.count(Asset.id))
        .join(AssetType, AssetType.category_id == AssetCategory.id)
        .outerjoin(Asset, (Asset.asset_type_id == AssetType.id) & Asset.archived_at.is_(None))
        .where(AssetCategory.archived_at.is_(None))
        .group_by(AssetCategory.name, AssetCategory.sort_order)
        .order_by(AssetCategory.sort_order)
    ).all()
    department_rows = db.execute(
        select(Department.id, Department.name, func.count(Asset.id))
        .outerjoin(
            Asset, (Asset.owner_department_id == Department.id) & Asset.archived_at.is_(None)
        )
        .where(Department.archived_at.is_(None))
        .group_by(Department.id, Department.name)
        .order_by(func.count(Asset.id).desc())
    ).all()
    return {
        "by_category": [{"label": row[0], "value": row[1]} for row in category_rows],
        "by_department": [
            {"id": str(row[0]), "label": row[1], "value": row[2]} for row in department_rows
        ],
    }


@router.get("/views/{dimension}")
def grouped_view(dimension: str, db: Session = Depends(get_db)) -> dict:
    if dimension == "departments":
        rows = db.execute(
            select(Department.id, Department.name, func.count(Asset.id))
            .outerjoin(
                Asset, (Asset.owner_department_id == Department.id) & Asset.archived_at.is_(None)
            )
            .where(Department.archived_at.is_(None))
            .group_by(Department.id, Department.name)
        ).all()
    elif dimension == "asset-types":
        rows = db.execute(
            select(AssetType.id, AssetType.name, func.count(Asset.id))
            .outerjoin(Asset, (Asset.asset_type_id == AssetType.id) & Asset.archived_at.is_(None))
            .where(AssetType.archived_at.is_(None))
            .group_by(AssetType.id, AssetType.name)
        ).all()
    elif dimension == "people":
        from app.models import AssetResponsibility

        rows = db.execute(
            select(Person.id, Person.display_name, func.count(AssetResponsibility.id))
            .outerjoin(
                AssetResponsibility,
                (AssetResponsibility.person_id == Person.id)
                & AssetResponsibility.archived_at.is_(None),
            )
            .where(Person.archived_at.is_(None))
            .group_by(Person.id, Person.display_name)
        ).all()
    else:
        from app.models import Platform, PlatformTenant

        rows = db.execute(
            select(Platform.id, Platform.name, func.count(PlatformTenant.id))
            .outerjoin(
                PlatformTenant,
                (PlatformTenant.platform_id == Platform.id) & PlatformTenant.archived_at.is_(None),
            )
            .where(Platform.archived_at.is_(None))
            .group_by(Platform.id, Platform.name)
        ).all()
    return {
        "dimension": dimension,
        "groups": [{"id": str(row[0]), "label": row[1], "count": row[2]} for row in rows],
    }


@router.get("/search")
def global_search(
    q: str = Query(min_length=1, max_length=100),
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
) -> dict:
    term = f"%{q.strip()}%"
    assets = list(
        db.execute(
            select(Asset.id, Asset.asset_code, Asset.name, Asset.status)
            .where(
                Asset.archived_at.is_(None),
                asset_visibility_clause(access),
                or_(Asset.name.ilike(term), Asset.asset_code.ilike(term)),
            )
            .limit(12)
        ).mappings()
    )
    people = list(
        db.execute(
            select(Person.id, Person.display_name, Person.email)
            .where(
                Person.archived_at.is_(None),
                or_(Person.display_name.ilike(term), Person.email.ilike(term)),
            )
            .limit(8)
        ).mappings()
    )
    return {"assets": [dict(row) for row in assets], "people": [dict(row) for row in people]}
