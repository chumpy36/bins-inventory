from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import Item, Bin

router = APIRouter(prefix="/item")
templates = Jinja2Templates(directory="/app/app/templates")


@router.post("/add/{token}")
async def add_item(
    token: str,
    name: str = Form(...),
    quantity: int = Form(1),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)
    item = Item(
        bin_id=b.id,
        name=name.strip(),
        quantity=quantity,
        notes=notes.strip() if notes else None,
    )
    db.add(item)
    db.commit()
    # Return just the updated items partial for HTMX
    db.refresh(b)
    return templates.TemplateResponse("partials/items_list.html", {
        "request": Request({"type": "http", "method": "GET", "headers": []}),
        "bin": b,
    })


@router.post("/{item_id}/delete")
async def delete_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return HTMLResponse("", status_code=404)
    bin_token = item.bin.token
    db.delete(item)
    db.commit()
    # Return empty string — HTMX will swap out the row
    return HTMLResponse("")


@router.get("/{item_id}/edit", response_class=HTMLResponse)
async def edit_item_form(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return HTMLResponse("Not found", status_code=404)
    return templates.TemplateResponse("partials/item_edit.html", {
        "request": request,
        "item": item,
    })


@router.get("/{item_id}/view", response_class=HTMLResponse)
async def view_item(item_id: int, request: Request, db: Session = Depends(get_db)):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return HTMLResponse("", status_code=404)
    return templates.TemplateResponse("partials/item_row.html", {
        "request": request,
        "item": item,
    })


@router.post("/{item_id}/edit")
async def edit_item(
    item_id: int,
    request: Request,
    name: str = Form(...),
    quantity: int = Form(1),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    item = db.query(Item).filter(Item.id == item_id).first()
    if not item:
        return HTMLResponse("Not found", status_code=404)
    item.name = name.strip()
    item.quantity = quantity
    item.notes = notes.strip() if notes else None
    db.commit()
    return templates.TemplateResponse("partials/item_row.html", {
        "request": request,
        "item": item,
    })
