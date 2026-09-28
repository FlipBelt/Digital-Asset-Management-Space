"""Bounded ZIP storage, without extracting or executing uploaded content."""

import hashlib
import io
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Annotated
from uuid import NAMESPACE_URL, UUID, uuid5

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
        and asset.status == "draft"
    )
    if not access.has_permission("asset.write") or not (
        owns_draft or can_manage_asset(db, access, asset)
    ):
        raise HTTPException(403, "无权上传该资产附件")
    content = await file.read(MAX_BYTES + 1)
    await file.close()
    validate_zip(content)
    digest = hashlib.sha256(content).hexdigest()
    identity = uuid5(NAMESPACE_URL, f"asset-attachment:{asset_id}:{digest}")
    existing = db.get(AssetAttachment, identity)
    if existing is not None:
        if existing.archived_at is not None:
            raise HTTPException(409, "相同附件已归档，请联系管理员")
        return existing
    STORAGE.mkdir(parents=True, exist_ok=True)
    path = STORAGE / f"{identity}.zip"
    # Content-addressed file names never contain client-supplied path components.
    with path.open("wb") as target:
        target.write(content)
    name = Path((file.filename or "asset.zip").replace("\\", "/")).name[:290]
    item = AssetAttachment(
        id=identity,
        asset_id=asset_id,
        file_name=name,
        file_path=path.name,
        content_type="application/zip",
        size_bytes=len(content),
    )
    db.add(item)
    asset.version += 1
    asset.review_status = "pending_review"
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
        media_type="application/zip",
        headers={"X-Content-Type-Options": "nosniff"},
    )
