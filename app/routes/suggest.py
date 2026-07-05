import base64
import json
import logging
import os

import anthropic
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Bin, Item

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bin")
templates = Jinja2Templates(directory="/app/app/templates")

PHOTOS_DIR = os.getenv("PHOTOS_DIR", "/app/data/photos")
MODEL = "claude-opus-4-8"
MAX_PHOTOS = 8

NO_KEY_ERROR = "AI suggestions aren't configured yet (ANTHROPIC_API_KEY is not set)."
NO_PHOTOS_ERROR = "This bin has no photos to analyze — add a photo first."
API_ERROR = "Couldn't get suggestions right now — try again in a minute."

SUGGESTION_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "quantity": {"type": "integer"},
                    "notes": {"type": "string"},
                },
                "required": ["name", "quantity", "notes"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string"},
    },
    "required": ["items", "summary"],
    "additionalProperties": False,
}

PROMPT = """You are helping catalog the contents of a storage bin from photos. \
The person doing the cataloging often doesn't know what the objects are, so your \
job is to identify them.

Existing cataloged items in this bin (do NOT suggest duplicates of these):
{existing_items}

Existing bin notes (for context only):
{existing_notes}

Look at the photos and list the items you can see that are NOT already cataloged \
above. For each item:
- name: short and specific — include brand/model if readable in the photo
- quantity: how many you can count (1 if unsure)
- notes: one plain-English sentence saying what the thing is or what it's used \
for, written for someone who doesn't recognize it

Only include items you can actually see. If everything visible is already \
cataloged, return an empty items list. Also write "summary": 1-2 sentences \
describing the bin's overall contents."""


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

    image_blocks = []
    for photo in b.photos[:MAX_PHOTOS]:
        path = os.path.join(PHOTOS_DIR, photo.filename)
        try:
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")
        except OSError:
            logger.warning("Photo file missing for suggest: %s", path)
            continue
        image_blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
        })

    if not image_blocks:
        return _suggest_error(request, b, NO_PHOTOS_ERROR)

    existing = "\n".join(
        f"- {i.name} (x{i.quantity})" + (f": {i.notes}" if i.notes else "")
        for i in b.items
    ) or "(none)"
    prompt = PROMPT.format(existing_items=existing, existing_notes=b.notes or "(none)")

    client = anthropic.Anthropic()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            output_config={"format": {"type": "json_schema", "schema": SUGGESTION_SCHEMA}},
            messages=[{
                "role": "user",
                "content": image_blocks + [{"type": "text", "text": prompt}],
            }],
        )
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

    db.commit()
    return RedirectResponse(f"/bin/{b.token}", status_code=303)
