"""Stage and commit a pre-reviewed, sanitized instance payload.

The payload contains only source facts required for L2/L3/L6. It is intended
for a one-time controlled production run and never accepts passwords or keys.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import ImportBatch, ImportProposedObject, ImportProposedRelation, SourceImportRecord, User
from app.services.import_commit import commit_reviewed_import_batch
from app.services.import_planning import rebuild_import_plan


def main() -> None:
    payload = json.load(sys.stdin)
    actor = None
    with SessionLocal() as db:
        actor = db.scalar(select(User).where(User.is_active.is_(True)).order_by(User.created_at))
        if actor is None:
            raise RuntimeError("没有可用的审计用户")
        results = []
        for item in payload.get("batches", []):
            batch = db.scalar(select(ImportBatch).where(ImportBatch.file_name == item["file_name"], ImportBatch.status != "committed").order_by(ImportBatch.created_at.desc()))
            if batch is None:
                batch = ImportBatch(file_name=item["file_name"], status="staged", total_count=len(item["records"]))
                db.add(batch)
                db.flush()
                for row in item["records"]:
                    db.add(SourceImportRecord(import_batch_id=batch.id, source_kind=item.get("source_kind", "curated"),
                        source_identifier=row.get("source_identifier") or row.get("来源文件") or item["file_name"],
                        raw_payload=row["raw_payload"], suggested_object_type=row.get("suggested_object_type"),
                        suggested_name=row.get("suggested_name"), confidence=row.get("confidence", 0.9), mapping_status="pending_review"))
                db.flush()
                rebuild_import_plan(db, batch)
                db.flush()
                # User has explicitly approved the curated L2/L3/L6 scope. Keep
                # L4/L5/finance proposals visible but out of the commit set.
                for proposal in db.scalars(select(ImportProposedObject).where(ImportProposedObject.import_batch_id == batch.id)):
                    proposal.review_status = "approved" if proposal.object_type in {"platform", "registration_identity", "service_instance", "resource", "internal_system"} else "rejected"
                for relation in db.scalars(select(ImportProposedRelation).where(ImportProposedRelation.import_batch_id == batch.id)):
                    relation.review_status = "approved" if relation.validation_status != "requires_configuration" else "rejected"
            db.commit()
            results.append(commit_reviewed_import_batch(db, batch_id=batch.id, actor_user_id=actor.id,
                reason="用户已确认实例化入库原则；本次仅提交L2/L3/L6，L4/L5不由系统推断。"))
        print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
