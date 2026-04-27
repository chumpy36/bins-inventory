from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import Bin, Item, InventoryItem, ItemAttribute

router = APIRouter()
templates = Jinja2Templates(directory="/app/app/templates")


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query(default=""),
    db: Session = Depends(get_db),
):
    bin_results = []
    gear_results = []

    if q.strip():
        term = f"%{q.strip()}%"

        # --- Bins ---
        matching_bins = db.query(Bin).filter(
            or_(Bin.name.ilike(term), Bin.location.ilike(term), Bin.notes.ilike(term))
        ).all()
        matching_items = db.query(Item).filter(
            or_(Item.name.ilike(term), Item.notes.ilike(term))
        ).all()

        seen = set()
        for b in matching_bins:
            if b.id not in seen:
                bin_results.append({"bin": b, "matched_items": []})
                seen.add(b.id)
        for item in matching_items:
            b = item.bin
            if b.id not in seen:
                bin_results.append({"bin": b, "matched_items": [item]})
                seen.add(b.id)
            else:
                for r in bin_results:
                    if r["bin"].id == b.id:
                        r["matched_items"].append(item)
                        break

        # --- Gear ---
        # Match on common fields
        gear_by_field = db.query(InventoryItem).filter(
            or_(
                InventoryItem.name.ilike(term),
                InventoryItem.brand.ilike(term),
                InventoryItem.model.ilike(term),
                InventoryItem.serial_number.ilike(term),
                InventoryItem.color.ilike(term),
                InventoryItem.notes.ilike(term),
                InventoryItem.story.ilike(term),
                InventoryItem.acquired_from.ilike(term),
            )
        ).all()

        # Match on EAV attributes
        matching_attrs = db.query(ItemAttribute).filter(
            ItemAttribute.value.ilike(term)
        ).all()

        seen_gear = set()
        for g in gear_by_field:
            if g.id not in seen_gear:
                gear_results.append({"item": g, "matched_attrs": []})
                seen_gear.add(g.id)
        for attr in matching_attrs:
            g = attr.inventory_item
            if g.id not in seen_gear:
                gear_results.append({"item": g, "matched_attrs": [attr]})
                seen_gear.add(g.id)
            else:
                for r in gear_results:
                    if r["item"].id == g.id:
                        r["matched_attrs"].append(attr)
                        break

    total = len(bin_results) + len(gear_results)

    return templates.TemplateResponse("search.html", {
        "request": request,
        "q": q,
        "bin_results": bin_results,
        "gear_results": gear_results,
        "total": total,
    })
