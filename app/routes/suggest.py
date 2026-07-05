import json
import logging
import os

import anthropic
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.ai_suggest import MODEL, SUGGESTION_SCHEMA, build_request_params
from app.database import get_db
from app.models import AISuggestion, Bin, Item

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bin")
review_router = APIRouter()
templates = Jinja2Templates(directory="/app/app/templates")

NO_KEY_ERROR = "AI suggestions aren't configured yet (ANTHROPIC_API_KEY is not set)."
NO_PHOTOS_ERROR = "This bin has no photos to analyze — add a photo first."
API_ERROR = "Couldn't get suggestions right now — try again in a minute."


def pending_context(b):
    """Map a bin's stored AISuggestion rows to the template shape."""
    suggestions = [
        {"name": s.name, "quantity": s.quantity or 1, "notes": s.notes or ""}
        for s in b.ai_suggestions if s.kind == "item"
    ]
    summary = next(
        (s.notes for s in b.ai_suggestions if s.kind == "summary" and s.notes), ""
    )
    return suggestions, summary


def _suggest_error(request: Request, b: Bin, message: str, status_code: int = 200):
    return templates.TemplateResponse("partials/suggestions.html", {
        "request": request,
        "bin": b,
        "error": message,
    }, status_code=status_code)


@router.post("/{token}/suggest", response_class=HTMLResponse)
async def suggest_items(token: str, request: Request, db: Session = Depends(get_db)):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)

    if not os.getenv("ANTHROPIC_API_KEY"):
        return _suggest_error(request, b, NO_KEY_ERROR)

    params = build_request_params(b)
    if params is None:
        return _suggest_error(request, b, NO_PHOTOS_ERROR)

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(**params)
    except anthropic.APIError:
        logger.exception("Anthropic API error during suggest for bin %s", b.id)
        return _suggest_error(request, b, API_ERROR)

    if response.stop_reason == "refusal":
        return _suggest_error(request, b, API_ERROR)

    try:
        text = next(block.text for block in response.content if block.type == "text")
        result = json.loads(text)
    except (StopIteration, json.JSONDecodeError):
        logger.error("Unparseable suggest response for bin %s: %r", b.id, response.content)
        return _suggest_error(request, b, API_ERROR)

    return templates.TemplateResponse("partials/suggestions.html", {
        "request": request,
        "bin": b,
        "suggestions": result.get("items", []),
        "summary": (result.get("summary") or "").strip(),
    })


@router.post("/{token}/suggest/accept")
async def accept_suggestions(token: str, request: Request, db: Session = Depends(get_db)):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("Bin not found", status_code=404)

    form = await request.form()

    # Additive only: accepted suggestions become new Item rows; existing
    # items and notes are never modified or replaced.
    for idx in form.getlist("accept"):
        name = (form.get(f"item-{idx}-name") or "").strip()
        if not name:
            continue
        try:
            quantity = max(1, int(form.get(f"item-{idx}-qty") or 1))
        except ValueError:
            quantity = 1
        notes = (form.get(f"item-{idx}-notes") or "").strip() or None
        db.add(Item(bin_id=b.id, name=name, quantity=quantity, notes=notes))

    if form.get("append_summary"):
        summary = (form.get("summary") or "").strip()
        if summary:
            b.notes = f"{b.notes}\n\n{summary}" if b.notes else summary

    # The review is done for this bin either way — clear its pending queue.
    db.query(AISuggestion).filter(AISuggestion.bin_id == b.id).delete()
    db.commit()

    next_url = form.get("next") or f"/bin/{b.token}"
    if not next_url.startswith("/"):
        next_url = f"/bin/{b.token}"
    return RedirectResponse(next_url, status_code=303)


@router.post("/{token}/suggest/dismiss", response_class=HTMLResponse)
async def dismiss_suggestions(token: str, db: Session = Depends(get_db)):
    b = db.query(Bin).filter(Bin.token == token).first()
    if not b:
        return HTMLResponse("", status_code=404)
    db.query(AISuggestion).filter(AISuggestion.bin_id == b.id).delete()
    db.commit()
    return HTMLResponse("")


@review_router.get("/suggestions", response_class=HTMLResponse)
async def review_suggestions(request: Request, db: Session = Depends(get_db)):
    bins = (
        db.query(Bin)
        .join(AISuggestion, AISuggestion.bin_id == Bin.id)
        .distinct()
        .order_by(Bin.name)
        .all()
    )
    entries = []
    for b in bins:
        suggestions, summary = pending_context(b)
        entries.append({"bin": b, "suggestions": suggestions, "summary": summary})
    return templates.TemplateResponse("suggestions_review.html", {
        "request": request,
        "entries": entries,
    })
