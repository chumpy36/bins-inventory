"""Batch backfill: run every photo'd bin through AI item suggestion and stage
the results for human review (ai_suggestions table → /suggestions page).

Runs INSIDE the bins-inventory container (needs the DB, photos, and API key):

    docker exec bins-inventory python /app/backfill_suggest.py submit
    docker exec bins-inventory python /app/backfill_suggest.py status
    docker exec bins-inventory python /app/backfill_suggest.py collect
    docker exec bins-inventory python /app/backfill_suggest.py watch   # poll until done, then collect

Uses the Message Batches API (50% price). Bins that already have pending
suggestions are skipped on submit, so re-running after a partial review is
safe. Results only ever land in the staging table — live items/notes are
untouched until someone approves them in the UI.
"""
import json
import sys
import time

import anthropic

sys.path.insert(0, "/app")

from app.ai_suggest import build_request_params  # noqa: E402
from app.database import SessionLocal  # noqa: E402
from app.models import AISuggestion, Bin  # noqa: E402

STATE_FILE = "/app/data/backfill_batch_ids.json"
# Keep each batch comfortably under the API's 256MB request cap.
MAX_BATCH_BYTES = 150 * 1024 * 1024


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"batch_ids": []}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)


def submit():
    db = SessionLocal()
    client = anthropic.Anthropic()

    bins = db.query(Bin).order_by(Bin.id).all()
    pending_bin_ids = {r.bin_id for r in db.query(AISuggestion.bin_id).distinct()}

    requests, skipped_no_photos, skipped_pending = [], 0, 0
    for b in bins:
        if b.id in pending_bin_ids:
            skipped_pending += 1
            continue
        params = build_request_params(b)
        if params is None:
            skipped_no_photos += 1
            continue
        requests.append({"custom_id": f"bin-{b.token}", "params": params})

    print(f"{len(requests)} bins to analyze "
          f"({skipped_no_photos} without photos, {skipped_pending} already pending review)")
    if not requests:
        return

    # Chunk by payload size so no single batch exceeds the API cap.
    state = load_state()
    chunk, chunk_bytes = [], 0
    chunks = []
    for req in requests:
        req_bytes = len(json.dumps(req))
        if chunk and chunk_bytes + req_bytes > MAX_BATCH_BYTES:
            chunks.append(chunk)
            chunk, chunk_bytes = [], 0
        chunk.append(req)
        chunk_bytes += req_bytes
    if chunk:
        chunks.append(chunk)

    for c in chunks:
        batch = client.messages.batches.create(requests=c)
        state["batch_ids"].append(batch.id)
        print(f"Submitted batch {batch.id} with {len(c)} bins")
    save_state(state)


def status(quiet=False):
    client = anthropic.Anthropic()
    state = load_state()
    if not state["batch_ids"]:
        print("No batches submitted.")
        return []
    batches = []
    for bid in state["batch_ids"]:
        b = client.messages.batches.retrieve(bid)
        batches.append(b)
        if not quiet:
            c = b.request_counts
            print(f"{bid}: {b.processing_status} "
                  f"(ok={c.succeeded} err={c.errored} processing={c.processing})")
    return batches


def collect():
    client = anthropic.Anthropic()
    db = SessionLocal()
    state = load_state()
    if not state["batch_ids"]:
        print("No batches submitted.")
        return

    ingested = errored = empty = 0
    remaining_ids = []
    for bid in list(state["batch_ids"]):
        batch = client.messages.batches.retrieve(bid)
        if batch.processing_status != "ended":
            print(f"{bid}: still {batch.processing_status}, skipping")
            remaining_ids.append(bid)
            continue

        for result in client.messages.batches.results(bid):
            token = result.custom_id.removeprefix("bin-")
            if result.result.type != "succeeded":
                print(f"  {token}: {result.result.type}")
                errored += 1
                continue
            msg = result.result.message
            if msg.stop_reason == "refusal":
                errored += 1
                continue
            try:
                text = next(bl.text for bl in msg.content if bl.type == "text")
                data = json.loads(text)
            except (StopIteration, json.JSONDecodeError):
                print(f"  {token}: unparseable response")
                errored += 1
                continue

            b = db.query(Bin).filter(Bin.token == token).first()
            if not b:
                continue
            # Replace any stale pending rows for this bin, then stage fresh ones.
            db.query(AISuggestion).filter(AISuggestion.bin_id == b.id).delete()
            items = data.get("items") or []
            summary = (data.get("summary") or "").strip()
            for it in items:
                name = (it.get("name") or "").strip()
                if not name:
                    continue
                db.add(AISuggestion(
                    bin_id=b.id, kind="item", name=name,
                    quantity=max(1, int(it.get("quantity") or 1)),
                    notes=(it.get("notes") or "").strip() or None,
                ))
            if summary:
                db.add(AISuggestion(bin_id=b.id, kind="summary", notes=summary))
            db.commit()
            if items or summary:
                ingested += 1
            else:
                empty += 1

    state["batch_ids"] = remaining_ids
    save_state(state)
    print(f"Done: {ingested} bins staged for review, "
          f"{empty} had nothing new, {errored} errored")


def watch():
    while True:
        batches = status()
        if batches and all(b.processing_status == "ended" for b in batches):
            collect()
            return
        if not batches:
            return
        time.sleep(60)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    {"submit": submit, "status": status, "collect": collect, "watch": watch}[cmd]()
