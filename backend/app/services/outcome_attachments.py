"""Validate inert outcome files and store content-addressed immutable attachments."""

import hashlib
import io
import warnings
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from PIL import Image, UnidentifiedImageError

from app.models import AssetAttachment

MAX_BYTES = 20 * 1024 * 1024
IMAGE_TYPES = {
    "PNG": ("image/png", ".png"),
    "JPEG": ("image/jpeg", ".jpg"),
    "WEBP": ("image/webp", ".webp"),
}


def validate_outcome(content: bytes, filename: str) -> tuple[str, str]:
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(422, "成果附件必须在20 MB以内")
    suffix = Path(filename).suffix.lower()
    if suffix == ".zip":
        from app.api.v1.asset_attachments import validate_zip

        validate_zip(content)
        return "application/zip", ".zip"
    if suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        raise HTTPException(422, "仅支持PNG、JPG、WebP截图或ZIP成果包")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                kind = image.format
                if kind not in IMAGE_TYPES or image.width * image.height > 40_000_000:
                    raise ValueError("image bounds")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("animated image")
                expected = {"PNG": {".png"}, "JPEG": {".jpg", ".jpeg"}, "WEBP": {".webp"}}
                if suffix not in expected[kind]:
                    raise ValueError("extension mismatch")
                image.verify()
            with Image.open(io.BytesIO(content)) as image:
                image.load()
    except (
        OSError,
        ValueError,
        UnidentifiedImageError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(422, "截图内容无效、格式不匹配或尺寸过大") from exc
    return IMAGE_TYPES[kind]


def store_outcome(db, asset, content: bytes, filename: str, storage: Path):
    content_type, suffix = validate_outcome(content, filename)
    digest = hashlib.sha256(content).hexdigest()
    identity = uuid5(NAMESPACE_URL, f"asset-attachment:{asset.id}:{digest}")
    existing = db.get(AssetAttachment, identity)
    if existing:
        if existing.archived_at:
            raise HTTPException(409, "相同附件已归档，请联系管理员")
        return existing, False
    storage.mkdir(parents=True, exist_ok=True)
    path = storage / f"{identity}{suffix}"
    path.write_bytes(content)
    name = Path(filename.replace(chr(92), "/")).name[:290]
    item = AssetAttachment(
        id=identity,
        asset_id=asset.id,
        file_name=name,
        file_path=path.name,
        content_type=content_type,
        size_bytes=len(content),
    )
    db.add(item)
    return item, True
