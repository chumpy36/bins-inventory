from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models import Bin, Category, Location

router = APIRouter(prefix="/bin")
templates = Jinja2Templates(directory="/app/app/templates")


@router.get("/new", response_class=HTMLResponse)
async def new_bin_form(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.name).all()
    locations = db.query(Location).order_by(Location.name).all()
    return templates.TemplateResponse("bin_form.html", {
        "request": request,
        "categories": categories,
        "locations": locations,
        "bin": None,
    })


@router.post("/new")
async def create_bin(
    name: str = Form(...),
    category_id: Optional[int] = Form(None),
    location_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    b = Bin(
        name=name.strip(),
        category_id=category_id or None,
        location_id=location_id or None,
        notes=notes.strip() if notes else None,
    )
    db.add(b)
    db.commit()
    db.refresh(b)
    return RedirectResponse(f"/bin/{b.token}", status_code=303)


@router.get("/{token}", response_class=HTMLResponse)
async def bin_detail(token: str, request: Request, db: Session = Depends(get_db)):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)
    return templates.TemplateResponse("bin_detail.html", {
        "request": request,
        "bin": b,
    })


@router.get("/{token}/edit", response_class=HTMLResponse)
async def edit_bin_form(token: str, request: Request, db: Session = Depends(get_db)):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)
    categories = db.query(Category).order_by(Category.name).all()
    locations = db.query(Location).order_by(Location.name).all()
    return templates.TemplateResponse("bin_form.html", {
        "request": request,
        "bin": b,
        "categories": categories,
        "locations": locations,
    })


@router.post("/{token}/edit")
async def edit_bin(
    token: str,
    name: str = Form(...),
    category_id: Optional[int] = Form(None),
    location_id: Optional[int] = Form(None),
    notes: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)
    b.name = name.strip()
    b.category_id = category_id or None
    b.location_id = location_id or None
    if location_id:
        b.location = None  # clear legacy text once structured location is set
    b.notes = notes.strip() if notes else None
    db.commit()
    return RedirectResponse(f"/bin/{token}", status_code=303)


@router.post("/{token}/delete")
async def delete_bin(token: str, db: Session = Depends(get_db)):
    b = db.query(Bin).filter(Bin.token == token).first()
    if b:
        db.delete(b)
        db.commit()
    return RedirectResponse("/", status_code=303)


@router.get("/s/all", response_class=HTMLResponse)
async def all_bins(request: Request, db: Session = Depends(get_db)):
    from app.models import Bin as BinModel
    bins = db.query(BinModel).order_by(BinModel.name).all()
    return templates.TemplateResponse("bins_list.html", {
        "request": request,
        "bins": bins,
    })
