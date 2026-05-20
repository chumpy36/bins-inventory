#!/usr/bin/env python3
"""
Extract photos from AllMyGuitars app and import into bins-inventory.

Runs on Mac via the bins-inventory venv (needs Pillow).
Transfers photos to NAS in one tar pipe, then inserts DB records.

Usage:
  .venv/bin/python import_amg_photos.py
"""

import io
import os
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageOps

AMG_DB = Path.home() / "Library/Containers/com.QuarkSolutions.AllMyGuitars/Data/Library/Application Support/AllMyGuitars/DataModel.sqlite"
AMG_EXT = Path.home() / "Library/Containers/com.QuarkSolutions.AllMyGuitars/Data/Library/Application Support/AllMyGuitars/.DataModel_SUPPORT/_EXTERNAL_DATA"
NAS_DB = "/volume1/docker/bins-inventory/data/bins.db"
NAS_PHOTOS = "/volume1/docker/bins-inventory/data/photos"
MAX_DIM = 1600
JPEG_QUALITY = 85


def decode_blob_uuid(blob):
    """Core Data external storage ref: 0x02 + ASCII UUID + 0x00."""
    if not blob or len(blob) < 3 or blob[0] != 0x02:
        return None
    return blob[1:].rstrip(b'\x00').decode('ascii')


def resize_jpeg(src_path):
    """Return resized JPEG bytes, max MAX_DIM on longest side."""
    img = ImageOps.exif_transpose(Image.open(src_path))
    img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return buf.getvalue()


def ssh(cmd, stdin_data=None):
    result = subprocess.run(
        ['ssh', 'nas', cmd],
        input=stdin_data, capture_output=True
    )
    return result.returncode, result.stdout, result.stderr


def normalize(s):
    """Normalize typographic apostrophes to straight for name matching."""
    return s.replace('’', "'").replace('‘', "'")


def get_inventory_items():
    """Return normalized_name → id map for all guitars in bins-inventory."""
    code, out, _ = ssh(
        f"sqlite3 {NAS_DB} \"SELECT name, id FROM inventory_items WHERE item_type_id IN "
        f"(SELECT id FROM item_types WHERE slug='guitar');\""
    )
    items = {}
    for line in out.decode().strip().split('\n'):
        if '|' in line:
            name, item_id = line.rsplit('|', 1)
            items[normalize(name)] = int(item_id)
    return items


def get_existing_photo_item_ids():
    """Return set of inventory_item_ids that already have photos."""
    code, out, _ = ssh(
        f"sqlite3 {NAS_DB} \"SELECT DISTINCT inventory_item_id FROM inventory_photos;\""
    )
    return {int(x) for x in out.decode().strip().split('\n') if x.strip()}


def main():
    if not AMG_DB.exists():
        print("ERROR: AllMyGuitars database not found.")
        sys.exit(1)

    print("Reading AllMyGuitars database...")
    amg = sqlite3.connect(AMG_DB)
    cur = amg.cursor()
    cur.execute("""
        SELECT ZNAME, ZPIC1, ZPIC2, ZPIC3, ZPIC4, ZPIC5, ZPIC6, ZPIC7, ZPIC8, ZPIC9
        FROM ZITEM WHERE ZPIC1 IS NOT NULL
    """)
    rows = cur.fetchall()
    amg.close()
    print(f"Found {len(rows)} guitars with photos in AllMyGuitars.")

    print("Fetching inventory items from NAS...")
    inv_items = get_inventory_items()
    print(f"Found {len(inv_items)} guitars in inventory.")

    existing_ids = get_existing_photo_item_ids()

    # Phase 1: resize + stage photos in a temp dir
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # List of (item_id, filename, sort_order) for DB inserts
        db_records = []
        staged = 0
        skipped = 0
        not_found = []

        for row in rows:
            name = row[0]
            blobs = row[1:]

            if normalize(name) not in inv_items:
                not_found.append(name)
                continue

            item_id = inv_items[normalize(name)]

            if item_id in existing_ids:
                print(f"  SKIP (photos exist): {name}")
                skipped += 1
                continue

            print(f"  Staging: {name}")
            sort_order = 0
            for blob in blobs:
                if not blob:
                    continue
                photo_uuid = decode_blob_uuid(blob)
                if not photo_uuid:
                    continue
                src = AMG_EXT / photo_uuid
                if not src.exists():
                    print(f"    WARN: source file missing: {photo_uuid}")
                    continue

                filename = f"{uuid.uuid4().hex}.jpg"
                dest = tmpdir / filename
                try:
                    dest.write_bytes(resize_jpeg(src))
                    db_records.append((item_id, filename, sort_order))
                    sort_order += 1
                    staged += 1
                except Exception as e:
                    print(f"    ERROR resizing {photo_uuid}: {e}")

        if not db_records:
            print("\nNo photos to import.")
            return

        print(f"\nStaged {staged} photos. Transferring to NAS...")

        # Phase 2: tar pipe to NAS
        tar_buf = io.BytesIO()
        with tarfile.open(fileobj=tar_buf, mode='w') as tar:
            for item_id, filename, sort_order in db_records:
                fpath = tmpdir / filename
                tar.add(fpath, arcname=filename)
        tar_buf.seek(0)

        result = subprocess.run(
            ['ssh', 'nas', f'tar -xf - -C {NAS_PHOTOS}'],
            input=tar_buf.getvalue(), capture_output=True
        )
        if result.returncode != 0:
            print(f"ERROR: tar transfer failed: {result.stderr.decode()}")
            sys.exit(1)
        print(f"Transfer complete.")

        # Phase 3: DB inserts
        print("Inserting photo records into DB...")
        now = datetime.now(timezone.utc).isoformat()
        sql_lines = ["BEGIN;"]
        for item_id, filename, sort_order in db_records:
            sql_lines.append(
                f"INSERT INTO inventory_photos (inventory_item_id, filename, sort_order, created_at) "
                f"VALUES ({item_id}, '{filename}', {sort_order}, '{now}');"
            )
        sql_lines.append("COMMIT;")

        result = subprocess.run(
            ['ssh', 'nas', f'sqlite3 {NAS_DB}'],
            input='\n'.join(sql_lines).encode(), capture_output=True
        )
        if result.returncode != 0:
            print(f"ERROR: DB inserts failed: {result.stderr.decode()}")
            sys.exit(1)

    print(f"\nDone. Imported: {staged} photos, Skipped: {skipped}")
    if not_found:
        print(f"Not in inventory ({len(not_found)}): {', '.join(not_found)}")


if __name__ == "__main__":
    main()
