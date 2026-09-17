from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from app.models import SourceImportRecord
from app.services.import_planning import BatchPlanner, classify_l6_asset_type


def test_l6_classifier_uses_service_facts() -> None:
    assert classify_l6_asset_type(
        object_type="service_instance",
        name="OpenAI ChatGPT",
        payload={"purpose": "ChatGPT API"},
    ) == "api_service"
    assert classify_l6_asset_type(
        object_type="service_instance", name="ChatGPT Team", payload={}
    ) == "saas_subscription"
    assert classify_l6_asset_type(
        object_type="resource", name="企业邮箱服务", payload={}
    ) == "email_service"
    assert classify_l6_asset_type(
        object_type="resource", name="影刀与VPN服务", payload={}
    ) == "vpn_network"
    assert classify_l6_asset_type(
        object_type="resource", name="真理时刻业务环境", payload={}
    ) == "business_environment"
    assert classify_l6_asset_type(
        object_type="service_instance",
        name="钉钉悟空",
        payload={
            "legacy_id": "DD-001",
            "service_name": "钉钉悟空",
            "purpose": "悟空全功能+API接入",
        },
    ) == "saas_subscription"
    assert classify_l6_asset_type(
        object_type="service_instance",
        name="OpenAI ChatGPT",
        payload={"legacy_id": "API-001", "purpose": "接入钉钉悟空"},
    ) == "api_service"


def test_identity_record_does_not_create_synthetic_resource() -> None:
    db = Mock()
    db.scalar.return_value = None
    db.scalars.return_value = []
    planner = BatchPlanner(
        db,
        SimpleNamespace(id=uuid4()),
        [],
    )
    record = SourceImportRecord(
        id=uuid4(),
        import_batch_id=planner.batch.id,
        source_kind="curated",
        source_identifier="identity-1",
        raw_payload={"平台": "阿里云", "注册邮箱": "identity@example.com"},
        suggested_object_type="registration_identity",
        suggested_name="identity@example.com",
        confidence=0.95,
    )

    planner.plan_record(record)

    assert {item.object_type for item in planner.objects.values()} == {
        "platform",
        "registration_identity",
    }
    assert not any(
        item.object_type in {"resource", "service_instance"}
        for item in planner.objects.values()
    )
