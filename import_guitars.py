#!/usr/bin/env python3
"""Import guitars from CSV into bins-inventory SQLite database.

Usage:
  python3 import_guitars.py <csv_path> [db_path]

  db_path defaults to /volume1/docker/bins-inventory/data/bins.db
"""

import csv
import sqlite3
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path


CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/Guitars.csv")
DB_PATH = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/volume1/docker/bins-inventory/data/bins.db")


def clean_money(s):
    if not s:
        return None
    s = s.replace("$", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def clean_int(s):
    if not s:
        return None
    try:
        return int(float(s.strip()))
    except ValueError:
        return None


def clean_bool(s):
    s = s.strip().lower()
    if s in ("yes", "true", "1"):
        return "1"
    if s in ("no", "false", "0"):
        return "0"
    return None


def gen_token():
    return secrets.token_urlsafe(6)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# CSV column → attr_key, optional transform fn
ATTR_MAP = [
    ("Type",                        "guitar_type",             None),
    ("Relic",                       "relic",                   None),
    ("Case",                        "case_cover",              None),
    ("Neck Pickup Type",            "neck_pickup_type",        None),
    ("Neck Pickup Brand",           "neck_pickup_brand",       None),
    ("Neck Pickup Model",           "neck_pickup_model",       None),
    ("Neck Pickup Notes",           "neck_pickup_notes",       None),
    ("Middle Pickup Type",          "mid_pickup_type",         None),
    ("Middle Pickup Brand",         "mid_pickup_brand",        None),
    ("Middle Pickup Model",         "mid_pickup_model",        None),
    ("Middle Pickup Notes",         "mid_pickup_notes",        None),
    ("Bridge Pickup Type",          "bridge_pickup_type",      None),
    ("Bridge Pickup Brand",         "bridge_pickup_brand",     None),
    ("Bridge Pickup Model",         "bridge_pickup_model",     None),
    ("Bridge Pickup Notes",         "bridge_pickup_notes",     None),
    ("Sound Hole Pickup Type",      "soundhole_pickup_type",   None),
    ("Sound Hole Pickup Brand",     "soundhole_pickup_brand",  None),
    ("Sound Hole Pickup Model",     "soundhole_pickup_model",  None),
    ("Sound Hole Pickup Notes",     "soundhole_pickup_notes",  None),
    ("Transducer Pickup Type",      "transducer_pickup_type",  None),
    ("Transducer Pickcup Brand",    "transducer_pickup_brand", None),  # typo in CSV intentional
    ("Transducer Pickup Model",     "transducer_pickup_model", None),
    ("Transducer Pickup Notes",     "transducer_pickup_notes", None),
    ("Pickup Selector",             "pickup_selector_type",    None),
    ("Weight",                      "weight",                  None),
    ("Body Style",                  "body_style",              None),
    ("Top Wood",                    "top_wood",                None),
    ("Body Wood",                   "body_wood",               None),
    ("Body Finish",                 "body_finish",             None),
    ("Neck Wood",                   "neck_wood",               None),
    ("Neck Finish",                 "neck_finish",             None),
    ("Neck Attachment",             "neck_attachment",         None),
    ("Has Skunk Stripe",            "has_skunk_stripe",        clean_bool),
    ("Side Wood",                   "side_wood",               None),
    ("Back Wood",                   "back_wood",               None),
    ("Fingerboard Wood",            "fingerboard_wood",        None),
    ("Neck Shape",                  "neck_shape",              None),
    ("Fret Size",                   "fret_size",               None),
    ("Nut Material",                "nut_material",            None),
    ("Nut Width",                   "nut_width",               None),
    ("Scale Length",                "scale_length",            None),
    ("Fingerboard Radius",          "fingerboard_radius",      None),
    ("Fingerboard Details",         "fingerboard_details",     None),
    ("Last Fingerboard Recondition","last_recondition",        None),
    ("Bracing Pattern",             "bracing_pattern",         None),
    ("Bracing Wood",                "bracing_wood",            None),
    ("Bridge Wood",                 "bridge_wood",             None),
    ("Pick Guard",                  "pick_guard",              None),
    ("Tuner Type",                  "tuner_type",              None),
    ("Hardware Finish",             "hardware_finish",         None),
    ("Build Wiring Notes",          "wiring_notes",            None),
    ("Build Maintenance Notes",     "maintenance_notes",       None),
    ("Bridge Style",                "bridge_style",            None),
    ("Bridge Brand",                "bridge_brand",            None),
    ("Bridge Model",                "bridge_model",            None),
    ("Bridge Material",             "bridge_material",         None),
    ("Saddle Material",             "saddle_material",         None),
    ("Number of Strings",           "number_of_strings",       None),
    ("Strings Min Guage",           "string_gauge_min",        None),
    ("Strings Max Guage",           "string_gauge_max",        None),
    ("Strings Tuning",              "string_tuning",           None),
    ("Strings Brand",               "string_brand",            None),
    ("Strings Model",               "string_model",            None),
    ("Date of Last Restring",       "last_restring",           None),
]


def main():
    print(f"CSV:  {CSV_PATH}")
    print(f"DB:   {DB_PATH}")

    if not CSV_PATH.exists():
        print(f"ERROR: CSV not found: {CSV_PATH}")
        sys.exit(1)
    if not DB_PATH.exists():
        print(f"ERROR: Database not found: {DB_PATH}")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    cur = conn.cursor()

    row = cur.execute("SELECT id FROM item_types WHERE slug='guitar'").fetchone()
    if not row:
        print("ERROR: 'guitar' item_type not found. Run the app first to initialize the DB.")
        sys.exit(1)
    guitar_type_id = row[0]

    # Add guitar_type attr def if missing
    existing = cur.execute(
        "SELECT id FROM attribute_definitions WHERE item_type_id=? AND key='guitar_type'",
        (guitar_type_id,)
    ).fetchone()
    if not existing:
        cur.execute("""
            INSERT INTO attribute_definitions
                (item_type_id, key, label, field_type, options, section, sort_order)
            VALUES (?, 'guitar_type', 'Guitar Type', 'select',
                    '["Acoustic","Electric","Bass","Classical"]', 'General', 0)
        """, (guitar_type_id,))
        conn.commit()
        print("Added 'Guitar Type' attribute definition.")

    # Build attr_key → def_id lookup
    attr_defs = {
        key: ad_id
        for ad_id, key in cur.execute(
            "SELECT id, key FROM attribute_definitions WHERE item_type_id=?",
            (guitar_type_id,)
        ).fetchall()
    }

    imported = 0
    skipped = 0

    with open(CSV_PATH, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", "").strip()
            if not name:
                continue

            existing = cur.execute(
                "SELECT id FROM inventory_items WHERE name=? AND item_type_id=?",
                (name, guitar_type_id)
            ).fetchone()
            if existing:
                print(f"  SKIP (exists): {name}")
                skipped += 1
                continue

            year = clean_int(row.get("Year Produced", ""))
            rating_raw = row.get("Rating", "").strip()
            rating = clean_int(rating_raw) if rating_raw and float(rating_raw or 0) != 0.0 else None
            sold_val = row.get("Sold?", "").strip()
            sold = 1 if sold_val.lower() in ("yes", "true", "1", "sold") else 0

            now = now_iso()
            cur.execute("""
                INSERT INTO inventory_items (
                    item_type_id, name, brand, model, year_produced, color,
                    condition, serial_number, country_of_manufacture,
                    date_acquired, acquired_from, amount_paid, current_value,
                    sold, sale_price, date_sold, rating, story, notes,
                    token, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                guitar_type_id,
                name,
                row.get("Brand", "").strip() or None,
                row.get("Model", "").strip() or None,
                year,
                row.get("Color", "").strip() or None,
                row.get("Condition", "").strip() or None,
                row.get("Serial Number", "").strip() or None,
                row.get("Country of Manufacture", "").strip() or None,
                row.get("Date Acquired", "").strip() or None,
                row.get("Acquired From", "").strip() or None,
                clean_money(row.get("Amount Paid", "")),
                clean_money(row.get("Current Value", "")),
                sold,
                clean_money(row.get("Sale Price", "")) if sold else None,
                row.get("Date Sold", "").strip() or None,
                rating,
                row.get("Story", "").strip() or None,
                row.get("Notes", "").strip() or None,
                gen_token(),
                now,
                now,
            ))
            item_id = cur.lastrowid

            for csv_col, attr_key, transform in ATTR_MAP:
                val = row.get(csv_col, "").strip()
                if not val:
                    continue
                if transform:
                    val = transform(val)
                    if val is None:
                        continue
                def_id = attr_defs.get(attr_key)
                if def_id is None:
                    print(f"  WARN: no attr_def for '{attr_key}' — skipping column '{csv_col}'")
                    continue
                cur.execute(
                    "INSERT INTO item_attributes (inventory_item_id, attribute_def_id, value) VALUES (?,?,?)",
                    (item_id, def_id, val)
                )

            conn.commit()
            print(f"  IMPORTED: {name}")
            imported += 1

    conn.close()
    print(f"\nDone. Imported: {imported}  Skipped (already exist): {skipped}")


if __name__ == "__main__":
    main()
