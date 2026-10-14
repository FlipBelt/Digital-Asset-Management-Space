"""Audited source reconciliation and explicit repository disclosure on isolated PG."""

from uuid import UUID, uuid4

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models import (
    AccessGrant,
    Asset,
    AssetFieldDefinition,
    AssetFieldValue,
    AssetResponsibility,
    AuditLog,
    InternalSystemProfile,
    LegalEntity,
    RegistrationIdentityProfile,
)
from tests.test_asset_center_integration import draft, employee_request_payload
from tests.test_subscription_verification import company_account as company_account

pytest_plugins = ["tests.test_asset_center_integration"]


def contact_body(actors, **changes):
    row = {
        "identifier": "188" + str(uuid4().int)[-8:],
        "legal_entity_id": actors.entity,
        "custodian_person_id": str(actors.person["owner"]),
        "owner_department_id": str(actors.teams[0]),
        "source_nature": "company_owned",
        "verification_status": "documented",
        "note": "隔离公司电话原表",
    }
    row.update(changes)
    return {"request_id": str(uuid4()), "source_note": "隔离资料核对，未发送短信", "rows": [row]}


def reconcile(client, body):
    return client.post("/api/v1/workspace/registration-identities/reconcile", json=body)


def test_contact_reconciliation_exact_retry_version_bound_update_and_holder(actors):
    body = contact_body(actors)
    assert reconcile(actors.owner, body).status_code == 403
    created = reconcile(actors.admin, body)
    assert created.status_code == 200, created.text
    first = created.json()[0]
    assert first["name"] == first["identifier"] == body["rows"][0]["identifier"]
    assert first["verification_status"] == "documented" and first["version"] == 1
    assert reconcile(actors.admin, body).json() == created.json()
    assert reconcile(actors.admin, {**body, "source_note": "变更来源"}).status_code == 409
    with SessionLocal() as db:
        db.get(Asset, UUID(first["asset_id"])).name = "历史通讯资源别名"
        db.commit()
    update = contact_body(
        actors,
        identifier=body["rows"][0]["identifier"],
        expected_version=1,
        custodian_person_id=str(actors.person["other"]),
        registration_blocked=True,
    )
    updated = reconcile(actors.admin, update)
    assert updated.status_code == 200, updated.text
    row = updated.json()[0]
    assert row["name"] == row["identifier"] == first["identifier"]
    assert row["asset_id"] == first["asset_id"] and row["version"] == 2
    assert row["registration_blocked"] and row["custodian_person_id"] == str(actors.person["other"])
    assert reconcile(actors.admin, {**update, "request_id": str(uuid4())}).status_code == 409
    with SessionLocal() as db:
        asset = db.get(Asset, UUID(first["asset_id"]))
        assert asset.name == first["identifier"]
        assert asset.review_status == "not_required" and asset.status == "active"
        responsibility = db.scalar(
            select(AssetResponsibility).where(
                AssetResponsibility.asset_id == asset.id,
                AssetResponsibility.role_type == "responsible",
            )
        )
        assert responsibility.person_id == actors.person["other"]
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.action == "contact.reconcile",
                    AuditLog.request_id == body["request_id"],
                )
            )
            == 1
        )


def test_contact_duplicate_batch_and_invalid_row_rollback_are_atomic(actors):
    body = contact_body(actors)
    duplicate = {
        **body,
        "rows": [
            body["rows"][0],
            {**body["rows"][0], "identifier": "+86 " + body["rows"][0]["identifier"]},
        ],
    }
    assert reconcile(actors.admin, duplicate).status_code == 422
    mixed = {**body, "rows": [body["rows"][0], {**body["rows"][0], "identifier": "bad"}]}
    assert reconcile(actors.admin, mixed).status_code == 422
    with SessionLocal() as db:
        assert not db.scalar(
            select(RegistrationIdentityProfile.id).where(
                RegistrationIdentityProfile.identifier_value == body["rows"][0]["identifier"]
            )
        )
    shared = contact_body(actors, custodian_person_id=None)
    saved = reconcile(actors.admin, shared)
    assert saved.status_code == 200, saved.text
    assert saved.json()[0]["custodian_person_id"] is None
    assert (
        reconcile(
            actors.admin, contact_body(actors, custodian_person_id=None, owner_department_id=None)
        ).status_code
        == 422
    )


def test_cross_company_contact_reference_preserves_holder_and_prevents_repeat_accounts(
    actors, company_account
):
    contact = reconcile(actors.admin, contact_body(actors)).json()[0]
    with SessionLocal() as db:
        entity = LegalEntity(code="cross-" + uuid4().hex, name="隔离集团公司")
        db.add(entity)
        db.commit()
        company_id = str(entity.id)
    body = {
        "request_id": str(uuid4()),
        "platform_id": str(company_account["platform"]),
        "legal_entity_id": company_id,
        "internal_name": "同一账号仅填一次",
        "external_identifier_value": "native-" + uuid4().hex,
        "registration_identity_asset_id": contact["asset_id"],
        "responsible_person_id": str(actors.person["owner"]),
    }
    assert actors.owner.post("/api/v1/workspace/platform-accounts", json=body).status_code == 422
    result = actors.admin.post("/api/v1/workspace/platform-accounts", json=body)
    assert result.status_code == 201, result.text
    assert (
        actors.admin.post("/api/v1/workspace/platform-accounts", json=body).json() == result.json()
    )
    assert (
        actors.admin.post(
            "/api/v1/workspace/platform-accounts", json={**body, "request_id": str(uuid4())}
        ).status_code
        == 409
    )
    identities = actors.admin.get("/api/v1/workspace/registration-identities").json()
    current = next(row for row in identities if row["asset_id"] == contact["asset_id"])
    assert current["legal_entity_id"] == actors.entity
    assert current["custodian_person_id"] == str(actors.person["owner"])
    blocked = reconcile(actors.admin, contact_body(actors, registration_blocked=True)).json()[0]
    assert (
        actors.admin.post(
            "/api/v1/workspace/platform-accounts",
            json={
                **body,
                "request_id": str(uuid4()),
                "external_identifier_value": "another",
                "registration_identity_asset_id": blocked["asset_id"],
            },
        ).status_code
        == 422
    )


def test_repository_unknown_public_private_filter_all_card_detail_profile_paths(actors):
    url = "https://github.com/example/private-project"
    asset = draft(actors.owner, actors, description=f"说明 {url}", source_reference=url)
    with SessionLocal() as db:
        db.add(
            InternalSystemProfile(
                asset_id=UUID(asset["id"]),
                repository_url=url,
                production_url="https://app.example.test/",
                deployment_guide_url=url + "/blob/main/deploy.md",
            )
        )
        field = AssetFieldDefinition(
            asset_type_id=UUID(actors.skill),
            field_key="repo_" + uuid4().hex,
            label="仓库",
            data_type="url",
            confidentiality="internal",
        )
        db.add(field)
        db.flush()
        db.add(
            AssetFieldValue(
                asset_id=UUID(asset["id"]), field_definition_id=field.id, value={"value": url}
            )
        )
        db.commit()
    paths = [
        f"/api/v1/assets/{asset['id']}",
        f"/api/v1/assets/{asset['id']}/internal-system-profile",
        f"/api/v1/assets/{asset['id']}/field-values",
        f"/api/v1/hudu/assets/{asset['id']}",
        "/api/v1/space/assets",
        "/api/v1/assets",
        "/api/v1/hudu/assets",
        "/api/v1/hudu/overview",
    ]
    for path in paths:
        response = actors.owner.get(path)
        assert response.status_code == 200, response.text
        assert url not in response.text, path
    endpoint = f"/api/v1/assets/{asset['id']}/repository-visibility"
    body = {"request_id": str(uuid4()), "version": 1, "visibility": "public"}
    assert actors.other.put(endpoint, json=body).status_code == 404
    public = actors.owner.put(endpoint, json=body)
    assert public.status_code == 200, public.text
    assert actors.owner.put(endpoint, json=body).json() == public.json()
    assert actors.owner.put(endpoint, json={**body, "visibility": "private"}).status_code == 409
    assert url in actors.owner.get(paths[0]).text
    private = actors.owner.put(
        endpoint, json={"request_id": str(uuid4()), "version": 2, "visibility": "private"}
    )
    assert private.status_code == 200, private.text
    for path in paths:
        assert url not in actors.owner.get(path).text, path
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(InternalSystemProfile.repository_url).where(
                    InternalSystemProfile.asset_id == UUID(asset["id"])
                )
            )
            == url
        )
    from io import BytesIO

    from openpyxl import load_workbook
    exported = actors.owner.get("/api/v1/exports/assets.xlsx")
    workbook = load_workbook(BytesIO(exported.content))
    assert url not in str(list(workbook.active.values))
    masked = actors.owner.get(paths[0]).json()
    edited = actors.owner.patch(paths[0], json={"version": masked["version"], "name": "更新说明", "description": masked["description"]})
    assert edited.status_code == 200 and url not in edited.text
    with SessionLocal() as db:
        assert url in db.get(Asset, UUID(asset["id"])).description


def test_requests_reference_real_platform_or_enterprise_account_and_do_not_allocate(
    actors, company_account
):
    no_reference = employee_request_payload(platform_id=None)
    assert actors.owner.post("/api/v1/space/requests", json=no_reference).status_code == 422
    body = employee_request_payload(
        platform_id=str(company_account["platform"]), resource_name="任意伪造名称"
    )
    result = actors.owner.post("/api/v1/space/requests", json=body)
    assert result.status_code == 201, result.text
    assert result.json()["detail"]["resource_name"] == "隔离核验平台"
    with SessionLocal() as db:
        db.get(Asset, UUID(company_account["asset"])).sharing_scope = "private"
        db.commit()
    targets = actors.owner.get("/api/v1/space/request-targets").json()
    assert company_account["asset"] not in {row["asset_id"] for row in targets["accounts"]}
    targets = actors.admin.get("/api/v1/space/request-targets").json()
    assert company_account["asset"] in {row["asset_id"] for row in targets["accounts"]}
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AccessGrant))
    account_request = actors.admin.post(
        "/api/v1/space/requests",
        json={**body, "request_id": str(uuid4()), "asset_id": company_account["asset"]},
    )
    assert account_request.status_code == 201, account_request.text
    assert account_request.json()["detail"]["resource_name"] == "隔离公司账号"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AccessGrant)) == before
