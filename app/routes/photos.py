import os
import uuid
from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from PIL import Image
import io

from app.database import get_db
from app.models import Photo, Bin

router = APIRouter(prefix="/photo")
templates = Jinja2Templates(directory="/app/app/templates")

PHOTOS_DIR = os.getenv("PHOTOS_DIR", "/app/data/photos")
MAX_WIDTH = 1200
JPEG_QUALITY = 85


def resize_and_save(upload: bytes, filename: str):
    img = Image.open(io.BytesIO(upload))
    # Convert to RGB (handles PNG, HEIC, etc.)
    if img.mode != "RGB":
        img = img.convert("RGB")
    # Auto-rotate based on EXIF
    try:
        from PIL import ImageOps
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass
    # Resize if wider than MAX_WIDTH
    if img.width > MAX_WIDTH:
        ratio = MAX_WIDTH / img.width
        new_size = (MAX_WIDTH, int(img.height * ratio))
        img = img.resize(new_size, Image.LANCZOS)
    path = os.path.join(PHOTOS_DIR, filename)
    img.save(path, "JPEG", quality=JPEG_QUALITY, optimize=True)


@router.post("/upload/{token}")
async def upload_photo(
    token: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)

    contents = await file.read()
    filename = f"{uuid.uuid4().hex}.jpg"
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    resize_and_save(contents, filename)

    # Max sort order + 1
    max_order = max((p.sort_order for p in b.photos), default=-1)
    photo = Photo(bin_id=b.id, filename=filename, sort_order=max_order + 1)
    db.add(photo)
    db.commit()
    db.refresh(b)

    return templates.TemplateResponse("partials/photos_strip.html", {
        "request": request,
        "bin": b,
    })


@router.post("/{photo_id}/delete")
async def delete_photo(photo_id: int, request: Request, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        return HTMLResponse("", status_code=404)
    bin_ref = photo.bin
    filepath = os.path.join(PHOTOS_DIR, photo.filename)
    if os.path.exists(filepath):
        os.remove(filepath)
    db.delete(photo)
    db.commit()
    db.refresh(bin_ref)

    return templates.TemplateResponse("partials/photos_strip.html", {
        "request": request,
        "bin": bin_ref,
    })
