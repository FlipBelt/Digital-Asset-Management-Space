from __future__ import annotations

import json
from datetime import UTC, datetime

COMPANY_SOURCE_FIELD = "主体（社保公司）"
COMPANY_STATUSES = {"available", "missing", "invalid", "conflict", "unavailable", "unknown"}


def _company_name(value: object) -> str | None:
    if isinstance(value, dict):
        value = value.get("text")
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > 200 or any(ord(char) < 32 for char in name):
        return None
    if not name.endswith(("公司", "合伙企业", "个体工商户")):
        return None
    return name


def company_affiliation_from_detail(detail: dict) -> dict:
    """Read only the verified company field, never infer it from department placements."""
    extension = detail.get("extension")
    if isinstance(extension, str):
        try:
            extension = json.loads(extension)
        except ValueError:
            extension = None
    values = []
    if isinstance(extension, dict) and COMPANY_SOURCE_FIELD in extension:
        values.append(extension[COMPANY_SOURCE_FIELD])
    attributes = detail.get("ext_attrs")
    if isinstance(attributes, list):
        values.extend(
            row.get("value")
            for row in attributes
            if isinstance(row, dict) and row.get("name") == COMPANY_SOURCE_FIELD
        )
    names = {_company_name(value) for value in values if value not in (None, "")}
    invalid = None in names
    names.discard(None)
    if len(names) > 1:
        state, name = "conflict", None
    elif invalid:
        state, name = "invalid", None
    elif names:
        state, name = "available", next(iter(names))
    else:
        state, name = "missing", None
    return {
        "name": name,
        "status": state,
        "source_field": COMPANY_SOURCE_FIELD,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def unavailable_company_affiliation() -> dict:
    return {
        "name": None,
        "status": "unavailable",
        "source_field": COMPANY_SOURCE_FIELD,
        "checked_at": datetime.now(UTC).isoformat(),
    }


def stored_company_affiliation(profile_data: dict | None) -> dict:
    stored = (profile_data or {}).get("company_affiliation")
    if not isinstance(stored, dict) or stored.get("source_field") != COMPANY_SOURCE_FIELD:
        return {"name": None, "status": "unknown", "source_field": None, "checked_at": None}
    state = stored.get("status")
    if not isinstance(state, str) or state not in COMPANY_STATUSES:
        state = "unknown"
    name = _company_name(stored.get("name")) if state == "available" else None
    if state == "available" and name is None:
        state = "invalid"
    checked_at = stored.get("checked_at")
    try:
        checked_at = datetime.fromisoformat(checked_at) if isinstance(checked_at, str) else None
    except ValueError:
        checked_at = None
    return {
        "name": name,
        "status": state,
        "source_field": COMPANY_SOURCE_FIELD,
        "checked_at": checked_at,
    }
