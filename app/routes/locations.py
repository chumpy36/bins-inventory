import io
import base64
import os
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional
import qrcode

from app.database import get_db
from app.models import Location, Bin, InventoryItem

router = APIRouter(prefix="/locations")
templates = Jinja2Templates(directory="/app/app/templates")

BASE_URL = os.getenv("BASE_URL", "https://inventory.hollandit.work")

KIND_LABELS = {
    "room": "Room",
    "shelf": "Shelf",
    "rack": "Rack",
    "case": "Case",
    "other": "Other",
}


def _make_qr_b64(url: str) -> str:
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def _tree(locations):
    """Return (top_level_list, {parent_id: [children]}) sorted by name."""
    by_parent = {}
    top = []
    for loc in sorted(locations, key=lambda l: l.name):
        if loc.parent_id:
            by_parent.setdefault(loc.parent_id, []).append(loc)
        else:
            top.append(loc)
    return top, by_parent


@router.get("", response_class=HTMLResponse)
async def list_locations(request: Request, db: Session = Depends(get_db)):
    locations = db.query(Location).order_by(Location.name).all()
    top, by_parent = _tree(locations)
    return templates.TemplateResponse("locations.html", {
        "request": request,
        "locations": locations,
        "top_locations": top,
        "by_parent": by_parent,
        "kind_labels": KIND_LABELS,
    })


@router.get("/{loc_id}", response_class=HTMLResponse)
async def location_detail(loc_id: int, request: Request, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if not loc:
        return HTMLResponse("Location not found", status_code=404)
    url = f"{BASE_URL}/locations/{loc_id}"
    qr_b64 = _make_qr_b64(url)
    children = db.query(Location).filter(Location.parent_id == loc_id).order_by(Location.name).all()
    return templates.TemplateResponse("location_detail.html", {
        "request": request,
        "loc": loc,
        "children": children,
        "kind_labels": KIND_LABELS,
        "qr_b64": qr_b64,
        "url": url,
    })


@router.get("/{loc_id}/label", response_class=HTMLResponse)
async def location_label(loc_id: int, request: Request, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if not loc:
        return HTMLResponse("Location not found", status_code=404)
    url = f"{BASE_URL}/locations/{loc_id}"
    qr_b64 = _make_qr_b64(url)
    return templates.TemplateResponse("location_label.html", {
        "request": request,
        "loc": loc,
        "qr_b64": qr_b64,
    })


@router.post("")
async def create_location(
    name: str = Form(...),
    kind: str = Form("other"),
    parent_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    loc = Location(
        name=name.strip(),
        kind=kind,
        parent_id=parent_id or None,
        notes=notes.strip() if notes else None,
    )
    db.add(loc)
    db.commit()
    return RedirectResponse("/locations", status_code=303)


@router.post("/{loc_id}/edit")
async def edit_location(
    loc_id: int,
    name: str = Form(...),
    kind: str = Form("other"),
    parent_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if loc:
        loc.name = name.strip()
        loc.kind = kind
        loc.parent_id = parent_id or None
        loc.notes = notes.strip() if notes else None
        db.commit()
    return RedirectResponse("/locations", status_code=303)


@router.post("/{loc_id}/delete")
async def delete_location(loc_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if loc:
        # Reparent children to this location's parent
        for child in db.query(Location).filter(Location.parent_id == loc_id).all():
            child.parent_id = loc.parent_id
        for b in loc.bins:
            b.location_id = None
        for item in loc.inventory_items:
            item.location_id = None
        db.delete(loc)
        db.commit()
    return RedirectResponse("/locations", status_code=303)
