"""Developer-only control plane for sanitized private intake review."""

from __future__ import annotations

from collections import Counter
from html import escape
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import require_developer_supervisor
from app.db.session import get_db
from app.models import Asset, AuditLog, DeveloperIntakeBatch, DeveloperIntakeRecord, User

router = APIRouter(prefix="/developer", tags=["developer-control"])
console_router = APIRouter()


def _control_plane_payload(db: Session, operator: User) -> dict[str, Any]:
    batches = list(
        db.scalars(
            select(DeveloperIntakeBatch).order_by(DeveloperIntakeBatch.created_at.desc()).limit(30)
        )
    )
    batch_ids = [batch.id for batch in batches]
    records = list(
        db.scalars(
            select(DeveloperIntakeRecord)
            .where(DeveloperIntakeRecord.developer_intake_batch_id.in_(batch_ids))
            .order_by(DeveloperIntakeRecord.source_file, DeveloperIntakeRecord.record_key)
        )
    ) if batch_ids else []
    records_by_batch: dict[str, list[dict[str, Any]]] = {str(batch.id): [] for batch in batches}
    for record in records:
        records_by_batch[str(record.developer_intake_batch_id)].append(
            {
                "record_key": record.record_key,
                "source_file": record.source_file,
                "suggested_name": record.suggested_name,
                "suggested_layers": record.suggested_layers,
                "disposition": record.disposition,
                "confidence": float(record.confidence),
                "evidence": record.evidence,
                "masked_identifiers": record.masked_identifiers,
                "review_status": record.review_status,
                "review_note": record.review_note,
            }
        )
    return {
        "operator": operator.username,
        "asset_count": db.scalar(
            select(func.count()).select_from(Asset).where(Asset.archived_at.is_(None))
        ) or 0,
        "batches": [
            {
                "id": str(batch.id),
                "title": batch.title,
                "source_location": batch.source_location,
                "status": batch.status,
                "confidentiality": batch.confidentiality,
                "summary": batch.summary,
                "review_note": batch.review_note,
                "records": records_by_batch[str(batch.id)],
            }
            for batch in batches
        ],
    }


def _audit_view(db: Session, operator: User) -> None:
    db.add(
        AuditLog(
            actor_user_id=operator.id,
            action="developer.control_plane.view",
            object_type="developer_control_plane",
            after_data={"operator": operator.username},
        )
    )
    db.commit()


@router.get("/control-plane")
def get_control_plane(
    db: Session = Depends(get_db),
    operator: User = Depends(require_developer_supervisor),
) -> dict[str, Any]:
    """JSON control-plane view. It is not part of the normal workbench APIs."""
    payload = _control_plane_payload(db, operator)
    _audit_view(db, operator)
    return payload


@console_router.get(
    "/developer/control-plane",
    response_class=HTMLResponse,
    include_in_schema=False,
)
def developer_control_plane_page(
    db: Session = Depends(get_db),
    operator: User = Depends(require_developer_supervisor),
) -> HTMLResponse:
    """Standalone server-rendered developer view, intentionally outside the SPA."""
    payload = _control_plane_payload(db, operator)
    rows: list[str] = []
    for batch in payload["batches"]:
        records = batch["records"]
        state_counts = Counter(record["disposition"] for record in records)
        rows.append(
            "<section><h2>{title}</h2><p><b>状态：</b>{status}　<b>可见性：</b>{visibility}　"
            "<b>记录：</b>{count}　<b>处理：</b>{states}</p><p>{note}</p><table>"
            "<thead><tr><th>来源</th><th>候选对象</th><th>层级建议</th><th>处置</th>"
            "<th>证据</th><th>脱敏标识</th></tr></thead><tbody>{records}</tbody></table></section>".format(
                title=escape(batch["title"]),
                status=escape(batch["status"]),
                visibility=escape(batch["confidentiality"]),
                count=len(records),
                states=escape("；".join(f"{key} {value}" for key, value in state_counts.items())),
                note=escape(batch["review_note"] or "仅存脱敏证据；未写入正式资产库。"),
                records="".join(
                    "<tr><td>{source}</td><td>{name}</td><td>{layers}</td><td>{disposition}</td>"
                    "<td>{evidence}</td><td>{identifiers}</td></tr>".format(
                        source=escape(record["source_file"]),
                        name=escape(record["suggested_name"]),
                        layers=escape("、".join(record["suggested_layers"])),
                        disposition=escape(record["disposition"]),
                        evidence=escape("；".join(str(item) for item in record["evidence"])),
                        identifiers=escape("；".join(str(item) for item in record["masked_identifiers"])),
                    )
                    for record in records
                ),
            )
        )
    body = "".join(rows) or "<p>暂无开发者私有暂存批次。</p>"
    _audit_view(db, operator)
    return HTMLResponse(
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><title>开发者控制面</title>"
        "<style>body{max-width:1440px;margin:32px auto;padding:0 24px;font:14px/1.55 system-ui,sans-serif;color:#18212f}"
        "h1{margin-bottom:4px}section{margin:28px 0;padding:20px;border:1px solid #dbe3ef;border-radius:12px}"
        "table{width:100%;border-collapse:collapse}th,td{padding:10px;border-top:1px solid #e5eaf1;text-align:left;vertical-align:top}"
        "th{background:#f6f8fb}small{color:#667085}</style>"
        f"<h1>开发者控制面</h1><p>操作人：{escape(payload['operator'])}；正式资产：{payload['asset_count']} 项。"
        "所有访问均记录审计日志；本页不展示或保存密码、密钥、Cookie。</p>"
        f"{body}</html>"
    )
