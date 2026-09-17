"""Load a sanitized developer-review fixture without touching the asset ledger."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import AuditLog, DeveloperIntakeBatch, DeveloperIntakeRecord, Person, User

FORBIDDEN_TERMS = ("password", "pwd", "secret", "token", "cookie", "api_key", "密钥", "密码", "验证码")


def assert_sanitized(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if any(term in str(key).casefold() for term in FORBIDDEN_TERMS):
                raise ValueError(f"fixture contains a forbidden field: {key}")
            assert_sanitized(item)
    elif isinstance(value, list):
        for item in value:
            assert_sanitized(item)


def seed(path: Path, operator_username: str, responsible_name: str) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert_sanitized(payload)
    with SessionLocal() as db:
        operator = db.scalar(select(User).where(User.username == operator_username, User.archived_at.is_(None)))
        responsible = db.scalar(select(Person).where(Person.display_name == responsible_name, Person.archived_at.is_(None)))
        if operator is None or responsible is None:
            raise ValueError("operator or responsible person is missing")
        existing = db.scalar(
            select(DeveloperIntakeBatch).where(
                DeveloperIntakeBatch.title == payload["title"],
                DeveloperIntakeBatch.source_location == payload["source_location"],
            )
        )
        if existing is not None:
            print(f"Developer intake already exists: {existing.id}")
            return
        batch = DeveloperIntakeBatch(
            title=payload["title"],
            source_location=payload["source_location"],
            status=payload.get("status", "staged"),
            responsible_person_id=responsible.id,
            created_by_user_id=operator.id,
            summary=payload.get("summary", {}),
            review_note=payload.get("review_note"),
        )
        db.add(batch)
        db.flush()
        for record in payload.get("records", []):
            db.add(
                DeveloperIntakeRecord(
                    developer_intake_batch_id=batch.id,
                    record_key=record["record_key"],
                    source_file=record["source_file"],
                    suggested_name=record["suggested_name"],
                    suggested_layers=record.get("suggested_layers", []),
                    disposition=record.get("disposition", "hold"),
                    confidence=Decimal(str(record["confidence"])),
                    evidence=record.get("evidence", []),
                    masked_identifiers=record.get("masked_identifiers", []),
                    review_note=record.get("review_note"),
                )
            )
        db.add(
            AuditLog(
                actor_user_id=operator.id,
                action="developer.intake.stage",
                object_type="developer_intake_batch",
                object_id=batch.id,
                after_data={"title": batch.title, "record_count": len(payload.get("records", []))},
            )
        )
        db.commit()
        print(f"Developer intake staged: {batch.id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--responsible", default="惜君-吴旭骏")
    arguments = parser.parse_args()
    seed(arguments.fixture, arguments.operator, arguments.responsible)
