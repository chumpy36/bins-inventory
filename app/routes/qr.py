import io
import os
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import qrcode
import qrcode.image.svg
import base64

from app.database import get_db
from app.models import Bin

router = APIRouter(prefix="/qr")
templates = Jinja2Templates(directory="/app/app/templates")

BASE_URL = os.getenv("BASE_URL", "https://bins.hollandit.work")


def make_qr_png_b64(url: str) -> str:
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


@router.get("/{token}", response_class=HTMLResponse)
async def qr_label(token: str, request: Request, db: Session = Depends(get_db)):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)
    url = f"{BASE_URL}/bin/{b.token}"
    qr_b64 = make_qr_png_b64(url)
    return templates.TemplateResponse("qr_label.html", {
        "request": request,
        "bin": b,
        "qr_b64": qr_b64,
        "url": url,
    })


@router.get("/sheet/all", response_class=HTMLResponse)
async def qr_sheet(request: Request, db: Session = Depends(get_db)):
    bins = db.query(Bin).order_by(Bin.name).all()
    items = []
    for b in bins:
        url = f"{BASE_URL}/bin/{b.token}"
        qr_b64 = make_qr_png_b64(url)
        items.append({"bin": b, "qr_b64": qr_b64})
    return templates.TemplateResponse("qr_sheet.html", {
        "request": request,
        "items": items,
    })
