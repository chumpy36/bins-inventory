import os
import uuid
import logging
import warnings
from fastapi import APIRouter, Depends, Request, UploadFile, File
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from PIL import Image
import io

from pillow_heif import register_heif_opener
register_heif_opener()

UPLOAD_ERROR = "Couldn't read that file as an image — try a JPEG, PNG, or HEIC photo."

MAX_UPLOAD_MB = 25
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
TOO_LARGE_ERROR = f"That file is too large — photos must be under {MAX_UPLOAD_MB}MB."

# A 40-megapixel ceiling is generous for phone photos while bounding decoded
# memory use (an RGB image alone needs about 120 MB before conversion overhead).
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_TOO_LARGE_ERROR = "That image is too large to process — photos must be 40 megapixels or smaller."


class ImageTooLargeError(ValueError):
    """Raised when image metadata or Pillow's safety checks exceed our limit."""


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

from app.templating import templates

router = APIRouter(prefix="/photo")

DEFAULT_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
PHOTOS_DIR = os.getenv("PHOTOS_DIR", os.path.join(os.getenv("DATA_DIR", DEFAULT_DATA_DIR), "photos"))
MAX_WIDTH = 1200
JPEG_QUALITY = 85


def move_photo(db: Session, photo, siblings, direction: str):
    """Move a photo one position and normalize its record's sort order."""
    if direction not in {"left", "right"}:
        return False

    ordered = sorted(siblings, key=lambda p: (p.sort_order, p.id))
    current = next((i for i, sibling in enumerate(ordered) if sibling.id == photo.id), None)
    if current is None:
        return False

    target = current - 1 if direction == "left" else current + 1
    if target < 0 or target >= len(ordered):
        return True

    ordered[current], ordered[target] = ordered[target], ordered[current]
    for sort_order, sibling in enumerate(ordered):
        sibling.sort_order = sort_order
    db.commit()
    return True


def resize_and_save(upload: bytes, filename: str):
    # Pillow opens lazily, so inspect dimensions before pixel decoding,
    # conversion, or resizing. Turn Pillow's own bomb warning into a rejection
    # too, including for formats with unusually large declared dimensions.
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            img = Image.open(io.BytesIO(upload))
    except Image.DecompressionBombWarning as exc:
        raise ImageTooLargeError from exc
    except Image.DecompressionBombError as exc:
        raise ImageTooLargeError from exc
    if img.width * img.height > MAX_IMAGE_PIXELS:
        raise ImageTooLargeError
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
    except ImageTooLargeError:
        return templates.TemplateResponse("partials/photos_strip.html", {
            "request": request,
            "bin": b,
            "error": IMAGE_TOO_LARGE_ERROR,
        })
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
    except ImageTooLargeError:
        return templates.TemplateResponse("partials/inventory_photos_strip.html", {
            "request": request,
            "item": item,
            "error": IMAGE_TOO_LARGE_ERROR,
        })
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


@router.post("/item/{photo_id}/move/{direction}")
async def move_inventory_photo(
    photo_id: int, direction: str, request: Request, db: Session = Depends(get_db)
):
    photo = db.query(InventoryPhoto).filter(InventoryPhoto.id == photo_id).first()
    if not photo:
        return HTMLResponse("", status_code=404)
    item_ref = photo.inventory_item
    siblings = (
        db.query(InventoryPhoto)
        .filter(InventoryPhoto.inventory_item_id == item_ref.id)
        .order_by(InventoryPhoto.sort_order, InventoryPhoto.id)
        .all()
    )
    if not move_photo(db, photo, siblings, direction):
        return HTMLResponse("Invalid direction", status_code=400)
    db.refresh(item_ref)
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


@router.post("/{photo_id}/move/{direction}")
async def move_bin_photo(
    photo_id: int, direction: str, request: Request, db: Session = Depends(get_db)
):
    photo = db.query(Photo).filter(Photo.id == photo_id).first()
    if not photo:
        return HTMLResponse("", status_code=404)
    bin_ref = photo.bin
    siblings = (
        db.query(Photo)
        .filter(Photo.bin_id == bin_ref.id)
        .order_by(Photo.sort_order, Photo.id)
        .all()
    )
    if not move_photo(db, photo, siblings, direction):
        return HTMLResponse("Invalid direction", status_code=400)
    db.refresh(bin_ref)
    return templates.TemplateResponse("partials/photos_strip.html", {
        "request": request,
        "bin": bin_ref,
    })
