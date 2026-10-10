"""Bounded ZIP storage, without extracting or executing uploaded content."""

import hashlib
import io
import stat
import zipfile
from pathlib import PurePosixPath
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.access import (
    AccessContext,
    can_manage_asset,
    get_access_context,
    require_asset_visible,
)
from app.core.auth import require_csrf
from app.core.config import BACKEND_DIR
from app.db.session import get_db
from app.models import Asset, AssetAttachment, AuditLog
from app.services.asset_confirmation import lock_asset

router = APIRouter(tags=["asset-attachments"])
STORAGE = BACKEND_DIR / ".local" / "asset-attachments"
MAX_BYTES = 20 * 1024 * 1024


class AttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    asset_id: UUID
    file_name: str
    size_bytes: int
    content_type: str


def validate_zip(content: bytes) -> None:
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(422, "ZIP 文件必须在 20 MB 以内")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            if (
                not entries
                or len(entries) > 2000
                or sum(e.file_size for e in entries) > 100 * 1024 * 1024
            ):
                raise HTTPException(422, "ZIP 内容数量或展开大小超出限制")
            for entry in entries:
                path = PurePosixPath(entry.filename.replace("\\", "/"))
                if path.is_absolute() or ".." in path.parts or ":" in entry.filename:
                    raise HTTPException(422, "ZIP 包含不安全路径")
                if stat.S_ISLNK(entry.external_attr >> 16) or entry.flag_bits & 1:
                    raise HTTPException(422, "ZIP 不支持符号链接或加密内容")
    except (zipfile.BadZipFile, ValueError) as exc:
        raise HTTPException(422, "文件不是有效 ZIP") from exc


def visible_asset(db, access, asset_id):
    asset = db.get(Asset, asset_id)
    if asset is None or asset.archived_at is not None:
        raise HTTPException(404, "资产不存在")
    require_asset_visible(db, access, asset)
    return asset


@router.get("/assets/{asset_id}/attachments", response_model=list[AttachmentRead])
def list_attachments(
    asset_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    visible_asset(db, access, asset_id)
    return list(
        db.scalars(
            select(AssetAttachment).where(
                AssetAttachment.asset_id == asset_id, AssetAttachment.archived_at.is_(None)
            )
        )
    )


@router.post(
    "/assets/{asset_id}/attachments",
    response_model=AttachmentRead,
    dependencies=[Depends(require_csrf)],
)
async def upload_attachment(
    asset_id: UUID,
    file: Annotated[UploadFile, File()],
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    asset = visible_asset(db, access, asset_id)
    asset = lock_asset(db, asset_id)
    if asset is None or asset.archived_at is not None:
        raise HTTPException(404, "资产不存在")
    owns_draft = (
        access.person_id is not None
        and asset.created_by_person_id == access.person_id
        and asset.status in {"draft", "active"}
    )
    if not access.has_permission("asset.write") or not (
        owns_draft or can_manage_asset(db, access, asset)
    ):
        raise HTTPException(403, "无权上传该资产附件")
    content = await file.read(MAX_BYTES + 1)
    await file.close()
    from app.services.outcome_attachments import store_outcome

    item, created = store_outcome(db, asset, content, file.filename or "asset.zip", STORAGE)
    if not created:
        return item
    identity = item.id
    digest = hashlib.sha256(content).hexdigest()
    from app.services.registrar_details import invalidate

    if asset.created_by_person_id == access.person_id:
        invalidate(asset)
    else:
        asset.version += 1
        asset.review_status = (
            "not_required" if asset.is_personal_subscription else "pending_review"
        )
        asset.confirmed_at = None
        asset.confirmed_by_person_id = None
    db.add(
        AuditLog(
            actor_user_id=access.user.id,
            action="asset.attachment.create",
            object_type="asset",
            object_id=asset_id,
            request_id=str(identity),
            after_data={"attachment_id": str(identity), "sha256": digest},
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "上传冲突，请重试同一文件") from exc
    db.refresh(item)
    return item


@router.get("/assets/{asset_id}/attachments/{attachment_id}/download")
def download_attachment(
    asset_id: UUID,
    attachment_id: UUID,
    db: Session = Depends(get_db),
    access: AccessContext = Depends(get_access_context),
):
    visible_asset(db, access, asset_id)
    item = db.get(AssetAttachment, attachment_id)
    if item is None or item.asset_id != asset_id or item.archived_at is not None:
        raise HTTPException(404, "附件不存在")
    path = (STORAGE / item.file_path).resolve()
    if path.parent != STORAGE.resolve() or not path.is_file():
        raise HTTPException(404, "附件文件不可用")
    return FileResponse(
        path,
        filename=item.file_name,
        media_type=item.content_type,
        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-store"},
    )
