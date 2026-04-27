from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import Location, Bin, InventoryItem

router = APIRouter(prefix="/locations")
templates = Jinja2Templates(directory="/app/app/templates")

KIND_LABELS = {
    "room": "Room",
    "bin": "Bin",
    "shelf": "Shelf",
    "rack": "Rack",
    "case": "Case",
    "other": "Other",
}


def _location_usage(loc: Location) -> dict:
    return {
        "bin_count": len(loc.bins),
        "item_count": len(loc.inventory_items),
    }


@router.get("", response_class=HTMLResponse)
async def list_locations(request: Request, db: Session = Depends(get_db)):
    locations = db.query(Location).order_by(Location.name).all()
    return templates.TemplateResponse("locations.html", {
        "request": request,
        "locations": locations,
        "kind_labels": KIND_LABELS,
    })


@router.post("")
async def create_location(
    name: str = Form(...),
    kind: str = Form("other"),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    loc = Location(
        name=name.strip(),
        kind=kind,
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
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if loc:
        loc.name = name.strip()
        loc.kind = kind
        loc.notes = notes.strip() if notes else None
        db.commit()
    return RedirectResponse("/locations", status_code=303)


@router.post("/{loc_id}/delete")
async def delete_location(loc_id: int, db: Session = Depends(get_db)):
    loc = db.query(Location).filter(Location.id == loc_id).first()
    if loc:
        for b in loc.bins:
            b.location_id = None
        for item in loc.inventory_items:
            item.location_id = None
        db.delete(loc)
        db.commit()
    return RedirectResponse("/locations", status_code=303)
