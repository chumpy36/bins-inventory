from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import Category

router = APIRouter()
templates = Jinja2Templates(directory="/app/app/templates")


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.name).all()
    # Bins without a category
    from app.models import Bin
    uncategorized = db.query(Bin).filter(Bin.category_id == None).order_by(Bin.name).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "categories": categories,
        "uncategorized": uncategorized,
    })


@router.get("/categories", response_class=HTMLResponse)
async def list_categories(request: Request, db: Session = Depends(get_db)):
    categories = db.query(Category).order_by(Category.name).all()
    return templates.TemplateResponse("categories.html", {
        "request": request,
        "categories": categories,
    })


@router.post("/categories")
async def create_category(
    request: Request,
    name: str = Form(...),
    color: str = Form("#6366f1"),
    db: Session = Depends(get_db),
):
    cat = Category(name=name.strip(), color=color)
    db.add(cat)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        categories = db.query(Category).order_by(Category.name).all()
        return templates.TemplateResponse("categories.html", {
            "request": request,
            "categories": categories,
            "error": f'A category named "{name.strip()}" already exists.',
        }, status_code=422)
    return RedirectResponse("/categories", status_code=303)


@router.post("/categories/{cat_id}/delete")
async def delete_category(cat_id: int, db: Session = Depends(get_db)):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if cat:
        # Unlink bins first
        for b in cat.bins:
            b.category_id = None
        db.delete(cat)
        db.commit()
    return RedirectResponse("/categories", status_code=303)


@router.post("/categories/{cat_id}/edit")
async def edit_category(
    cat_id: int,
    name: str = Form(...),
    color: str = Form("#6366f1"),
    db: Session = Depends(get_db),
):
    cat = db.query(Category).filter(Category.id == cat_id).first()
    if cat:
        cat.name = name.strip()
        cat.color = color
        db.commit()
    return RedirectResponse("/categories", status_code=303)
