"""Category tabs query the same visible assets on a disposable PostgreSQL DB."""

from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.main import app
from app.models import Asset, AssetCategory, AssetType, Role, User, UserRoleScope

pytest_plugins = ["test_asset_center_integration"]


@pytest.fixture
def catalog(actors):
    marker = "category-test-" + uuid4().hex
    with SessionLocal() as db:
        categories = {
            key: AssetCategory(code=f"{marker}-{key}", name=f"Synthetic category {key}")
            for key in ("parent", "other", "empty", "child")
        }
        db.add_all(categories.values())
        db.flush()
        categories["child"].parent_id = categories["parent"].id
        types = {
            key: AssetType(
                category_id=categories[category].id,
                code=f"{marker}-{key}",
                name=f"Synthetic type {key}",
            )
            for key, category in (
                ("a", "parent"), ("b", "parent"), ("other", "other"), ("child", "child")
            )
        }
        db.add_all(types.values())
        db.flush()
        rows = {}

        def add(key, type_key="a", team=0, status="active", scope="company", creator="other"):
            asset = Asset(
                asset_code=f"CAT-{uuid4().hex}",
                name=f"{marker}-{key}",
                asset_type_id=types[type_key].id,
                legal_entity_id=UUID(actors.entity),
                owner_department_id=actors.teams[team],
                created_by_person_id=actors.person[creator],
                sharing_scope=scope,
                confidentiality="personal" if scope == "private" else "internal",
                status=status,
                archived_at=datetime.now(UTC) if status in {"archived", "deleted"} else None,
                criticality="important" if key == "active_a" else "normal",
            )
            db.add(asset)
            rows[key] = asset

        add("active_a")
        add("active_b", type_key="b", team=1)
        add("draft_a", status="draft")
        add("archived_a", status="archived")
        add("deleted_a", status="deleted")
        add("other", type_key="other")
        add("child", type_key="child")
        add("private_owner", status="draft", scope="private", creator="owner")
        add("private_other", team=1, status="draft", scope="private")
        add("team_other", team=1, scope="team")
        add("team_stranger", team=2, scope="team", creator="stranger")
        db.commit()
        return SimpleNamespace(
            marker=marker,
            categories={key: str(item.id) for key, item in categories.items()},
            types={key: str(item.id) for key, item in types.items()},
            assets={key: str(item.id) for key, item in rows.items()},
            names={key: item.name for key, item in rows.items()},
        )


def listing(client, catalog, **params):
    response = client.get(
        "/api/v1/assets", params={"keyword": catalog.marker, "page_size": 100, **params}
    )
    assert response.status_code == 200, response.text
    value = response.json()
    return {row["id"] for row in value["data"]}, value["pagination"]["total"]


def test_category_matches_each_actual_type_exactly_and_preserves_pagination(actors, catalog):
    parent = catalog.categories["parent"]
    expected = {
        catalog.assets[key]
        for key in (
            "active_a", "active_b", "draft_a", "private_owner", "private_other",
            "team_other", "team_stranger",
        )
    }
    assert listing(actors.admin, catalog, category_id=parent) == (expected, 7)
    assert listing(actors.admin, catalog) == (
        expected | {catalog.assets["other"], catalog.assets["child"]}, 9
    )
    assert listing(actors.admin, catalog, category_id=catalog.categories["child"]) == (
        {catalog.assets["child"]}, 1
    )
    pages = []
    for page in range(1, 5):
        ids, total = listing(actors.admin, catalog, category_id=parent, page=page, page_size=2)
        assert total == 7
        assert len(ids) == (2 if page < 4 else 1)
        assert not ids.intersection(set().union(*pages))
        pages.append(ids)
    assert set().union(*pages) == expected
    assert listing(actors.admin, catalog, category_id=parent, page=5, page_size=2) == (set(), 7)


@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"asset_type_id": "type:b"}, {"active_b"}),
        ({"asset_type_id": "type:other"}, set()),
        ({"status": "active"}, {"active_a", "active_b", "team_other", "team_stranger"}),
        (
            {
                "asset_type_id": "type:a", "status": "active", "department_id": "team:0",
                "legal_entity_id": "entity", "criticality": "important",
            },
            {"active_a"},
        ),
        ({"asset_type_id": "type:b", "department_id": "team:0"}, set()),
        ({"keyword": "name:private_owner"}, {"private_owner"}),
    ],
)
def test_category_combines_with_existing_filters(actors, catalog, filters, expected):
    params = {}
    for key, value in filters.items():
        if value.startswith("type:"):
            params[key] = catalog.types[value.removeprefix("type:")]
        elif value.startswith("team:"):
            params[key] = str(actors.teams[int(value.removeprefix("team:"))])
        elif value.startswith("name:"):
            params[key] = catalog.names[value.removeprefix("name:")]
        else:
            params[key] = actors.entity if value == "entity" else value
    expected_ids = {catalog.assets[key] for key in expected}
    assert listing(actors.admin, catalog, category_id=catalog.categories["parent"], **params) == (
        expected_ids, len(expected_ids)
    )


def test_category_keeps_identity_and_department_visibility_in_list_and_total(actors, catalog):
    common = {"active_a", "active_b", "draft_a"}
    for client, keys in (
        (actors.owner, common | {"private_owner", "team_other"}),
        (actors.other, common | {"private_other", "team_other"}),
        (actors.stranger, common | {"team_stranger"}),
    ):
        expected = {catalog.assets[key] for key in keys}
        assert listing(client, catalog, category_id=catalog.categories["parent"]) == (
            expected, len(expected)
        )
        first, total = listing(
            client, catalog, category_id=catalog.categories["parent"], page_size=1
        )
        assert len(first) == 1 and first <= expected and total == len(expected)
        assert listing(client, catalog, category_id=catalog.categories["other"]) == (
            {catalog.assets["other"]}, 1
        )


@pytest.mark.parametrize("category", ["empty", "unknown"])
def test_empty_or_unknown_category_never_falls_back_to_all_assets(actors, catalog, category):
    category_id = str(uuid4()) if category == "unknown" else catalog.categories[category]
    assert listing(actors.admin, catalog, category_id=category_id) == (set(), 0)
    assert listing(
        actors.admin, catalog, category_id=category_id, include_archived=True
    ) == (set(), 0)
    assert listing(actors.admin, catalog, category_id=category_id, deleted_only=True) == (set(), 0)


def test_category_keeps_archived_and_deleted_assets_separate(actors, catalog):
    parent = catalog.categories["parent"]
    active, total = listing(actors.admin, catalog, category_id=parent)
    archived, archived_total = listing(
        actors.admin, catalog, category_id=parent, include_archived=True
    )
    assert archived == active | {catalog.assets["archived_a"]}
    assert archived_total == total + 1
    assert catalog.assets["deleted_a"] not in archived
    assert listing(actors.admin, catalog, category_id=parent, status="archived") == (set(), 0)
    assert listing(
        actors.admin, catalog, category_id=parent, status="archived", include_archived=True
    ) == ({catalog.assets["archived_a"]}, 1)
    assert listing(actors.admin, catalog, category_id=parent, deleted_only=True) == (
        {catalog.assets["deleted_a"]}, 1
    )
    assert listing(
        actors.admin, catalog, category_id=parent, deleted_only=True,
        asset_type_id=catalog.types["b"]
    ) == (set(), 0)


def test_category_does_not_bypass_recycle_bin_permissions(actors, catalog):
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.person_id == actors.person["owner"]))
        role = db.scalar(select(Role).where(Role.code == "department_manager"))
        db.add(
            UserRoleScope(
                user_id=user.id, role_id=role.id, scope_type="department", scope_id=actors.teams[0]
            )
        )
        db.commit()
    for client in (actors.owner, actors.other):
        for category in (catalog.categories["parent"], str(uuid4())):
            response = client.get(
                "/api/v1/assets", params={"category_id": category, "deleted_only": True}
            )
            assert response.status_code == 403


def test_category_uuid_validation_and_anonymous_authentication(actors, catalog):
    for value in ("not-a-uuid", ""):
        response = actors.admin.get("/api/v1/assets", params={"category_id": value})
        assert response.status_code == 422
    client = TestClient(app)
    try:
        assert client.get(
            "/api/v1/assets", params={"category_id": catalog.categories["parent"]}
        ).status_code == 401
    finally:
        client.close()
