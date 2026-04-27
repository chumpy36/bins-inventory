import io
import base64
import json
import os
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import qrcode

from app.database import get_db
from app.models import (
    InventoryItem, ItemType, AttributeDefinition,
    ItemAttribute, Location, Category,
)

router = APIRouter(prefix="/inventory")
templates = Jinja2Templates(directory="/app/app/templates")

PHOTOS_DIR = os.getenv("PHOTOS_DIR", "/app/data/photos")

CONDITIONS = ["Mint", "Excellent", "Good", "Fair", "Poor"]


def _sections(attr_defs):
    """Group attr defs by section, preserving sort order."""
    out = {}
    for a in attr_defs:
        s = a.section or "Other"
        out.setdefault(s, []).append(a)
    return out


def _attr_options(sections):
    """Return {attr_def_id: [str, ...]} for select and datalist attrs."""
    opts = {}
    for attrs in sections.values():
        for a in attrs:
            if a.field_type in ("select", "datalist") and a.options:
                try:
                    opts[a.id] = json.loads(a.options)
                except Exception:
                    opts[a.id] = []
    return opts


def _load_form_context(item_type, db):
    attr_defs = (
        db.query(AttributeDefinition)
        .filter(AttributeDefinition.item_type_id == item_type.id)
        .order_by(AttributeDefinition.sort_order)
        .all()
    )
    sections = _sections(attr_defs)
    return {
        "sections": sections,
        "attr_options": _attr_options(sections),
        "locations": db.query(Location).order_by(Location.name).all(),
        "categories": db.query(Category).order_by(Category.name).all(),
        "conditions": CONDITIONS,
    }


async def _parse_form(request: Request, item_type_id: int, db: Session):
    form = await request.form()

    def g(key):
        v = form.get(key, "")
        return v.strip() if isinstance(v, str) else ""

    def maybe_int(key):
        v = g(key)
        return int(v) if v.lstrip("-").isdigit() else None

    def maybe_float(key):
        v = g(key)
        try:
            return float(v) if v else None
        except ValueError:
            return None

    common = dict(
        name=g("name"),
        brand=g("brand") or None,
        model=g("model") or None,
        year_produced=maybe_int("year_produced"),
        color=g("color") or None,
        condition=g("condition") or None,
        serial_number=g("serial_number") or None,
        country_of_manufacture=g("country_of_manufacture") or None,
        date_acquired=g("date_acquired") or None,
        acquired_from=g("acquired_from") or None,
        amount_paid=maybe_float("amount_paid"),
        current_value=maybe_float("current_value"),
        sold=1 if form.get("sold") else 0,
        sale_price=maybe_float("sale_price"),
        date_sold=g("date_sold") or None,
        rating=maybe_int("rating"),
        story=g("story") or None,
        notes=g("notes") or None,
        category_id=maybe_int("category_id"),
        location_id=maybe_int("location_id"),
    )

    attr_defs = db.query(AttributeDefinition).filter(
        AttributeDefinition.item_type_id == item_type_id
    ).all()

    attrs = []
    for attr_def in attr_defs:
        raw = form.get(f"attr_{attr_def.key}", "")
        if attr_def.field_type == "boolean":
            value = "true" if raw else None
        else:
            value = raw.strip() if isinstance(raw, str) else ""
            value = value or None
        if value:
            attrs.append((attr_def.id, value))

    return common, attrs


# ── List ─────────────────────────────────────────────────────────────────────

@router.get("", response_class=HTMLResponse)
async def inventory_list(request: Request, db: Session = Depends(get_db)):
    item_types = db.query(ItemType).order_by(ItemType.sort_order).all()
    type_filter = request.query_params.get("type")
    query = db.query(InventoryItem).filter(InventoryItem.sold == 0)
    if type_filter:
        query = query.join(ItemType).filter(ItemType.slug == type_filter)
    items = query.order_by(InventoryItem.brand, InventoryItem.name).all()
    total_value = sum(i.current_value or 0 for i in items)
    return templates.TemplateResponse("inventory_list.html", {
        "request": request,
        "items": items,
        "item_types": item_types,
        "type_filter": type_filter,
        "total_value": total_value,
    })


# ── Financials ────────────────────────────────────────────────────────────────

@router.get("/financials", response_class=HTMLResponse)
async def financials(request: Request, db: Session = Depends(get_db)):
    all_items = db.query(InventoryItem).order_by(InventoryItem.name).all()

    active = [i for i in all_items if not i.sold]
    sold = [i for i in all_items if i.sold]

    active_value = sum(i.current_value or 0 for i in active)
    active_paid = sum(i.amount_paid or 0 for i in active)
    sold_proceeds = sum(i.sale_price or 0 for i in sold)
    sold_paid = sum(i.amount_paid or 0 for i in sold)

    active_sorted = sorted(active, key=lambda i: i.current_value or 0, reverse=True)
    sold_sorted = sorted(sold, key=lambda i: i.date_sold or "", reverse=True)

    return templates.TemplateResponse("inventory_financials.html", {
        "request": request,
        "active": active_sorted,
        "sold": sold_sorted,
        "active_value": active_value,
        "active_paid": active_paid,
        "unrealized_gain": active_value - active_paid,
        "sold_proceeds": sold_proceeds,
        "sold_paid": sold_paid,
        "realized_gain": sold_proceeds - sold_paid,
    })


# ── New ───────────────────────────────────────────────────────────────────────

@router.get("/new", response_class=HTMLResponse)
async def new_item_picker(request: Request, db: Session = Depends(get_db)):
    item_types = db.query(ItemType).order_by(ItemType.sort_order).all()
    return templates.TemplateResponse("inventory_new_type.html", {
        "request": request,
        "item_types": item_types,
    })


@router.get("/new/{type_slug}", response_class=HTMLResponse)
async def new_item_form(type_slug: str, request: Request, db: Session = Depends(get_db)):
    item_type = db.query(ItemType).filter(ItemType.slug == type_slug).first()
    if not item_type:
        return HTMLResponse("Item type not found", status_code=404)
    ctx = _load_form_context(item_type, db)
    return templates.TemplateResponse("inventory_form.html", {
        "request": request,
        "item_type": item_type,
        "item": None,
        "attr_values": {},
        **ctx,
    })


@router.post("/new/{type_slug}")
async def create_item(type_slug: str, request: Request, db: Session = Depends(get_db)):
    item_type = db.query(ItemType).filter(ItemType.slug == type_slug).first()
    if not item_type:
        return HTMLResponse("Item type not found", status_code=404)

    common, attrs = await _parse_form(request, item_type.id, db)
    item = InventoryItem(item_type_id=item_type.id, **common)
    db.add(item)
    db.flush()

    for attr_def_id, value in attrs:
        db.add(ItemAttribute(inventory_item_id=item.id, attribute_def_id=attr_def_id, value=value))

    db.commit()
    return RedirectResponse(f"/inventory/{item.token}", status_code=303)


# ── QR Label ──────────────────────────────────────────────────────────────────

BASE_URL = os.getenv("BASE_URL", "https://inventory.hollandit.work")


def _make_qr_b64(url: str) -> str:
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@router.get("/{token}/label", response_class=HTMLResponse)
async def item_label(
    token: str, request: Request, db: Session = Depends(get_db),
    skip: int = Query(default=0, ge=0, le=9),
    count: int = Query(default=1, ge=1, le=10),
):
    item = db.query(InventoryItem).filter(InventoryItem.token == token).first()
    if not item:
        return HTMLResponse("Item not found", status_code=404)
    url = f"{BASE_URL}/inventory/{item.token}"
    qr_b64 = _make_qr_b64(url)
    slots = []
    for i in range(count):
        n = skip + i
        row = n // 2
        col = n % 2
        top = 0.5 + row * 2
        left = col * 4.125 + 0.157
        slots.append({"top": top, "left": left})
    return templates.TemplateResponse("inventory_label.html", {
        "request": request,
        "item": item,
        "qr_b64": qr_b64,
        "slots": slots,
    })


# ── Detail ────────────────────────────────────────────────────────────────────

@router.get("/{token}", response_class=HTMLResponse)
async def item_detail(token: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.token == token).first()
    if not item:
        return HTMLResponse("Item not found", status_code=404)
    attr_defs = (
        db.query(AttributeDefinition)
        .filter(AttributeDefinition.item_type_id == item.item_type_id)
        .order_by(AttributeDefinition.sort_order)
        .all()
    )
    sections = _sections(attr_defs)
    attr_map = {a.attribute_def_id: a.value for a in item.attributes}
    return templates.TemplateResponse("inventory_detail.html", {
        "request": request,
        "item": item,
        "sections": sections,
        "attr_map": attr_map,
    })


# ── Edit ──────────────────────────────────────────────────────────────────────

@router.get("/{token}/edit", response_class=HTMLResponse)
async def edit_item_form(token: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.token == token).first()
    if not item:
        return HTMLResponse("Item not found", status_code=404)
    ctx = _load_form_context(item.item_type, db)
    attr_values = {a.attribute_def_id: a.value for a in item.attributes}
    return templates.TemplateResponse("inventory_form.html", {
        "request": request,
        "item_type": item.item_type,
        "item": item,
        "attr_values": attr_values,
        **ctx,
    })


@router.post("/{token}/edit")
async def edit_item(token: str, request: Request, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.token == token).first()
    if not item:
        return HTMLResponse("Item not found", status_code=404)

    common, attrs = await _parse_form(request, item.item_type_id, db)
    for k, v in common.items():
        setattr(item, k, v)

    for a in list(item.attributes):
        db.delete(a)
    db.flush()

    for attr_def_id, value in attrs:
        db.add(ItemAttribute(inventory_item_id=item.id, attribute_def_id=attr_def_id, value=value))

    db.commit()
    return RedirectResponse(f"/inventory/{item.token}", status_code=303)


# ── Delete ────────────────────────────────────────────────────────────────────

@router.post("/{token}/delete")
async def delete_item(token: str, db: Session = Depends(get_db)):
    item = db.query(InventoryItem).filter(InventoryItem.token == token).first()
    if item:
        for photo in item.photos:
            filepath = os.path.join(PHOTOS_DIR, photo.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        db.delete(item)
        db.commit()
    return RedirectResponse("/inventory", status_code=303)
