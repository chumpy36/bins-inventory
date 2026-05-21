import io
import os
from fastapi import APIRouter, Depends, Query, Request, Response
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
async def qr_label(token: str, request: Request, db: Session = Depends(get_db), skip: int = Query(default=0, ge=0, le=9), count: int = Query(default=1, ge=1, le=10)):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)
    url = f"{BASE_URL}/bin/{b.token}"
    qr_b64 = make_qr_png_b64(url)
    slots = []
    for i in range(count):
        n = skip + i
        row = n // 2
        col = n % 2
        top = 0.5 + row * 2          # inches, 0.5in top margin (Avery 8163 spec) + 2in per row
        left = col * 4.125 + 0.157  # inches, 4mm left offset + 4.125in per col
        slots.append({"top": top, "left": left})
    return templates.TemplateResponse("qr_label.html", {
        "request": request,
        "bin": b,
        "qr_b64": qr_b64,
        "url": url,
        "skip": skip,
        "count": count,
        "slots": slots,
    })


@router.get("/sheet/all", response_class=HTMLResponse)
async def qr_sheet(
    request: Request,
    db: Session = Depends(get_db),
    bins: list[str] | None = Query(default=None),
):
    if bins:
        rows = db.query(Bin).filter(Bin.token.in_(bins)).all()
        # Preserve the order of the `bins=` parameter so callers can control
        # print sequence (e.g. created-at order). SQL IN() loses ordering.
        order_map = {tok: i for i, tok in enumerate(bins)}
        rows.sort(key=lambda b: order_map.get(b.token, len(bins)))
    else:
        rows = db.query(Bin).order_by(Bin.name).all()

    # Avery 8163: 2 cols × 5 rows = 10 labels per sheet.
    # Slot formula matches the single-bin label route above.
    pages = []
    for chunk_start in range(0, len(rows), 10):
        chunk = rows[chunk_start:chunk_start + 10]
        labels = []
        for j, b in enumerate(chunk):
            row = j // 2
            col = j % 2
            top = 0.5 + row * 2
            left = col * 4.125 + 0.157
            url = f"{BASE_URL}/bin/{b.token}"
            qr_b64 = make_qr_png_b64(url)
            labels.append({
                "bin": b,
                "qr_b64": qr_b64,
                "top": top,
                "left": left,
            })
        pages.append(labels)

    return templates.TemplateResponse("qr_sheet.html", {
        "request": request,
        "pages": pages,
    })
