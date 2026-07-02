import os
import uuid
import logging
from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from PIL import Image
import io

from pillow_heif import register_heif_opener
register_heif_opener()

UPLOAD_ERROR = "Couldn't read that file as an image — try a JPEG, PNG, or HEIC photo."

MAX_UPLOAD_MB = 25
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
TOO_LARGE_ERROR = f"That file is too large — photos must be under {MAX_UPLOAD_MB}MB."


async def read_capped(file):
    """Read an UploadFile in chunks; return None if it exceeds MAX_UPLOAD_BYTES."""
    chunks = []
    total = 0
    while chunk := await file.read(1024 * 1024):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            return None
        chunks.append(chunk)
    return b"".join(chunks)

from app.database import get_db
from app.models import Photo, Bin, InventoryPhoto, InventoryItem

logger = logging.getLogger(__name__)

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

    contents = await read_capped(file)
    if contents is None:
        return templates.TemplateResponse("partials/photos_strip.html", {
            "request": request,
            "bin": b,
            "error": TOO_LARGE_ERROR,
        })
    filename = f"{uuid.uuid4().hex}.jpg"
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    try:
        resize_and_save(contents, filename)
    except Exception:
        return templates.TemplateResponse("partials/photos_strip.html", {
            "request": request,
            "bin": b,
            "error": UPLOAD_ERROR,
        })

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


@router.post("/upload/item/{token}")
async def upload_inventory_photo(
    token: str,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    item = db.query(InventoryItem).filter(InventoryItem.token == token).first()
    if not item:
        return HTMLResponse("Item not found", status_code=404)

    contents = await read_capped(file)
    if contents is None:
        return templates.TemplateResponse("partials/inventory_photos_strip.html", {
            "request": request,
            "item": item,
            "error": TOO_LARGE_ERROR,
        })
    filename = f"{uuid.uuid4().hex}.jpg"
    os.makedirs(PHOTOS_DIR, exist_ok=True)
    try:
        resize_and_save(contents, filename)
    except Exception:
        return templates.TemplateResponse("partials/inventory_photos_strip.html", {
            "request": request,
            "item": item,
            "error": UPLOAD_ERROR,
        })

    max_order = max((p.sort_order for p in item.photos), default=-1)
    photo = InventoryPhoto(inventory_item_id=item.id, filename=filename, sort_order=max_order + 1)
    db.add(photo)
    db.commit()
    db.refresh(item)

    return templates.TemplateResponse("partials/inventory_photos_strip.html", {
        "request": request,
        "item": item,
    })


@router.post("/item/{photo_id}/delete")
async def delete_inventory_photo(photo_id: int, request: Request, db: Session = Depends(get_db)):
    photo = db.query(InventoryPhoto).filter(InventoryPhoto.id == photo_id).first()
    if not photo:
        return HTMLResponse("", status_code=404)
    item_ref = photo.inventory_item
    filename = photo.filename
    db.delete(photo)
    db.commit()
    db.refresh(item_ref)

    # Remove the file only after the DB delete has committed. A leftover file
    # on unlink failure is a safer failure mode than a dangling DB row.
    filepath = os.path.join(PHOTOS_DIR, filename)
    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Failed to remove photo file %s after DB delete", filepath, exc_info=True)

    return templates.TemplateResponse("partials/inventory_photos_strip.html", {
        "request": request,
        "item": item_ref,
    })


@router.post("/{photo_id}/delete")
async def delete_photo(photo_id: int, request: Request, db: Session = Depends(get_db)):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        return HTMLResponse("", status_code=404)
    bin_ref = photo.bin
    filename = photo.filename
    db.delete(photo)
    db.commit()
    db.refresh(bin_ref)

    # Remove the file only after the DB delete has committed. A leftover file
    # on unlink failure is a safer failure mode than a dangling DB row.
    filepath = os.path.join(PHOTOS_DIR, filename)
    try:
        os.remove(filepath)
    except FileNotFoundError:
        pass
    except OSError:
        logger.warning("Failed to remove photo file %s after DB delete", filepath, exc_info=True)

    return templates.TemplateResponse("partials/photos_strip.html", {
        "request": request,
        "bin": bin_ref,
    })
