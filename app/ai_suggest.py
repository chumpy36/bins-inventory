"""Shared pieces for AI item suggestions — used by the live suggest route
and the batch backfill script so both send the identical request."""
import base64
import logging
import os

logger = logging.getLogger(__name__)

PHOTOS_DIR = os.getenv("PHOTOS_DIR", "/app/data/photos")
MODEL = "claude-opus-4-8"
MAX_PHOTOS = 8

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


def build_prompt(b):
    existing = "\n".join(
        f"- {i.name} (x{i.quantity})" + (f": {i.notes}" if i.notes else "")
        for i in b.items
    ) or "(none)"
    return PROMPT.format(existing_items=existing, existing_notes=b.notes or "(none)")


def build_image_blocks(b):
    """Base64 image blocks for a bin's photos. Missing files are skipped."""
    blocks = []
    for photo in b.photos[:MAX_PHOTOS]:
        path = os.path.join(PHOTOS_DIR, photo.filename)
        try:
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")
        except OSError:
            logger.warning("Photo file missing: %s", path)
            continue
        blocks.append({
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
        })
    return blocks


def build_request_params(b):
    """Full Messages API params for one bin, or None if no readable photos."""
    image_blocks = build_image_blocks(b)
    if not image_blocks:
        return None
    return {
        "model": MODEL,
        "max_tokens": 16000,
        "thinking": {"type": "adaptive"},
        "output_config": {"format": {"type": "json_schema", "schema": SUGGESTION_SCHEMA}},
        "messages": [{
            "role": "user",
            "content": image_blocks + [{"type": "text", "text": build_prompt(b)}],
        }],
    }
