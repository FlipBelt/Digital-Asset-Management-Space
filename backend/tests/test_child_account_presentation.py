"""Inherited account governance and actionable asset cards on disposable PostgreSQL."""

from datetime import date
from uuid import UUID, uuid4

from app.db.session import SessionLocal
from app.models import (
    Asset,
    AssetFieldDefinition,
    AssetFieldValue,
    AssetResponsibility,
    InternalSystemProfile,
    PlatformTenant,
)
from tests.test_account_hierarchy_lifecycle import child
from tests.test_asset_center_integration import draft
from tests.test_subscription_verification import company_account as company_account

pytest_plugins = ["tests.test_asset_center_integration"]


def test_children_are_excluded_before_home_counts_search_and_pagination(actors, company_account):
    before = actors.admin.get("/api/v1/space/summary").json()
    children = [child(actors, company_account)[0] for _ in range(3)]
    assert actors.admin.get("/api/v1/space/summary").json() == before
    for category in ("all", "created", "drafts", "responsible", "using", "bookmarks"):
        response = actors.admin.get(f"/api/v1/space/assets?category={category}&page_size=1").json()
        assert not {row["asset_id"] for row in children} & {row["id"] for row in response["data"]}
    with SessionLocal() as db:
        marker = "Home-" + uuid4().hex
        db.get(Asset, UUID(company_account["asset"])).name = marker
        for row in children:
            asset = db.get(Asset, UUID(row["asset_id"]))
            asset.name = marker + " child"
            asset.status = "draft"
            asset.review_status = "pending_review"
        db.commit()
    response = actors.admin.get(f"/api/v1/space/assets?keyword={marker}&page_size=1").json()
    assert response["pagination"]["total"] == 1
    assert response["data"][0]["id"] == company_account["asset"]
    hierarchy = actors.admin.get("/api/v1/account-hierarchy").json()["platforms"]
    tenant = next(row for platform in hierarchy for row in platform["company_accounts"]
                  if row["asset_id"] == company_account["asset"])
    assert len(tenant["children"]) == 3


def test_old_children_inherit_current_parent_without_rewriting_history(actors, company_account):
    row, _ = child(actors, company_account)
    with SessionLocal() as db:
        parent = db.get(Asset, UUID(company_account["asset"]))
        parent.status = "active"
        parent.owner_department_id = actors.teams[0]
        parent.ownership_scope = "department"
        parent.expires_at = date(2027, 1, 1)
        parent.description = "父账号治理资料"
        tenant = db.get(PlatformTenant, UUID(company_account["id"]))
        tenant.verification_status = "verified"
        legacy = db.get(Asset, UUID(row["asset_id"]))
        legacy.status = "draft"
        legacy.review_status = "pending_review"
        original_version = legacy.version
        db.add(AssetResponsibility(asset_id=parent.id, person_id=actors.person["owner"],
                                   role_type="responsible", is_primary=True))
        db.commit()
    value = actors.admin.get(f"/api/v1/assets/{row['asset_id']}").json()
    assert value["id"] == row["asset_id"] and value["version"] == original_version
    assert value["is_child_account"] and value["review_status"] == "not_required"
    assert value["status"] == "active" and value["verification_status"] == "verified"
    assert value["parent_asset_id"] == company_account["asset"]
    assert value["expires_at"] == "2027-01-01" and value["description"] == "父账号治理资料"
    assert value["owner_department_id"] == str(actors.teams[0])
    assert "tenant=" + company_account["asset"] in value["management_href"]
    assignment = actors.admin.get(f"/api/v1/assets/{row['asset_id']}/assignment").json()
    assert assignment["responsible_person_id"] == str(actors.person["owner"])
    detail = actors.admin.get(f"/api/v1/hudu/assets/{row['asset_id']}").json()
    assert detail["asset"]["review_status"] == "not_required"
    assert detail["asset"]["responsible_person_id"] == str(actors.person["owner"])
    with SessionLocal() as db:
        assert db.get(Asset, UUID(row["asset_id"])).review_status == "pending_review"
        db.get(Asset, UUID(company_account["asset"])).expires_at = date(2028, 1, 1)
        db.commit()
    assert actors.admin.get(f"/api/v1/assets/{row['asset_id']}").json()["expires_at"] == "2028-01-01"


def test_child_cannot_create_independent_review_or_governance(actors, company_account):
    row, _ = child(actors, company_account)
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(row["asset_id"]))
        assert asset.review_status == "not_required"
        # A mistyped legacy account must still stay out of the outcome review queue.
        asset.asset_type_id = UUID(actors.skill)
        asset.status = "active"
        asset.review_status = "pending_review"
        db.commit()
    value = actors.admin.get(f"/api/v1/assets/{row['asset_id']}").json()
    assert actors.admin.get("/api/v1/asset-reviews", params={"asset_id": row["asset_id"]}).json()["pagination"]["total"] == 0
    assert actors.admin.post(f"/api/v1/asset-reviews/{row['asset_id']}",
                             json={"version": value["version"], "decision": "approved"}).status_code == 404
    assert actors.admin.patch(f"/api/v1/assets/{row['asset_id']}",
                              json={"version": value["version"], "expires_at": "2029-01-01"}).status_code == 409
    assert actors.admin.put(f"/api/v1/assets/{row['asset_id']}/assignment", json={
        "version": value["version"], "responsible_person_id": str(actors.person["owner"]),
    }).status_code == 409
    assert actors.admin.post(f"/api/v1/assets/{row['asset_id']}/confirmation", json={
        "request_id": str(uuid4()), "version": value["version"], "sharing_scope": "private",
    }).status_code == 409


def test_child_read_does_not_expose_private_parent(actors, company_account):
    row, _ = child(actors, company_account)
    with SessionLocal() as db:
        parent = db.get(Asset, UUID(company_account["asset"]))
        parent.sharing_scope = "private"
        parent.confidentiality = "personal"
        child_asset = db.get(Asset, UUID(row["asset_id"]))
        child_asset.created_by_person_id = actors.person["owner"]
        db.commit()
    for suffix in ("", "/assignment", "/responsibilities"):
        assert actors.owner.get(f"/api/v1/assets/{row['asset_id']}{suffix}").status_code == 404
    assert actors.owner.get(f"/api/v1/hudu/assets/{row['asset_id']}").status_code == 404


def test_source_label_cannot_fake_child_exemption(actors):
    asset = draft(actors.owner, actors, source_system="child-account")
    assert not asset["is_child_account"] and asset["review_status"] == "pending_review"


def test_card_links_include_existing_profiles_and_url_fields_without_secret_fields(actors):
    asset = draft(actors.owner, actors)
    with SessionLocal() as db:
        from app.services.repository_visibility import set_visibility
        set_visibility(db, UUID(asset["id"]), "public")
        db.add(InternalSystemProfile(asset_id=UUID(asset["id"]),
                                    repository_url="https://github.com/example/project",
                                    production_url="https://app.example.test/",
                                    deployment_guide_url="https://docs.example.test/start"))
        for confidentiality in ("internal", "restricted"):
            field = AssetFieldDefinition(asset_type_id=UUID(actors.skill),
                                        field_key="url_" + uuid4().hex, label=confidentiality,
                                        data_type="url", confidentiality=confidentiality)
            db.add(field)
            db.flush()
            db.add(AssetFieldValue(asset_id=UUID(asset["id"]), field_definition_id=field.id,
                                   value={"value": f"https://{confidentiality}.example.test/"}))
        db.commit()
    response = actors.owner.get("/api/v1/space/assets", params={"keyword": asset["name"]}).json()
    links = next(row["card_links"] for row in response["data"] if row["id"] == asset["id"])
    assert {link["url"] for link in links} == {
        "https://github.com/example/project", "https://app.example.test/",
        "https://docs.example.test/start", "https://internal.example.test/",
    }
    assert actors.other.get(f"/api/v1/assets/{asset['id']}").status_code == 404
