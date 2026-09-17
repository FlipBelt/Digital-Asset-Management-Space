from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.access import AccessContext, require_permission
from app.db.session import get_db
from app.models import (
    Department,
    DepartmentMembership,
    LegalEntity,
    LegalEntityIdentifier,
    LegalEntityProfile,
    Person,
)
from app.schemas.organizations import (
    DepartmentCreate,
    DepartmentMembershipRead,
    DepartmentPatch,
    DepartmentRead,
    LegalEntityCreate,
    LegalEntityIdentifierCreate,
    LegalEntityIdentifierRead,
    LegalEntityPatch,
    LegalEntityProfileRead,
    LegalEntityProfileWrite,
    LegalEntityRead,
    PersonCreate,
    PersonPatch,
    PersonRead,
)

router = APIRouter(tags=["organization"])
require_organization_write = Depends(require_permission("organization.write"))


@router.get("/legal-entities", response_model=list[LegalEntityRead])
def list_legal_entities(db: Session = Depends(get_db)) -> list[LegalEntity]:
    return list(
        db.scalars(
            select(LegalEntity).where(LegalEntity.archived_at.is_(None)).order_by(LegalEntity.name)
        )
    )


@router.post("/legal-entities", response_model=LegalEntityRead, status_code=status.HTTP_201_CREATED)
def create_legal_entity(
    payload: LegalEntityCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_organization_write,
) -> LegalEntity:
    item = LegalEntity(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/legal-entities/{entity_id}", response_model=LegalEntityRead)
def patch_legal_entity(
    entity_id: str,
    payload: LegalEntityPatch,
    db: Session = Depends(get_db),
    _: AccessContext = require_organization_write,
) -> LegalEntity:
    item = db.get(LegalEntity, entity_id)
    if item is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="公司主体不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


def require_legal_entity(db: Session, entity_id: str) -> LegalEntity:
    item = db.get(LegalEntity, entity_id)
    if item is None or item.archived_at is not None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="公司主体不存在")
    return item


@router.get("/legal-entities/{entity_id}/profile", response_model=LegalEntityProfileRead | None)
def get_legal_entity_profile(
    entity_id: str,
    db: Session = Depends(get_db),
) -> LegalEntityProfile | None:
    require_legal_entity(db, entity_id)
    return db.scalar(select(LegalEntityProfile).where(LegalEntityProfile.legal_entity_id == entity_id))


@router.put("/legal-entities/{entity_id}/profile", response_model=LegalEntityProfileRead)
def save_legal_entity_profile(
    entity_id: str,
    payload: LegalEntityProfileWrite,
    db: Session = Depends(get_db),
    _: AccessContext = require_organization_write,
) -> LegalEntityProfile:
    require_legal_entity(db, entity_id)
    item = db.scalar(select(LegalEntityProfile).where(LegalEntityProfile.legal_entity_id == entity_id))
    if item is None:
        item = LegalEntityProfile(legal_entity_id=entity_id, **payload.model_dump())
        db.add(item)
    else:
        for key, value in payload.model_dump().items():
            setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.get("/legal-entities/{entity_id}/identifiers", response_model=list[LegalEntityIdentifierRead])
def list_legal_entity_identifiers(
    entity_id: str,
    db: Session = Depends(get_db),
) -> list[LegalEntityIdentifier]:
    require_legal_entity(db, entity_id)
    return list(
        db.scalars(
            select(LegalEntityIdentifier)
            .where(
                LegalEntityIdentifier.legal_entity_id == entity_id,
                LegalEntityIdentifier.archived_at.is_(None),
            )
            .order_by(LegalEntityIdentifier.is_primary.desc(), LegalEntityIdentifier.identifier_type)
        )
    )


@router.post(
    "/legal-entities/{entity_id}/identifiers",
    response_model=LegalEntityIdentifierRead,
    status_code=status.HTTP_201_CREATED,
)
def create_legal_entity_identifier(
    entity_id: str,
    payload: LegalEntityIdentifierCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_organization_write,
) -> LegalEntityIdentifier:
    require_legal_entity(db, entity_id)
    if payload.is_primary:
        for item in db.scalars(
            select(LegalEntityIdentifier).where(
                LegalEntityIdentifier.legal_entity_id == entity_id,
                LegalEntityIdentifier.archived_at.is_(None),
            )
        ):
            item.is_primary = False
    item = LegalEntityIdentifier(legal_entity_id=entity_id, **payload.model_dump())
    db.add(item)
    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        from fastapi import HTTPException

        raise HTTPException(status_code=409, detail="该主体标识已存在") from exc
    db.refresh(item)
    return item


@router.get("/departments", response_model=list[DepartmentRead])
def list_departments(db: Session = Depends(get_db)) -> list[Department]:
    return list(
        db.scalars(
            select(Department).where(Department.archived_at.is_(None)).order_by(Department.name)
        )
    )


@router.post("/departments", response_model=DepartmentRead, status_code=status.HTTP_201_CREATED)
def create_department(
    payload: DepartmentCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_organization_write,
) -> Department:
    item = Department(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/departments/{department_id}", response_model=DepartmentRead)
def patch_department(
    department_id: str,
    payload: DepartmentPatch,
    db: Session = Depends(get_db),
    _: AccessContext = require_organization_write,
) -> Department:
    item = db.get(Department, department_id)
    if item is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="部门不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item


@router.get("/people", response_model=list[PersonRead])
def list_people(db: Session = Depends(get_db)) -> list[Person]:
    return list(
        db.scalars(select(Person).where(Person.archived_at.is_(None)).order_by(Person.display_name))
    )


@router.get("/department-memberships", response_model=list[DepartmentMembershipRead])
def list_department_memberships(db: Session = Depends(get_db)) -> list[DepartmentMembership]:
    return list(
        db.scalars(
            select(DepartmentMembership)
            .where(DepartmentMembership.is_active.is_(True))
            .order_by(DepartmentMembership.is_manager.desc(), DepartmentMembership.created_at)
        )
    )


@router.post("/people", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
def create_person(
    payload: PersonCreate,
    db: Session = Depends(get_db),
    _: AccessContext = require_organization_write,
) -> Person:
    item = Person(**payload.model_dump())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/people/{person_id}", response_model=PersonRead)
def patch_person(
    person_id: str,
    payload: PersonPatch,
    db: Session = Depends(get_db),
    _: AccessContext = require_organization_write,
) -> Person:
    item = db.get(Person, person_id)
    if item is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="人员不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(item, key, value)
    db.commit()
    db.refresh(item)
    return item
