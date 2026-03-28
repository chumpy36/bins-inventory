from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.database import get_db
from app.models import Bin, Item

router = APIRouter()
templates = Jinja2Templates(directory="/app/app/templates")


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: str = Query(default=""),
    db: Session = Depends(get_db),
):
    results = []
    if q.strip():
        term = f"%{q.strip()}%"
        # Find bins by name or location
        matching_bins = db.query(Bin).filter(
            or_(Bin.name.ilike(term), Bin.location.ilike(term), Bin.notes.ilike(term))
        ).all()
        # Find bins via matching items
        matching_items = db.query(Item).filter(
            or_(Item.name.ilike(term), Item.notes.ilike(term))
        ).all()
        # Deduplicate bins
        seen = set()
        for b in matching_bins:
            if b.id not in seen:
                results.append({"bin": b, "matched_items": []})
                seen.add(b.id)
        for item in matching_items:
            b = item.bin
            if b.id not in seen:
                results.append({"bin": b, "matched_items": [item]})
                seen.add(b.id)
            else:
                for r in results:
                    if r["bin"].id == b.id:
                        r["matched_items"].append(item)
                        break

    return templates.TemplateResponse("search.html", {
        "request": request,
        "q": q,
        "results": results,
    })
