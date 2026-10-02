import io
import base64
import os
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from typing import Optional
import qrcode

from app.database import get_db
from app.models import Location, Bin, InventoryItem

from app.templating import templates

router = APIRouter(prefix="/locations")

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
    """Flatten all location levels for display, tolerating legacy bad links."""
    by_parent = {}
    for loc in sorted(locations, key=lambda l: l.name):
        if loc.parent_id is not None:
            by_parent.setdefault(loc.parent_id, []).append(loc)
    rows, visited = [], set()

    def visit(loc, depth):
        pending = [(loc, depth)]
        while pending:
            current, current_depth = pending.pop()
            if current.id in visited:
                continue
            visited.add(current.id)
            rows.append({"location": current, "depth": current_depth})
            pending.extend((child, current_depth + 1)
                           for child in reversed(by_parent.get(current.id, [])))

    location_ids = {loc.id for loc in locations}
    roots = [loc for loc in locations if loc.parent_id is None or loc.parent_id not in location_ids]
    for loc in sorted(roots, key=lambda l: l.name):
        visit(loc, 0)
    for loc in sorted(locations, key=lambda l: l.name):
        visit(loc, 0)
    return rows


def _descendant_ids(locations, loc_id):
    children = {}
    for location in locations:
        children.setdefault(location.parent_id, []).append(location.id)
    result, pending = set(), list(children.get(loc_id, []))
    while pending:
        child_id = pending.pop()
        if child_id in result or child_id == loc_id:
            continue
        result.add(child_id)
        pending.extend(children.get(child_id, []))
    return result


@router.get("", response_class=HTMLResponse)
async def list_locations(request: Request, db: Session = Depends(get_db)):
    locations = db.query(Location).order_by(Location.name).all()
    descendants = {loc.id: _descendant_ids(locations, loc.id) for loc in locations}
    return templates.TemplateResponse("locations.html", {
        "request": request,
        "locations": locations,
        "location_rows": _tree(locations),
        "descendant_ids": descendants,
        "kind_labels": KIND_LABELS,
    })


@router.get("/{loc_id}", response_class=HTMLResponse)
async def location_detail(loc_id: int, request: Request, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if not loc:
        return HTMLResponse("Location not found", status_code=404)
    ancestors, parent = [], loc.parent
    seen = {loc.id}
    while parent and parent.id not in seen:
        ancestors.append(parent)
        seen.add(parent.id)
        parent = parent.parent
    url = f"{BASE_URL}/locations/{loc_id}"
    qr_b64 = _make_qr_b64(url)
    children = db.query(Location).filter(Location.parent_id == loc_id).order_by(Location.name).all()
    return templates.TemplateResponse("location_detail.html", {
        "request": request,
        "loc": loc,
        "ancestors": list(reversed(ancestors)),
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
    if loc.parent_id and not db.query(Location).filter(Location.id == loc.parent_id).first():
        return HTMLResponse("Parent location not found", status_code=404)
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
        parent_id = parent_id or None
        locations = db.query(Location).all()
        if parent_id and (parent_id == loc_id or parent_id in _descendant_ids(locations, loc_id)):
            return HTMLResponse("A location cannot be moved beneath itself or one of its descendants.", status_code=422)
        if parent_id and not any(location.id == parent_id for location in locations):
            return HTMLResponse("Parent location not found", status_code=404)
        loc.name = name.strip()
        loc.kind = kind
        loc.parent_id = parent_id
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
