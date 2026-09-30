from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, MetaData, String, Table, Uuid, create_engine, select

from app.core.access import asset_visibility_clause
from app.models import Asset


def visible_ids(*, manager=False, linked=True):
    engine = create_engine("sqlite://")
    metadata = MetaData()
    assets = Table(
        "assets",
        metadata,
        Column("id", Uuid),
        Column("sharing_scope", String),
        Column("confidentiality", String),
        Column("created_by_person_id", Uuid),
        Column("owner_department_id", Uuid),
    )
    people = Table(
        "people",
        metadata,
        Column("id", Uuid),
        Column("department_id", Uuid),
        Column("archived_at", Date),
        Column("employment_status", String),
    )
    departments = Table("departments", metadata, Column("id", Uuid), Column("archived_at", Date))
    members = Table(
        "department_memberships",
        metadata,
        Column("person_id", Uuid),
        Column("department_id", Uuid),
        Column("is_active", Boolean),
    )
    Table(
        "accounts",
        metadata,
        Column("id", Uuid),
        Column("asset_id", Uuid),
        Column("archived_at", Date),
    )
    for name in ("asset_responsibilities", "access_grants"):
        columns = [
            Column("id", Uuid),
            Column("asset_id", Uuid),
            Column("person_id", Uuid),
            Column("archived_at", Date),
            Column("starts_at", Date),
            Column("ends_at", Date),
        ]
        columns += (
            [Column("role_type", String)]
            if name == "asset_responsibilities"
            else [
                Column("account_id", Uuid),
                Column("department_id", Uuid),
                Column("status", String),
            ]
        )
        Table(name, metadata, *columns)
    metadata.create_all(engine)
    person, other, team, secondary = [uuid4() for _ in range(4)]
    ids = {key: uuid4() for key in ("legacy", "own", "private", "company", "team")}
    with engine.begin() as db:
        db.execute(departments.insert(), [{"id": team}, {"id": secondary}])
        db.execute(people.insert(), dict(id=person, department_id=team, employment_status="active"))
        db.execute(
            members.insert(), dict(person_id=person, department_id=secondary, is_active=True)
        )
        db.execute(
            assets.insert(),
            [
                dict(
                    id=ids["legacy"],
                    sharing_scope=None,
                    confidentiality="internal",
                    created_by_person_id=other,
                    owner_department_id=None,
                ),
                dict(
                    id=ids["own"],
                    sharing_scope="private",
                    confidentiality="personal",
                    created_by_person_id=person,
                    owner_department_id=team,
                ),
                dict(
                    id=ids["private"],
                    sharing_scope="private",
                    confidentiality="personal",
                    created_by_person_id=other,
                    owner_department_id=secondary,
                ),
                dict(
                    id=ids["company"],
                    sharing_scope="company",
                    confidentiality="internal",
                    created_by_person_id=other,
                    owner_department_id=None,
                ),
                dict(
                    id=ids["team"],
                    sharing_scope="team",
                    confidentiality="internal",
                    created_by_person_id=other,
                    owner_department_id=secondary,
                ),
            ],
        )
        context = SimpleNamespace(
            is_global_manager=manager,
            person_id=person if linked else None,
            department_scopes=frozenset(),
        )
        found = set(db.scalars(select(Asset.id).where(asset_visibility_clause(context))))
    return {key for key, identity in ids.items() if identity in found}


def test_shared_discovery_preserved_for_manager():
    assert visible_ids(manager=True) == {"legacy", "own", "private", "company", "team"}


def test_personal_records_visible_only_with_verified_personal_or_shared_scope():
    assert visible_ids() == {"legacy", "own", "company", "team"}


def test_unlinked_identity_cannot_read_personal_or_team_records():
    assert visible_ids(linked=False) == {"legacy", "company"}
