from __future__ import annotations

import hashlib
import os
import shutil
import time
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from database.database import get_db
from database.models import MediaObject

router = APIRouter(tags=["images"])
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "/app/uploads/wrong"))


def _safe_extension(filename: str | None) -> str:
    suffix = Path(filename or "").suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp", ".heic"} else ".jpg"


@router.post("/upload/image")
async def upload_image(file: UploadFile = File(...), image_id: str = "", image_hash: str = "", database: Session = Depends(get_db)) -> dict[str, str]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    temporary = UPLOAD_DIR / f".upload_{time.time_ns()}"
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as output:
            while content := await file.read(1024 * 1024):
                size += len(content)
                if size > 25 * 1024 * 1024:
                    raise HTTPException(status_code=413, detail="图片不能超过 25MB")
                digest.update(content)
                output.write(content)
        calculated_hash = digest.hexdigest()
        if image_hash and image_hash != calculated_hash:
            raise HTTPException(status_code=400, detail="图片 SHA-256 校验失败")
        relative_path = f"{calculated_hash}{_safe_extension(file.filename)}"
        final_file = UPLOAD_DIR / relative_path
        if final_file.exists():
            temporary.unlink(missing_ok=True)
        else:
            shutil.move(str(temporary), str(final_file))
        now = int(time.time() * 1000)
        media = database.query(MediaObject).filter(MediaObject.image_hash == calculated_hash).one_or_none()
        if media is None:
            database.add(MediaObject(
                id=f"media_{calculated_hash}", image_hash=calculated_hash, image_path=f"wrong/{relative_path}",
                file_size=size, created_at=now, updated_at=now, sync_status="SYNCED", deleted=False,
            ))
        else:
            media.updated_at = now
            media.deleted = False
        database.commit()
        return {"image_id": image_id, "image_hash": calculated_hash, "image_path": f"wrong/{relative_path}"}
    except HTTPException:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as error:
        temporary.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"图片保存失败：{error}") from error


@router.get("/images/wrong/{file_name}")
def get_image(file_name: str) -> FileResponse:
    safe_name = Path(file_name).name
    target = UPLOAD_DIR / safe_name
    if not target.is_file():
        raise HTTPException(status_code=404, detail="图片不存在")
    return FileResponse(target)
