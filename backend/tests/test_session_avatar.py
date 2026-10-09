from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from app.api.v1.sessions import serialize_current_user
from app.services.avatar import safe_avatar_url


@pytest.mark.parametrize(
    "value",
    [
        None,
        {},
        42,
        "",
        "http://cdn.example/avatar.png",
        "//cdn.example/avatar.png",
        "javascript:alert(1)",
        "data:image/png;base64,abc",
        "https://user:pass@cdn.example/a",
        "https://[invalid/a",
        "https://cdn.example:invalid/a",
        "https://cdn.example/\nother",
        "https://cdn.example/" + "x" * 2048,
    ],
)
def test_avatar_rejects_missing_or_unsafe_urls(value: object) -> None:
    assert safe_avatar_url(value) is None


def test_avatar_keeps_public_https_resource() -> None:
    assert safe_avatar_url(" https://cdn.example/avatar.png ") == "https://cdn.example/avatar.png"


@pytest.mark.parametrize(
    "has_person,avatar", [(True, "https://cdn.example/avatar.png"), (True, None), (False, None)]
)
def test_current_user_avatar_is_read_from_own_profile(has_person: bool, avatar: str | None) -> None:
    person_id = uuid4() if has_person else None
    user = SimpleNamespace(id=uuid4(), username="test-user", person_id=person_id)
    session = SimpleNamespace(csrf_token="synthetic-csrf")
    db = Mock()
    db.get.return_value = SimpleNamespace(display_name="测试人员", department_id=None)
    db.scalar.return_value = SimpleNamespace(job_title=None, profile_data={"avatar": avatar})
    with (
        patch("app.api.v1.sessions.get_role_codes", return_value=["employee"]),
        patch("app.api.v1.sessions.get_permission_codes", return_value=["asset.read"]),
    ):
        current = serialize_current_user(db, user, session)
    assert current.avatar_url == avatar
    assert current.roles == ["employee"]
    assert current.permissions == ["asset.read"]
    assert current.person_id == person_id
    if has_person:
        query = db.scalar.call_args.args[0]
        assert person_id in query.compile().params.values()
    else:
        db.scalar.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()
