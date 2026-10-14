from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import Boolean, Column, Date, MetaData, String, Table, Uuid, create_engine, select

from app.core.access import asset_visibility_clause
from app.models import Asset, ProviderConnection
from app.services.personal_subscription_policy import personal_subscription_connection_clause


def visible_ids(*, manager=False, linked=True, include_personal=False, department_manager=False):
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
        Column("source_system", String),
        Column("asset_type_id", Uuid),
    )
    asset_types = Table("asset_types", metadata, Column("id", Uuid), Column("code", String))
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
    saas_type, ai_type = uuid4(), uuid4()
    ids = {key: uuid4() for key in ("legacy", "own", "private", "company", "team")}
    with engine.begin() as db:
        db.execute(
            asset_types.insert(),
            [dict(id=saas_type, code="saas_subscription"), dict(id=ai_type, code="ai_skill")],
        )
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
        if include_personal:
            for key, owner, scope, type_id in (
                ("own_membership", person, "private", saas_type),
                ("public_membership", other, "company", saas_type),
                ("team_membership", other, "team", saas_type),
                ("legacy_membership", other, None, saas_type),
                ("orphan_membership", None, "company", saas_type),
                ("membership_source_ai", other, "company", ai_type),
            ):
                ids[key] = uuid4()
                db.execute(
                    assets.insert(),
                    dict(
                        id=ids[key],
                        sharing_scope=scope,
                        confidentiality="internal",
                        created_by_person_id=owner,
                        owner_department_id=secondary,
                        source_system="membership-registration",
                        asset_type_id=type_id,
                    ),
                )
                if key.endswith("membership") and owner != person:
                    db.execute(
                        metadata.tables["asset_responsibilities"].insert(),
                        dict(
                            id=uuid4(),
                            asset_id=ids[key],
                            person_id=person,
                            role_type="responsible",
                        ),
                    )
                    db.execute(
                        metadata.tables["access_grants"].insert(),
                        dict(id=uuid4(), asset_id=ids[key], person_id=person, status="active"),
                    )
        context = SimpleNamespace(
            is_global_manager=manager,
            person_id=person if linked else None,
            department_scopes=frozenset({secondary}) if department_manager else frozenset(),
        )
        found = set(db.scalars(select(Asset.id).where(asset_visibility_clause(context))))
    return {key for key, identity in ids.items() if identity in found}


def test_shared_discovery_preserved_for_manager():
    assert visible_ids(manager=True) == {"legacy", "own", "private", "company", "team"}


def test_personal_records_visible_only_with_verified_personal_or_shared_scope():
    assert visible_ids() == {"legacy", "own", "company", "team"}


def test_unlinked_identity_cannot_read_personal_or_team_records():
    assert visible_ids(linked=False) == {"legacy", "company"}


def test_personal_memberships_ignore_public_scope_responsibility_and_grants():
    assert visible_ids(include_personal=True, department_manager=True) == {
        "legacy",
        "own",
        "company",
        "team",
        "own_membership",
        "membership_source_ai",
    }


def test_unlinked_identity_cannot_read_orphan_or_public_personal_memberships():
    assert visible_ids(include_personal=True, linked=False) == {
        "legacy",
        "company",
        "membership_source_ai",
    }


def test_global_manager_can_read_personal_memberships_without_changing_ai_policy():
    assert visible_ids(include_personal=True, manager=True) == {
        "legacy",
        "own",
        "private",
        "company",
        "team",
        "own_membership",
        "public_membership",
        "team_membership",
        "legacy_membership",
        "orphan_membership",
        "membership_source_ai",
    }


def test_usage_connections_keep_null_source_company_and_unbound_connections():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    assets = Table(
        "assets",
        metadata,
        Column("id", Uuid),
        Column("source_system", String),
        Column("asset_type_id", Uuid),
        Column("created_by_person_id", Uuid),
    )
    types = Table("asset_types", metadata, Column("id", Uuid), Column("code", String))
    instances = Table("service_instances", metadata, Column("id", Uuid), Column("asset_id", Uuid))
    connections = Table(
        "provider_connections", metadata, Column("id", Uuid), Column("service_instance_id", Uuid)
    )
    metadata.create_all(engine)
    person, other, saas, ai = [uuid4() for _ in range(4)]
    ids = {key: uuid4() for key in ("company", "own", "other", "orphan", "ai", "unbound")}
    with engine.begin() as db:
        db.execute(
            types.insert(), [dict(id=saas, code="saas_subscription"), dict(id=ai, code="ai_skill")]
        )
        for key, source, owner, type_id in (
            ("company", None, other, saas),
            ("own", "membership-registration", person, saas),
            ("other", "membership-registration", other, saas),
            ("orphan", "membership-registration", None, saas),
            ("ai", "membership-registration", other, ai),
        ):
            asset_id, instance_id = uuid4(), uuid4()
            db.execute(
                assets.insert(),
                dict(
                    id=asset_id,
                    source_system=source,
                    created_by_person_id=owner,
                    asset_type_id=type_id,
                ),
            )
            db.execute(instances.insert(), dict(id=instance_id, asset_id=asset_id))
            db.execute(connections.insert(), dict(id=ids[key], service_instance_id=instance_id))
        db.execute(connections.insert(), dict(id=ids["unbound"], service_instance_id=None))
        for actor, expected in (
            (person, {"company", "own", "ai", "unbound"}),
            (None, {"company", "ai", "unbound"}),
        ):
            found = set(
                db.scalars(
                    select(ProviderConnection.id).where(
                        personal_subscription_connection_clause(actor)
                    )
                )
            )
            assert {key for key, identity in ids.items() if identity in found} == expected
