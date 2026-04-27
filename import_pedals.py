#!/usr/bin/env python3
"""Import pedals from CSV into bins-inventory SQLite database.

Usage:
  python3 import_pedals.py <csv_path> [db_path]

  db_path defaults to /volume1/docker/bins-inventory/data/bins.db
"""

import csv
import sqlite3
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path


CSV_PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/Pedals.csv")
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


def get_row(row, key):
    """Look up a CSV column, tolerating leading/trailing spaces in header."""
    val = row.get(key, "")
    if val != "":
        return val
    for k, v in row.items():
        if k.strip() == key.strip():
            return v
    return ""


# (csv_column, attr_key, transform_fn)
ATTR_MAP = [
    ("Type",                    "pedal_type",         None),
    ("Voltage",                 "voltage",            None),
    ("Supply",                  "supply",             None),
    ("Tip",                     "tip_polarity",       None),
    ("Power Draw (mA)",         "power_draw_ma",      None),
    ("True Bypass",             "true_bypass",        clean_bool),
    ("Input",                   "input",              None),
    ("Output",                  "output",             None),
    ("Loop",                    "loop",               clean_bool),
    ("Expression Pedal Control","expression_control", clean_bool),
    ("MIDI Control",            "midi_control",       clean_bool),
    ("Dimensions (LxWxH)",      "dimensions",         None),
    ("Weight",                  "weight",             None),
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

    row = cur.execute("SELECT id FROM item_types WHERE slug='pedal'").fetchone()
    if not row:
        print("ERROR: 'pedal' item_type not found. Run the app first to initialize the DB.")
        sys.exit(1)
    pedal_type_id = row[0]

    # Add pedal_type attr def if missing
    existing = cur.execute(
        "SELECT id FROM attribute_definitions WHERE item_type_id=? AND key='pedal_type'",
        (pedal_type_id,)
    ).fetchone()
    if not existing:
        cur.execute("""
            INSERT INTO attribute_definitions
                (item_type_id, key, label, field_type, options, section, sort_order)
            VALUES (?, 'pedal_type', 'Pedal Type', 'text', NULL, 'Power', 0)
        """, (pedal_type_id,))
        conn.commit()
        print("Added 'Pedal Type' attribute definition.")

    attr_defs = {
        key: ad_id
        for ad_id, key in cur.execute(
            "SELECT id, key FROM attribute_definitions WHERE item_type_id=?",
            (pedal_type_id,)
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
                (name, pedal_type_id)
            ).fetchone()
            if existing:
                print(f"  SKIP (exists): {name}")
                skipped += 1
                continue

            sold_val = row.get("Sold?", "").strip()
            sold = 1 if sold_val.lower() in ("yes", "true", "1", "sold") else 0

            now = now_iso()
            cur.execute("""
                INSERT INTO inventory_items (
                    item_type_id, name, brand, model, year_produced, color,
                    condition, serial_number, country_of_manufacture,
                    date_acquired, acquired_from, amount_paid, current_value,
                    sold, sale_price, date_sold, story, notes,
                    token, created_at, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                pedal_type_id,
                name,
                row.get("Brand", "").strip() or None,
                row.get("Model", "").strip() or None,
                clean_int(row.get("Year Produced", "")),
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
                row.get("Story", "").strip() or None,
                row.get("Notes", "").strip() or None,
                gen_token(),
                now,
                now,
            ))
            item_id = cur.lastrowid

            for csv_col, attr_key, transform in ATTR_MAP:
                val = get_row(row, csv_col).strip()
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
