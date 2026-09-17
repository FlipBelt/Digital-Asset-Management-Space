from types import SimpleNamespace

from app.services import usage_connectors


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_deepseek_balance_snapshot_uses_reported_currency(monkeypatch) -> None:
    monkeypatch.setattr(
        usage_connectors.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse(
            {
                "is_available": True,
                "balance_infos": [
                    {"currency": "CNY", "total_balance": "12.34"},
                    {"currency": "USD", "total_balance": "5.6"},
                ],
            }
        ),
    )
    _, metrics, snapshot = usage_connectors.collect_snapshot(
        SimpleNamespace(configuration={"api_key": "test-key"}), "deepseek"
    )
    assert metrics == [
        ("balance", usage_connectors.Decimal("12.34"), "CNY"),
        ("balance", usage_connectors.Decimal("5.6"), "USD"),
    ]
    assert snapshot["kind"] == "account_balance"


def test_minimax_payg_is_not_a_supported_quota_connection() -> None:
    result = usage_connectors.test_connection(
        SimpleNamespace(configuration={"api_key": "test-key", "key_type": "payg"}), "minimax"
    )
    assert result["status"] == "failed"


def test_minimax_remaining_values_are_recorded_without_guessing() -> None:
    values = usage_connectors._find_remaining_values(
        {"model_remains": [{"remain": "321"}], "not_a_quota": 99}
    )
    assert values == [("model_remains[0].remain", usage_connectors.Decimal("321"))]


def test_minimax_token_plan_snapshot_preserves_returned_quota_labels(monkeypatch) -> None:
    monkeypatch.setattr(
        usage_connectors.httpx,
        "get",
        lambda *args, **kwargs: FakeResponse(
            {"base_resp": {"status_code": 0}, "quota": {"daily_remaining": "18"}}
        ),
    )
    _, metrics, snapshot = usage_connectors.collect_snapshot(
        SimpleNamespace(configuration={"api_key": "test-key", "key_type": "token_plan"}),
        "minimax",
    )
    assert metrics == [("quota_remaining", usage_connectors.Decimal("18"), None)]
    assert snapshot["items"] == [{"label": "quota.daily_remaining", "remaining": "18"}]


def test_aliyun_account_balance_uses_documented_balance_fields(monkeypatch) -> None:
    request: dict = {}

    def fake_get(*args, **kwargs):
        request.update(kwargs)
        return FakeResponse(
            {
                "Success": True,
                "Data": {
                    "Currency": "CNY",
                    "AvailableAmount": "100.00",
                    "AvailableCashAmount": "80.00",
                    "CreditAmount": "20.00",
                },
            }
        )

    monkeypatch.setattr(usage_connectors.httpx, "get", fake_get)
    _, metrics, snapshot = usage_connectors.collect_snapshot(
        SimpleNamespace(
            configuration={"access_key_id": "test-id", "access_key_secret": "test-secret"}
        ),
        "aliyun",
    )
    assert request["params"]["Action"] == "QueryAccountBalance"
    assert request["params"]["Signature"]
    assert metrics == [("balance", usage_connectors.Decimal("100.00"), "CNY")]
    assert snapshot["balances"][0] == {
        "key": "AvailableAmount",
        "label": "可用额度",
        "value": "100.00",
        "currency": "CNY",
    }
