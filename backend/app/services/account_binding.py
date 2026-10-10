from fastapi import HTTPException
from sqlalchemy import select

from app.models import Person


def require_active_employee(db, person_id, legal_entity_id):
    if person_id is None:
        return None
    person = db.scalar(
        select(Person)
        .where(
            Person.id == person_id,
            Person.archived_at.is_(None),
            Person.employment_status == "active",
            Person.person_type == "employee",
            Person.legal_entity_id == legal_entity_id,
        )
        .with_for_update()
    )
    if person is None:
        raise HTTPException(422, "请选择所属公司的在职员工；离职或待核实员工不可新增绑定")
    return person
