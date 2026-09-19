from pathlib import Path
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
import hashlib

router = APIRouter(prefix="/upload", tags=["upload"])
BASE = Path(__file__).resolve().parent.parent / "uploads" / "images"
BASE.mkdir(parents=True, exist_ok=True)

@router.post("/image")
def upload_image(file: UploadFile = File(...), image_id: str = Form(...), image_hash: str = Form("")):
    suffix = Path(file.filename or "img").suffix or ".jpg"
    target = BASE / f"{image_id}{suffix}"
    data = file.file.read()
    digest = hashlib.sha256(data).hexdigest()
    if image_hash and digest != image_hash:
        raise HTTPException(400, "图片校验失败")
    target.write_bytes(data)
    return {"image_path": str(target.relative_to(BASE.parent.parent)), "image_hash": digest}
